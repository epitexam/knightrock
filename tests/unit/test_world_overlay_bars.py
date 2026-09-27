"""The world-space health bars: a production path, and a leaf module.

`Level.draw` calls `renderer.draw_health_bars` *before* it checks whether
`DEBUG` is set, so these bars are painted on every frame of a real game. They
used to live inside `world_ui.py`, among ~1800 lines of F1-layer debug
drawing, which is the kind of arrangement that decays quietly: a production
path gets reviewed with the debug layer's eye, and its tests get counted
against the debug layer's coverage.

So this file has two jobs. It checks that the bars are reached with `DEBUG`
off -- the reason they were extracted -- and that the module they moved to
depends on nothing back in `world_ui`, which is what makes the label code's
use of it (dodging around a bar it never draws) a sensible direction.
"""

import ast
import os
from pathlib import Path

import pygame
import pytest

from src.core.colors import Colors
from src.ui import world_ui
from src.ui.world_overlay_bars import (
    draw_health_bars,
    has_health_bar,
    health_bar_rect,
    health_colour,
)
from src.ui.world_overlay_metrics import HEALTH_BAR_HEIGHT

BARS_MODULE = Path(world_ui.__file__).with_name("world_overlay_bars.py")
UI_DIR = BARS_MODULE.parent


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


class _Sprite:
    """A sprite carrying only the attributes the bar pass reads."""

    def __init__(self, rect, **fields):
        self.rect = pygame.FRect(rect)
        for name, value in fields.items():
            setattr(self, name, value)


def _entity(x=100.0, y=100.0, **fields) -> _Sprite:
    base = {"faction": "enemy", "max_health": 100.0, "health": 100.0, "is_dead": False}
    return _Sprite((x, y, 40, 40), **{**base, **fields})


# -- why it was extracted -----------------------------------------------------


def test_level_draws_health_bars_before_it_checks_debug() -> None:
    """The invariant that makes this a production path, asserted on the source.

    Reading the call order rather than running it: the failure this guards is
    someone moving the call below the `if not debug_enabled: return`, which
    would look like a tidy-up and would silently delete the bars from the game.
    """
    source = (UI_DIR.parent / "core/level/level.py").read_text(encoding="utf-8")
    body = source[source.index("    def draw(") :]
    bars = body.index("draw_health_bars")
    gate = body.index("if not debug_enabled")

    assert bars < gate, "the bars must be painted before the debug gate returns"


def test_the_bars_module_does_not_import_the_debug_overlay() -> None:
    """The direction of the dependency, which is the reason it is a module.

    `world_ui` imports the bars (to dodge around them); the bars must not
    import `world_ui`, or the extraction has only moved the cycle.
    """
    tree = ast.parse(BARS_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not any("world_ui" in name for name in imported), sorted(imported)


def test_world_ui_delegates_the_bar_methods_rather_than_reimplementing_them() -> None:
    """Two names, and each is a call. A copy would rot the moment one moved.

    ``has_health_bar`` is deliberately absent: the gate that decides whether a
    sprite gets a bar belongs to the draw pass itself, and relaying it onto the
    facade only left a dead name there once the cards moved to the bars module
    and started calling it directly.
    """
    import inspect

    for name in ("_health_bar_rect", "draw_health_bars"):
        body = inspect.getsource(getattr(world_ui.WorldUI, name))
        assert "return _" in body, f"{name} no longer delegates"
        assert body.count("pygame.draw") == 0, f"{name} grew past a delegation"


# -- behaviour, unchanged by the move ----------------------------------------


def test_the_player_gets_no_world_bar() -> None:
    """Its HP is on the screen HUD; a second bar above it is redundant."""
    assert has_health_bar(_entity(faction="player")) is False
    assert has_health_bar(_entity(faction="enemy")) is True


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"is_dead": True}, False),
        ({"max_health": 0}, False),
        ({"is_dead": True, "faction": "player"}, False),
    ],
)
def test_sprites_that_cannot_be_barred_are_skipped(fields, expected) -> None:
    assert has_health_bar(_entity(**fields)) is expected


def test_a_bar_flips_below_the_entity_near_the_top_of_the_screen() -> None:
    """No room above is not a reason to clip: it moves instead."""
    surface = pygame.Surface((320, 240))
    high = _entity(y=4.0)  # near the top
    screen_rect = pygame.Rect(100, 4, 40, 40)

    bar = health_bar_rect(surface, high, screen_rect)

    assert bar is not None
    assert bar.top > screen_rect.bottom, "it should have flipped below"


def test_a_bar_with_no_room_at_all_is_not_drawn() -> None:
    """Half a bar off the top of the screen is worse than no bar."""
    surface = pygame.Surface((320, 12))
    sprite = _entity(y=0.0)

    assert health_bar_rect(surface, sprite, pygame.Rect(100, 0, 40, 40)) is None


def test_a_bar_is_clamped_inside_the_target() -> None:
    surface = pygame.Surface((320, 240))
    sprite = _entity(x=-5000.0)  # far off the left edge
    screen_rect = pygame.Rect(-5000, 100, 40, 40)

    bar = health_bar_rect(surface, sprite, screen_rect)

    assert bar is not None
    assert bar.left >= 0
    assert bar.right <= surface.get_width()
    assert bar.height == HEALTH_BAR_HEIGHT


@pytest.mark.parametrize(
    ("ratio", "colour"),
    [
        (1.0, Colors.text_ok),
        (0.6, Colors.text_ok),
        (0.4, Colors.text_warn),
        (0.1, Colors.text_crit),
    ],
)
def test_the_health_colour_thresholds(ratio: float, colour: tuple) -> None:
    assert health_colour(100.0 * ratio, 100.0) == colour


def test_drawing_returns_the_rects_it_painted() -> None:
    """A caller reasoning about what the bars covered needs them back."""
    from src.core.rendering.camera import Camera

    surface = pygame.Surface((320, 240))
    camera = Camera()
    camera.begin_frame(1.0)

    rects = draw_health_bars(surface, [_entity()], camera)

    assert len(rects) == 1
    assert surface.get_at(rects[0].center)[:3] != (0, 0, 0), "something was painted"


def test_an_offscreen_entity_is_not_drawn() -> None:
    from src.core.rendering.camera import Camera

    surface = pygame.Surface((320, 240))
    camera = Camera()
    camera.begin_frame(1.0)

    assert draw_health_bars(surface, [_entity(x=9000.0)], camera) == []
