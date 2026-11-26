"""The HUD sits in the part of the target the window shows.

Under the zoom fit the window shows a centred crop of the target, so gauges
anchored to the target's corners were painted in the cropped-off margins: on a
window wider than 16:9 the bottom bars ran off the screen.
"""

from __future__ import annotations

import os

import pygame
import pytest

from src.presentation.display.framing import Framing
from src.presentation.display.letterbox import FitPolicy, picture
from tests.unit.helpers import make_overlay
from tests.unit.test_hud import _player


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_a_wide_window_under_zoom_shows_a_crop_of_the_target() -> None:
    shown = picture((1706, 901), Framing(1152.0, 648.0), FitPolicy.ZOOM)

    assert shown.target.height > 901, "the picture is taller than the window"
    assert shown.source.height == 901
    assert shown.source.top > 0, "and its top and bottom are cut off"


def test_the_gauges_are_laid_out_inside_the_shown_area() -> None:
    target = pygame.Surface((1706, 959))
    ui = make_overlay(target)
    shown = pygame.Rect(0, 29, 1706, 901)

    with ui.drawing_within(shown):
        layout = ui.hud.layout(_player())
        assert ui.renderer.surface.get_size() == shown.size
    assert layout is not None
    for gauge in layout.gauges:
        assert gauge.bar.bottom <= shown.height, "laid out against the shown bottom"
    assert ui.renderer.surface is target, "the target is handed back"


def test_painting_within_lands_in_the_shown_area_only() -> None:
    target = pygame.Surface((400, 300))
    target.fill((0, 0, 0))
    ui = make_overlay(target)
    shown = pygame.Rect(0, 40, 400, 220)

    with ui.drawing_within(shown):
        ui.draw_hud(_player())

    below = [target.get_at((x, y))[:3] for x in range(0, 400, 4) for y in range(shown.bottom, 300)]
    assert all(pixel == (0, 0, 0) for pixel in below), "nothing in the cropped-off strip"
    assert any(
        target.get_at((x, y))[:3] != (0, 0, 0)
        for x in range(0, 400, 2)
        for y in range(shown.top, shown.bottom)
    )


def test_the_whole_target_shown_changes_nothing() -> None:
    target = pygame.Surface((400, 300))
    ui = make_overlay(target)
    with ui.drawing_within(target.get_rect()):
        assert ui.renderer.surface is target
    with ui.drawing_within(None):
        assert ui.renderer.surface is target
