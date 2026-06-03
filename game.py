import sys
from os.path import join

import pygame
from pytmx.util_pygame import load_pygame

from level import Level
from settings import *


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(CAPTION)
        self.tmx_maps = {0: load_pygame(join(".", "data", "levels", "omni.tmx"))}
        self.current_stage = Level(self.display_surface, self.tmx_maps[0])
        self.clock = pygame.time.Clock()

    def run(self):
        while True:
            delta_time = self.clock.tick() / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.current_stage.run(delta_time)
            pygame.display.update()
