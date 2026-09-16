"""Juggle / hit-stun avancé tests (audit Phase 5 #4)."""

from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.data.attacks import attack_definition_to_dict, read_attack_definition
from tests.unit.helpers import make_active_attacker, make_entity


def _hit(damage: float, **kwargs) -> HitProperties:
    return HitProperties(
        damage=damage,
        knockback=KnockbackConfig(power=(0.0, 0.0)),
        **kwargs,
    )


def test_hitstun_scales_with_damage() -> None:
    light_target = make_entity(faction="enemy")
    heavy_target = make_entity(faction="enemy")
    attacker = make_active_attacker(light_target)

    HitResolver.resolve(attacker, light_target, _hit(5.0, stagger=0.1))
    HitResolver.resolve(attacker, heavy_target, _hit(30.0, stagger=0.1))

    assert heavy_target.stagger_timer > light_target.stagger_timer
    assert light_target.stagger_timer == 0.1 + 5.0 * CombatSettings.HITSTUN_DAMAGE_FACTOR


def test_airborne_hit_applies_juggle_gravity() -> None:
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = False
    attacker = make_active_attacker(target)

    HitResolver.resolve(attacker, target, _hit(10.0, stagger=0.1, juggle_gravity_mult=0.5))

    assert target.gravity_scale == 0.5
    assert target.juggle_timer == CombatSettings.JUGGLE_GRAVITY_TIME


def test_grounded_hit_leaves_gravity_untouched() -> None:
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = True
    attacker = make_active_attacker(target)

    HitResolver.resolve(attacker, target, _hit(10.0, stagger=0.1, juggle_gravity_mult=0.5))

    assert target.gravity_scale == 1.0
    assert target.juggle_timer == 0.0


def test_otg_window_blocks_non_otg_hits() -> None:
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = True
    target.otg_timer = CombatSettings.OTG_INVULN_DURATION
    attacker = make_active_attacker(target)

    blocked = HitResolver.resolve(attacker, target, _hit(10.0, stagger=0.1))
    assert not blocked.applied
    assert target.health == 100.0

    allowed = HitResolver.resolve(attacker, target, _hit(10.0, stagger=0.1, otg_allowed=True))
    assert allowed.applied
    assert target.health == 90.0


def test_air_combo_counts_only_airborne_hits() -> None:
    from tests.unit.helpers import make_attack, make_phase

    definition = make_attack(make_phase())
    attacker = make_entity(faction="player", attacks={"punch": definition})
    ground_target = make_entity(faction="enemy")
    ground_target.on_surface["floor"] = True
    air_target = make_entity(faction="enemy")
    air_target.on_surface["floor"] = False

    HitResolver.resolve(attacker, ground_target, _hit(10.0, stagger=0.1))
    assert attacker.combat.air_combo_count == 0

    HitResolver.resolve(attacker, air_target, _hit(10.0, stagger=0.1))
    assert attacker.combat.air_combo_count == 1


def test_landing_from_juggle_grants_otg_and_clears_gravity() -> None:
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = False
    target.stagger_timer = 0.3
    target.set_juggle(0.5, 0.4)

    target.on_surface["floor"] = True
    target._tick_juggle(1 / 60, was_grounded=False)

    assert target.otg_timer == CombatSettings.OTG_INVULN_DURATION
    assert target.gravity_scale == 1.0
    assert target.juggle_timer == 0.0


def test_juggle_json_roundtrip() -> None:
    raw = {
        "phases": [
            {
                "startup_frames": 3,
                "active_frames": 4,
                "recovery_frames": 3,
                "hitbox_size": [40.0, 20.0],
                "hitbox_offset": [20.0, 0.0],
                "hit": {
                    "damage": 12,
                    "knockback": {"power": [100.0, -100.0], "mode": "from_attacker"},
                    "damage_type": "slash",
                    "stagger": 0.2,
                    "juggle_gravity_mult": 0.6,
                    "otg_allowed": True,
                },
            }
        ],
        "cooldown": 0.5,
    }
    definition = read_attack_definition(raw, "test.juggle")
    hit = definition.phases[0].hit
    assert hit.juggle_gravity_mult == 0.6
    assert hit.otg_allowed is True

    back = attack_definition_to_dict(definition)["phases"][0]["hit"]
    assert back["juggle_gravity_mult"] == 0.6
    assert back["otg_allowed"] is True
