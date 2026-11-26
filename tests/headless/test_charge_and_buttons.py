"""A charge grows the blow it throws, and the blade and the body are two kinds of blow.

Played on real fighters: the shape a held move strikes with is longer and
reaches farther with the charge, and it hits harder; a full charge keeps the
charge's power on top of its own extras. The blade (X) is quick and long and
pushes little; the body (Y) is slower and shorter, pushes hard, stuns and goes
through guards.
"""

from __future__ import annotations

from src.simulation.combat.attack_data import PLAYER_ATTACKS
from src.simulation.combat.frame_data import move_id
from src.simulation.combat.hitbox_manager import charge_reach_scale
from src.simulation.entities.shots import SHOTS, charged
from src.simulation.settings import Combat
from tests.headless.arena import DT, PLAYER_X, arena, foe, settle

STILL = {"vision_range": 0.0, "chase_speed": 0.0}


def _reach(move: str, charge: float) -> tuple[float, float]:
    """The longest shape and the farthest tip in front, over the move's live frames."""
    level, _pad, player = arena()
    settle(level)
    assert player.combat.start_attack(move_id(move), charge)
    longest = farthest = 0.0
    for _ in range(30):
        level.update(DT)
        for shape in player.combat.attack_shapes:
            longest = max(longest, max(shape.size))
            farthest = max(
                farthest, shape.position[0] + max(shape.size) / 2 - player.hitbox.centerx
            )
        if not player.combat.is_attacking:
            break
    return longest, farthest


def _damage(move: str, charge: float) -> float:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 46.0, guards=False, **STILL)
    settle(level)
    goblin.health = goblin.max_health = 500.0
    assert player.combat.start_attack(move_id(move), charge)
    for _ in range(40):
        level.update(DT)
    return 500.0 - goblin.health


def test_the_charge_scale_is_one_uncharged_and_grows_with_the_charge() -> None:
    assert charge_reach_scale(1.0) == 1.0
    assert charge_reach_scale(2.0) == 1.0 + Combat.CHARGE_REACH_GAIN
    assert charge_reach_scale(1.5) < charge_reach_scale(2.0)


def test_a_charged_cut_is_longer_and_reaches_farther_with_the_charge() -> None:
    low = _reach("charged_slash", 1.0)
    mid = _reach("charged_slash", 1.5)
    high = _reach("charged_slash", 2.0)

    assert low[0] < mid[0] < high[0]
    assert low[1] < mid[1] < high[1]


def test_a_charged_cut_hits_harder_with_the_charge() -> None:
    assert _damage("charged_slash", 1.0) < _damage("charged_slash", 2.0)


def test_a_full_charge_keeps_the_charge_power() -> None:
    """The full tier adds a crescent; it never hits softer than the charge it caps."""
    assert _damage("charged_slash_full", 2.0) >= _damage("charged_slash", 2.0)


def test_a_charged_shot_is_bigger_and_harder() -> None:
    plain, held = SHOTS["bolt"], charged(SHOTS["bolt"], 2.0)

    assert held.config.size[0] > plain.config.size[0]
    assert held.config.hit.damage > plain.config.hit.damage
    assert charged(plain, 1.0) is plain


def test_the_blade_is_quick_and_light_and_the_body_slow_and_heavy() -> None:
    blades = [PLAYER_ATTACKS[move_id(f"slash_high_{n}")] for n in (1, 2)]
    blades += [PLAYER_ATTACKS[move_id(f"slash_low_{n}")] for n in (1, 2)]
    body = [PLAYER_ATTACKS[move_id(name)] for name in ("punch_1", "punch_2", "kick_1")]

    def startup(d):  # type: ignore[no-untyped-def]
        return d.phases[0].startup_frames

    def push(d):  # type: ignore[no-untyped-def]
        return abs(d.phases[0].hit.knockback.power[0]) + abs(d.phases[0].hit.knockback.power[1])

    def freeze(d):  # type: ignore[no-untyped-def]
        return d.phases[0].hit.hit_stop or 0.0

    assert max(map(startup, blades)) < min(map(startup, body))
    assert max(map(push, blades)) < min(map(push, body))
    assert max(map(freeze, blades)) < min(map(freeze, body))
    assert all(d.phases[0].hit.unblockable for d in body)
    assert not any(d.phases[0].hit.unblockable for d in blades)
