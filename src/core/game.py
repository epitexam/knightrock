import os
import sys
import traceback
from os.path import join

import pygame

from src.core.settings import Display, Simulation
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider
from src.core.level.level_manager import LevelManager
from src.core.level.level import Level


class Game:
    def __init__(self) -> None:
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

        pygame.init()
        pygame.joystick.init()

        self.display_surface = pygame.display.set_mode((Display.WIDTH, Display.HEIGHT))
        pygame.display.set_caption(Display.TITLE)

        self.joysticks: dict[int, pygame.joystick.Joystick] = {}

        self.level_manager = LevelManager()
        self.level_manager.register(0, join(".", "assets", "data", "levels", "1.tmx"))
        # Ajoute ici les autres niveaux, par ex :
        # self.level_manager.register(1, join(".", "assets", "data", "levels", "autre.tmx"))

        self.input_provider = LocalInputProvider()
        self.input_manager = InputManager(self.input_provider)

        self.current_level_id = 0
        self.current_stage = self._load_level(self.current_level_id)

        self.clock = pygame.time.Clock()
        self._accumulator = 0.0

    def _load_level(self, level_id: int) -> Level:
        level_data = self.level_manager.get(level_id)
        return Level(self.display_surface, level_data, self.input_manager)

    def run(self) -> None:
        while True:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            self._accumulator += min(raw_delta, 0.1)

            self._handle_events()

            try:
                while self._accumulator >= Simulation.TIMESTEP:
                    self.input_manager.update()
                    self.current_stage.update(Simulation.TIMESTEP)
                    self._accumulator -= Simulation.TIMESTEP

                if self.current_stage.completed:
                    self._advance_level()

                self.current_stage.draw(self.clock.get_fps())

            except Exception as e:
                traceback.print_exc()
                self._handle_fatal_error(e)

            pygame.display.update()

    def _advance_level(self) -> None:
        next_id = self.level_manager.next_id(self.current_level_id)
        if next_id is None:
            return
        self.current_level_id = next_id
        self.current_stage = self._load_level(next_id)
        self._accumulator = 0.0

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                self.joysticks[joy.get_instance_id()] = joy
                print(f"Connected controller : {joy.get_name()}")
                if self.input_provider._joystick is None:
                    self.input_provider.connect_joystick(joy)

            elif event.type == pygame.JOYDEVICEREMOVED:
                if event.instance_id in self.joysticks:
                    disconnected_joy = self.joysticks[event.instance_id]
                    print(f"Controller disconnected : {disconnected_joy.get_name()}")
                    self.input_provider.disconnect_joystick(event.instance_id)
                    del self.joysticks[event.instance_id]
                    self.input_provider.reassign_joystick(self.joysticks)

    def _handle_fatal_error(self, error: Exception) -> None:
        self.display_surface.fill((0, 0, 0))
        font = pygame.font.SysFont("Arial", 30)
        text = font.render("FATAL ERROR: " + str(error), True, (255, 0, 0))
        self.display_surface.blit(text, (10, 10))
        pygame.display.update()
        pygame.time.wait(5000)
        pygame.quit()
        sys.exit(1)