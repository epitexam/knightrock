"""A press buffered just before a prompt or a charge must not come back later.

The input handler stops reading attacks while a prompt is up and while a charge
runs, but it used to keep the previous buffer intact through both. When the
prompt closed or the charge was released, that stale press fired as an attack
the player had never asked for again.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.combat.combatant_protocol import DamageResult
from src.core.input.input_actions import InputAction
from src.core.settings import Input as InputSettings
from tests.headless.test_feel_latency import DT, _scene


def _buffer(handler: object, action: InputAction) -> None:
    handler.buffered_action = action  # type: ignore[attr-defined]
    handler.buffer_timer = InputSettings.ATTACK_BUFFER_WINDOW  # type: ignore[attr-defined]


def test_a_press_buffered_before_a_death_blow_prompt_does_not_fire_after_it() -> None:
    level, pad, starts = _scene(InputAction.ATTACK_1, set())
    player = level.player
    _buffer(player.input_handler, InputAction.ATTACK_1)

    player.on_hit_confirmed(SimpleNamespace(id="e1"), False, DamageResult(doomed=True))
    for tick in range(5):
        pad.tick = tick
        level.update(DT)
    # Simulate the prompt ending without consuming an attack (a failed prompt).
    player.prompt.kind = None
    for tick in range(5, 20):
        pad.tick = tick
        level.update(DT)

    assert starts == []


def test_a_clash_prompt_discards_the_buffer_too() -> None:
    level, pad, starts = _scene(InputAction.ATTACK_1, set())
    player = level.player
    _buffer(player.input_handler, InputAction.ATTACK_1)

    player.on_clash(SimpleNamespace(id="e1", is_dead=False))
    for tick in range(5):
        pad.tick = tick
        level.update(DT)
    player.prompt.kind = None
    for tick in range(5, 20):
        pad.tick = tick
        level.update(DT)

    assert starts == []


def test_starting_a_charge_clears_a_press_buffered_on_the_same_tick() -> None:
    level, _pad, _starts = _scene(InputAction.ATTACK_1, set())
    handler = level.player.input_handler
    level.player.on_surface["floor"] = True
    _buffer(handler, InputAction.ATTACK_2)
    handler.held_for[InputAction.ATTACK_2] = InputSettings.CHARGE_DELAY

    handler._maybe_start_charge()

    assert handler.buffered_action is None
