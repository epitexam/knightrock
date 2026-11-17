"""Pointing at a row never moves the rows.

Each focused row may show a note under the list, and the panel used to be sized
for the focused row's note alone. On the Video screen, Back has no note: the
pointer reaching it removed the note band, every row grew and slid down, the
pointer was then over Reset, whose note brought the band back -- and the focus
flickered between the two. The same happened on the option lists whose entries
have no note. The panel is now sized for every note the page can show.

Checked by driving the real pointer path: a mouse event at the centre of each
row, routed through the game, then the rows compared with where they were.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pygame
import pytest

from src.application.game import Game
from src.application.scenes.menu_scene import MenuScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.video_scene import VideoScene

SIZES = ((1152, 648), (800, 600), (640, 480))


def _game(tmp_path: Path, size: tuple[int, int]) -> Game:
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    assert game.presentation is not None
    game.presentation.retarget(pygame.Surface(size))
    game._retarget()
    game.scene_manager.switch(MenuScene(game))
    game.scene_manager.push(OptionsScene(game))
    game.scene_manager.push(VideoScene(game))
    return game


def _video(game: Game) -> None:
    pass


def _list(key: str) -> Callable[[Game], None]:
    def open_list(game: Game) -> None:
        scene = game.scene_manager.current
        assert isinstance(scene, VideoScene)
        scene._open(key)

    return open_list


PAGES: dict[str, Callable[[Game], None]] = {
    "video": _video,
    "fit": _list("fit"),
    "frame_limit": _list("frame_limit"),
    "size": _list("size"),
}


def _frame(game: Game) -> None:
    assert game.presentation is not None
    game._handle_events()
    game.scene_manager.draw(game.presentation.surface)


@pytest.mark.parametrize("size", SIZES, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("page", sorted(PAGES))
def test_hovering_any_row_leaves_every_row_in_place(
    page: str, size: tuple[int, int], tmp_path: Path
) -> None:
    game = _game(tmp_path, size)
    PAGES[page](game)
    scene = game.scene_manager.current
    assert scene is not None and scene.view is not None
    for _ in range(3):
        _frame(game)
    picture = game.presentation.picture  # type: ignore[union-attr]
    model = scene.model  # type: ignore[attr-defined]

    for index, item in enumerate(model.items):
        rect = scene.view.item_rects[index]  # type: ignore[attr-defined]
        if rect.width == 0 or item.kind == "header":
            continue
        before = [tuple(r) for r in scene.view.item_rects]  # type: ignore[attr-defined]
        position = (
            rect.centerx - picture.source.x + picture.dest.x,
            rect.centery - picture.source.y + picture.dest.y,
        )
        pygame.event.post(
            pygame.event.Event(pygame.MOUSEMOTION, pos=position, rel=(1, 1), buttons=(0, 0, 0))
        )
        for _ in range(3):
            _frame(game)

        if item.enabled:
            assert model.current_index == index, f"hovering {item.action} focused another row"
        after = [tuple(r) for r in scene.view.item_rects]  # type: ignore[attr-defined]
        if getattr(scene, "_scroll", 0) == 0:
            assert after == before, f"hovering {item.action} moved the rows"
