"""Tests for PanelRenderer (ui/panel_renderer)."""

import os

import pygame
import pytest

from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BG, TEXT_MUTED, TEXT_TITLE


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def renderer() -> PanelRenderer:
    return PanelRenderer(pygame.display.get_surface())


def test_render_text_caches_surfaces(renderer: PanelRenderer) -> None:
    font = renderer.debug_font
    surf1 = renderer.render_text("hello", font, TEXT_MUTED)
    surf2 = renderer.render_text("hello", font, TEXT_MUTED)
    assert surf1 is surf2


def test_render_text_different_params_not_shared(renderer: PanelRenderer) -> None:
    surf_a = renderer.render_text("hello", renderer.debug_font, TEXT_MUTED)
    surf_b = renderer.render_text("hello", renderer.debug_font, TEXT_TITLE)
    assert surf_a is not surf_b
    assert surf_a is renderer.render_text("hello", renderer.debug_font, TEXT_MUTED)


def test_draw_panel_without_title_returns_height(renderer: PanelRenderer) -> None:
    height = renderer.draw_panel(10, 10, ["line1", "line2"])
    assert height > 0


def test_draw_panel_with_title_returns_height(renderer: PanelRenderer) -> None:
    height = renderer.draw_panel(10, 10, ["line1"], title="TEST")
    assert height > 0


def test_draw_panel_with_line_colors(renderer: PanelRenderer) -> None:
    height = renderer.draw_panel(
        10, 10, ["a", "b"], line_colors={0: (255, 0, 0)}
    )
    assert height > 0


def test_draw_panel_empty_lines(renderer: PanelRenderer) -> None:
    height = renderer.draw_panel(10, 10, [])
    assert height > 0


def test_draw_panel_custom_color(renderer: PanelRenderer) -> None:
    height = renderer.draw_panel(10, 10, ["x"], color=(10, 20, 30, 200))
    assert height > 0


def test_get_panel_width_matches_content(renderer: PanelRenderer) -> None:
    lines = ["short", "a much longer line of text"]
    width = renderer.get_panel_width(lines)
    assert width > 24  # at least padding


def test_get_panel_width_consistent(renderer: PanelRenderer) -> None:
    lines = ["test"]
    width = renderer.get_panel_width(lines)
    assert width == renderer.get_panel_width(lines)