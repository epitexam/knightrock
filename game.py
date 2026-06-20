import sys
from os.path import join

import pygame
from pytmx.util_pygame import load_pygame

from level import Level
from settings import Display


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.display_surface = pygame.display.set_mode((Display.WIDTH, Display.HEIGHT))
        pygame.display.set_caption(Display.TITLE)
        self.tmx_maps = {0: load_pygame(join(".", "data", "levels", "omni.tmx"))}
        self.current_stage = Level(self.display_surface, self.tmx_maps[0])
        self.clock = pygame.time.Clock()

    def run(self):
        while True:
            raw_delta = self.clock.tick() / 1000.0
            delta_time = min(raw_delta, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.current_stage.run(delta_time)
            pygame.display.update()
