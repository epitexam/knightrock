"""HitResolver combined cases and numeric limits."""

import pytest

from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver, _finisher_damage, _juggle_scale, _otg_blocked
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from tests.unit.helpers import make_entity


def _hit(damage: float, **kwargs) -> HitProperties:
    return HitProperties(damage=damage, knockback=KnockbackConfig(power=(0.0, 0.0)), **kwargs)


def test_juggle_scale_floor_and_decay() -> None:
    assert _juggle_scale(0) == pytest.approx(1.0)
    assert _juggle_scale(1) == pytest.approx(1.0 - CombatSettings.JUGGLE_DECAY_STEP)
    assert _juggle_scale(100) == pytest.approx(CombatSettings.JUGGLE_DAMAGE_FLOOR)


def test_otg_admissibility_matrix() -> None:
    assert _otg_blocked(True, 0.5, _hit(10)) is True
    assert _otg_blocked(True, 0.5, _hit(10, otg_allowed=True)) is False
    assert _otg_blocked(True, 0.0, _hit(10)) is False
    assert _otg_blocked(False, 0.5, _hit(10)) is False


def test_charge_juggle_combined_formula() -> None:
    from tests.unit.helpers import make_attack, make_phase

    attacker = make_entity(faction="player", attacks={"p": make_attack(make_phase())})
    for _ in range(2):
        attacker.combat.record_hit_landed(True)
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = False
    expected_scale = 1.0 - 2 * CombatSettings.JUGGLE_DECAY_STEP
    HitResolver.resolve(attacker, target, _hit(10.0, stagger=0.0), charge_multiplier=2.0)
    assert target.health == pytest.approx(100.0 - 10.0 * 2.0 * expected_scale)


def test_finisher_threshold_boundary() -> None:
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = True
    assert _finisher_damage(_hit(10, is_finisher=True), target, 79.0) == 79.0
    assert _finisher_damage(_hit(10, is_finisher=True), target, 80.0) == 100.0


def test_zero_damage_applies_nothing() -> None:
    from tests.unit.helpers import make_attack, make_phase

    attacker = make_entity(faction="player", attacks={"p": make_attack(make_phase())})
    target = make_entity(faction="enemy")
    target.on_surface["floor"] = False
    result = HitResolver.resolve(attacker, target, _hit(0.0, stagger=0.5))
    assert result.applied is False
    assert target.health == 100.0
    assert attacker.combat.air_combo_count == 0


def test_blocked_hit_records_no_combo_no_stagger() -> None:
    from pygame.sprite import Group

    from src.entities.player import Player
    from tests.unit.helpers import InputStub

    player = Player(
        pos=(100.0, 100.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),
    )
    player.state_machine.current_state_name = "block"
    from tests.unit.helpers import AttackerStub

    attacker = AttackerStub(centerx=80.0)
    result = HitResolver.resolve(attacker, player, _hit(10.0, stagger=0.5, is_finisher=True))
    assert result.blocked is True
    assert player.stagger_timer == 0.0
    assert player.combat.is_hurt is False
