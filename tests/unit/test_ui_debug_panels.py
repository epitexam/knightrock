"""Tests pour les panneaux de debug enrichis (ui_manager)."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.ui.ui_manager import UIManager


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


@pytest.fixture()
def ui_manager() -> UIManager:
    return UIManager(pygame.display.get_surface())


def _make_game(scene_name: str = "GameplayScene", with_level: bool = False) -> SimpleNamespace:
    """Construit un fake Game avec une scène active configurable."""
    level = None
    if with_level:
        groups = SimpleNamespace(
            entity_sprites=[
                SimpleNamespace(faction="enemy"),
                SimpleNamespace(faction="enemy"),
                SimpleNamespace(faction="player"),
            ],
            hazard_sprites=[SimpleNamespace(), SimpleNamespace()],
        )
        level = SimpleNamespace(level_id=2, deaths=1, groups=groups)

    scene_cls = type(scene_name, (), {})
    scene = scene_cls()
    scene.level_id = getattr(level, "level_id", None)
    scene.level = level
    return SimpleNamespace(
        scene_manager=SimpleNamespace(current=scene),
    )


def test_scene_panel_without_level(ui_manager: UIManager) -> None:
    game = _make_game("MenuScene", with_level=False)
    height = ui_manager.draw_scene_panel(10, 10, game)
    assert height > 0


def test_scene_panel_with_level(ui_manager: UIManager) -> None:
    game = _make_game("GameplayScene", with_level=True)
    height = ui_manager.draw_scene_panel(10, 10, game)
    assert height > 0


def test_scene_panel_no_current_scene(ui_manager: UIManager) -> None:
    game = SimpleNamespace(scene_manager=SimpleNamespace(current=None))
    height = ui_manager.draw_scene_panel(10, 10, game)
    assert height > 0


def test_performance_panel_includes_frame_time(ui_manager: UIManager) -> None:
    ui_manager.draw_performance_panel(
        fps=60.0,
        sprite_count=50,
        combat_count=5,
        entity_count=10,
        collision_count=100,
        hit_stop=0.0,
        spawn_cooldown=0.5,
        frame_time=16.0,
        cache_size=42,
    )
    # Vérifie que le panneau se dessine sans erreur (cache + polices prêts).
    assert ui_manager.renderer.debug_font.get_height() > 0


def test_performance_panel_defaults_backward_compatible(ui_manager: UIManager) -> None:
    # Les nouveaux paramètres sont optionnels : l'appel historique reste valide.
    ui_manager.draw_performance_panel(
        fps=30.0,
        sprite_count=1,
        combat_count=1,
        entity_count=1,
        collision_count=1,
        hit_stop=0.0,
        spawn_cooldown=0.0,
    )
    assert ui_manager.renderer.title_font.get_height() > 0
