"""Entity-pairing systems (contact damage, separation) keep working.

Regression guard for the PERF-02 integration: the environment spatial hash
buckets tiles/platforms, NOT entities, so these systems must never filter
their candidates through it — doing so silently disabled contact damage,
separation, and combat (every candidate list came back empty).
"""

import pygame

from src.core.settings import Combat as CombatSettings
from src.physics.contact_damage import ContactDamageSystem
from src.physics.separation import SeparationSystem


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