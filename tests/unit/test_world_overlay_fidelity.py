"""The debug overlay must draw what the contact pipeline actually tests.

The layout goldens pin where annotations go, but they are built from fakes, so
they cannot catch a layer that silently drops geometry from a real entity.
These two cases cover the gaps the fakes hid: a property returning a tuple was
read as if it were a method, and a zone equal to the collider was drawn twice.
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame

from src.ui.world_overlay_geo import GeoLayer
from tests.unit.helpers import activate, make_attack, make_entity, make_phase


def test_sweep_ghosts_are_read_from_a_real_combat_property() -> None:
    entity = make_entity(attacks={"test": make_attack(make_phase())})
    activate(entity)
    boxes = entity.combat.attack_boxes
    assert boxes, "the entity actually has a live attack box"

    ghosts = GeoLayer.swept_boxes(entity.combat, len(boxes))

    assert len(ghosts) == len(boxes)
    assert all(ghost is not None for ghost in ghosts)


def test_zone_index_alignment_survives_a_zone_equal_to_the_collider() -> None:
    collider = pygame.FRect(0.0, 0.0, 40.0, 56.0)
    head = pygame.FRect(collider)
    sprite = SimpleNamespace(hurtboxes=(head, pygame.FRect(0.0, 0.0, 40.0, 16.0)))

    # The redundant zone keeps its slot: dropping it would move the head's
    # damage multiplier and tags onto the second zone.
    assert GeoLayer.hurtbox_zones(sprite) == sprite.hurtboxes
