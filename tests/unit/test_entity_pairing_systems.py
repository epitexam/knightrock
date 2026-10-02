"""Entity-pairing systems (contact damage, separation) keep working.

Regression guard for the PERF-02 integration: the environment spatial hash
buckets tiles/platforms, NOT entities, so these systems must never filter
their candidates through it — doing so silently disabled contact damage,
separation, and combat (every candidate list came back empty).
"""

import pygame
import pytest

from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.separation_system import SeparationSystem
from src.core.settings import Combat as CombatSettings


class PairEntity(pygame.sprite.Sprite):
    """Minimal entity stub for the pairing systems."""

    def __init__(self, x: float, faction: str, speed: float = 500.0):
        super().__init__()
        self.hitbox = pygame.FRect(x, 0, 40, 40)
        self.velocity = pygame.Vector2(speed, 0)
        self.faction = faction
        self.is_dead = False
        self.pushable = True
        self.on_surface = {"floor": True, "left": False, "right": False}
        self.combat = type("CombatStub", (), {"is_hurt": False})()
        self.damage_taken = 0.0

    def receive_damage(self, amount: float = 0.0, **_) -> None:
        self.damage_taken += amount

    def sync_rects(self) -> None:  # separation calls it after pushing
        pass


def test_contact_damage_applies_to_fast_overlapping_pair():
    a, b = PairEntity(0, "player"), PairEntity(20, "enemy")

    ContactDamageSystem().process(pygame.sprite.Group(a, b))

    assert a.damage_taken == CombatSettings.CONTACT_DAMAGE_AMOUNT
    assert b.damage_taken == CombatSettings.CONTACT_DAMAGE_AMOUNT


def test_contact_damage_ignores_slow_pair():
    # The momentum threshold is covered in test_contact_unified.py; this file
    # only needs the pair to be below it, which two zero-speed entities are.
    a, b = PairEntity(0, "player", speed=0.0), PairEntity(20, "enemy", speed=0.0)

    ContactDamageSystem().process(pygame.sprite.Group(a, b))

    assert a.damage_taken == 0.0
    assert b.damage_taken == 0.0


def test_contact_damage_ignores_same_faction_pair():
    a, b = PairEntity(0, "player"), PairEntity(20, "player")

    ContactDamageSystem().process(pygame.sprite.Group(a, b))

    assert a.damage_taken == 0.0
    assert b.damage_taken == 0.0


def test_contact_damage_skips_dead_entities():
    a, b = PairEntity(0, "player"), PairEntity(20, "enemy")
    a.is_dead = True

    ContactDamageSystem().process(pygame.sprite.Group(a, b))

    assert a.damage_taken == 0.0
    assert b.damage_taken == 0.0


def test_separation_pushes_overlapping_entities_apart():
    a, b = PairEntity(0, "player", speed=0.0), PairEntity(20, "enemy", speed=0.0)

    SeparationSystem().process(pygame.sprite.Group(a, b))

    assert a.hitbox.x < 10.0 and b.hitbox.x > 10.0
    # Horizontal separation zeroes the horizontal velocity.
    assert a.velocity.x == 0.0 and b.velocity.x == 0.0


def test_separation_reports_exactly_the_entities_it_displaced():
    """The gameplay loop re-syncs the attack boxes of what this returns.

    An attack box is positioned from the hitbox, and ``sync_rects`` does not
    know about it -- so a fighter pushed here has to have its box repaired
    before ``process_attacks`` reads it. The loop used to repair every
    combatant every tick to cover this; narrowing it to the return value is
    only safe while the return value is honest about who moved.

    Both halves are asserted. Returning too many costs the saving; returning
    too few is the bug that matters, and it is a fighter whose swing is drawn
    one frame behind where its owner actually is.
    """
    a, b, bystander = (
        PairEntity(0, "player", speed=0.0),
        PairEntity(20, "enemy", speed=0.0),
        PairEntity(400, "enemy", speed=0.0),
    )

    moved = SeparationSystem().process(pygame.sprite.Group(a, b, bystander))

    assert sorted(id(e) for e in moved) == sorted([id(a), id(b)])
    assert bystander not in moved, "a fighter nobody touched was reported as moved"


def test_separation_reports_nobody_when_nobody_overlaps():
    """The common tick, and the one the whole saving rests on.

    Standing near somebody is not overlapping somebody: the grid offers
    candidates, and the hitbox test is what rejects them. A system that reported
    its candidates instead of its displacements would make this non-empty and
    put the cost straight back where it started.
    """
    a, b = PairEntity(0, "player", speed=0.0), PairEntity(200, "enemy", speed=0.0)

    assert SeparationSystem().process(pygame.sprite.Group(a, b)) == []


def test_separation_reports_one_entity_when_only_one_is_pushable():
    """The asymmetric case, where the immovable one must not be listed.

    A wall-like entity is `pushable=False` and absorbs the whole displacement.
    Reporting it anyway would re-sync an attack box that did not move, which
    is the harmless half -- but reporting *only* it would skip the one that
    did, so the pair is checked in both directions.
    """
    a, b = PairEntity(0, "player", speed=0.0), PairEntity(20, "enemy", speed=0.0)
    b.pushable = False
    before_x, before_y = b.hitbox.x, b.hitbox.y

    moved = SeparationSystem().process(pygame.sprite.Group(a, b))

    assert moved == [a]
    assert (b.hitbox.x, b.hitbox.y) == (before_x, before_y)


def test_separation_reports_each_entity_once_however_many_pairs_moved_it():
    """One entity in a crowd is pushed once per pair; it is synced once.

    The list is deduplicated, so a fighter boxed in by three enemies does not
    get its attack box positioned three times -- which is the same cost the
    unconditional loop used to pay, reintroduced for the crowded case.
    """
    middle = PairEntity(100, "enemy", speed=0.0)
    crowd = [PairEntity(100 + offset, "enemy", speed=0.0) for offset in (-25, 25, 60)]

    moved = SeparationSystem().process(pygame.sprite.Group(middle, *crowd))

    assert moved.count(middle) == 1


# -- the per-entity box cache -------------------------------------------------
#
# Same contract as the hazard cache, and the same reasons: the contact hit
# properties are constants of the rule, and only the geometry and the gate's
# speed change per tick.


def test_contact_boxes_are_reused_across_ticks():
    system = ContactDamageSystem()
    entity = PairEntity(0, "player")

    first = system.produce_boxes([entity])[0]
    second = system.produce_boxes([entity])[0]

    assert first is second


def test_every_contact_box_shares_one_hit_properties():
    """Damage and knockback are constants of the rule, not of the entity."""
    system = ContactDamageSystem()
    entities = [PairEntity(0, "player"), PairEntity(20, "enemy")]

    boxes = system.produce_boxes(entities)

    assert boxes[0].hit is boxes[1].hit
    assert boxes[0].hit.damage == CombatSettings.CONTACT_DAMAGE_AMOUNT


def test_a_reused_contact_gate_tracks_the_entity_speed():
    """The gate carries the source speed; a cached one must not keep the first."""
    system = ContactDamageSystem()
    entity = PairEntity(0, "player", speed=500.0)
    system.produce_boxes([entity])

    entity.velocity.update(-900.0, 0.0)
    box = system.produce_boxes([entity])[0]

    assert box.accept.speed == pytest.approx(900.0)


def test_the_contact_cache_releases_an_entity_that_left():
    system = ContactDamageSystem()
    kept, gone = PairEntity(0, "player"), PairEntity(20, "enemy")
    system.produce_boxes([kept, gone])

    remaining = system.produce_boxes([kept])

    assert len(remaining) == 1
    assert len(system._boxes) == 1
