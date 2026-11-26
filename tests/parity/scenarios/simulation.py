"""Deterministic simulation scenarios for the parity suite.

Every scenario uses the real fixed-tick pipeline through
``tests.headless.arena`` and returns the **full trace** of canonical snapshots
(one per tick), not just the final state. Sampling every tick is what lets the
suite see transient differences such as hit-stop, i-frames and contact damage.

No scenario depends on art or on the display: they build a programmatic level
and set every animator to ``None``, so they run on a bare CI checkout.
"""

from __future__ import annotations

import random
from typing import Any

from tests.headless.arena import (
    BEAT,
    DASH,
    DOWN,
    GUARD,
    JUMP,
    SLASH,
    arena,
    foe,
    settle,
)
from tests.parity.canonical import snapshot

DT = 1 / 60
SEED = 20260913

__all__ = ["SCENARIOS", "idle", "run_jump_dash", "melee", "guard", "contact", "long_fall", "kill"]


def seed_world(level: Any) -> None:
    """Seed each fighter's RNG, exactly like the golden simulation test.

    ``Entity`` defaults to an ``os.urandom``-seeded ``random.Random``; without
    this the enemy AI makes different choices between runs and the harness
    compares noise instead of behavior.
    """
    for index, entity in enumerate(level.groups.fighters):
        entity.rng = random.Random(SEED + index)
        if hasattr(entity, "patrol_direction"):
            entity.patrol_direction = 1 if entity.rng.random() > 0.5 else -1


def _advance(level: Any, ticks: int) -> tuple[dict[str, Any], ...]:
    frames = []
    for _ in range(ticks):
        level.update(DT)
        frames.append(snapshot(level))
    return tuple(frames)


def hold_axis(level: Any, pad: Any, axis: float, ticks: int) -> tuple[dict[str, Any], ...]:
    """Hold the stick for ``ticks`` ticks, then centre it."""
    pad.axis = axis
    try:
        return _advance(level, ticks)
    finally:
        pad.axis = 0.0


def tap(level: Any, pad: Any, *buttons: Any, ticks: int = 1) -> tuple[dict[str, Any], ...]:
    """Press ``buttons`` for one tick, then release for ``ticks - 1`` more."""
    pad.held = frozenset(buttons)
    frames = _advance(level, 1)
    pad.held = frozenset()
    return frames + _advance(level, ticks - 1)


def _trace(*parts: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {"frames": tuple(frame for part in parts for frame in part)}


def idle() -> dict[str, Any]:
    """Gravity, ground contact and idle state over 90 ticks."""
    level, _pad, _player = arena()
    seed_world(level)
    settle(level, 30)
    return _trace(_advance(level, 90))


def run_jump_dash() -> dict[str, Any]:
    """Run, jump, fast-fall and air dash — the movement hot path."""
    level, pad, _player = arena()
    seed_world(level)
    settle(level, 30)
    frames: list[tuple[dict[str, Any], ...]] = []
    frames.append(hold_axis(level, pad, 1.0, 20))
    frames.append(tap(level, pad, JUMP, ticks=25))
    frames.append(tap(level, pad, DOWN, ticks=10))
    frames.append(hold_axis(level, pad, 1.0, 4))
    pad.axis = 1.0  # the dash request reads move_axis and needs >= threshold
    frames.append(tap(level, pad, DASH, ticks=20))
    pad.axis = 0.0
    frames.append(_advance(level, 40))
    return _trace(*frames)


def melee() -> dict[str, Any]:
    """Approach and hit a goblin: damage, knockback, hit-stop and AI."""
    level, pad, _player = arena()
    foe(level, "goblin", 1100.0)
    seed_world(level)
    settle(level, 60)
    return _trace(
        hold_axis(level, pad, 1.0, 90),
        tap(level, pad, SLASH, ticks=12),
        _advance(level, 30),
    )


def guard() -> dict[str, Any]:
    """Hold guard against an enemy blow: guard, chip and stagger rules."""
    level, pad, _player = arena()
    foe(level, "goblin", 1060.0)
    seed_world(level)
    settle(level, 60)
    return _trace(tap(level, pad, GUARD, BEAT, ticks=45))


def contact() -> dict[str, Any]:
    """Dash through two enemies: momentum contact damage, i-frames, null knockback."""
    level, pad, _player = arena()
    foe(level, "goblin", 1060.0)
    foe(level, "slime", 1120.0)
    seed_world(level)
    settle(level, 60)
    pad.axis = 1.0
    frames = tap(level, pad, DASH, ticks=20)
    pad.axis = 0.0
    return _trace(frames, _advance(level, 40))


def long_fall() -> dict[str, Any]:
    """A fall long enough to reach terminal velocity."""
    import pygame

    from src.core.input.input_manager import InputManager
    from src.core.input.input_provider import InputProvider, InputState
    from src.core.level.level import Level
    from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
    from src.core.sprites import Sprite
    from src.data.provider import shipped_gameplay_data

    class Still(InputProvider):
        def poll(self) -> InputState:
            return InputState()

    player = ObjectData(
        name="player",
        x=100.0,
        y=50.0,
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
            width=20,
            height=60,
            tile_size=64,
            object_layers={"Entities": ObjectLayerData(name="Entities", objects=[player])},
            config=LevelConfig(death_border_bottom=0.0),
        ),
        InputManager(Still()),
        gameplay_data=shipped_gameplay_data(),
    )
    level.player.animator = None
    floor = Sprite(
        (0.0, 60 * 64 - 64.0),
        surf=pygame.Surface((5000, 64)),
        groups=(level.groups.collision_sprites,),
    )
    level.spatial_hash.add(floor)
    seed_world(level)
    return _trace(_advance(level, 260))


def kill() -> dict[str, Any]:
    """A killing blow: the kill hit-stop from settings is the only free parameter."""
    level, pad, _player = arena()
    foe(level, "goblin", 1100.0, health=1.0, max_health=1.0)
    seed_world(level)
    settle(level, 60)
    return _trace(
        hold_axis(level, pad, 1.0, 90), tap(level, pad, SLASH, ticks=12), _advance(level, 30)
    )


SCENARIOS = {
    "idle": idle,
    "run_jump_dash": run_jump_dash,
    "melee": melee,
    "guard": guard,
    "contact": contact,
    "long_fall": long_fall,
    "kill": kill,
}
