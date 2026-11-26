"""The combat component is resolved from the dense row when bound."""

import os

import pygame
import pytest

from tests.headless.arena import arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_bound_fighters_resolve_combat_from_the_row() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.combat_slot
    assert slot is not None

    assert player.combat is level.combat_table.combat_of(slot)
    assert player.combat is player._combat


def test_rebinding_the_component_updates_the_row() -> None:
    from src.simulation.combat.null_combat import NullCombatComponent

    level, _pad, player = arena()
    settle(level)
    slot = player.combat_slot
    assert slot is not None

    replacement = NullCombatComponent()
    player.combat = replacement

    assert level.combat_table.combat_of(slot) is replacement
    assert player.combat is replacement


def test_a_rewind_keeps_the_combat_row_bound() -> None:
    level, _pad, player = arena()
    settle(level)
    snapshot = level.save_state()
    slot = player.combat_slot

    from src.simulation.combat.null_combat import NullCombatComponent

    player.combat = NullCombatComponent()
    level.load_state(snapshot)

    assert player.combat_slot == slot
    assert player.combat is level.combat_table.combat_of(slot)
