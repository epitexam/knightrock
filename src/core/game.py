import logging
import os
import sys
import traceback
from pathlib import Path

import pygame
from pygame.joystick import JoystickType

from src.application.events import EventBus, LevelCompleted, LevelStarted, PlayerDied
from src.application.save_game import SaveGame, default_save_path
from src.application.scene_manager import SceneManager
from src.application.scenes.menu_scene import MenuScene
from src.application.settings_store import (
    MAX_FRAME_LIMIT,
    SettingsStore,
    UserSettings,
)
from src.core import fx
from src.core.asset_library import shared_library
from src.core.audio import AudioBus
from src.core.display import detection
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.mode import DisplayMode
from src.core.display.presentation import Presentation
from src.core.display.size_mode import SizeMode
from src.core.display.stage import Stage, WindowSpec
from src.core.display.viewport import DEFAULT_RENDER_SCALE, Viewport
from src.core.input.event_router import EventRouter
from src.core.input.input_bindings import InputBindings
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.settings import Display, Simulation
from src.data.provider import GameplayData, load_gameplay_data

logger = logging.getLogger(__name__)

#: Ceiling a vsync frame is allowed to reach, as a runaway backstop only.
#:
#: A working vsync presents once per refresh -- 16.7ms at 60Hz, 4.2ms at
#: 240Hz -- and that present is the pacer, so this target must never bite. It
#: is derived from ``Display.FPS`` rather than hardcoded so that raising the
#: configured frame rate cannot leave the ceiling *below* it: a fixed 125 sat
#: under a 240 target and quietly halved the frame rate the user had asked
#: for, with vsync on and nothing on screen to say so. The multiplier is
#: generous on purpose, clearing any real refresh rate by a wide margin, so
#: the only thing it ever catches is a present that does not block at all.
DISPLAY_SAFETY_CEILING_FPS = max(Display.FPS * 4, MAX_FRAME_LIMIT)

#: SDL environment set before ``pygame.init()``.
#:
#: High-DPI has to be requested here: SDL reads it when the video subsystem
#: comes up. pygame-ce 2.5.7 has no ``HIDPI`` flag, so this variable is the
#: whole mechanism. With a scaled desktop and no hint, SDL matches the pixel
#: size to the window size and the compositor resamples the result.
SDL_HINTS = {
    "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
    "SDL_VIDEO_HIDPI": "1",
}


class Game:
    """Application runtime: display, input, and the scene stack.

    The loop itself no longer owns gameplay state (audit F8.1, Phase 2
    #4): :class:`SceneManager` holds Menu/Play/Pause/GameOver scenes and
    the loop simply feeds it fixed ticks, events, and presents the dirty
    rects returned by the active scene.  Gameplay systems notify the app
    layer (UI, save, audio) through the synchronous :class:`EventBus`
    (Phase 2 #5) — subscribers must never mutate the simulation.
    """

    def __init__(self, save_path: Path | None = None, bindings_path: Path | None = None) -> None:
        for name, value in SDL_HINTS.items():
            os.environ[name] = value
        self.stage: Stage | None = None
        self.viewport: Viewport | None = None
        self.presentation: Presentation | None = None
        self.joysticks: dict[int, JoystickType] = {}
        self.settings_store = SettingsStore(bindings_path)
        self.settings = self.settings_store.load()
        self.input_bindings = self.settings.bindings
        self.input_router = EventRouter(self.input_bindings, joystick_reader=lambda: self.joysticks)
        self.input_provider = LocalInputProvider(self.input_bindings)
        self.input_manager = InputManager(self.input_provider)
        # Gameplay data driven by JSON (Phase 3 #4): attack sets, enemy
        # configs, player config and level registry. Falls back to the
        # historical in-code values when the JSON assets are absent.
        self.gameplay_data: GameplayData = load_gameplay_data()
        # Owned here rather than fetched from a module-level singleton, so the
        # scene stack, the input dispatcher and every later audio subscriber
        # share one bus that a test can replace. Constructed before the mixer
        # exists: it stays silent until ``_initialize`` starts it.
        self.audio = AudioBus()
        self.level_manager = LevelManager(
            self.gameplay_data.levels if self.gameplay_data.levels else LEVEL_PATHS
        )
        self._save_path = save_path if save_path is not None else default_save_path()
        self.save_game = SaveGame.load(self._save_path)
        self.events = EventBus()
        # The one line in the application layer that knows the audio system
        # exists. It subscribes to the facts it answers, so the screens and the
        # dispatcher never name it.
        self.audio.attach(self.events)
        self._subscribe_notifications()
        self.scene_manager = SceneManager(self)
        self.running = True
        self.clock: pygame.time.Clock | None = None
        self._accumulator = 0.0
        self._settings_dirty = False

    def _subscribe_notifications(self) -> None:
        """Log the gameplay notifications (hook point for UI/audio/save)."""
        self.events.subscribe(LevelStarted, self._on_level_started)
        self.events.subscribe(PlayerDied, self._on_player_died)
        self.events.subscribe(LevelCompleted, self._on_level_completed)

    @staticmethod
    def _on_level_started(event: LevelStarted) -> None:
        logger.info("Level %s started", event.level_id)

    def _on_player_died(self, event: PlayerDied) -> None:
        logger.info("Player died (death #%s)", event.deaths + 1)

    def _on_level_completed(self, event: LevelCompleted) -> None:
        """Persist progression: unlock the TMX-declared level (F8.1)."""
        logger.info("Level %s completed", event.level_id)
        self.save_game.last_level_id = event.level_id
        if event.unlock_level_id is not None and self.save_game.unlock(event.unlock_level_id):
            logger.info("Level %s unlocked", event.unlock_level_id)
        try:
            self.save_game.save(self._save_path)
        except OSError:
            logger.exception("Unable to persist the save at %s", self._save_path)

    def _initialize(self) -> None:
        pygame.init()
        pygame.joystick.init()
        # After pygame.init(), and never fatal: a machine with no sound card
        # must still reach the menu (audit UI, lot 5).
        self.audio.initialize()

        self._resolve_display_settings()
        self.initialize_display()
        pygame.display.set_caption(Display.TITLE)

        self.clock = pygame.time.Clock()
        self._accumulator = 0.0
        # Level loading took an arbitrary amount of wall time; the first frame
        # must not bill all of it to the simulation. The clock measures the gap
        # since its own previous tick, so one tick here moves the baseline to
        # now and the next one bills a single frame.
        self.clock.tick(0)
        self.scene_manager.switch(MenuScene(self))

    @property
    def surface(self) -> pygame.Surface | None:
        """The window's surface. For window-level work only.

        Nothing is *drawn* here any more: the game draws into
        ``self.viewport.surface``. Reaching for this to draw is how the window
        and the visible world got tangled in the first place.
        """
        return None if self.stage is None else self.stage.surface

    def _draw_target(self) -> pygame.Surface:
        """The surface every scene draws into."""
        assert self.viewport is not None, "the display is not initialized"
        return self.viewport.surface

    def _window_spec(self) -> WindowSpec:
        """The window the settings currently ask for."""
        return WindowSpec(
            width=self.settings.width,
            height=self.settings.height,
            mode=self.settings.display,
            vsync=self.settings.vsync,
        )

    def _resolve_display_settings(self) -> None:
        """Re-decide the window size against the machine we actually landed on.

        Two cases, and both of them are "a settings file travelled":

        - **auto** is re-evaluated, every launch. Docking a laptop or running
          the game on another machine changes the answer, and that is the
          entire point of the mode.
        - **manual** is honoured *if it still fits*. A player who chose
          2560x1440 gets it on a screen that can show it; on a 1366x768 laptop
          it becomes the auto choice, because opening a window larger than the
          screen is not honouring anything.

        Runs after ``pygame.init()`` and before the window exists, since that
        is when the desktop becomes queryable.
        """
        desktop = detection.desktop_size()
        if desktop[0] <= 0 or desktop[1] <= 0:
            return
        size = (self.settings.width, self.settings.height)
        if self.settings.size_mode is SizeMode.MANUAL and detection.fits_on_desktop(size, desktop):
            return
        if self.settings.display is DisplayMode.AUTO:
            self.settings = self.settings.with_video(
                display=detection.auto_display_mode(DEFAULT_FRAMING, desktop)
            )
        resolved = self.settings.with_video(
            width=detection.largest_window_size(desktop)[0],
            height=detection.largest_window_size(desktop)[1],
            size_mode=SizeMode.AUTO,
        )
        if self.settings.size_mode is SizeMode.MANUAL:
            # It was a hand-picked size that no longer fits: say so, rather
            # than silently substituting one and leaving the menu lying.
            logger.info(
                "Window %dx%d does not fit the %dx%d desktop; using the automatic size",
                size[0],
                size[1],
                desktop[0],
                desktop[1],
            )
        self.settings = resolved

    def initialize_display(self) -> None:
        """Build the window, the render target and the presentation, once.

        Public because the headless fixtures need the same three objects the
        loop does, built the same way, rather than half of them.
        """
        desktop = detection.desktop_size()
        self.stage = Stage(self._window_spec(), desktop)
        self.viewport = Viewport(DEFAULT_FRAMING, DEFAULT_RENDER_SCALE)
        self.presentation = Presentation(self.stage, self.viewport)

    def _rebuild_display(self) -> None:
        """Create or recreate the window, the render target and the presentation.

        Three different things change here and it is worth keeping them apart,
        because they invalidate different caches:

        - the **window** only when a window setting changed. Nothing drawn is
          affected: the render target is the same size either way.
        - the **render target** only when the render scale changed, since its
          size is the framing times that scale and nothing else.
        - the **presentation** on either, since it is the mapping between them.
        """
        desktop = detection.desktop_size()
        spec = self._window_spec()
        assert self.stage is not None
        self.stage.rebuild(spec, desktop)
        # set_mode leaves every surface converted for the *previous* display
        # format stale. AssetLibrary has no display to compare against, so it
        # must be invalidated explicitly or the next frame blits through a
        # software alpha path, then pays a full re-decode and re-conversion.
        self._invalidate_assets()

        assert self.viewport is not None
        assert self.presentation is not None
        self.presentation.recompute()

    def _rebuild_render_target(self, scale: int) -> None:
        """Replace the render target, after the render scale changed.

        The only path that has to tell the scene stack about a new surface.
        Every other display change lands in ``_rebuild_display`` and touches
        nothing that is drawn.

        The scale is validated by the settings store, and again by
        ``Framing.viewport_size``, so a value that somehow got through cannot
        produce a zero-sized target.
        """
        self.viewport = Viewport(DEFAULT_FRAMING, scale)
        if self.presentation is not None:
            self.presentation.viewport = self.viewport
            self.presentation.recompute()
        self.scene_manager.set_surface(self.viewport.surface)

    def apply_settings(self, settings: UserSettings) -> None:
        """Apply new settings, recreating only what the change actually touches.

        A setting that changes the window rebuilds the window and nothing else:
        the render target keeps its size, so no view recomputes its layout and
        no art is re-decoded. A UI scale change touches neither. Only the render
        scale replaces the surface everything is drawn into.
        """
        previous = self.settings
        self.settings = settings
        self.input_bindings = settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self._persist_settings()
        if self.stage is None:
            return
        if self._window_signature(previous) != self._window_signature(settings):
            self._rebuild_display()
        if previous.render_scale != settings.render_scale:
            self._rebuild_render_target(settings.render_scale)
        elif self.presentation is not None:
            self.presentation.smoothing = settings.smoothing
        self.scene_manager.set_ui_scale(settings.ui_scale)

    @staticmethod
    def _invalidate_assets() -> None:
        """Drop every surface derived from the old display format.

        Two independent caches sit on top of the art: ``AssetLibrary`` and the
        module-level frame cache in ``fx``. Clearing only the first would let
        the second hand back pre-reformat surfaces anyway.
        """
        shared_library().clear()
        fx.clear_frame_cache()

    @staticmethod
    def _window_signature(settings: UserSettings) -> tuple[object, ...]:
        """The settings that require a new ``pygame.display.set_mode`` call.

        Render scale, smoothing, frame limit and UI scale are deliberately not
        here: none of them touches the window, and the render target only
        changes with the scale, which has its own path.
        """
        return (settings.width, settings.height, settings.display, settings.vsync)

    def _persist_settings(self) -> None:
        """Queue the settings for a write, coalesced to one per frame.

        ``SettingsStore.save`` re-reads, rewrites and atomically replaces the
        JSON file, which blocked the frame on every keypress in the Video menu
        and on every captured key during rebinding. Marking the state dirty and
        flushing it from the loop keeps a burst of changes (holding a key on
        the resolution row) down to a single write.
        """
        self._settings_dirty = True

    def render_alpha(self) -> float:
        """How far the presentation sits into the pending simulation tick.

        The loop accumulates real time and drains it in fixed steps, so after
        the last tick a fraction of a step is always left over. That fraction
        is how far ahead of the simulation the picture is: 0 means the
        picture matches the last completed tick exactly, 1 that a whole tick
        is already owed. Handing it to the renderer blends each sprite from
        its last drawn position towards the one the next tick will write,
        which is what removes the judder of a fixed-step sim on a
        variable-rate display.
        """
        return self._accumulator / Simulation.TIMESTEP

    def flush_settings(self) -> None:
        """Write the pending settings immediately, if any."""
        if not self._settings_dirty:
            return
        self._settings_dirty = False
        try:
            self.settings_store.save(self.settings)
        except OSError:
            logger.exception("Unable to persist the settings")

    def apply_bindings(self, bindings: InputBindings) -> None:
        """Met à jour les bindings sans recréer l'affichage (rebinding en jeu).

        ``apply_settings`` reconstruit la fenêtre (échelle UI, plein écran…) :
        inacceptable à chaque capture de touche de l'écran Contrôles. Ici on ne
        persiste que les bindings et on réarme routeur + provider.
        """
        self.settings = self.settings.with_bindings(bindings)
        self.input_bindings = self.settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self._persist_settings()

    def run(self) -> None:
        """Initialize and run the game, always releasing Pygame resources."""
        try:
            self._initialize()
            self._run_loop()
        except Exception as error:
            traceback.print_exc()
            self._handle_fatal_error(error)
            raise SystemExit(1) from error
        finally:
            self.flush_settings()
            pygame.quit()

    def quit(self) -> None:
        """Stop the loop at the end of the current frame."""
        self.running = False

    def _frame_delta(self) -> float:
        """Seconds elapsed since the previous frame, for the fixed-step accumulator.

        With vsync off, the clock is the pacer: it sleeps to hold 60fps.

        With vsync on, the present already blocks until the vertical blank, so
        sleeping to a 60fps target here as well paces the loop twice. The two
        waiters do not add up cleanly -- a frame lands just past the blank, the
        present then waits for the *next* one, and the frame after finds its
        sleep already elapsed -- so the cadence alternates between on time and
        one refresh late. That reads as a small stutter every other frame
        rather than as a steady 30fps.

        The clock is still ticked, against a runaway ceiling far above any
        real refresh rate rather than against 60. A present takes 16.7ms at
        60Hz and 4.2ms at 240Hz, so that target never bites and the present
        stays the only pacer; a display that ignores the vsync flag gets held
        to the ceiling instead of running flat out. Ticking the clock is also
        what feeds its FPS meter, which reads 0.0 for a loop that never ticks
        it -- and a manual ``pygame.time.wait`` would not do, since a wait
        lands outside the window the clock measures and the meter would miss
        it entirely.
        """
        if self.clock is None:
            raise RuntimeError("The game runtime is not initialized")
        if not self.settings.vsync:
            return self.clock.tick(self._frame_target()) / 1000.0
        return self.clock.tick(max(DISPLAY_SAFETY_CEILING_FPS, self._frame_target())) / 1000.0

    def _frame_target(self) -> int:
        """The rate the clock paces to when vsync is not doing it.

        ``0`` is pygame's "no limit", which is what an uncapped setting means.
        Named *target* rather than FPS on purpose: with vsync on, the present
        decides the rate and this number is ignored, so calling it FPS would
        promise something the game does not deliver.
        """
        return 0 if self.settings.frame_limit is None else self.settings.frame_limit

    def _run_loop(self) -> None:
        if self.clock is None:
            raise RuntimeError("The game runtime is not initialized")
        while self.running:
            self.step()

    def step(self) -> None:
        """One frame: events, fixed ticks, one draw, one present.

        Split out of the loop so a single frame can be driven from outside --
        the manual acceptance run does, to hold a display state on screen while
        it is looked at.
        """
        if self.clock is None:
            raise RuntimeError("The game runtime is not initialized")
        self._accumulator += min(self._frame_delta(), Simulation.MAX_FRAME_TIME)

        self._handle_events()
        self.scene_manager.poll_held_repeats()
        self.flush_settings()

        self._run_ticks()
        self.scene_manager.draw(self._draw_target())
        self._present()

    def _run_ticks(self) -> None:
        """Drain the accumulator, but never more than a frame's worth of ticks.

        The accumulator already refuses to believe a frame longer than
        ``MAX_FRAME_TIME``, which stops one hitch from being replayed forever.
        It does not stop a *sustained* overload from queueing ticks faster than
        they can be run: with 20 owed and 6 affordable, the debt grows and every
        frame after the hitch spends its whole budget trying to catch up, so the
        game never recovers.

        Dropping the surplus is the decision every engine makes here, and the
        fixed timestep is what makes it cheap: the ticks that get dropped were
        never going to be seen. Catching up on a machine that cannot render
        fast enough to show them only makes the next frame later.
        """
        affordable = min(
            int(self._accumulator / Simulation.TIMESTEP), Simulation.MAX_TICKS_PER_FRAME
        )
        if affordable >= Simulation.MAX_TICKS_PER_FRAME:
            # The surplus is time the player has already lost; carrying it
            # forward is what turns one hitch into a stall.
            self._accumulator = 0.0
        for _ in range(affordable):
            self.scene_manager.update(Simulation.TIMESTEP)
            self._accumulator -= Simulation.TIMESTEP
        # The subtraction above leaves a residue around -1e-17, and a negative
        # accumulator makes ``render_alpha`` negative for one frame.
        self._accumulator = max(0.0, self._accumulator)

    def _present(self) -> None:
        """Put the finished frame on the screen. The only screen read in the loop."""
        assert self.presentation is not None, "the display is not initialized"
        self.presentation.present()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            # Latched before any filtering: the provider reads a per-poll
            # keyboard snapshot, so a tap shorter than a frame would otherwise
            # be over before the simulation ever looks at it.
            self.input_provider.note_event(event)

            if event.type == pygame.VIDEORESIZE:
                # La fenêtre est redimensionnable, et un redimensionnement ne
                # change plus rien de ce qui est dessiné : la cible de rendu a
                # une taille fixe. Il n'y a donc qu'une chose à recalculer, le
                # rectangle de présentation. SDL annonce aussi cet évènement
                # lors d'un set_mode() interne, ce qui est idempotent.
                if self.presentation is not None:
                    self.presentation.recompute()
                continue

            if event.type == pygame.JOYDEVICEADDED:
                should_assign = not self.joysticks
                joy = pygame.joystick.Joystick(event.device_index)
                self.joysticks[joy.get_instance_id()] = joy
                logger.info(f"Connected controller : {joy.get_name()}")
                self.input_router.notify_joystick_connected(joy.get_instance_id(), joy)
                if should_assign:
                    self.input_provider.connect_joystick(joy)

            elif event.type == pygame.JOYDEVICEREMOVED and event.instance_id in self.joysticks:
                disconnected_joy = self.joysticks[event.instance_id]
                logger.info(f"Controller disconnected : {disconnected_joy.get_name()}")
                self.input_provider.disconnect_joystick(event.instance_id)
                self.input_router.notify_joystick_removed(event.instance_id)
                del self.joysticks[event.instance_id]
                self.input_provider.reassign_joystick(self.joysticks)

            self.scene_manager.handle_event(self._to_target_coordinates(event))

    #: Pointer events whose position the interface hit-tests against.
    _POINTER_EVENTS = frozenset(
        {
            pygame.MOUSEMOTION,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
        }
    )
    #: The subset that *acts*. A press on a letterbox bar is a press on nothing.
    _POINTER_PRESSES = frozenset({pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP})

    def _to_target_coordinates(self, event: pygame.event.Event) -> pygame.event.Event | None:
        """Rewrite a pointer event's position into render-target coordinates.

        Every hit rect in the interface is expressed in the render target's
        space, and the pointer arrives in the window's, so the position has to
        come back through the inverse of the presentation. Doing it here, once,
        is what keeps every scene from having to know a window exists.

        A press that lands in a letterbox bar is dropped rather than clamped.
        Clamping would fire whatever row happens to be nearest the edge of the
        image, which is worse than doing nothing: the player clicked black and
        the game answered. Motion is clamped instead of dropped, so the cursor
        keeps a sensible position while it crosses a bar.
        """
        if self.presentation is None or event.type not in self._POINTER_EVENTS:
            return event
        position = getattr(event, "pos", None)
        if position is None:
            return event

        if not self.presentation.pointer_in_viewport(position):
            if event.type in self._POINTER_PRESSES:
                return None
            rect = self.presentation.rect
            position = (
                min(max(position[0], rect.left), rect.right - 1),
                min(max(position[1], rect.top), rect.bottom - 1),
            )
        event.pos = tuple(round(value) for value in self.presentation.pointer_to_viewport(position))
        return event

    def _handle_fatal_error(self, error: Exception) -> None:
        logger.error(f"FATAL ERROR: {error}")
        surface = self.surface
        if surface is None:
            return

        try:
            surface.fill((0, 0, 0))
            font = pygame.font.SysFont("Arial", 30)
            text = font.render(f"FATAL ERROR: {error}", True, (255, 0, 0))
            surface.blit(text, (10, 10))
            pygame.display.update()
        except pygame.error:
            print("Unable to render the fatal error screen", file=sys.stderr)
