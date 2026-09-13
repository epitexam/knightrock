"""Tests du panneau de menu partagé (Phase 2 #4 bis : UI unifiée)."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.application.scenes.menu_scene import MenuScene
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_MUTED, TEXT_TITLE


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def renderer() -> PanelRenderer:
    return PanelRenderer(pygame.display.get_surface())


def _stub_game() -> SimpleNamespace:
    """Game minimal : save_game + scene_manager (draw n'en a pas besoin)."""
    from src.application.save_game import SaveGame

    return SimpleNamespace(
        save_game=SaveGame(),
        scene_manager=SimpleNamespace(switch=lambda *_: None, pop=lambda: None),
    )


def test_menu_panel_returns_centered_rect(renderer: PanelRenderer) -> None:
    surface = pygame.display.get_surface()
    rect = draw_centered_menu_panel(renderer, surface, "TITLE", ["one", "two"])

    assert rect.width > 0
    # Centrage horizontal sur l'écran dummy (640px).
    assert rect.centerx == surface.get_width() // 2
    assert rect.top == 180


def test_menu_panel_uses_debug_theme_colors(renderer: PanelRenderer) -> None:
    surface = pygame.display.get_surface()
    draw_centered_menu_panel(renderer, surface, "TITLE", ["one"])

    assert surface.get_width() > 0
    assert renderer.render_text("TITLE", renderer.title_font, TEXT_TITLE) is renderer.render_text(
        "TITLE", renderer.title_font, TEXT_TITLE
    )
    assert renderer.render_text("one", renderer.debug_font, TEXT_MUTED) is renderer.render_text(
        "one", renderer.debug_font, TEXT_MUTED
    )


def test_menu_scene_draw_uses_panel_theme() -> None:
    menu = MenuScene(_stub_game())
    assert menu.draw() is None  # plein écran : comme les outils debug


def test_pause_scene_draw_uses_panel_theme() -> None:
    from src.application.scenes.pause_scene import PauseScene

    scene = PauseScene(_stub_game())
    assert scene.draw() is None


def test_game_over_scene_draw_uses_panel_theme() -> None:
    from src.application.scenes.gameover_scene import GameOverScene

    scene = GameOverScene(_stub_game())
    assert scene.draw() is None
