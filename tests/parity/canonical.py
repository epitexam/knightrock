"""Canonical observation of simulation state for parity comparisons.

The shape mirrors ``tests/headless/test_simulation_golden.py`` but adds state
that matters to the migration (facing, state name, id factory sequence,
projectiles). Render-only FX are deliberately excluded: they use their own
module-level RNG and are not part of the deterministic world.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.simulation.entities.entity import Entity

__all__ = ["snapshot", "digest", "canonical_json"]


def _round(value: float) -> float:
    return round(float(value), 4)


def _entity_state(entity: Entity) -> tuple[Any, ...]:
    return (
        entity.id,
        _round(entity.hitbox.x),
        _round(entity.hitbox.y),
        _round(entity.velocity.x),
        _round(entity.velocity.y),
        _round(getattr(entity, "health", 0.0)),
        bool(getattr(entity, "is_dead", False)),
        bool(entity.facing_right),
        str(entity.state_machine.current_state_name),
    )


def snapshot(level: Any) -> dict[str, Any]:
    """Every observable bit of one tick, in a stable JSON-compatible shape."""
    fighters = tuple(_entity_state(entity) for entity in level.groups.fighters)
    shots = tuple(
        (
            shot.id,
            _round(shot.hitbox.x),
            _round(shot.hitbox.y),
            _round(shot.velocity.x),
            _round(shot.velocity.y),
            bool(shot.is_dead),
        )
        for proxy in level.groups.projectile_sprites
        if (shot := getattr(proxy, "entity", proxy)) is not None
    )
    return {
        "tick": level.tick,
        "respawn_timer": _round(level.respawn_timer),
        "deaths": level.deaths,
        "exit_reached": bool(level.exit_reached),
        "fighters": fighters,
        "shots": shots,
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
