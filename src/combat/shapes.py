from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import pygame

from src.core.settings import Combat as CombatSettings

_EPSILON = CombatSettings.SHAPE_CONTACT_EPSILON_PX
_DEFAULT_SWEEP_ITERATIONS = CombatSettings.SHAPE_SWEEP_MAX_ITERATIONS


class ShapeKind(Enum):
    AABB = "aabb"
    CIRCLE = "circle"
    CAPSULE = "capsule"
    OBB = "obb"


class EasingKind(Enum):
    LINEAR = "linear"
    STEP = "step"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


class AnchorKind(Enum):
    CENTER = "center"
    HIP = "hip"
    CHEST = "chest"
    HAND = "hand"
    WEAPON = "weapon"


@dataclass(frozen=True, slots=True)
class ShapePose:
    kind: ShapeKind
    size: tuple[float, float]
    position: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0

    def __post_init__(self) -> None:
        width, height = self.size
        values = (*self.size, *self.position, self.angle)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Shape values must be finite")
        if self.kind is ShapeKind.AABB:
            if width <= 0.0 or height <= 0.0:
                raise ValueError("AABB dimensions must be strictly positive")
        elif self.kind is ShapeKind.CIRCLE:
            if width <= 0.0 or width != height:
                raise ValueError("Circle size must be a strictly positive diameter twice")
        elif self.kind is ShapeKind.CAPSULE:
            if width < 0.0 or height <= 0.0:
                raise ValueError("Capsule length must be non-negative and diameter positive")
        elif width <= 0.0 or height <= 0.0:
            raise ValueError("OBB dimensions must be strictly positive")


@dataclass(frozen=True, slots=True)
class SweptShape:
    previous: ShapePose | None
    current: ShapePose


@dataclass(frozen=True, slots=True)
class AnchorSpec:
    kind: AnchorKind
    offset: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in self.offset):
            raise ValueError("Anchor offsets must be finite")


def _bounds(aabb: pygame.FRect) -> tuple[float, float, float, float]:
    left, top = float(aabb.left), float(aabb.top)
    right, bottom = float(aabb.right), float(aabb.bottom)
    return min(left, right), min(top, bottom), max(left, right), max(top, bottom)


def aabb_aabb_intersects(first: pygame.FRect, second: pygame.FRect) -> bool:
    first_left, first_top, first_right, first_bottom = _bounds(first)
    second_left, second_top, second_right, second_bottom = _bounds(second)
    return (
        first_right + _EPSILON >= second_left
        and second_right + _EPSILON >= first_left
        and first_bottom + _EPSILON >= second_top
        and second_bottom + _EPSILON >= first_top
    )


def circle_aabb_intersects(circle: ShapePose, aabb: pygame.FRect) -> bool:
    if circle.kind is not ShapeKind.CIRCLE:
        raise ValueError("circle_aabb_intersects requires a circle pose")
    radius = circle.size[0] / 2.0
    center_x, center_y = circle.position
    left, top, right, bottom = _bounds(aabb)
    closest_x = min(max(center_x, left), right)
    closest_y = min(max(center_y, top), bottom)
    return math.hypot(center_x - closest_x, center_y - closest_y) <= radius + _EPSILON


def _segment_intersects_aabb(
    start: tuple[float, float],
    end: tuple[float, float],
    aabb: pygame.FRect,
) -> bool:
    left, top, right, bottom = _bounds(aabb)
    minimum_t = 0.0
    maximum_t = 1.0
    for start_value, end_value, lower, upper in (
        (start[0], end[0], left, right),
        (start[1], end[1], top, bottom),
    ):
        direction = end_value - start_value
        if abs(direction) <= _EPSILON:
            if start_value < lower - _EPSILON or start_value > upper + _EPSILON:
                return False
            continue
        first_t = (lower - start_value) / direction
        second_t = (upper - start_value) / direction
        if first_t > second_t:
            first_t, second_t = second_t, first_t
        minimum_t = max(minimum_t, first_t)
        maximum_t = min(maximum_t, second_t)
        if minimum_t > maximum_t + _EPSILON / max(abs(direction), 1.0):
            return False
    return True


def capsule_aabb_intersects(capsule: ShapePose, aabb: pygame.FRect) -> bool:
    if capsule.kind is not ShapeKind.CAPSULE:
        raise ValueError("capsule_aabb_intersects requires a capsule pose")
    length, diameter = capsule.size
    radius = diameter / 2.0
    radians = math.radians(capsule.angle)
    offset_x = math.cos(radians) * length / 2.0
    offset_y = math.sin(radians) * length / 2.0
    start = (capsule.position[0] - offset_x, capsule.position[1] - offset_y)
    end = (capsule.position[0] + offset_x, capsule.position[1] + offset_y)
    left, top, right, bottom = _bounds(aabb)
    expanded = pygame.FRect(
        left - radius,
        top - radius,
        right - left + diameter,
        bottom - top + diameter,
    )
    return _segment_intersects_aabb(start, end, expanded)


def _obb_axes(angle: float) -> tuple[tuple[float, float], tuple[float, float]]:
    radians = math.radians(angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (cosine, sine), (-sine, cosine)


def _sat_intersects(
    first_position: tuple[float, float],
    first_half_size: tuple[float, float],
    first_axes: tuple[tuple[float, float], tuple[float, float]],
    second_position: tuple[float, float],
    second_half_size: tuple[float, float],
    second_axes: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    center_delta = (
        second_position[0] - first_position[0],
        second_position[1] - first_position[1],
    )
    world_axes = ((1.0, 0.0), (0.0, 1.0))
    for axis in (*world_axes, *first_axes, *second_axes):
        first_radius = (
            abs(first_axes[0][0] * axis[0] + first_axes[0][1] * axis[1]) * first_half_size[0]
            + abs(first_axes[1][0] * axis[0] + first_axes[1][1] * axis[1]) * first_half_size[1]
        )
        second_radius = (
            abs(second_axes[0][0] * axis[0] + second_axes[0][1] * axis[1]) * second_half_size[0]
            + abs(second_axes[1][0] * axis[0] + second_axes[1][1] * axis[1]) * second_half_size[1]
        )
        projection = abs(center_delta[0] * axis[0] + center_delta[1] * axis[1])
        if projection > first_radius + second_radius + _EPSILON:
            return False
    return True


def obb_aabb_intersects(obb: ShapePose, aabb: pygame.FRect) -> bool:
    if obb.kind is not ShapeKind.OBB:
        raise ValueError("obb_aabb_intersects requires an OBB pose")
    left, top, right, bottom = _bounds(aabb)
    aabb_center = ((left + right) / 2.0, (top + bottom) / 2.0)
    aabb_half_size = ((right - left) / 2.0, (bottom - top) / 2.0)
    aabb_axes = ((1.0, 0.0), (0.0, 1.0))
    return _sat_intersects(
        obb.position,
        (obb.size[0] / 2.0, obb.size[1] / 2.0),
        _obb_axes(obb.angle),
        aabb_center,
        aabb_half_size,
        aabb_axes,
    )


def obb_obb_intersects(first: ShapePose, second: ShapePose) -> bool:
    if first.kind is not ShapeKind.OBB or second.kind is not ShapeKind.OBB:
        raise ValueError("obb_obb_intersects requires two OBB poses")
    return _sat_intersects(
        first.position,
        (first.size[0] / 2.0, first.size[1] / 2.0),
        _obb_axes(first.angle),
        second.position,
        (second.size[0] / 2.0, second.size[1] / 2.0),
        _obb_axes(second.angle),
    )


def shape_aabb_intersects(shape: ShapePose, aabb: pygame.FRect) -> bool:
    if shape.kind is ShapeKind.AABB:
        shape_aabb = pygame.FRect(
            shape.position[0] - shape.size[0] / 2.0,
            shape.position[1] - shape.size[1] / 2.0,
            shape.size[0],
            shape.size[1],
        )
        return aabb_aabb_intersects(shape_aabb, aabb)
    if shape.kind is ShapeKind.CIRCLE:
        return circle_aabb_intersects(shape, aabb)
    if shape.kind is ShapeKind.CAPSULE:
        return capsule_aabb_intersects(shape, aabb)
    return obb_aabb_intersects(shape, aabb)


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    direction_x = end[0] - start[0]
    direction_y = end[1] - start[1]
    length_squared = direction_x * direction_x + direction_y * direction_y
    if length_squared <= _EPSILON:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    progress = (
        (point[0] - start[0]) * direction_x + (point[1] - start[1]) * direction_y
    ) / length_squared
    progress = min(1.0, max(0.0, progress))
    closest = (start[0] + direction_x * progress, start[1] + direction_y * progress)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _segment_distance(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> float:
    def orientation(
        a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
    ) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    if (
        orientation(first_start, first_end, second_start)
        * orientation(first_start, first_end, second_end)
        <= 0.0
        and orientation(second_start, second_end, first_start)
        * orientation(second_start, second_end, first_end)
        <= 0.0
    ):
        return 0.0
    return min(
        _point_segment_distance(first_start, second_start, second_end),
        _point_segment_distance(first_end, second_start, second_end),
        _point_segment_distance(second_start, first_start, first_end),
        _point_segment_distance(second_end, first_start, first_end),
    )


def _capsule_segment(capsule: ShapePose) -> tuple[tuple[float, float], tuple[float, float]]:
    length = capsule.size[0]
    radians = math.radians(capsule.angle)
    offset = (math.cos(radians) * length / 2.0, math.sin(radians) * length / 2.0)
    return (
        (capsule.position[0] - offset[0], capsule.position[1] - offset[1]),
        (capsule.position[0] + offset[0], capsule.position[1] + offset[1]),
    )


def shape_shape_intersects(first: ShapePose, second: ShapePose) -> bool:
    if first.kind is ShapeKind.OBB and second.kind is ShapeKind.OBB:
        return obb_obb_intersects(first, second)
    if first.kind is ShapeKind.AABB:
        return shape_aabb_intersects(
            second,
            pygame.FRect(
                first.position[0] - first.size[0] / 2.0,
                first.position[1] - first.size[1] / 2.0,
                first.size[0],
                first.size[1],
            ),
        )
    if second.kind is ShapeKind.AABB:
        return shape_aabb_intersects(
            first,
            pygame.FRect(
                second.position[0] - second.size[0] / 2.0,
                second.position[1] - second.size[1] / 2.0,
                second.size[0],
                second.size[1],
            ),
        )
    if first.kind is ShapeKind.CIRCLE and second.kind is ShapeKind.CIRCLE:
        return (
            math.hypot(
                first.position[0] - second.position[0],
                first.position[1] - second.position[1],
            )
            <= (first.size[0] + second.size[0]) / 2.0 + _EPSILON
        )
    if first.kind is ShapeKind.CIRCLE and second.kind is ShapeKind.CIRCLE:
        return (
            math.hypot(
                first.position[0] - second.position[0],
                first.position[1] - second.position[1],
            )
            <= (first.size[0] + second.size[0]) / 2.0 + _EPSILON
        )
    if first.kind is ShapeKind.CAPSULE and second.kind is ShapeKind.CAPSULE:
        first_start, first_end = _capsule_segment(first)
        second_start, second_end = _capsule_segment(second)
        return _segment_distance(first_start, first_end, second_start, second_end) <= (
            first.size[1] / 2.0 + second.size[1] / 2.0 + _EPSILON
        )
    if first.kind is ShapeKind.CIRCLE or second.kind is ShapeKind.CIRCLE:
        circle = first if first.kind is ShapeKind.CIRCLE else second
        capsule = second if first.kind is ShapeKind.CIRCLE else first
        if capsule.kind is not ShapeKind.CAPSULE:
            return False
        start, end = _capsule_segment(capsule)
        return _point_segment_distance(circle.position, start, end) <= (
            circle.size[0] / 2.0 + capsule.size[1] / 2.0 + _EPSILON
        )
    return False


def swept_shape_shape_intersects(
    first_start: ShapePose,
    first_end: ShapePose,
    second_start: ShapePose,
    second_end: ShapePose,
    *,
    iterations: int = _DEFAULT_SWEEP_ITERATIONS,
) -> bool:
    if first_start.kind is not first_end.kind or second_start.kind is not second_end.kind:
        raise ValueError("Swept poses must use the same shape kind")
    if shape_shape_intersects(first_start, second_start) or shape_shape_intersects(
        first_end, second_end
    ):
        return True
    for index in range(1, iterations):
        progress = index / iterations
        if shape_shape_intersects(
            _interpolated_pose(first_start, first_end, progress),
            _interpolated_pose(second_start, second_end, progress),
        ):
            return True
    return False


def broadphase_aabb(shape: ShapePose) -> pygame.FRect:
    center_x, center_y = shape.position
    if shape.kind is ShapeKind.CIRCLE:
        radius = shape.size[0] / 2.0
        return pygame.FRect(
            center_x - radius,
            center_y - radius,
            shape.size[0],
            shape.size[0],
        )
    if shape.kind is ShapeKind.CAPSULE:
        length, diameter = shape.size
        radians = math.radians(shape.angle)
        radius = diameter / 2.0
        offset_x = abs(math.cos(radians)) * length / 2.0 + radius
        offset_y = abs(math.sin(radians)) * length / 2.0 + radius
        return pygame.FRect(
            center_x - offset_x, center_y - offset_y, offset_x * 2.0, offset_y * 2.0
        )
    if shape.kind is ShapeKind.OBB:
        first_axis, second_axis = _obb_axes(shape.angle)
        half_width = shape.size[0] / 2.0
        half_height = shape.size[1] / 2.0
        offset_x = abs(first_axis[0]) * half_width + abs(second_axis[0]) * half_height
        offset_y = abs(first_axis[1]) * half_width + abs(second_axis[1]) * half_height
        return pygame.FRect(
            center_x - offset_x, center_y - offset_y, offset_x * 2.0, offset_y * 2.0
        )
    return pygame.FRect(
        center_x - shape.size[0] / 2.0,
        center_y - shape.size[1] / 2.0,
        shape.size[0],
        shape.size[1],
    )


def ease(kind: EasingKind, progress: float) -> float:
    if not math.isfinite(progress):
        raise ValueError("Easing progress must be finite")
    clamped = min(1.0, max(0.0, progress))
    if kind is EasingKind.LINEAR:
        return clamped
    if kind is EasingKind.STEP:
        return 0.0 if clamped < 1.0 else 1.0
    if kind is EasingKind.EASE_IN:
        return clamped**3
    if kind is EasingKind.EASE_OUT:
        return 1.0 - (1.0 - clamped) ** 3
    if clamped <= 0.5:
        return 4.0 * clamped**3
    return 1.0 - (-2.0 * clamped + 2.0) ** 3 / 2.0


def interpolate_angle(
    start: float,
    end: float,
    progress: float,
    easing: EasingKind = EasingKind.LINEAR,
) -> float:
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("Angles must be finite")
    if progress <= 0.0:
        return start
    if progress >= 1.0:
        return end
    blend = ease(easing, progress)
    delta = (end - start + 180.0) % 360.0 - 180.0
    return start + delta * blend


def _interpolated_pose(start: ShapePose, end: ShapePose, progress: float) -> ShapePose:
    if start.kind is not end.kind:
        raise ValueError("Swept poses must use the same shape kind")
    width = start.size[0] + (end.size[0] - start.size[0]) * progress
    height = start.size[1] + (end.size[1] - start.size[1]) * progress
    position_x = start.position[0] + (end.position[0] - start.position[0]) * progress
    position_y = start.position[1] + (end.position[1] - start.position[1]) * progress
    return ShapePose(
        start.kind,
        (width, height),
        (position_x, position_y),
        interpolate_angle(start.angle, end.angle, progress),
    )


def swept_intersects_aabb(
    start: ShapePose,
    end: ShapePose,
    hurtbox: pygame.FRect,
    *,
    iterations: int = _DEFAULT_SWEEP_ITERATIONS,
) -> bool:
    if iterations < 2:
        raise ValueError("A swept test requires at least two iterations")
    if start.kind is not end.kind:
        raise ValueError("Swept poses must use the same shape kind")
    displacement = math.hypot(
        end.position[0] - start.position[0],
        end.position[1] - start.position[1],
    )
    if displacement > CombatSettings.SWEEP_MAX_DISPLACEMENT_PX:
        return shape_aabb_intersects(end, hurtbox)
    first_bounds = broadphase_aabb(start)
    second_bounds = broadphase_aabb(end)
    if not aabb_aabb_intersects(first_bounds.union(second_bounds), hurtbox):
        return False
    if shape_aabb_intersects(start, hurtbox) or shape_aabb_intersects(end, hurtbox):
        return True
    for index in range(1, iterations):
        pose = _interpolated_pose(start, end, index / iterations)
        if shape_aabb_intersects(pose, hurtbox):
            return True
    return False
