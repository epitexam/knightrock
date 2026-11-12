"""A rollback restores *everything* the simulation holds, not a chosen few fields.

The rollback is not switched on in the game yet -- it is the groundwork of the
planned multiplayer mode -- so nothing exercises it but this file. Its narrow
predecessor compared a handful of fields, and a player whose juggle, OTG and
parry state came back reset passed it (audit C3).

This one walks every plain value on each entity and on each of its components,
captures them, scrambles the level, restores it and compares. A new field that
a snapshot forgets fails here, which is the point: the alternative is finding
out when two machines disagree.

``NOT_SNAPSHOTTED`` lists what is left out on purpose, each with its reason.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.entities.entity import Entity
from src.entities.player import Player
from tests.headless.conftest import make_viewport

#: Attribute names that are not simulation state, and why.
NOT_SNAPSHOTTED = {
    # Re-derived at the next sweep capture; documented on Entity.load_state.
    "_prev_pushbox": "sweep origin, re-derived",
    "_prev_hurtboxes": "sweep origin, re-derived",
    "_previous_contact_shape": "sweep origin, re-derived",
    # Identity and wiring, not state.
    "id": "identity",
    "entity": "back-reference",
}


class _Pad(InputProvider):
    def __init__(self) -> None:
        self.next = InputState()

    def poll(self) -> InputState:
        return self.next


def _object(name: str, x: float) -> ObjectData:
    return ObjectData(
        name=name,
        x=x,
        y=100.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )


def _level() -> tuple[Level, _Pad]:
    pad = _Pad()
    data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={
            "Entities": ObjectLayerData(
                name="Entities",
                objects=[
                    _object("player", 100.0),
                    _object("goblin", 160.0),
                    _object("slime", 260.0),
                ],
            )
        },
        config=LevelConfig(),
    )
    level = Level(make_viewport().surface, data, InputManager(pad), rollback_enabled=True)
    for entity in level.groups.entity_sprites:
        entity.animator = None  # no art needed: nothing here is about pixels
    return level, pad


def _plain(value: Any) -> Any:
    """``value`` as something comparable, or ``None`` when it is not plain data."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, pygame.math.Vector2):
        return (value.x, value.y)
    if isinstance(value, (pygame.Rect, pygame.FRect)):
        return (value.x, value.y, value.w, value.h)
    if isinstance(value, (tuple, list)) and all(_plain(item) is not None for item in value):
        return tuple(_plain(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(map(str, value)))
    if isinstance(value, dict) and all(isinstance(key, (str, Enum)) for key in value):
        items = {str(_plain(key)): _plain(item) for key, item in value.items()}
        if all(item is not None for item in items.values()):
            return tuple(sorted(items.items()))
    return None


def _walk(obj: Any, prefix: str, out: dict[str, Any]) -> None:
    for name, value in vars(obj).items():
        if name in NOT_SNAPSHOTTED:
            continue
        plain = _plain(value)
        if plain is not None or value is None:
            out[f"{prefix}.{name}"] = plain


def _components(entity: Entity) -> dict[str, Any]:
    """Every object whose fields are the entity's simulation state."""
    combat = entity.combat
    parts: dict[str, Any] = {
        "entity": entity,
        "vitals": entity.vitals,
        "movement": entity._movement,
        "combat": combat,
        "machine": entity.state_machine,
    }
    for name in ("state", "combo", "charging"):
        if hasattr(combat, name):
            parts[f"combat.{name}"] = getattr(combat, name)
    for name, state in getattr(entity.state_machine, "states", {}).items():
        parts[f"state[{name}]"] = state
    if isinstance(entity, Player):
        for name in ("jump", "guard", "dash", "crouch", "input_handler"):
            parts[name] = getattr(entity, name)
    return parts


def _fingerprint(level: Level) -> dict[str, Any]:
    out: dict[str, Any] = {"level.tick": level.tick}
    for entity in sorted(level.groups.entity_sprites, key=lambda e: e.id):
        for prefix, part in _components(entity).items():
            _walk(part, f"{entity.id}:{prefix}", out)
        out[f"{entity.id}:rng"] = entity.rng.getstate()
    return out


def _play(level: Level, pad: _Pad, script: list[frozenset[InputAction]], axis: float) -> None:
    for held in script:
        pad.next = InputState(move_axis=axis, held_actions=held)
        level.update(1 / 60)


def _scramble(level: Level) -> None:
    """Give every entity non-default values in the fields a hit leaves behind."""
    for index, entity in enumerate(level.groups.entity_sprites, start=1):
        entity.juggle_timer = 0.1 * index
        entity.otg_timer = 0.05 * index
        entity.gravity_scale = 0.5 + 0.1 * index
        entity.parries_given = index
        entity.parries_taken = index + 1


def test_a_restore_brings_back_every_simulated_value() -> None:
    level, pad = _level()
    attack, dash = frozenset({InputAction.ATTACK_1}), frozenset({InputAction.DASH})
    _play(level, pad, [frozenset()] * 20 + [attack] + [frozenset()] * 6 + [dash], axis=1.0)
    _scramble(level)

    snapshot = level.save_state()
    captured = _fingerprint(level)

    _play(level, pad, [attack, frozenset(), dash] + [frozenset()] * 12, axis=-1.0)
    for entity in level.groups.entity_sprites:
        entity.juggle_timer = entity.otg_timer = 0.0
        entity.gravity_scale = 1.0
        entity.parries_given = entity.parries_taken = 0
    level.load_state(snapshot)
    restored = _fingerprint(level)

    differences = {
        key: (captured.get(key), restored.get(key))
        for key in captured.keys() | restored.keys()
        if captured.get(key) != restored.get(key)
    }
    assert not differences, "not restored by a rollback:\n" + "\n".join(
        f"  {key}: captured {was!r}, restored {now!r}"
        for key, (was, now) in sorted(differences.items())
    )


def test_a_replay_from_a_restore_ends_where_the_first_run_did() -> None:
    """Restore, replay the same input: the end state is the same, to the last field."""
    level, pad = _level()
    attack = frozenset({InputAction.ATTACK_1})
    _play(level, pad, [frozenset()] * 20, axis=1.0)
    snapshot = level.save_state()

    script = [attack] + [frozenset()] * 10 + [frozenset({InputAction.JUMP})] + [frozenset()] * 8
    _play(level, pad, script, axis=1.0)
    first = _fingerprint(level)

    level.load_state(snapshot)
    _play(level, pad, script, axis=1.0)

    assert _fingerprint(level) == first
