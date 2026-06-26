import sys
import traceback
from os.path import join

import pygame
from pytmx.util_pygame import load_pygame

from src.core.level import Level
from src.core.settings import Display
from src.core.input_manager import InputManager


class Game:
    def __init__(self) -> None:
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

    def run(self):
        while True:
            raw_delta = self.clock.tick(Display.FPS) / 1000.0
            delta_time = min(raw_delta, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.input_manager.update()
            fps = self.clock.get_fps()

            try:
                self.current_stage.run(delta_time, fps)
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