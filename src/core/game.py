import logging
import os
import traceback
from pathlib import Path
from time import perf_counter

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
from src.core.display import detection, letterbox
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy, density_for
from src.core.display.monitors import Monitor, Topology
from src.core.display.presentation import Presentation
from src.core.display.stage import Stage, WindowSpec
from src.core.input.event_router import EventRouter
from src.core.input.input_bindings import InputBindings
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.settings import Display, Simulation
from src.data.provider import GameplayData, load_gameplay_data
from src.ui.ui_manager import UIManager

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
#:
#: ``MAX_FRAME_LIMIT`` is deliberately *below* this number, and the video menu
#: says so rather than hiding it: the ladder tops out at 500, so with vsync on
#: every one of its values sits under the ceiling and is ignored. That is the
#: contract -- the present paces, and the ladder is what runs when nothing
#: does -- and it is why the frame-limit row reads "ignored while VSync is
#: on" rather than promising a rate it does not deliver. Raising the ladder
#: past this ceiling would silently re-introduce the double pacer that the
#: comment above describes.
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
        #: The size the window was last built at, so SDL's own announcement of
        #: it can be told from a drag. See :meth:`_forget_the_window_preference`.
        self._built_window_size: tuple[int, int] | None = None
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
        #: The interface drawn over the world, built on the first level.
        #: See :meth:`world_overlay`.
        self.ui: UIManager | None = None
        self.running = True
        #: The display list, read once at launch and re-read on a poll. See
        #: :meth:`topology`.
        self._topology: Topology | None = None
        self._topology_age = 0.0
        self.clock: pygame.time.Clock | None = None
        self._accumulator = 0.0
        self._settings_dirty = False
        #: A transient message for the player, with the seconds left on it.
        #: Empty when there is nothing to say. The only user-visible feedback
        #: the loop owns, which is why there is exactly one.
        self._notice: tuple[str, ...] = ()
        self._notice_ttl = 0.0

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

    def world_overlay(self, target: pygame.Surface) -> UIManager:
        """The interface drawn over the world, built once and kept.

        Owned here rather than by the renderer, for two reasons. The layering
        one: the application layer is where ``core`` and ``ui`` meet, and
        ``core`` importing ``ui`` is the dependency
        :mod:`src.core.rendering.overlay` exists to remove. The practical one:
        a level transition used to build a second interface and throw the
        first one away, which threw away every font it had cached, and font
        scanning is what those caches are for.

        The density is read with the same rule the camera uses -- the target's
        own, via ``density_for`` -- rather than measured a second way here.
        """
        if self.ui is None:
            self.ui = UIManager(
                target,
                density_for(target.get_size(), DEFAULT_FRAMING),
                # The panel scale is a constructor argument, not a call after:
                # this is the first time the overlay exists, so anything applied
                # earlier found nothing to apply itself to. That is why a saved
                # preference used to come back as the right number in the menu
                # and the wrong size on screen.
                self.settings.panel_scale,
            )
        return self.ui

    def _forget_the_window_preference(self) -> None:
        """A drag is the player's last word: stop the menu's stored size overriding it.

        The menu says it plainly -- "a normal window; drag it, and its size is
        remembered" -- and it used to be false. Nothing ever wrote the geometry a
        drag produced, so the preference the player had *chosen earlier* went on
        overriding them: pick 1600x900, drag the window to 1200x800, toggle VSync,
        and the window snapped back to 1600x900. Every setting that touched the
        window was a way to throw away their own last word.

        **What is remembered is the choice, not the measurement.** The stored
        size goes back to ``None``, which now means "follow the window" rather
        than "open as large as fits" -- see :meth:`_window_spec`. That is what
        makes the file stop being a description of the machine: it records that
        the player stopped choosing a size, not how big their panel happened to
        be the day the window moved. A file that grew a width on every launch
        would describe the hardware, and the first launch on another machine
        would be a lie the next one had to be rewritten around.

        Ignored for a resize the game itself asked for. SDL announces its own
        ``set_mode`` as a ``VIDEORESIZE``, and treating that as a drag would
        clear the preference the menu had just set, one event after applying it.
        """
        if self.stage is None:
            return
        # Off the presentation, like :meth:`_follow_the_window`, and for the same
        # reason: the stage's surface and the presentation's are one object in
        # production, and asking the one that keeps the window is what makes the
        # two agree in a test that owns its own window.
        window = self.presentation.window_size if self.presentation is not None else self.stage.size
        if window == self._built_window_size:
            return  # The window the game just built, not a drag.
        if self.settings.window_size is None:
            return  # Already following the window: nothing to forget.
        logger.info("The window moved to %s; the stored window size no longer applies", window)
        self.settings = self.settings.with_video(window_size=None)
        self._persist_settings()

    def _window_spec(self) -> WindowSpec:
        """The window the settings currently ask for.

        A size the player has not chosen is the window's *own* size. That is the
        one place the two readings of "no preference" meet: with no size in the
        file, a rebuild used to re-open the window as large as the frame allowed,
        so any display setting undid a drag. Keeping the live geometry instead
        means the file never has to describe the window, and the window still
        survives every rebuild after a drag.
        """
        return WindowSpec(
            vsync=self.settings.vsync,
            size=self._asked_window_size(),
        )

    def _asked_window_size(self) -> tuple[int, int] | None:
        """The size to ask for, and the fallback that follows the player.

        Two readings, in order:

        - a size the player chose is asked for as it stands;
        - otherwise, a rebuild keeps the size the window currently has, which is
          what makes a drag survive the next display setting rather than being
          undone by it. A first launch has no window yet, so the stage asks for
          itself and gets ``opening_size``.
        """
        if self.settings.window_size is not None:
            return self.settings.window_size
        if self.stage is not None and self.presentation is not None:
            # The window the picture is drawn onto, for the same reason as
            # everywhere else in this file: the stage's surface is that surface in
            # production, and asking the presentation keeps the two readings of
            # "the window" from drifting apart.
            return self.presentation.window_size
        return None

    def topology(self, *, refresh: bool = False) -> Topology:
        """The machine's displays, read on launch and on every poll.

        Cached, because it is asked on every menu rebuild and every window
        rebuild and neither is a reason to walk the display list. Invalidated by
        ``refresh``, which is how a plugged-in screen is noticed: the platform
        does not report one arriving, so it has to be asked again (see
        :meth:`_poll_displays`).

        The cache is a snapshot and not a promise. It goes stale the moment a cable
        changes, which is why the poll exists and why every decision that depends
        on it resolves a *name* rather than trusting an index.
        """
        if self._topology is None or refresh:
            self._topology = detection.topology()
            self._topology_age = 0.0
        return self._topology

    def monitor(self) -> Monitor:
        """The panel the game is built on: the one holding the window.

        One rule decides it (**Rule W**), and it is the only anchor this game has
        left. Everything the menu derives from a panel -- the size ladder, the
        clamp a rebuild asks with, the centre a new window is placed at -- used to
        read the *primary*, and that answer is only right where one answer cannot
        be: measured on a real two-panel desk, every ``set_mode`` that replaces
        the window runs :meth:`Stage._place`, which re-centred on the primary -- so
        a size change teleported the window back to a panel the player had moved
        off, and then the size list opened describing the very panel the game had
        just left. Three readers, three answers, and the one the player sees was
        the least reliable of them.

        Reading the panel the *window* is on closes that triangle: the window did
        the moving, so the window is the record of where it is, and every reader
        that anchored on the primary was anchoring on a default instead of a fact.
        The fallbacks are the only two states where no fact exists -- a first
        launch, which has no window yet, and a degraded topology, which knows no
        geometry -- and both fall back to the primary, which is the best answer a
        machine with one report can give.
        """
        held = self.window_monitor()
        if held is not None:
            return held
        return self.topology().primary

    def effective_fit(self) -> FitPolicy:
        """The picture's fit, as the runtime draws it and the menu reports it.

        The single definition of the policy in force, and it is read by the
        presentation -- which draws with it -- and by the video menu's read-out,
        which describes it. Reading :attr:`settings.fit` directly was the
        bug: two readers that looked identical and were not, so with
        ``pixel_perfect`` set and no remembered policy the settings answers
        "bars" while the game draws at whole pixels, and the menu describes a
        target size nothing is drawn at.

        The rule lives in :func:`src.core.display.letterbox.effective_fit`,
        which is a pure function of the two stored names, so the migration
        case is its own decision and not a property of this runtime.
        """
        return letterbox.effective_fit(self.settings.fit, self.settings.pixel_perfect)

    def initialize_display(self) -> None:
        """Build the window and the presentation, once.

        Public because the headless fixtures need the same construction the loop
        does, rather than half of it.
        """
        self.stage = Stage(self._window_spec(), self.monitor())
        self._built_window_size = self.stage.size
        # The window exists, so the picture can be drawn at its size: the target
        # is the window's fitted rectangle and the density is read back off it.
        self.presentation = Presentation(
            self.stage.surface,
            DEFAULT_FRAMING,
            fit=self.effective_fit(),
            convert=True,
        )
        # Nothing is announced about where the window landed. The game used to
        # check which panel it ended up on and tell the player when it was not the
        # one they asked for -- but there is nothing asked for any more, so there
        # is nothing to be wrong about.

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
        assert self.stage is not None
        assert self.presentation is not None
        self.stage.rebuild(self._window_spec(), self.monitor())
        self._built_window_size = self.stage.size
        self.presentation.retarget(self.stage.surface)
        self._invalidate_assets()
        self.scene_manager.set_surface(self.presentation.surface)
        self.scene_manager.set_ui_scale(self.ui_scale)

    def window_monitor(self) -> Monitor | None:
        """The monitor the window is *actually* on, and ``None`` when nobody can say.

        Not the primary, which is where the game *opened*: on a two-screen desk
        the two differ as soon as the player drags the window across. The video
        menu's VSync row reads this rather than the primary display's rate, which
        is what made it report 60Hz while the window sat on a 180Hz panel.

        The top-left corner is what decides it: a window may legitimately be
        larger than the panel, and ``nearest`` gives the closest panel when the
        corner falls in a gap between two of them.

        ``None`` where the desktop has no readable geometry at all -- a degraded
        topology knows sizes and no origins, so there is nothing to be honest
        about, and a caller that has to print a rate would otherwise print the
        wrong one.
        """
        try:
            position = tuple(pygame.display.get_window_position())
        except pygame.error:
            return None
        topology = self.topology()
        if not topology.has_geometry:
            return None
        return topology.nearest(position)  # type: ignore[arg-type]

    def apply_settings(self, settings: UserSettings) -> None:
        """Apply new settings, doing only what the change actually touches.

        A chosen window size or a vsync flag changes the window, and therefore the
        picture, because the picture *is* the window's size. ``pixel_perfect``
        changes the letterbox, and therefore the target, without the window
        moving at all. A frame limit touches neither. The interface scale goes
        last, and always as the player's preference times the density -- which
        is why it is not a number read straight out of the settings.

        The file is written *last*, for the same reason the stage's rebuild is
        atomic: a ``set_mode`` that fails between the write and the call would
        leave the file describing a window that was never there, with every menu
        row agreeing with it -- the state the settings screen visualised in
        reverse, where the game claims a setting the player never got. Which is
        also why the in-memory state is rolled back on the way out: a raise
        unwound bindings and scales that no window reapplied, and leaving those
        set is a file-without-a-window by the frame after.
        """
        previous = self.settings
        self.settings = settings
        self.input_bindings = settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self._apply_panel_scale(settings)
        if self.stage is None or self.presentation is None:
            # Nothing to change the window, so there is nothing to fail first:
            # the write is the whole application.
            self._persist_settings()
            return
        # Before anything else, and unconditionally: the letterbox belongs to
        # the presentation, and a rebuild reads it. Setting it only on the branch
        # that does not touch the window is how the two drift apart -- a display
        # change and a sharpness change applied together left the presentation
        # snapping to whole pixels with the setting saying otherwise, which the
        # acceptance run caught and nothing else did.
        self.presentation.fit = self.effective_fit()
        try:
            if self._window_signature(previous) != self._window_signature(settings):
                self._rebuild_display()
            elif previous.pixel_perfect != settings.pixel_perfect or previous.fit != settings.fit:
                self._retarget()
            self.scene_manager.set_ui_scale(self.ui_scale)
        except Exception:
            self.settings = previous
            self.input_bindings = previous.bindings
            self.input_router.set_bindings(previous.bindings)
            self.input_provider.set_bindings(previous.bindings)
            raise
        self._persist_settings()

    def _apply_panel_scale(self, settings: UserSettings) -> None:
        """Hand the debug-panel scale to the overlay, if one has been built.

        Before the ``stage`` guard, because the overlay exists independently of
        it and can already be holding fonts sized for the old scale. And guarded
        on ``self.ui`` rather than calling :meth:`world_overlay`, which *builds*
        the overlay: applying a preference must not be the thing that brings the
        whole debug UI into existence.

        Not in :meth:`_window_signature` on purpose. A window change rebuilds the
        display, and the rebuild re-derives the screen scale from the new density
        -- so putting it there would rebuild the window on every step of the
        ladder, for a setting that has nothing to do with the window.
        """
        if self.ui is not None:
            self.ui.set_panel_scale(settings.panel_scale)

    def _invalidate_assets(self) -> None:
        """Drop every surface derived from the old display format.

        Three independent caches sit on top of the art: ``AssetLibrary``, the
        module-level frame cache in ``fx``, and the level cache, whose tiles
        PyTMX converted against the display format at load time. Clearing only
        the first would let the others hand back pre-reformat surfaces anyway.
        """
        shared_library().clear()
        fx.clear_frame_cache()
        self.level_manager.invalidate()

    @staticmethod
    def _window_signature(settings: UserSettings) -> tuple[object, ...]:
        """The settings that require a new ``pygame.display.set_mode`` call.

        A chosen window size and a vsync flag, and nothing else. Pixel-perfect art
        changes the target without the window moving, the frame limit touches
        neither, and the interface scale is a multiplier on a density the window
        already decided.
        """
        return (
            settings.vsync,
            settings.window_size,
        )

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
        """Update the bindings without rebuilding the window (in-game rebinding).

        ``apply_settings`` rebuilds the window (a new size, a vsync flag), which
        is unacceptable on every key capture in the controls screen. This
        persists the bindings and re-arms the router and provider only.
        """
        self.settings = self.settings.with_bindings(bindings)
        self.input_bindings = self.settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self._persist_settings()

    #: Seconds between two display-list reads. Long enough that the poll is not
    #: a per-frame cost (a read is ~0.005ms but is not free), short enough that
    #: unplugging a screen is noticed while the player is still looking at it.
    DISPLAY_POLL_SECONDS = 0.75

    def _poll_displays(self, frame_delta: float) -> None:
        """Notice a screen arriving or leaving, and cope with it.

        pygame-ce surfaces ``WINDOWDISPLAYCHANGED`` -- the window moving to
        another display -- but no event at all for a display being *added* or
        *removed*: SDL keeps those two internal and translates neither. Measured
        against the event constants pygame actually exports. So there is no
        callback to hook and the only way to see a second screen arrive is to ask
        again, which is what this does.

        What it does about it is the part that matters. Losing the screen the
        window is on would otherwise leave the window on a display that no longer
        exists, which on some drivers is a black screen with a running game behind
        it. So the window is rebuilt on the new primary, and the player is told,
        because a silent move is indistinguishable from the game deciding to ignore
        them. A screen *arriving* is worth saying too, since the list the game
        reads has changed.
        """
        self._topology_age += frame_delta
        if self.stage is None or self._topology_age < self.DISPLAY_POLL_SECONDS:
            return
        self._topology_age = 0.0
        current = detection.topology()
        if current == self._topology:
            return

        self._topology = current
        if self.stage.monitor.index not in current.indices:
            logger.info(
                "Display %d is gone; moving the window to the primary", self.stage.monitor.index
            )
            self.notice("That screen is no longer connected.", "The game moved to the main one.")
            self._rebuild_display()
        else:
            self.notice(
                f"{len(current.monitors)} screen(s) connected.",
                "The window stays where it is.",
            )

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
            raise RuntimeError("the game runtime is not initialized")
        frame_started = perf_counter()
        frame_delta = self._frame_delta()
        self._accumulator += min(frame_delta, Simulation.MAX_FRAME_TIME)

        # The window before the input: a click is converted through the picture
        # that is in force now and hit-tested against the rectangles the last draw
        # produced, so if the window moved between the two the two disagree --
        # measured, 244px off on the last row of the video menu after a snap, and
        # the click landed on a neighbour or on nothing. Laying the stack out
        # first is what makes them one geometry again.
        if self._follow_the_window():
            self.scene_manager.draw(self._draw_target())

        self._handle_events()
        self._poll_displays(frame_delta)
        self.scene_manager.poll_held_repeats()
        self.flush_settings()

        self._run_ticks()

        self.scene_manager.draw(self._draw_target())

        self._present()

        if self._notice_ttl > 0.0:
            self._notice_ttl = max(0.0, self._notice_ttl - _elapsed_ms(frame_started) / 1000.0)
            if self._notice_ttl == 0.0:
                self._notice = ()

    def _follow_the_window(self) -> bool:
        """Refit the picture when the window is no longer the size it was built at.

        **Read off the window, not off an event.** This started as a
        ``VIDEORESIZE`` handler and it was the wrong seam: pygame-ce translates
        SDL's window events into seven events of its own, and which one a resize
        arrives as depends on the platform and on the gesture. Measured on the
        development machine:

            Super+Left/Right (a snap)     WINDOWSIZECHANGED
            maximise, restore             WINDOWSIZECHANGED + VIDEORESIZE + WINDOWRESIZED
            a plain drag                  VIDEORESIZE

        So a snap -- the gesture that produces the most resizes of all -- told
        the game nothing at all, while a maximise happened to work. The symptom
        was the picture keeping the size it had: a 1000x562 frame blitted into a
        640x500 window is clipped at the right and the bottom, and a 1000x562
        frame in a 1600x1100 window leaves the new area holding whatever was
        there before. Both measured, both reproduced by the acceptance run.

        The window's own size is the one fact that holds whether or not SDL felt
        like mentioning it: with every event thrown away, the surface still
        reported 700x600 within a frame. One ``get_size`` per frame is 0.07
        microseconds, and :meth:`_retarget` decides for itself whether anything
        actually moved -- so this costs a comparison, not a cascade.

        Returns whether the window moved, which is the one thing the caller has to
        know: a frame in which it did has to lay the scenes out before it reads
        the input, or the click is measured against rectangles from a geometry
        that no longer exists.
        """
        if self.stage is None or self.presentation is None:
            return False
        # Off the presentation rather than the stage: they are the same surface in
        # production, and the presentation is the one that keeps it -- so this
        # asks the object that owns the window what shape it is now, which is also
        # the only question a caller can ask about a window it did not build.
        live = self.presentation.window_size
        if live == self._built_window_size:
            return False
        logger.info(
            "The window is now %sx%s (it was built at %s)",
            live[0],
            live[1],
            self._built_window_size,
        )
        # In that order: forgetting compares the window against the size the game
        # built it at, so the build size has to still be the old one here.
        self._forget_the_window_preference()
        self._retarget()
        self._built_window_size = live
        return True

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

    def notice(self, *lines: str, seconds: float = 4.0) -> None:
        """Say something on screen for a few seconds, replacing what was there.

        For the keys that cannot act. A key that does nothing and says nothing
        is indistinguishable from a key that is broken, and that ambiguity is
        exactly what made the debug overlay's death look like a wiring problem
        instead of a culling one.
        """
        self._notice = tuple(lines)
        self._notice_ttl = max(0.0, seconds)

    @property
    def notice_lines(self) -> tuple[str, ...]:
        """The live notice, ticked down by the frame loop."""
        return self._notice

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

            if event.type in self._WINDOW_SIZE_EVENTS:
                # Not scene input, and not the trigger either: the reaction to a
                # resize is read off the window every frame by
                # :meth:`_follow_the_window`, because which of these events a
                # resize arrives as is the platform's business, not the game's.
                continue

            if event.type == pygame.JOYDEVICEADDED:
                should_assign = not self.joysticks
                joy = pygame.joystick.Joystick(event.device_index)
                self.joysticks[joy.get_instance_id()] = joy
                logger.info("Connected controller : %s", joy.get_name())
                self.input_router.notify_joystick_connected(joy.get_instance_id(), joy)
                if should_assign:
                    self.input_provider.connect_joystick(joy)

            elif event.type == pygame.JOYDEVICEREMOVED and event.instance_id in self.joysticks:
                disconnected_joy = self.joysticks[event.instance_id]
                logger.info("Controller disconnected : %s", disconnected_joy.get_name())
                self.input_provider.disconnect_joystick(event.instance_id)
                self.input_router.notify_joystick_removed(event.instance_id)
                del self.joysticks[event.instance_id]
                self.input_provider.reassign_joystick(self.joysticks)

            elif not self._is_a_real_pointer_move(event):
                continue

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

    #: The events a change of window size can arrive as, listed so they are kept
    #: out of the scenes rather than acted on. Which one is delivered depends on
    #: the platform and the gesture -- measured, a snap sends only
    #: ``WINDOWSIZECHANGED`` on this machine while a maximise sends all three --
    #: so this is a list of "not input", not a list of "handle it here". The
    #: reaction is :meth:`_follow_the_window`, which reads the window instead.
    _WINDOW_SIZE_EVENTS = frozenset(
        {pygame.VIDEORESIZE, pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED}
    )

    @staticmethod
    def _is_a_real_pointer_move(event: pygame.event.Event) -> bool:
        """Whether this is the pointer moving, or the platform re-reporting it.

        A window rebuilt -- which is what every display setting does -- makes SDL
        emit a ``MOUSEMOTION`` with ``rel == (0, 0)``: the pointer did not move,
        the window under it did. That is not a gesture, and routing it as one
        moved the keyboard's selection: measured, the focus sat on "Display mode",
        the player changed the display mode, and the focus came back as
        "Back" -- because the menu takes its selection from the row under the
        pointer, and the pointer was somewhere over the panel. The next press
        closed the menu, or on a neighbouring row reset their video settings.

        A real move always carries a delta, which is the only thing that
        distinguishes the two here: there is no "moved to" event, and comparing
        positions would say a pointer that did move and returned is idle.
        """
        if event.type != pygame.MOUSEMOTION:
            return True
        return tuple(getattr(event, "rel", (0, 0))) != (0, 0)

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
        """Log the failure with its traceback, then try to show it.

        Three things were wrong with this and each had a consequence.

        It logged ``f"FATAL ERROR: {error}"`` at ``error`` level, which is the
        exception's *message*: a crash with an empty message logged an empty
        line, and the frame that raised it was not recorded anywhere. It is
        ``logger.critical`` with the traceback now, and that log is the artifact
        worth having -- the screen below is a courtesy.

        It drew on ``self.surface``, the window, bypassing the render target
        and the presentation. So the message appeared at 1:1 on the window
        whatever the letterbox and the density were, and the next
        ``present()`` -- had there been one -- would have overwritten it. It
        paints the target and presents it like any other frame, and falls back
        to the window only when there is no presentation yet, which is the
        case where the crash happened before the display was up.

        And it built its own ``SysFont("Arial")``, outside the chain that
        scales and caches every other glyph in the game, so the one message
        that matters most was the one drawn at the wrong size on a machine with
        no Arial. The panel chain is used instead, and if even that fails --
        a font cache that cannot allocate, a display that has gone away -- the
        failure is logged and swallowed. Raising out of the handler would
        replace a reportable crash with an unreportable one.
        """
        logger.critical("Fatal error; the game cannot continue", exc_info=error)
        try:
            self._paint_fatal_error(error)
        except Exception:  # noqa: BLE001 - this is the last line of defence
            logger.exception("Could not paint the fatal error screen")

    def _paint_fatal_error(self, error: Exception) -> None:
        """Put the failure on screen, on whichever surface is still alive."""
        # An exception with an empty str() would otherwise paint a blank panel.
        message = f"{type(error).__name__}: {error}".strip(": ")
        if self.presentation is not None:
            target = self.presentation.surface
            self._paint_error_panel(target, message)
            self.presentation.present()
            return
        # Crashed before the display came up: the window is all there is.
        surface = self.surface
        if surface is not None:
            surface.fill((0, 0, 0))
            text = pygame.font.Font(None, 24).render(message, True, (255, 0, 0))
            surface.blit(text, (10, 10))
            pygame.display.update()

    def _paint_error_panel(self, target: pygame.Surface, message: str) -> None:
        """Paint the message with the game's own panel chain."""
        target.fill((12, 8, 10))
        if self.ui is None:
            font = pygame.font.Font(None, 24)
            target.blit(font.render(message, True, (255, 0, 0)), (10, 10))
            return
        self.ui.renderer.draw_panel(10, 10, [message], title="FATAL ERROR")


def _elapsed_ms(started: float) -> float:
    """Milliseconds since ``started``, from a :func:`time.perf_counter` reading."""
    return (perf_counter() - started) * 1000.0
