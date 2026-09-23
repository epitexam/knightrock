"""P2 reception: push / hurt / hit + multi-hurtbox (hitbox_amelioration.md).

- zone 0 (defaut legacy) : contact byte-identique au pipeline mono-box.
- tete x1.2 : `hurtbox_mult` localise via le resolver `zone_mult`.
- jambes taguees : matcher `_zone_vulnerable` unitaire (aucun coup ne
  porte de tags en P2, donc aucun E2E jambes-invulnees ici — P3t1).
- squish dash : la pushbox mutee n'elargit pas la vulnerabilite.
- zones swept : un dodge rate en discret touche en swept (P1 x P2).
"""

import pytest

from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.combat.knockback import KnockbackConfig
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.contact_system import _zone_vulnerable
from src.entities.hurtbox_zones import HurtboxZoneDef
from tests.unit.helpers import AttackerStub, entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _zones() -> tuple[HurtboxZoneDef, ...]:
    # 40x40 pushbox (helpers default size): zones are horizontal bands —
    # head is the short upper band, torso the full height, legs a short
    # lower band. Distinct heights so the head-vs-body split is geometric,
    # not just a multiplier.
    return (
        HurtboxZoneDef(name="head", inflate=(0.0, -12.0), mult=1.2),
        HurtboxZoneDef(name="torso", inflate=(0.0, 0.0), mult=1.0),
        HurtboxZoneDef(name="legs", inflate=(0.0, -12.0), mult=1.0, tags=("low_crush",)),
    )


def _hit(damage: float = 10.0) -> HitProperties:
    return HitProperties(
        damage=damage,
        knockback=KnockbackConfig(power=(0.0, 0.0)),
    )


def test_legacy_single_zone_contact_unchanged() -> None:
    """Zone 0 par defaut : meme contact que le pipeline mono-box P1."""
    attacker = entity_at(
        10.0,
        faction="A",
        definition=attack(phase(startup=1, active=8, recovery=1, size=(20.0, 20.0))),
    )
    target = entity_at(20.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()

    system = CombatSystem()
    system.process_attacks([attacker, target])

    assert system.metrics.contacts == 1


def test_head_zone_applies_localized_mult() -> None:
    """La tete (mult 1.2) scale les degats, pas le reste du corps."""
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    target.sync_rects()
    # Union legacy = englobe les 3 zones ; la tete (bandeau court) est
    # strictement plus petite que le torse pleine hauteur.
    head, torso, _legs = target.hurtboxes
    attacker = AttackerStub()

    base = HitResolver.resolve(attacker, target, _hit(10.0), zone_mult=1.0)
    target.health = target.max_health
    zoned = HitResolver.resolve(attacker, target, _hit(10.0), zone_mult=target.hurtbox_mult[0])

    assert head.h < torso.h
    assert head.h == pytest.approx(torso.h - 12.0)
    assert zoned.actual_damage == pytest.approx(base.actual_damage * 1.2)


def test_zone_vulnerable_matcher_unit() -> None:
    """Jambes taguees immunisees contre un coup portant le tag (P3t1)."""
    assert _zone_vulnerable(("low_crush",), ("low_crush",)) is False
    assert _zone_vulnerable(("low_crush",), ()) is True
    assert _zone_vulnerable((), ("low_crush",)) is True


def test_squish_dash_does_not_add_zones() -> None:
    """Squish : pushbox mutee puis re-derivee — meme zones, meme mults."""
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    target.sync_rects()
    # Dash squish mock: elargit/retrecit la pushbox puis restore + re-derive,
    # comme `apply_squish`/`restore_hitbox` autour de `sync_rects`.
    target.hitbox.inflate_ip(8.0, -10.0)
    target.sync_rects()
    target.hitbox.inflate_ip(-8.0, 10.0)
    target.sync_rects()

    assert len(target.hurtboxes) == 3
    assert target.hurtbox_mult == (1.2, 1.0, 1.0)
    assert target.hurtbox_tags[2] == ("low_crush",)


def test_swept_zones_catch_dodge_between_syncs() -> None:
    """Cible esquivant entre deux syncs : ratee en discret, touchee en swept."""
    attacker = entity_at(
        10.0,
        faction="A",
        definition=attack(phase(startup=1, active=8, recovery=1, size=(20.0, 20.0))),
    )
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    attacker.combat.capture_attack_origin()
    target.capture_sweep_origin()
    target.sync_rects()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()
    attack_box = attacker.combat.attack_boxes[0].copy()

    # Dodge vertical de 30px (hors plan horizontal du coup, au-dela du
    # seuil MIN 4px, sous le plafond MAX 64px) : ni prev ni cur ne
    # touchent la box...
    target.hitbox.y -= 30.0
    target.sync_rects()
    assert not any(attack_box.colliderect(zone) for zone in target.hurtboxes)
    # ...mais le swept couvre le segment balaye : contact.
    system = CombatSystem()
    system.process_attacks([attacker, target])
    assert system.metrics.contacts == 1


def test_first_vulnerable_zone_wins_candidate() -> None:
    """Contact multi-zones : la premiere zone touchee non invulnerable gagne."""
    attacker = entity_at(
        10.0,
        faction="A",
        definition=attack(
            phase(startup=1, active=8, recovery=1, size=(200.0, 200.0), offset=(40.0, 0.0))
        ),
    )
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()
    health_before = target.health

    system = CombatSystem()
    system.process_attacks([attacker, target])

    # Zone 0 (head, mult 1.2) is touched first: its multiplier lands, not
    # the torso's. Every zone overlaps here, so the order is what decides.
    assert system.metrics.overlaps == 1
    assert system.metrics.contacts == 1
    assert health_before - target.health == pytest.approx(10.0 * 1.2)
    # P2.4: the absorbing zone is remembered for dump/debug, not just applied.
    zone_contacts = system.contact_system.zone_contacts
    assert len(zone_contacts) == 1
    assert zone_contacts[0].zone_index == 0
    assert zone_contacts[0].zone_mult == pytest.approx(1.2)
    assert zone_contacts[0].target_id == target.id


def test_hurtbox_singular_is_union_of_zones() -> None:
    """Legacy view: ``hurtbox`` covers every zone, not only zone 0."""
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    target.sync_rects()
    union = target.hurtbox
    for zone in target.hurtboxes:
        assert union.contains(zone)
    # Legacy single-zone path stays exact: union == the only zone.
    legacy = entity_at(40.0, faction="B")
    assert legacy.hurtbox == legacy.hurtboxes[0]


def test_zone_names_exposed_for_debug_overlay() -> None:
    """Named zones surface on the entity so the overlay can list them."""
    target = entity_at(20.0, faction="B", hurtbox_zones=_zones())
    assert target.hurtbox_zone_names == ("head", "torso", "legs")
    # Legacy unnamed zone: no roster row (mult 1.0, empty name).
    assert target.hurtbox_mult == (1.2, 1.0, 1.0)
