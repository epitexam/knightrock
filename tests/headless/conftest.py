"""Fixtures partagées des tests headless (audit F7.1, Phase 1 #10).

Initialise SDL en mode dummy une seule fois par session et fournit
un constructeur de ``Level`` orchestral à partir de données programmatiques
(aucun asset TMX requis, donc fonctionne en CI sans le dossier ``assets/``).
"""

import os

import pygame
import pytest

from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.settings import Display


@pytest.fixture(scope="session", autouse=True)
def _headless_pygame_display() -> None:
    """Initialise pygame + une fenêtre SDL dummy pour toute la session."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((min(Display.WIDTH, 640), min(Display.HEIGHT, 480)))


def make_programmatic_level_data() -> LevelData:
    """Construit un LevelData minimal (1 joueur, rien d'autre)."""
    player_object = ObjectData(
        name="player",
        x=100.0,
        y=100.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )
    entities = ObjectLayerData(name="Entities", objects=[player_object])
    return LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={"Entities": entities},
        config=LevelConfig(death_border_bottom=0.0),
    )


@pytest.fixture()
def build_level(mock_input_manager):
    """Factory renvoyant un vrai ``Level`` garni par le joueur."""

    def _build() -> Level:
        level = Level(
            pygame.display.get_surface(),
            make_programmatic_level_data(),
            mock_input_manager,
        )
        return level

    return _build
