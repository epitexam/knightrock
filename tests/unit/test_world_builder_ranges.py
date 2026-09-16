"""Tiled rectangles are travel ranges, not sprites.

Moving platforms (`helicopter`/`boat`) and span hazards (`saw`) must launch
centred inside their Tiled rectangle and patrol its full extent back and
forth at the object's 'speed' property — the rectangle itself is the range,
not the element (they used to be built as large sprites sliding a few px).
"""

import pygame
import pytest

from src.core.level.level_data import ObjectData
from src.core.level.world_builder import (
    _build_moving_platform,
    _build_span_hazard,
    _explicit_waypoints,
    _rect_path,
)
from src.core.settings import World
from src.core.sprite_groups import SpriteGroups


def make_obj(name: str, x: float, y: float, w: float, h: float, **props) -> ObjectData:
    return ObjectData(
        name=name, x=x, y=y, width=w, height=h, gid=None, image=None, points=None, properties=props
    )


def test_rect_path_follows_the_rectangle_centre_line() -> None:
    start, end = _rect_path(make_obj("boat", 1000.0, 500.0, 400.0, 40.0))

    assert (start.x, start.y) == (1000.0, 520.0)
    assert (end.x, end.y) == (1400.0, 520.0)


def test_rect_path_is_vertical_for_tall_rectangles() -> None:
    start, end = _rect_path(make_obj("helicopter", 100.0, 200.0, 10.0, 320.0))

    assert (start.x, start.y) == (105.0, 200.0)
    assert (end.x, end.y) == (105.0, 520.0)


def test_explicit_waypoints_take_priority_over_the_rectangle() -> None:
    obj = make_obj("boat", 0.0, 0.0, 400.0, 40.0, waypoints="10,20;110,20")
    assert _explicit_waypoints(obj) == [(10.0, 20.0), (110.0, 20.0)]

    obj.points = [(5.0, 5.0), (45.0, 5.0)]
    assert _explicit_waypoints(obj) == [(5.0, 5.0), (45.0, 5.0)]

    obj.points = None
    obj.properties = {"end_x": "300"}
    assert _explicit_waypoints(obj) == [(0.0, 0.0), (300.0, 0.0)]


def test_explicit_waypoints_are_none_for_plain_rectangles() -> None:
    assert _explicit_waypoints(make_obj("boat", 0.0, 0.0, 400.0, 40.0)) is None


def test_moving_platform_launches_centred_and_patrols_the_full_range() -> None:
    groups = SpriteGroups()
    _build_moving_platform(make_obj("boat", 1000.0, 500.0, 400.0, 40.0, speed=120.0), groups)

    (platform,) = groups.moving_platforms.sprites()
    # Small pad (2 tiles x half tile), launched at the rectangle's centre.
    assert platform.rect.size == (World.TILE_SIZE * 2, World.TILE_SIZE // 2)
    assert platform.rect.center == (1200.0, 520.0)
    # The pad's *centre* travels from edge to edge of the rectangle.
    assert platform.waypoints == [(936.0, 504.0), (1336.0, 504.0)]


def test_moving_platform_size_is_configurable_per_object() -> None:
    groups = SpriteGroups()
    _build_moving_platform(
        make_obj("boat", 0.0, 0.0, 400.0, 40.0, platform_width=200, platform_height=40),
        groups,
    )

    (platform,) = groups.moving_platforms.sprites()
    assert platform.rect.size == (200.0, 40.0)


def test_moving_platform_keeps_authored_waypoints_when_present() -> None:
    groups = SpriteGroups()
    obj = make_obj("boat", 0.0, 0.0, 400.0, 40.0, waypoints="10,10;210,10")
    _build_moving_platform(obj, groups)

    (platform,) = groups.moving_platforms.sprites()
    assert platform.waypoints == [(10.0, 10.0), (210.0, 10.0)]


class _FakeAnimator:
    """Animator stub exposing only what SpanHazard's builder needs."""

    frame_size = (76, 76)

    def update(self, delta_time: float) -> None:
        return None

    def surface(self, size, facing_right: bool):
        return None


def test_span_hazard_launches_centred_and_sweeps_the_full_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.core.level.world_builder.build_hazard_animator",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError),
    )
    groups = SpriteGroups()
    _build_span_hazard(make_obj("saw", 2000.0, 800.0, 300.0, 10.0, speed=150.0), groups)

    (hazard,) = groups.hazard_sprites.sprites()
    # No animator in this test: falls back to a one-tile saw sprite.
    assert hazard.rect.size == (World.TILE_SIZE, World.TILE_SIZE)
    assert hazard.rect.center == (2150.0, 805.0)
    assert hazard.progress == 0.5
    assert hazard.speed == 150.0

    centre_x = [hazard.rect.centerx]
    for _ in range(700):  # 300 px at 150 px/s each way: past both ends.
        hazard.update(1 / 60)
        centre_x.append(hazard.rect.centerx)

    assert max(centre_x) == pytest.approx(2300.0, abs=2.0)
    assert min(centre_x) == pytest.approx(2000.0, abs=2.0)


def test_span_hazard_uses_the_animation_natural_frame_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.core.level.world_builder.build_hazard_animator", lambda *a, **k: _FakeAnimator()
    )
    groups = SpriteGroups()
    _build_span_hazard(make_obj("saw", 0.0, 0.0, 300.0, 10.0), groups)

    (hazard,) = groups.hazard_sprites.sprites()
    assert hazard.rect.size == (76, 76)
    assert hazard.rect.center == (150.0, 5.0)


def test_span_hazard_size_property_overrides_the_frame_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.core.level.world_builder.build_hazard_animator", lambda *a, **k: _FakeAnimator()
    )
    groups = SpriteGroups()
    _build_span_hazard(make_obj("saw", 0.0, 0.0, 300.0, 10.0, size=32), groups)

    (hazard,) = groups.hazard_sprites.sprites()
    assert hazard.rect.size == (32, 32)


def test_static_hazard_keeps_its_placed_rect() -> None:
    """Immobile hazards (no span) are unaffected by the range semantics."""
    from src.core.hazards import SpanHazard

    surf = pygame.Surface((64, 32))
    hazard = SpanHazard((10.0, 20.0), surf, 0.0, False)

    assert hazard.rect.topleft == (10.0, 20.0)
    assert hazard.progress == 0.0
    hazard.update(1 / 60)
    assert hazard.rect.topleft == (10.0, 20.0)
