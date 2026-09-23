"""Canonical geometry checksums for rollback desynchronization detection."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable

import pygame

from src.core.settings import Combat

__all__ = ["GeometryDesyncError", "geometry_checksum"]


class GeometryDesyncError(RuntimeError):
    """Raised when geometry restored from a snapshot differs from its checksum."""


def geometry_checksum(rects: Iterable[pygame.Rect | pygame.FRect]) -> str:
    """Return a stable SHA-256 digest of ordered quantized rectangles."""
    digest = hashlib.sha256()
    boxes = tuple(rects)
    digest.update(struct.pack("<Q", len(boxes)))
    quantum = Combat.GEOMETRY_CHECKSUM_QUANTUM
    for rect in boxes:
        values = (rect.x, rect.y, rect.width, rect.height)
        digest.update(struct.pack("<qqqq", *(round(value / quantum) for value in values)))
    return digest.hexdigest()
