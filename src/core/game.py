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
        pygame.init()
        pygame.joystick.init()
        self.display_surface = pygame.display.set_mode((Display.WIDTH, Display.HEIGHT))
        pygame.display.set_caption(Display.TITLE)
        if pygame.joystick.get_count() > 0:
            pygame.joystick.Joystick(0).init()
        self.tmx_maps = {
            0: load_pygame(join(".", "assets", "data", "levels", "omni.tmx"))
        }
        self.input_manager = InputManager()
        self.current_stage = Level(
            self.display_surface, self.tmx_maps[0], self.input_manager
        )
        self.clock = pygame.time.Clock()
        self._accumulator = 0.0

    def run(self):
        """Run the main loop."""
        while True:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            self._accumulator += min(raw_delta, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

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
