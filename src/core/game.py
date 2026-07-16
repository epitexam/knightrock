"""
Main game application class and entry point for the fixed timestep loop.
"""
import os
import sys
import traceback
from os.path import join
import pygame
from pytmx.util_pygame import load_pygame

from src.core.level import Level
from src.core.settings import Display, Simulation
from src.core.input_manager import InputManager


class Game:
    """Initialize the game engine and run the main fixed-timestep loop."""

    def __init__(self) -> None:
        """Initialize Pygame subsystems, display, and the first level."""
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

        pygame.init()
        pygame.joystick.init()

        self.display_surface = pygame.display.set_mode(
            (Display.WIDTH, Display.HEIGHT))
        pygame.display.set_caption(Display.TITLE)

        self.joysticks: dict[int, pygame.joystick.Joystick] = {}

        self.tmx_maps = {
            0: load_pygame(join(".", "assets", "data", "levels", "omni.tmx"))
        }

        self.input_manager = InputManager()
        self.current_stage = Level(
            self.display_surface, self.tmx_maps[0], self.input_manager
        )

        self.clock = pygame.time.Clock()
        self._accumulator = 0.0

    def run(self) -> None:
        """Execute the main game loop, handling events, fixed updates, and rendering."""
        while True:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            self._accumulator += min(raw_delta, 0.1)

            self._handle_events()

            try:
                while self._accumulator >= Simulation.TIMESTEP:
                    self.input_manager.update()
                    self.current_stage.update(Simulation.TIMESTEP)
                    self._accumulator -= Simulation.TIMESTEP

                self.current_stage.draw(self.clock.get_fps())

            except Exception as e:
                traceback.print_exc()
                self._handle_fatal_error(e)

            pygame.display.update()

    def _handle_events(self) -> None:
        """Poll and process Pygame system and input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                self.joysticks[joy.get_instance_id()] = joy
                print(f"Connected controller : {joy.get_name()}")
                if self.input_manager._joystick is None:
                    self.input_manager.connect_joystick(joy)

            elif event.type == pygame.JOYDEVICEREMOVED:
                if event.instance_id in self.joysticks:
                    disconnected_joy = self.joysticks[event.instance_id]
                    print(f"Controller disconnected : {disconnected_joy.get_name()}")
                    self.input_manager.disconnect_joystick(event.instance_id)
                    del self.joysticks[event.instance_id]
                    self.input_manager.reassign_joystick(self.joysticks)

    def _handle_fatal_error(self, error: Exception) -> None:
        """Display a fatal error screen and gracefully exit the application."""
        self.display_surface.fill((0, 0, 0))
        font = pygame.font.SysFont("Arial", 30)
        text = font.render("FATAL ERROR: " + str(error), True, (255, 0, 0))
        self.display_surface.blit(text, (10, 10))
        pygame.display.update()
        pygame.time.wait(5000)
        pygame.quit()
        sys.exit(1)