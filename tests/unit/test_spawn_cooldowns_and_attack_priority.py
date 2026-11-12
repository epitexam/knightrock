"""Spawner cooldowns and attack priority branches."""

import pytest

from src.core.input.input_actions import InputAction
from src.core.level.systems.spawn_system import SpawnSystem
from src.core.sprite_groups import SpriteGroups
from src.entities.player_input import ATTACK_BUTTONS


def _system() -> SpawnSystem:
    return SpawnSystem(SpriteGroups())


def test_decay_cooldowns_ticks_both_dicts() -> None:
    system = _system()
    system.spawn_cooldowns["goblin"] = 0.5
    system.debug_cooldowns["twin_fangs"] = 0.3
    system._decay_cooldowns(0.2)
    # No clamp to zero: the cooldown is allowed to go negative, and the point
    # of the assertion is that it does. The first version tested the same value
    # twice -- once through a Vector2 roundabout -- so it read as a clamp check
    # while only ever checking one number.
    assert system.spawn_cooldowns["goblin"] == pytest.approx(0.3)
    assert system.debug_cooldowns["twin_fangs"] == pytest.approx(0.1)
    system._decay_cooldowns(1.0)
    assert system.spawn_cooldowns["goblin"] < 0
    assert system.debug_cooldowns["twin_fangs"] < 0


def test_debug_ready_and_arm_roundtrip() -> None:
    system = _system()
    assert system._debug_ready("twin_fangs") is True
    system._arm_debug_cooldown("twin_fangs")
    assert system._debug_ready("twin_fangs") is False


def test_attack_priority_special_first() -> None:
    """A tick can only start one attack, so the button order is the contract.

    Asserted against ``ATTACK_BUTTONS`` rather than by scraping the source of
    ``_handle_attack_request``: the previous version read the order out of the
    method's text, which broke on any reformat and asserted nothing about
    behaviour -- it passed if the branches were ordered one way and merely
    happened to *mention* the moves in that order. The declared list is what the
    method iterates, so this is now the actual claim.
    """
    assert ATTACK_BUTTONS == (
        InputAction.SPECIAL_ATTACK,
        InputAction.ATTACK_1,
        InputAction.ATTACK_2,
        InputAction.ATTACK_3,
        InputAction.ATTACK_4,
    )
