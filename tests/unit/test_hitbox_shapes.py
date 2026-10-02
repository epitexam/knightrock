from dataclasses import FrozenInstanceError

import pygame
import pytest

from src.combat.shapes import (
    AnchorKind,
    AnchorSpec,
    EasingKind,
    ShapeKind,
    ShapePose,
    aabb_aabb_intersects,
    broadphase_aabb,
    capsule_aabb_intersects,
    circle_aabb_intersects,
    ease,
    interpolate_angle,
    obb_aabb_intersects,
    obb_obb_intersects,
    shape_aabb_intersects,
    swept_intersects_aabb,
)
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def test_pose_and_anchor_specs_are_immutable() -> None:
    pose = ShapePose(ShapeKind.CIRCLE, (20.0, 20.0))
    anchor = AnchorSpec(AnchorKind.WEAPON, (4.0, -2.0))

    with pytest.raises(FrozenInstanceError):
        pose.position = (1.0, 1.0)
    with pytest.raises(FrozenInstanceError):
        anchor.offset = (0.0, 0.0)


def test_shape_dimensions_follow_their_conventions() -> None:
    with pytest.raises(ValueError, match="diameter twice"):
        ShapePose(ShapeKind.CIRCLE, (20.0, 10.0))
    with pytest.raises(ValueError, match="length"):
        ShapePose(ShapeKind.CAPSULE, (-1.0, 10.0))
    with pytest.raises(ValueError, match="OBB"):
        ShapePose(ShapeKind.OBB, (20.0, 0.0))


def test_aabb_corners_tangency_and_near_miss() -> None:
    target = pygame.FRect(10.0, 10.0, 20.0, 20.0)

    assert aabb_aabb_intersects(pygame.FRect(20.0, 20.0, 10.0, 10.0), target)
    assert aabb_aabb_intersects(pygame.FRect(0.0, 0.0, 10.0, 10.0), target)
    assert aabb_aabb_intersects(pygame.FRect(-10.0, 10.0, 20.0, 20.0), target)
    assert not aabb_aabb_intersects(pygame.FRect(-10.1, 10.0, 20.0, 20.0), target)


def test_circle_corners_tangency_and_near_miss() -> None:
    target = pygame.FRect(20.0, 20.0, 20.0, 20.0)
    corner_tangent = ShapePose(ShapeKind.CIRCLE, (20.0, 20.0), (13.0, 13.0))
    near_corner = ShapePose(ShapeKind.CIRCLE, (20.0, 20.0), (12.9, 12.9))

    assert circle_aabb_intersects(ShapePose(ShapeKind.CIRCLE, (20.0, 20.0), (20.0, 20.0)), target)
    assert circle_aabb_intersects(corner_tangent, target)
    assert not circle_aabb_intersects(near_corner, target)


def test_oblique_capsule_uses_its_rotated_segment() -> None:
    capsule = ShapePose(ShapeKind.CAPSULE, (20.0, 4.0), (0.0, 0.0), 45.0)
    tangent_target = pygame.FRect(14.8283, -10.0, 4.0, 20.0)
    near_miss_target = pygame.FRect(14.8384271247, -10.0, 4.0, 20.0)
    tangent = ShapePose(ShapeKind.CAPSULE, (20.0, 4.0), (2.8284271247, 0.0))

    assert capsule_aabb_intersects(capsule, pygame.FRect(8.0, 0.0, 4.0, 40.0))
    assert capsule_aabb_intersects(tangent, tangent_target)
    assert not capsule_aabb_intersects(tangent, near_miss_target)


def test_obb_45_degrees_against_aabb() -> None:
    target = pygame.FRect(0.0, 0.0, 10.0, 40.0)
    diamond = ShapePose(ShapeKind.OBB, (16.0, 16.0), (0.0, 0.0), 45.0)
    tangent = ShapePose(ShapeKind.OBB, (16.0, 16.0), (21.313708499, 0.0), 45.0)
    near_miss = ShapePose(ShapeKind.OBB, (16.0, 16.0), (21.323708499, 0.0), 45.0)

    assert obb_aabb_intersects(diamond, target)
    assert obb_aabb_intersects(tangent, target)
    assert not obb_aabb_intersects(near_miss, target)


def test_obb_obb_uses_separating_axes() -> None:
    first = ShapePose(ShapeKind.OBB, (20.0, 4.0), (0.0, 0.0), 45.0)
    overlapping = ShapePose(ShapeKind.OBB, (20.0, 4.0), (6.0, 6.0), -45.0)
    separated_by_obb_axis = ShapePose(ShapeKind.OBB, (4.0, 20.0), (20.0, 0.0), 45.0)

    assert obb_obb_intersects(first, overlapping)
    assert not obb_obb_intersects(first, separated_by_obb_axis)


@pytest.mark.parametrize(
    ("shape", "left"),
    [
        (ShapePose(ShapeKind.AABB, (20.0, 10.0), (20.0, 0.0)), 10.0),
        (ShapePose(ShapeKind.CIRCLE, (10.0, 10.0), (20.0, 0.0)), 15.0),
        (ShapePose(ShapeKind.CAPSULE, (20.0, 6.0), (20.0, 0.0), 90.0), 17.0),
        (ShapePose(ShapeKind.OBB, (20.0, 10.0), (20.0, 0.0), 90.0), 15.0),
    ],
)
def test_broadphase_encloses_rotated_shape(shape: ShapePose, left: float) -> None:
    target = pygame.FRect(left - 0.5, -0.5, 1.0, 1.0)
    assert broadphase_aabb(shape).left == pytest.approx(left)
    assert aabb_aabb_intersects(broadphase_aabb(shape), target)


def test_shape_dispatch_uses_the_source_dimensions() -> None:
    source = ShapePose(ShapeKind.AABB, (20.0, 10.0), (0.0, 0.0))
    target = pygame.FRect(9.0, -2.0, 2.0, 4.0)

    assert shape_aabb_intersects(source, target)
    assert not shape_aabb_intersects(source, pygame.FRect(10.1, -2.0, 2.0, 4.0))


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (EasingKind.LINEAR, 0.5),
        (EasingKind.STEP, 0.0),
        (EasingKind.EASE_IN, 0.125),
        (EasingKind.EASE_OUT, 0.875),
        (EasingKind.EASE_IN_OUT, 0.5),
    ],
)
def test_easings_are_deterministic(kind: EasingKind, expected: float) -> None:
    assert ease(kind, 0.5) == pytest.approx(expected)
    assert ease(kind, 0.5) == ease(kind, 0.5)
    assert ease(kind, -1.0) == 0.0
    assert ease(kind, 2.0) == 1.0


def test_step_switches_at_completion() -> None:
    assert ease(EasingKind.STEP, 0.999999) == 0.0
    assert ease(EasingKind.STEP, 1.0) == 1.0


def test_angle_interpolation_takes_the_shortest_path() -> None:
    assert interpolate_angle(350.0, 10.0, 0.5) == pytest.approx(360.0)
    assert interpolate_angle(350.0, 10.0, 1.0) == pytest.approx(10.0)
    assert interpolate_angle(10.0, 350.0, 0.5) == pytest.approx(0.0)
    assert interpolate_angle(0.0, 90.0, 0.5, EasingKind.EASE_IN_OUT) == pytest.approx(45.0)


def test_static_sweep_finds_a_tunneled_hit_deterministically() -> None:
    start = ShapePose(ShapeKind.CIRCLE, (10.0, 10.0), (-30.0, 0.0))
    end = ShapePose(ShapeKind.CIRCLE, (10.0, 10.0), (30.0, 0.0))
    target = pygame.FRect(-5.0, -5.0, 10.0, 10.0)

    assert not circle_aabb_intersects(start, target)
    assert not circle_aabb_intersects(end, target)
    assert swept_intersects_aabb(start, end, target)
    assert swept_intersects_aabb(start, end, target) == swept_intersects_aabb(start, end, target)


def test_static_sweep_rejects_broadphase_and_invalid_iterations() -> None:
    start = ShapePose(ShapeKind.OBB, (8.0, 8.0), (-20.0, 0.0), 0.0)
    end = ShapePose(ShapeKind.OBB, (8.0, 8.0), (20.0, 0.0), 180.0)
    target = pygame.FRect(0.0, 100.0, 10.0, 10.0)

    assert not swept_intersects_aabb(start, end, target)
    with pytest.raises(ValueError, match="at least two"):
        swept_intersects_aabb(start, end, target, iterations=1)
    with pytest.raises(ValueError, match="same shape kind"):
        swept_intersects_aabb(start, ShapePose(ShapeKind.CIRCLE, (8.0, 8.0), (20.0, 0.0)), target)


def test_broadphase_dimensions_match_capsule_rotation() -> None:
    axis_aligned = broadphase_aabb(ShapePose(ShapeKind.CAPSULE, (20.0, 6.0)))
    vertical = broadphase_aabb(ShapePose(ShapeKind.CAPSULE, (20.0, 6.0), angle=90.0))

    assert axis_aligned.size == pytest.approx((26.0, 6.0))
    assert vertical.size == pytest.approx((6.0, 26.0))
    assert axis_aligned.center == vertical.center == (0.0, 0.0)


def test_the_primary_hitbox_spec_is_built_once_per_phase() -> None:
    """It is read once per box per tick and every field it reads is frozen.

    ``HitboxManager`` rebuilt it on every positioning pass: a ``HitboxSpec``,
    its validator, and the throwaway ``ShapePose`` that validator constructs.
    ``extra_hitboxes`` stored its specs for exactly this reason, and the primary
    was the only one recomputing. Identity is the observable that pins the
    cache -- two equal-but-distinct specs would still be correct, so comparing
    them would pass whether or not the cache exists.
    """
    definition = phase(startup=1, active=2, recovery=1, size=(30.0, 20.0), offset=(20.0, 0.0))
    equal_but_separate = attack(
        phase(startup=1, active=2, recovery=1, size=(30.0, 20.0), offset=(20.0, 0.0))
    ).phases[0]

    assert definition.hitbox_spec == equal_but_separate.hitbox_spec
    assert definition.hitbox_spec is definition.hitbox_spec


def test_a_cached_spec_never_leaks_into_another_phase() -> None:
    """The regression a cache on a frozen dataclass can have and cannot have a
    type checker for.

    ``cached_property`` stores through ``__dict__``, which a frozen dataclass
    forbids via ``__setattr__`` -- so this works because there are no
    ``__slots__``, and it would stop working the day somebody added them. The
    failure mode if the store became shared would be two phases of the same
    attack, or of two different attacks, reporting one box's geometry: a
    player's swing shaped like an enemy's, silently, in data rather than in
    code. So the second phase's box is deliberately a different size.
    """
    definition = phase(startup=1, active=2, recovery=1, size=(30.0, 20.0), offset=(20.0, 0.0))
    other = phase(startup=1, active=2, recovery=1, size=(99.0, 40.0), offset=(-5.0, 3.0))

    assert definition.hitbox_spec.size == (30.0, 20.0)
    assert other.hitbox_spec.size == (99.0, 40.0)
    assert definition.hitbox_spec.offset == (20.0, 0.0)
    assert other.hitbox_spec.offset == (-5.0, 3.0)


def test_the_cached_spec_is_still_validated_when_it_is_first_built() -> None:
    """Caching the result must not cache away the refusal.

    The validator is what rejects a non-positive dimension or a non-finite
    angle, and it runs inside ``HitboxSpec.__post_init__``. Reading the spec is
    now the first thing that triggers it, so a phase carrying bad geometry is
    caught when the box is first positioned rather than at load -- which is
    still before anything is drawn with it.
    """
    with pytest.raises(ValueError, match="strictly positive"):
        _ = phase(startup=1, active=2, recovery=1, size=(0.0, 20.0), offset=(20.0, 0.0)).hitbox_spec
