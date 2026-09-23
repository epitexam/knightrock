"""P4.1 reception: one pipeline, four producers, unchanged behaviour.

Every offensive producer now emits :class:`OffensiveBox` records into
:class:`ContactSystem` (broadphase -> narrowphase -> resolve). This module
pins the parity that matters:

- melee: exhaustive and grid-pruned passes agree on counters and damage,
  and the producer still exposes counters/hit-stop for its consumers;
- projectile: shared ``HitResolver``, target memory, single-hit release;
- hazard: configured damage/knockback, no interruption, grid-free overlap;
- contact damage: momentum gate (faster side wins, equal trades, guards).
"""

import pygame
import pytest
from pygame.sprite import Group

from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.combat.knockback import KnockbackConfig
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.contact_system import ContactSystem
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.settings import Combat as CombatSettings
from src.core.sprite_groups import SpriteGroups
from src.entities.projectile import ProjectileConfig
from src.physics.entity_grid import EntityGrid
from src.entities.hurtbox_zones import HurtboxZoneDef
from tests.unit.helpers import entity_at, make_entity
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _hit() -> HitProperties:
    return HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0)))


def test_melee_grid_and_exhaustive_paths_agree() -> None:
    """Melee parity: the unified broadphase prunes nothing that can overlap."""
    results = []
    for use_grid in (False, True):
        attacker = entity_at(
            10.0, faction="A", definition=attack(phase(size=(20.0, 20.0), offset=(0.0, 0.0)))
        )
        target = entity_at(20.0, faction="B")
        attacker.combat.capture_attack_origin()
        assert attacker.combat.start_attack("test")
        attacker.combat.update(1 / 60)
        attacker.combat.sync_attack_box()

        system = CombatSystem()
        if use_grid:
            grid = EntityGrid()
            grid.rebuild([attacker, target])
            system.process_attacks([attacker, target], grid)
        else:
            system.process_attacks([attacker, target])
        results.append(
            (
                system.metrics.pairs_tested,
                system.metrics.overlaps,
                system.metrics.contacts,
                target.health,
            )
        )

    assert results[0] == results[1]


def test_melee_counters_and_hit_stop_are_merged_back() -> None:
    """The producer still exposes counters/hit-stop for its consumers."""
    attacker = entity_at(10.0, faction="A", definition=attack(phase(size=(20.0, 20.0))))
    target = entity_at(20.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()

    system = CombatSystem()
    system.process_attacks([attacker, target])

    assert system.metrics.contacts == 1
    assert system.hit_stop_timer > 0.0
    assert system.contact_system.metrics.contacts == 1


def test_shared_engine_accumulates_tick_metrics_until_begin_tick() -> None:
    """One shared ContactSystem: metrics pile up across producers per tick."""
    engine = ContactSystem()
    engine.begin_tick()
    hazard = HazardDamageSystem(contact_system=engine)
    contact = ContactDamageSystem(contact_system=engine)
    target = _TargetStub(pygame.FRect(10, 10, 40, 40), "player")

    hazard.process([target], [_HazardStub(pygame.FRect(10, 10, 64, 64), damage=25.0)])
    assert engine.metrics.contacts == 1  # last resolve only
    assert engine.tick_metrics.contacts == 1

    a, b = _momentum_pair(600.0, 0.0)
    contact.process(Group(a, b))
    assert engine.metrics.contacts == 1  # contact pass overwrote metrics
    assert engine.tick_metrics.contacts == 2  # tick accumulator kept both

    engine.begin_tick()
    assert engine.tick_metrics.contacts == 0
    assert engine.metrics.contacts == 1  # last-call view survives the reset
    assert engine.zone_contacts == []  # P2.4 accumulator cleared with the tick


def test_zone_index_propagated_to_resolver() -> None:
    """P2.4: melee contact records which zone absorbed the hit."""
    zones = (
        HurtboxZoneDef(name="head", inflate=(0.0, -12.0), mult=1.2),
        HurtboxZoneDef(name="torso", inflate=(0.0, 0.0), mult=1.0),
    )
    attacker = entity_at(
        10.0,
        faction="A",
        definition=attack(
            phase(startup=1, active=8, recovery=1, size=(200.0, 200.0), offset=(40.0, 0.0))
        ),
    )
    target = entity_at(20.0, faction="B", hurtbox_zones=zones)
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()

    system = CombatSystem()
    system.process_attacks([attacker, target])

    contacts = system.contact_system.zone_contacts
    assert len(contacts) == 1
    assert contacts[0].zone_index == 0
    assert contacts[0].zone_mult == pytest.approx(1.2)
    assert contacts[0].kind == "melee"



def test_projectile_parity_with_direct_resolver() -> None:
    """Projectile: same damage as a direct ``HitResolver`` pass."""
    reference = make_entity(pos=(100.0, 100.0), faction="enemy")
    HitResolver.resolve(attacker=reference, target=reference, hit=_hit())
    expected = reference.health

    target = make_entity(pos=(100.0, 100.0), faction="enemy")
    groups = SpriteGroups()
    groups.entity_sprites.add(target)
    groups.all_sprites.add(target)
    engine = ContactSystem()
    system = ProjectileSystem(groups, contact_system=engine)
    system.spawn(
        ProjectileConfig(size=(10.0, 10.0), lifetime=2.0, hit=_hit()),
        pos=(100.0, 100.0),
        velocity=(0.0, 0.0),
        faction="player",
    )

    system.process(1 / 60)

    assert target.health == expected
    assert engine.metrics.contacts == 1
    assert len(groups.projectile_sprites) == 0


def test_projectile_pierce_keeps_flying_but_remembers_targets() -> None:
    """Piercing box keeps flying but still remembers its targets."""
    target = make_entity(pos=(100.0, 100.0), faction="enemy")
    groups = SpriteGroups()
    groups.entity_sprites.add(target)
    groups.all_sprites.add(target)
    system = ProjectileSystem(groups)
    projectile = system.spawn(
        ProjectileConfig(size=(10.0, 10.0), lifetime=2.0, hit=_hit(), pierce=True),
        pos=(100.0, 100.0),
        velocity=(0.0, 0.0),
        faction="player",
    )

    system.process(1 / 60)

    assert target.health == 90.0
    assert projectile.targets_hit == {target.id}
    assert len(groups.projectile_sprites) == 1


class _HazardStub:
    def __init__(self, box: pygame.FRect, damage: float) -> None:
        self.rect = box
        self.damage = damage


class _TargetStub(pygame.sprite.Sprite):
    def __init__(self, box: pygame.FRect, faction: str, speed: float = 0.0) -> None:
        super().__init__()
        self.hitbox = box
        self.velocity = pygame.Vector2(speed, 0.0)
        self.faction = faction
        self.is_dead = False
        self.is_invincible = False
        self.combat = type("CombatStub", (), {"is_hurt": False})()
        self.damage_taken = 0.0

    def receive_damage(self, amount: float = 0.0, **_: object) -> None:
        self.damage_taken += amount


def test_hazard_boxes_route_through_the_shared_engine() -> None:
    """Hazard: configured damage, no interrupt, one contact per overlap."""
    engine = ContactSystem()
    system = HazardDamageSystem(contact_system=engine)
    target = _TargetStub(pygame.FRect(10, 10, 40, 40), "player")
    hazard = _HazardStub(pygame.FRect(10, 10, 64, 64), damage=25.0)

    system.process([target], [hazard])

    assert target.damage_taken == 25.0
    assert engine.metrics.contacts == 1
    assert engine.metrics.overlaps == 1


def test_hazard_outside_its_box_never_contacts() -> None:
    engine = ContactSystem()
    system = HazardDamageSystem(contact_system=engine)
    target = _TargetStub(pygame.FRect(600, 600, 40, 40), "player")

    system.process([target], [_HazardStub(pygame.FRect(10, 10, 64, 64), damage=25.0)])

    assert target.damage_taken == 0.0
    assert engine.metrics.contacts == 0


def _momentum_pair(speed_a: float, speed_b: float) -> tuple[_TargetStub, _TargetStub]:
    a = _TargetStub(pygame.FRect(0, 0, 40, 40), "player", speed=speed_a)
    b = _TargetStub(pygame.FRect(20, 0, 40, 40), "enemy", speed=speed_b)
    return a, b


def test_contact_damage_faster_side_wins() -> None:
    a, b = _momentum_pair(600.0, 0.0)

    ContactDamageSystem().process(Group(a, b))

    assert a.damage_taken == 0.0
    assert b.damage_taken == CombatSettings.CONTACT_DAMAGE_AMOUNT


def test_contact_damage_equal_speeds_trade_both_ways() -> None:
    a, b = _momentum_pair(500.0, 500.0)

    ContactDamageSystem().process(Group(a, b))

    assert a.damage_taken == CombatSettings.CONTACT_DAMAGE_AMOUNT
    assert b.damage_taken == CombatSettings.CONTACT_DAMAGE_AMOUNT


def test_contact_damage_ignores_slow_pair() -> None:
    a, b = _momentum_pair(CombatSettings.CONTACT_DAMAGE_THRESHOLD - 1.0, 0.0)

    ContactDamageSystem().process(Group(a, b))

    assert a.damage_taken == 0.0
    assert b.damage_taken == 0.0


def test_contact_damage_skips_hurt_and_invincible_targets() -> None:
    a, b = _momentum_pair(600.0, 0.0)
    b.combat.is_hurt = True  # already reacting: no re-application

    ContactDamageSystem().process(Group(a, b))

    assert b.damage_taken == 0.0

    c, d = _momentum_pair(600.0, 0.0)
    d.is_invincible = True

    ContactDamageSystem().process(Group(c, d))

    assert d.damage_taken == 0.0

