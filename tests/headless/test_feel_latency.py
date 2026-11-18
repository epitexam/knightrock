"""Ticks between a press and the action it asks for.

The feel matrix pins *what* a hit does, and ``combat_feel.py`` reports how many
swings a masher gets per second. Neither says how long a press waits before the
fighter obeys it. These scenarios start from the tick before the press, the way
a player experiences it, and pin the latency in the three situations that steal
ticks: an idle fighter, a recovery, and a hit that freezes the world.

The numbers are characterisation values, not laws of physics: a tuning change
that moves them must update them here, with the reason recorded in the audit.
"""

from __future__ import annotations

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.settings import Combat as CombatSettings
from src.core.sprites import Sprite
from src.data.provider import shipped_gameplay_data
from tests.headless.arena import DT, FLOOR_Y, PLAYER_X, foe


class _ClockedPad(InputProvider):
    """A pad driven by the test's tick counter, latching taps between polls.

    ``Level`` skips its poll on a frozen tick. A state held only on that tick
    would be lost; this pad remembers a press until a poll actually consumes it,
    exactly as ``LocalInputProvider.note_event`` does for the real keyboard.
    """

    def __init__(self, action: InputAction, pressed_on: set[int]) -> None:
        self.action = action
        self.pressed_on = pressed_on
        self.tick = 0
        self._last_poll = -1

    def poll(self) -> InputState:
        held = self.tick in self.pressed_on
        tapped = any(t in self.pressed_on for t in range(self._last_poll + 1, self.tick))
        self._last_poll = self.tick
        return InputState(held_actions=frozenset({self.action}) if held or tapped else frozenset())


def _scene(action: InputAction, pressed_on: set[int]) -> tuple[Level, _ClockedPad, list[int]]:
    pad = _ClockedPad(action, pressed_on)
    spawn = ObjectData(
        name="player",
        x=PLAYER_X,
        y=300.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )
    level = Level(
        pygame.Surface((1152, 648)),
        LevelData(
            width=80,
            height=12,
            tile_size=64,
            object_layers={"E": ObjectLayerData(name="E", objects=[spawn])},
            config=LevelConfig(),
        ),
        InputManager(pad),
        gameplay_data=shipped_gameplay_data(),
    )
    floor = Sprite(
        (0.0, FLOOR_Y),
        surf=pygame.Surface((5000, 64)),
        groups=(level.groups.collision_sprites,),
    )
    level.spatial_hash.add(floor)
    level.player.animator = None
    starts: list[int] = []
    original = level.player.combat.start_attack

    def record(*args: object, **kwargs: object) -> object:
        refusal = original(*args, **kwargs)  # type: ignore[arg-type]
        if getattr(refusal, "name", None) == "NONE":
            starts.append(pad.tick)
        return refusal

    level.player.combat.start_attack = record  # type: ignore[method-assign]
    return level, pad, starts


def _run(level: Level, pad: _ClockedPad, ticks: int = 30) -> None:
    for tick in range(ticks):
        pad.tick = tick
        level.update(DT)


def test_press_from_neutral_acts_on_the_same_tick() -> None:
    level, pad, starts = _scene(InputAction.ATTACK_1, {10})
    _run(level, pad)
    assert starts == [10]


def test_press_during_recovery_waits_for_the_cancel_window() -> None:
    """Both presses are on the same button; only the second may chain."""
    level, pad, starts = _scene(InputAction.ATTACK_1, {0, 5})
    _run(level, pad)
    # The second press is buffered and replayed as soon as recovery allows it.
    assert len(starts) == 2
    assert starts[0] == 0
    assert starts[1] - 5 == 4  # characterisation: 4 ticks of buffered waiting


def test_press_before_contact_waits_for_the_hit_and_the_freeze() -> None:
    """The chain-link press is refused in ACTIVE until the hit is recorded."""
    level, pad, starts = _scene(InputAction.ATTACK_1, {0, 3})
    foe(level, "goblin", level.player.hitbox.centerx + 20.0, guards=False, vision_range=0.0)
    _run(level, pad)
    assert len(starts) >= 2
    assert starts[0] == 0
    assert starts[1] - 3 == 9  # characterisation: refused in ACTIVE, replayed after hit-stop


def test_a_hit_freezes_at_least_one_tick_of_world_time() -> None:
    level, pad, _ = _scene(InputAction.ATTACK_1, {0})
    foe(level, "goblin", level.player.hitbox.centerx + 20.0, guards=False, vision_range=0.0)
    frozen = 0
    for tick in range(30):
        pad.tick = tick
        level.update(DT)
        frozen += level.gameplay_loop.combat_system.in_hit_stop
    assert frozen >= 1
    assert frozen * DT >= CombatSettings.HITSTOP_BASE
