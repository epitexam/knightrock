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
    SettingsStore,
    UserSettings,
)
from src.core.input.event_router import EventRouter
from src.core.input.input_bindings import InputBindings
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.settings import Display, Simulation
from src.data.provider import GameplayData, load_gameplay_data

logger = logging.getLogger(__name__)


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
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        self.display_surface: pygame.Surface | None = None
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
        self.level_manager = LevelManager(
            self.gameplay_data.levels if self.gameplay_data.levels else LEVEL_PATHS
        )
        self._save_path = save_path if save_path is not None else default_save_path()
        self.save_game = SaveGame.load(self._save_path)
        self.events = EventBus()
        self._subscribe_notifications()
        self.scene_manager = SceneManager(self)
        self.running = True
        self.clock: pygame.time.Clock | None = None
        self._accumulator = 0.0

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

        self.display_surface = self._configure_display()
        pygame.display.set_caption(Display.TITLE)

        self.clock = pygame.time.Clock()
        self._accumulator = 0.0
        self.scene_manager.switch(MenuScene(self))

    def apply_settings(self, settings: UserSettings) -> None:
        self.settings = settings
        self.input_bindings = settings.bindings
        self.input_router.set_bindings(self.input_bindings)
        self.input_provider.set_bindings(self.input_bindings)
        self.settings_store.save(settings)
        if self.display_surface is not None:
            self.display_surface = self._configure_display()
            self.scene_manager.set_display_surface(self.display_surface)
            self.scene_manager.set_ui_scale(settings.ui_scale)

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
        self.settings_store.save(self.settings)

    def _configure_display(self) -> pygame.Surface:
        """Create the window at the logical resolution chosen in the menu.

        The window is deliberately **not** resizable: the selected resolution
        is the stable gameplay viewport the camera culling and the level
        streaming budget are computed against. A user drag would change that
        viewport mid-run, so the only way to change it is the Video menu.

        In fullscreen ``pygame.SCALED`` keeps the logical aspect ratio and
        letterboxes (black bars) the leftover desktop area instead of
        stretching the image or distorting the menus.
        """
        flags = 0
        if self.settings.fullscreen:
            flags |= pygame.FULLSCREEN | pygame.SCALED
        return pygame.display.set_mode(
            (self.settings.width, self.settings.height),
            flags,
            vsync=1 if self.settings.vsync else 0,
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
            pygame.quit()

    def quit(self) -> None:
        """Stop the loop at the end of the current frame."""
        self.running = False

    def _run_loop(self) -> None:
        if self.clock is None:
            raise RuntimeError("The game runtime is not initialized")

        while self.running:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            self._accumulator += min(raw_delta, Simulation.MAX_FRAME_TIME)

            self._handle_events()
            self.scene_manager.poll_held_repeats()

            while self._accumulator >= Simulation.TIMESTEP:
                self.scene_manager.update(Simulation.TIMESTEP)
                self._accumulator -= Simulation.TIMESTEP

            dirty_rects = self.scene_manager.draw()
            if dirty_rects is None:
                pygame.display.update()
            else:
                pygame.display.update(dirty_rects)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            if event.type == pygame.VIDEORESIZE:
                # La fenêtre n'est pas redimensionnable : la résolution est
                # pilotée uniquement par le menu vidéo. SDL peut encore
                # annoncer un VIDEORESIZE lors d'un set_mode() interne ou d'un
                # basculement plein écran ; on l'ignore pour que le viewport
                # logique reste stable et qu'aucune boucle ne naisse.
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

            self.scene_manager.handle_event(event)

    def _handle_fatal_error(self, error: Exception) -> None:
        logger.error(f"FATAL ERROR: {error}")
        if self.display_surface is None:
            return

        try:
            self.display_surface.fill((0, 0, 0))
            font = pygame.font.SysFont("Arial", 30)
            text = font.render(f"FATAL ERROR: {error}", True, (255, 0, 0))
            self.display_surface.blit(text, (10, 10))
            pygame.display.update()
        except pygame.error:
            print("Unable to render the fatal error screen", file=sys.stderr)
