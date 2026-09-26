"""Shared headless test fixtures (audit F7.1, Phase 1 #10).

Initialize SDL in dummy mode once per session and provide an orchestral
``Level`` builder from programmatic data (no TMX asset required, so it works
in CI without the ``assets/`` folder).
"""

import os

import pygame
import pytest

from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import DEFAULT_RENDER_SCALE, Viewport
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.settings import Display


@pytest.fixture(scope="session", autouse=True)
def _headless_pygame_display() -> None:
    """Initialize pygame + a dummy SDL window for the whole session."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((min(Display.WIDTH, 640), min(Display.HEIGHT, 480)))


def make_viewport(scale: int = DEFAULT_RENDER_SCALE) -> Viewport:
    """A render target, the way the game builds one.

    Tests used to hand ``pygame.display.get_surface()`` straight to a Level,
    which is the coupling this rework removed: the window is not what anything is
    drawn into. It happens to still work under the dummy driver, and it is the
    reason a fixture can quietly disagree with the game about what a frame is.
    """
    return Viewport(DEFAULT_FRAMING, scale)


def make_programmatic_level_data() -> LevelData:
    """Build a minimal LevelData (1 player, nothing else)."""
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
    """Factory returning a real player-populated ``Level``."""

    def _build() -> Level:
        return Level(
            make_viewport().surface,
            make_programmatic_level_data(),
            mock_input_manager,
        )

    return _build


@pytest.fixture()
def game_runtime(tmp_path):
    """An initialized ``Game`` (dummy display) without running the loop."""
    from src.core.game import Game

    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    # The real construction path, so the fixture cannot drift from the loop:
    # window, render target and presentation, all three.
    game.initialize_display()
    game.clock = pygame.time.Clock()
    return game
