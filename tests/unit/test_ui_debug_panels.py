"""Tests for the enriched debug panels (ui_manager)."""

import inspect
import os
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from src.core.level.level import Level
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


def _make_host(scene_name: str = "GameplayScene", with_level: bool = False) -> SimpleNamespace:
    """Build a fake `SceneHost` with a configurable active scene."""
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
    host = _make_host("MenuScene", with_level=False)
    height = ui_manager.draw_scene_panel(10, 10, host)
    assert height > 0


def test_scene_panel_with_level(ui_manager: UIManager) -> None:
    host = _make_host("GameplayScene", with_level=True)
    height = ui_manager.draw_scene_panel(10, 10, host)
    assert height > 0


def test_scene_panel_no_current_scene(ui_manager: UIManager) -> None:
    host = SimpleNamespace(scene_manager=SimpleNamespace(current=None))
    height = ui_manager.draw_scene_panel(10, 10, host)
    assert height > 0


def test_scene_panel_with_no_host_at_all(ui_manager: UIManager) -> None:
    """A level drawn outside the scene stack has nobody to ask.

    The panel still draws, with "None" for the scene, rather than raising:
    this is the same thing `game=None` used to mean.
    """
    height = ui_manager.draw_scene_panel(10, 10, None)
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
    # Check the panel draws without error (cache + fonts ready).
    assert ui_manager.renderer.debug_font.get_height() > 0


def test_performance_panel_reports_real_cache_size() -> None:
    ui = UIManager(pygame.Surface((640, 480)))
    ui.renderer.render_text("cache-probe", ui.renderer.debug_font, (255, 255, 255))

    ui.draw_performance_panel(
        fps=60.0,
        sprite_count=0,
        combat_count=0,
        entity_count=0,
        collision_count=0,
        hit_stop=0.0,
        spawn_cooldown=0.0,
    )

    assert ui.renderer.text_cache_stats["entries"] > 1


def test_performance_panel_defaults_backward_compatible(ui_manager: UIManager) -> None:
    # New params are optional: the historic call stays valid.
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


def test_the_scene_host_port_is_what_the_panel_actually_needs() -> None:
    """The panel reads one attribute, so the port declares one.

    Worth pinning because the audit asked for a six-member `SceneHost`
    describing a seam that does not exist here; a Protocol that
    under-describes its subject is `Any` with better manners.
    """
    from src.core.level.scene_host import SceneHost, SceneStack

    assert set(SceneHost.__protocol_attrs__) == {"scene_manager"}
    assert set(SceneStack.__protocol_attrs__) == {"current"}


def test_the_game_satisfies_the_scene_host_port(tmp_path: Path) -> None:
    """Checked on a real instance, because a Protocol nothing satisfies is a comment.

    `Game.scene_manager` is assigned in `__init__`, so this has to be an
    instance: `hasattr(Game, ...)` would be false for a member that is very
    much there.
    """
    from src.core.game import Game
    from src.core.level.scene_host import SceneHost

    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    for member in SceneHost.__protocol_attrs__:
        assert hasattr(game, member), f"Game does not satisfy SceneHost.{member}"


def test_a_level_can_be_drawn_with_no_application_at_all() -> None:
    """`Level.draw` used to take `game: Any`; the point of the port is that a
    level no longer needs one to produce a frame."""
    from src.core.level.scene_host import SceneHost

    signature = inspect.signature(Level.draw)
    annotation = signature.parameters["scene_host"].annotation
    assert annotation == (SceneHost | None)
    assert signature.parameters["scene_host"].default is None
