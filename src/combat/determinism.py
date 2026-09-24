"""Canonical geometry checksums for rollback desynchronization detection."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable

import pygame

from src.combat.shapes import ShapePose
from src.core.settings import Combat

__all__ = ["GeometryDesyncError", "geometry_checksum"]


class GeometryDesyncError(RuntimeError):
    """Raised when geometry restored from a snapshot differs from its checksum."""


def geometry_checksum(
    rects: Iterable[pygame.Rect | pygame.FRect],
    shapes: Iterable[ShapePose] = (),
) -> str:
    """Return a stable digest of ordered rectangles and advanced shapes."""
    digest = hashlib.sha256()
    boxes = tuple(rects)
    shape_list = tuple(shapes)
    digest.update(struct.pack("<QQ", len(boxes), len(shape_list)))
    quantum = Combat.GEOMETRY_CHECKSUM_QUANTUM
    for rect in boxes:
        values = (rect.x, rect.y, rect.width, rect.height)
        digest.update(struct.pack("<qqqq", *(round(value / quantum) for value in values)))
    for shape in shape_list:
        shape_values: tuple[float, ...] = (*shape.position, *shape.size, shape.angle)
        digest.update(
            struct.pack(
                "<Bddddd",
                shape.kind.value.encode()[0],
                *(round(value / quantum) for value in shape_values),
            )
        )
    return digest.hexdigest()
