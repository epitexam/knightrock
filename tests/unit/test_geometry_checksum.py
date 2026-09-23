"""Determinism checks for canonical combat geometry."""

import pygame

from src.combat.determinism import geometry_checksum


def test_geometry_checksum_is_stable_and_order_sensitive() -> None:
    boxes = (pygame.FRect(0, 0, 10, 20), pygame.FRect(30, 4, 12, 8))
    assert geometry_checksum(boxes) == geometry_checksum(boxes)
    assert geometry_checksum(boxes) != geometry_checksum(tuple(reversed(boxes)))


def test_geometry_checksum_quantizes_small_differences() -> None:
    first = (pygame.FRect(0, 0, 10, 20),)
    second = (pygame.FRect(0.0001, 0, 10, 20),)
    assert geometry_checksum(first) == geometry_checksum(second)
