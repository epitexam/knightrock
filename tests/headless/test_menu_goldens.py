"""The menus as pictures: a rendered screen compared with a reference image.

The menu bugs that mattered were visual -- two panels showing through each
other, a panel sliding sideways as the selection moved -- and every other test
checks numbers. These compare whole frames, pixel for pixel, against PNGs in
``tests/golden``. The font is bundled and the dummy driver draws the same
pixels on every machine, so a difference is a change to the picture.

After a deliberate visual change, regenerate and look at the images:

    UPDATE_GOLDENS=1 pytest tests/headless/test_menu_goldens.py
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pygame
import pytest

from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.menu_scene import MenuScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.video_scene import VideoScene
from src.core.game import Game

GOLDEN = Path(__file__).resolve().parent.parent / "golden"
SIZES = ((1152, 648), (1920, 1080))


def _game(tmp_path: Path, size: tuple[int, int]) -> Game:
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    assert game.presentation is not None
    game.presentation.retarget(pygame.Surface(size))
    game._retarget()
    return game


def _main_menu(game: Game) -> None:
    game.scene_manager.switch(MenuScene(game))


def _video(game: Game) -> None:
    game.scene_manager.switch(MenuScene(game))
    game.scene_manager.push(OptionsScene(game))
    game.scene_manager.push(VideoScene(game))


def _fit_list(game: Game) -> None:
    _video(game)
    scene = game.scene_manager.current
    assert isinstance(scene, VideoScene)
    scene._open("fit")


def _controls(game: Game) -> None:
    game.scene_manager.switch(MenuScene(game))
    game.scene_manager.push(ControlsScene(game, ControlsScene.MENU_SECTION))


SCREENS: dict[str, Callable[[Game], None]] = {
    "main_menu": _main_menu,
    "controls": _controls,
    "video": _video,
    "fit_list": _fit_list,
}


@pytest.mark.parametrize("size", SIZES, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("name", sorted(SCREENS))
def test_the_screen_looks_like_its_reference(
    name: str, size: tuple[int, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    game = _game(tmp_path, size)
    SCREENS[name](game)
    assert game.presentation is not None
    surface = game.presentation.surface
    # Two frames: the first lays the list out, the second draws it settled.
    game.scene_manager.draw(surface)
    game.scene_manager.draw(surface)

    reference = GOLDEN / f"{name}-{size[0]}x{size[1]}.png"
    if os.environ.get("UPDATE_GOLDENS") == "1" or not reference.exists():
        if os.environ.get("UPDATE_GOLDENS") != "1":
            pytest.fail(f"No reference image at {reference}; run with UPDATE_GOLDENS=1")
        GOLDEN.mkdir(exist_ok=True)
        pygame.image.save(surface, str(reference))
        return

    expected = pygame.image.load(str(reference))
    assert expected.get_size() == surface.get_size()
    got = pygame.image.tobytes(surface, "RGB")
    want = pygame.image.tobytes(expected, "RGB")
    if got != want:
        actual = tmp_path / reference.name
        pygame.image.save(surface, str(actual))
        pytest.fail(
            f"{name} at {size} no longer matches {reference.name}; the new frame is "
            f"{actual}. If the change is deliberate, run with UPDATE_GOLDENS=1."
        )
