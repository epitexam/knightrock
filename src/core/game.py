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
from src.core.display.stage import Stage, WindowSpec
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
    the loop simply feeds it fixed ticks, draws the stack into the render
    target and presents it once.  Gameplay systems notify the app
    layer (UI, save, audio) through the synchronous :class:`EventBus`
    (Phase 2 #5) — subscribers must never mutate the simulation.
    """

    def __init__(self, save_path: Path | None = None, bindings_path: Path | None = None) -> None:
        for name, value in SDL_HINTS.items():
            os.environ[name] = value
        self.stage: Stage | None = None
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
        ``self.presentation.surface``. Reaching for this to draw is how the
        window and the visible world got tangled in the first place.
        """
        return None if self.stage is None else self.stage.surface

    @property
    def ui_scale(self) -> float:
        """The scale the interface is laid out at.

        The player's own preference multiplied by the target's pixel density,
        and the multiplication is the whole point: the layout is written once,
        in the units of a 1152x648 picture, and drawn at whatever density the
        window turned out to have. The alternative -- laying the interface out
        in target pixels -- makes every font size and every padding a thing that
        has to be right for every window, which is the mistake a fixed render
        target was supposed to prevent.
        """
        if self.presentation is None:
            return self.settings.ui_scale
        return self.settings.ui_scale * self.presentation.density

    def _draw_target(self) -> pygame.Surface:
        """The surface every scene draws into."""
        assert self.presentation is not None, "the display is not initialized"
        return self.presentation.surface

    def _window_spec(self) -> WindowSpec:
        """The window the settings currently ask for."""
        return WindowSpec(mode=self.settings.display, vsync=self.settings.vsync)

    def _resolve_display_settings(self) -> None:
        """Turn ``AUTO`` into a mode the window can be built from.

        The only resolution left at launch, and it is a *mode*, not a size: how
        to occupy a screen whose dimensions the game does not know. It is
        re-evaluated every launch, which is what ``AUTO`` is for, and it is not
        written back -- the file keeps saying "auto" so the next launch on
        another machine answers again.
        """
        if self.settings.display is not DisplayMode.AUTO:
            return
        self.settings = self.settings.with_video(
            display=detection.auto_display_mode(DEFAULT_FRAMING, detection.desktop_size())
        )

    def initialize_display(self) -> None:
        """Build the window and the presentation, once.

        Public because the headless fixtures need the same construction the loop
        does, rather than half of it.
        """
        desktop = detection.desktop_size()
        self.stage = Stage(self._window_spec(), desktop)
        # The window exists, so the picture can be drawn at its size: the target
        # is the window's letterbox rectangle and the density is read back off
        # it. Nothing here is chosen, and nothing here is stored.
        self.presentation = Presentation(
            self.stage.surface, DEFAULT_FRAMING, pixel_perfect=self.settings.pixel_perfect
        )

    def _retarget(self) -> None:
        """Re-point everything at the render target after it changed size.

        The single cascade for "the window is a different size now", and it is
        reached from the two things that can cause one: a display setting
        changing, and the player dragging the window. Both produce the same
        three consequences -- a new surface to draw into, a new density for the
        camera, a new interface scale -- and doing them in one place is what
        keeps a resize from leaving one of the three behind.
        """
        assert self.presentation is not None
        if not self.presentation.recompute():
            return
        # set_mode leaves every surface converted for the *previous* display
        # format stale. AssetLibrary has no display to compare against, so it
        # must be invalidated explicitly or the next frame blits through a
        # software alpha path, then pays a full re-decode and re-conversion.
        self._invalidate_assets()
        self.scene_manager.set_surface(self.presentation.surface)
        self.scene_manager.set_ui_scale(self.ui_scale)

    def _rebuild_display(self) -> None:
        """Recreate the window, then refit the picture to it.

        The window is the only thing a display setting can replace, and the
        picture follows it: the target is the window's letterbox rectangle, so
        there is no separate "render target" setting left to keep in step.
        """
        desktop = detection.desktop_size()
        assert self.stage is not None
        assert self.presentation is not None
        self.stage.rebuild(self._window_spec(), desktop)
        self.presentation.retarget(self.stage.surface)
        self._invalidate_assets()
        self.scene_manager.set_surface(self.presentation.surface)
        self.scene_manager.set_ui_scale(self.ui_scale)

    def apply_settings(self, settings: UserSettings) -> None:
        """Apply new settings, doing only what the change actually touches.

        A display mode or a vsync flag changes the window, and therefore the
        picture, because the picture *is* the window's size. ``pixel_perfect``
        changes the letterbox, and therefore the target, without the window
        moving at all. A frame limit touches neither. The interface scale goes
        last, and always as the player's preference times the density -- which
        is why it is not a number read straight out of the settings.
        """
        previous = self.settings
        self.settings = settings
        self.input_bindings = settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self._persist_settings()
        if self.stage is None or self.presentation is None:
            return
        # Before anything else, and unconditionally: the letterbox belongs to
        # the presentation, and a rebuild reads it. Setting it only on the branch
        # that does not touch the window is how the two drift apart -- a display
        # change and a sharpness change applied together left the presentation
        # snapping to whole pixels with the setting saying otherwise, which the
        # acceptance run caught and nothing else did.
        self.presentation.pixel_perfect = settings.pixel_perfect
        if self._window_signature(previous) != self._window_signature(settings):
            self._rebuild_display()
        elif previous.pixel_perfect != settings.pixel_perfect:
            self._retarget()
        self.scene_manager.set_ui_scale(self.ui_scale)

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

        A mode and a vsync flag, and nothing else. Pixel-perfect art changes the
        target without the window moving, the frame limit touches neither, and
        the interface scale is a multiplier on a density the window already
        decided.
        """
        return (settings.display, settings.vsync)

    def _persist_settings(self) -> None:
        """Queue the settings for a write, coalesced to one per frame.

        The write is a small file replaced atomically, and it used to block the
        frame on every keypress in the Video menu and on every captured key
        during rebinding. Marking the state dirty and flushing it from the loop
        keeps a burst of changes down to a single write.
        """
        self._settings_dirty = True

    def render_alpha(self) -> float:
        """How far the presentation sits into the pending simulation tick.

        The loop accumulates real time and drains it in fixed steps, so after
        the last tick a fraction of a step is always left over. That fraction
        is how far ahead of the simulation the picture is: 0 means the
        picture matches the last completed tick exactly, 1 that a whole tick
        is already owed.         Handing it to the renderer blends each sprite from
        its last drawn position towards the one the next tick will write,
        which is what removes the judder of a fixed-step sim on a
        variable-rate display.

        While a scene is holding the world still, the answer is 1 and not a
        fraction. The leftover in the accumulator keeps being fed real time and
        drained by ticks that do nothing, so the fraction wanders -- and with
        no tick running there is nothing to close the gap the camera is
        interpolating across, so every wandering fraction is drawn as motion.
        The game visibly trembles behind the pause menu. 1 says the picture is
        exactly where the simulation is, which is both true and still.
        """
        if self.scene_manager.halts_simulation:
            return 1.0
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
                # The window is resizable and the picture is the window's size,
                # so a drag rebuilds the render target, re-reads the density and
                # re-lays out the interface -- the same cascade as a display
                # setting change, which is why it is one method. SDL also
                # announces this during an internal set_mode(), and recomputing
                # an unchanged size is a no-op.
                self._retarget()
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
        event.pos = self.presentation.pointer_to_viewport(position)
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
