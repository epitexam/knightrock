"""Behaviour over several ticks: what happens *before* a contact matters too.

The single-tick tests of contact damage, hazards and input all start with the
two objects already touching, or the button already pressed on a running
tick. These start from the moment before, which is where the three defects of
the 2026-11-12 audit (C1, C2, C5) lived:

* a press made during hit-stop was dropped;
* a contact cooldown was armed by a pair that never touched, so the first real
  contact could go unpunished for up to 12 (bodies) or 24 (hazards) ticks;
* the reset key teleported the player home at full health outside debug mode.
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.gameplay_scene import GameplayScene
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.settings import Combat as CombatSettings
from tests.headless.conftest import make_programmatic_level_data, make_viewport
from tests.unit.helpers import ScriptedInputProvider, make_entity
from tests.unit.test_hazard_damage import FakeHazard

DT = 1 / 60
#: Known to fail until the audit's stage 1; ``strict`` turns a silent fix into a
#: failure, so the marker cannot outlive the defect.
DEFECT_C1 = pytest.mark.xfail(strict=True, reason="audit C1: presses during hit-stop are dropped")
DEFECT_C2 = pytest.mark.xfail(strict=True, reason="audit C2: cooldown armed without contact")
DEFECT_C5 = pytest.mark.xfail(strict=True, reason="audit C5: reset heals outside debug mode")


# -- hit-stop and input -----------------------------------------------------------


def _press(action: InputAction, ticks: set[int], total: int) -> list[InputState]:
    return [
        InputState(held_actions=frozenset({action}) if tick in ticks else frozenset())
        for tick in range(total)
    ]


def _scene(states: list[InputState]) -> tuple[GameplayScene, Level]:
    """A gameplay scene over a real level, fed a scripted pad.

    The animator is dropped so the player can tick without the art in
    ``assets/``; nothing here is about what the player looks like.
    """
    manager = InputManager(ScriptedInputProvider(states))
    level = Level(make_viewport().surface, make_programmatic_level_data(), manager)
    level.player.animator = None
    game = SimpleNamespace(input_manager=manager, scene_manager=None, level_manager=None)
    return GameplayScene(game, level=level), level  # type: ignore[arg-type]


def _run(
    action: InputAction, press: set[int], freeze: set[int], total: int = 24
) -> tuple[Level, int | None]:
    """Tick a level, holding the world still on ``freeze``; when did ``action`` act?"""
    scene, level = _scene(_press(action, press, total))
    player = level.player
    acted_at: int | None = None
    start_y = player.velocity.y
    for tick in range(total):
        if tick in freeze:
            level.gameplay_loop.combat_system.hit_stop_timer = max(
                level.gameplay_loop.combat_system.hit_stop_timer, 1e-9 + DT
            )
        scene.update(DT)
        if acted_at is None:
            if action is InputAction.ATTACK_1 and player.combat.is_attacking:
                acted_at = tick
            if action is InputAction.DASH and player.is_dashing:
                acted_at = tick
            if action is InputAction.JUMP and player.velocity.y < start_y - 1.0:
                acted_at = tick
    return level, acted_at


@pytest.mark.parametrize("action", [InputAction.ATTACK_1, InputAction.DASH])
def test_a_press_outside_hit_stop_acts_on_its_tick(action: InputAction) -> None:
    _level, acted_at = _run(action, press={10, 11}, freeze=set())

    assert acted_at == 10


@DEFECT_C1
@pytest.mark.parametrize("action", [InputAction.ATTACK_1, InputAction.DASH])
def test_a_tap_during_hit_stop_acts_on_the_first_tick_after_it(action: InputAction) -> None:
    """Pressed and released inside the freeze: played as soon as the world moves."""
    _level, acted_at = _run(action, press={10, 11}, freeze={9, 10, 11, 12})

    assert acted_at == 13


@DEFECT_C1
def test_a_press_held_through_hit_stop_acts_on_the_first_tick_after_it() -> None:
    """Pressed during the freeze and still held when it ends."""
    _level, acted_at = _run(InputAction.ATTACK_1, press=set(range(10, 20)), freeze={9, 10, 11})

    assert acted_at == 12


# -- contact damage between bodies ----------------------------------------------------


def _bodies(gap: float, speed: float = 500.0):
    runner = make_entity(pos=(0.0, 0.0), faction="player")
    standing = make_entity(pos=(40.0 + gap, 0.0), faction="enemy")
    runner.velocity.x = speed
    return runner, standing


def test_bodies_already_touching_deal_damage_on_the_first_tick() -> None:
    runner, standing = _bodies(gap=-20.0)

    ContactDamageSystem().process(pygame.sprite.Group(runner, standing))

    assert standing.health == standing.max_health - CombatSettings.CONTACT_DAMAGE_AMOUNT


@DEFECT_C2
def test_bodies_that_meet_deal_damage_on_the_tick_they_touch() -> None:
    runner, standing = _bodies(gap=150.0)
    system = ContactDamageSystem()
    system.process(pygame.sprite.Group(runner, standing))  # apart: nothing
    assert standing.health == standing.max_health

    standing.hitbox.x = runner.hitbox.right - 20.0
    standing.sync_rects()
    system.process(pygame.sprite.Group(runner, standing))

    assert standing.health == standing.max_health - CombatSettings.CONTACT_DAMAGE_AMOUNT


@DEFECT_C2
def test_a_slow_touch_arms_no_cooldown() -> None:
    """Below the momentum threshold nothing happens, so nothing is owed a wait."""
    runner, standing = _bodies(gap=-20.0, speed=10.0)
    system = ContactDamageSystem()

    system.process(pygame.sprite.Group(runner, standing))

    assert not system._cooldowns


# -- hazards --------------------------------------------------------------------


@DEFECT_C2
def test_stepping_on_a_spike_hurts_on_the_first_tick_on_it() -> None:
    walker = make_entity(pos=(0.0, 0.0), faction="player")
    spike = FakeHazard(pygame.FRect(400.0, 0.0, 40.0, 40.0))
    system = HazardDamageSystem()
    system.process([walker], [spike])  # far from it
    assert walker.health == walker.max_health

    walker.hitbox.x = 400.0
    walker.sync_rects()
    system.process([walker], [spike])

    assert walker.health < walker.max_health


def test_a_spike_does_not_hurt_twice_within_its_cooldown() -> None:
    walker = make_entity(pos=(400.0, 0.0), faction="player")
    spike = FakeHazard(pygame.FRect(400.0, 0.0, 40.0, 40.0), damage=10.0)
    system = HazardDamageSystem()

    for _ in range(HazardDamageSystem.CONTACT_COOLDOWN_TICKS):
        system.process([walker], [spike])

    assert walker.health == walker.max_health - 10.0


# -- the reset key --------------------------------------------------------------


@DEFECT_C5
def test_the_reset_key_does_nothing_outside_debug_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    scene, level = _scene(_press(InputAction.RESET, {3}, 6))
    player = level.player
    player.health = 10.0
    for _ in range(6):
        scene.update(DT)

    assert player.health == 10.0
