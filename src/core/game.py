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
    """Initialize and run the main game loop."""

    def __init__(self) -> None:
        """Initialize the Game instance."""
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

        pygame.init()
        pygame.joystick.init()

        self.display_surface = pygame.display.set_mode(
            (Display.WIDTH, Display.HEIGHT))
        pygame.display.set_caption(Display.TITLE)

        self.joysticks = {}

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
        """Run the main loop."""
        while True:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            self._accumulator += min(raw_delta, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.JOYDEVICEADDED:
                    joy = pygame.joystick.Joystick(event.device_index)
                    self.joysticks[joy.get_instance_id()] = joy
                    print(f"Connected controller : {joy.get_name()}")

                    if self.input_manager._joystick is None:
                        self.input_manager._joystick = joy
                        self.input_manager._button_prev.clear()
                        self.input_manager._trigger_prev.clear()

                elif event.type == pygame.JOYDEVICEREMOVED:
                    if event.instance_id in self.joysticks:
                        print(
                            f"Controller disconnected : {self.joysticks[event.instance_id].get_name()}")

                        if self.input_manager._joystick and self.input_manager._joystick.get_instance_id() == event.instance_id:
                            self.input_manager._joystick = None
                            self.input_manager._button_prev.clear()
                            self.input_manager._trigger_prev.clear()

                        del self.joysticks[event.instance_id]

                        if not self.input_manager._joystick and self.joysticks:
                            self.input_manager._joystick = list(
                                self.joysticks.values())[0]

            try:
                while self._accumulator >= Simulation.TIMESTEP:
                    self.input_manager.update()
                    self.current_stage.update(Simulation.TIMESTEP)

                    self._accumulator -= Simulation.TIMESTEP

                self.current_stage.draw(self.clock.get_fps())

            except Exception as e:
                traceback.print_exc()
                self.display_surface.fill((0, 0, 0))
                font = pygame.font.SysFont("Arial", 30)
                text = font.render("FATAL ERROR: " + str(e), True, (255, 0, 0))
                self.display_surface.blit(text, (10, 10))
                pygame.display.update()
                pygame.time.wait(5000)
                pygame.quit()
                sys.exit(1)

            pygame.display.update()
