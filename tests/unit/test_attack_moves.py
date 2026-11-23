"""Which move a press throws: the blade or the body, high or low, and the chains."""

from __future__ import annotations

import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.frame_data import AttackButton, Height, Stance, move_id
from src.core.input.input_actions import InputAction
from src.entities.attack_moves import (
    AIR_STARTERS,
    GROUND_STARTERS,
    SLASHES,
    STAB,
    MoveContext,
    press_for,
    resolve_move,
)
from src.entities.player_input import ATTACK_BUTTONS


def test_two_buttons_each_thrown_high_or_low() -> None:
    assert press_for(InputAction.ATTACK_1, low=False) is AttackButton.SLASH_HIGH
    assert press_for(InputAction.ATTACK_1, low=True) is AttackButton.SLASH_LOW
    assert press_for(InputAction.ATTACK_2, low=False) is AttackButton.BEAT_HIGH
    assert press_for(InputAction.ATTACK_2, low=True) is AttackButton.BEAT_LOW
    assert press_for(InputAction.SHOOT, low=False) is AttackButton.SHOOT
    assert press_for(InputAction.SHOOT, low=True) is AttackButton.SHOOT
    assert press_for(InputAction.SPECIAL_ATTACK, low=False) is None


def test_every_bound_button_is_in_the_press_order() -> None:
    assert ATTACK_BUTTONS == (InputAction.ATTACK_1, InputAction.ATTACK_2, InputAction.SHOOT)


@pytest.mark.parametrize("press", list(AttackButton))
def test_each_press_starts_its_chain_on_the_ground(press: AttackButton) -> None:
    assert resolve_move(press, MoveContext(Stance.GROUND)) == GROUND_STARTERS[press]


@pytest.mark.parametrize("press", list(AttackButton))
def test_in_the_air_the_blade_slashes_and_the_body_dives(press: AttackButton) -> None:
    assert resolve_move(press, MoveContext(Stance.AIR)) == AIR_STARTERS[press]


def test_nothing_comes_off_a_wall() -> None:
    assert all(resolve_move(press, MoveContext(Stance.WALL)) is None for press in AttackButton)


def test_a_low_slash_over_a_downed_foe_is_the_stab() -> None:
    context = MoveContext(Stance.GROUND, downed_in_reach=True)

    assert resolve_move(AttackButton.SLASH_LOW, context) == STAB
    assert resolve_move(AttackButton.SLASH_HIGH, context) == "slash_high_1"


@pytest.mark.parametrize("family", ["slash_high", "slash_low"])
def test_the_slash_chains_are_four_links_and_switch_stance_freely(family: str) -> None:
    for n in range(1, 4):
        running = PLAYER_ATTACKS[move_id(f"{family}_{n}")]
        context = MoveContext(Stance.GROUND, running=running)
        assert resolve_move(AttackButton.SLASH_HIGH, context) == f"slash_high_{n + 1}"
        assert resolve_move(AttackButton.SLASH_LOW, context) == f"slash_low_{n + 1}"
        assert resolve_move(AttackButton.BEAT_HIGH, context) == "punch_1"
        assert resolve_move(AttackButton.BEAT_LOW, context) == "kick_1"
    finisher = PLAYER_ATTACKS[move_id(f"{family}_4")]
    finisher_context = MoveContext(Stance.GROUND, running=finisher)
    # The fourth link ends the blade's chain; the body and the shot still follow it.
    assert finisher.follow_up(AttackButton.SLASH_HIGH) is None
    assert finisher.follow_up(AttackButton.SLASH_LOW) is None
    assert resolve_move(AttackButton.BEAT_HIGH, finisher_context) == "punch_1"
    assert resolve_move(AttackButton.SHOOT, finisher_context) == "shot"


def test_the_slashes_strike_the_height_of_their_stance() -> None:
    for n in range(1, 5):
        assert PLAYER_ATTACKS[move_id(f"slash_high_{n}")].phases[0].hit.height is Height.HIGH
        assert PLAYER_ATTACKS[move_id(f"slash_low_{n}")].phases[0].hit.height is Height.LOW


def test_the_body_breaks_guards_and_stuns_and_the_blade_does_not() -> None:
    for name, definition in PLAYER_ATTACKS.items():
        hit = definition.phases[0].hit
        if name.startswith(("punch", "kick")):
            assert all(phase.hit.unblockable for phase in definition.phases), name
            assert sum(phase.hit.stun for phase in definition.phases) >= 12.0, name
        if name.startswith("slash_"):
            assert not hit.unblockable, name
            assert hit.stun <= 2.0, name


def test_only_the_finishing_moves_execute() -> None:
    executing = {
        name for name, d in PLAYER_ATTACKS.items() if any(p.hit.execute for p in d.phases)
    }

    assert executing == {"stab", "death_blow", "throw"}
    # The first half of the throw is a marker pose: no offensive flags at all.
    marker = PLAYER_ATTACKS[move_id("throw")].phases[0]
    assert marker.hit.damage == 0
    assert not (marker.hit.execute or marker.hit.unblockable or marker.hit.otg_allowed)


def test_the_death_blow_and_the_throw_are_played_out_untouched() -> None:
    assert PLAYER_ATTACKS[move_id("death_blow")].invincible
    assert PLAYER_ATTACKS[move_id("throw")].invincible
    assert not PLAYER_ATTACKS[move_id("slash_high_1")].invincible


def test_the_blade_moves_are_the_ones_that_cost_battery() -> None:
    assert {move_id(f"slash_high_{n}") for n in range(1, 5)} <= SLASHES
    assert move_id("charged_slash") in SLASHES
    assert move_id("punch_1") not in SLASHES
    assert move_id("death_blow") not in SLASHES
