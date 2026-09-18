"""Integration: the entity grid must not change simulation results (Phase 3 #1).

PERF-02 turned the three pairing systems (separation, contact damage,
combat hits) from exhaustive O(n²) to grid-pruned O(n·k).  The grid may
only remove pairs that could never overlap — never reorder them.  This
test locks that guarantee: the same seeded level simulated with the grid
and with the systems forced back to exhaustive pairing must produce
identical snapshots (positions, health) for the whole run.
"""

import random

import pygame

from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData

TICKS = 180  # 3 simulated seconds: plenty of pushes, chases, and hits
SEED = 20260913


def _object(name: str, x: float, y: float) -> ObjectData:
    return ObjectData(
        name=name,
        x=x,
        y=y,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )


def _make_level(mock_input_manager) -> Level:
    """Player + two AI goblins: one overlapping (separation), one chasing."""
    entities = ObjectLayerData(
        name="Entities",
        objects=[
            _object("player", 100.0, 100.0),
            _object("goblin", 110.0, 100.0),  # overlapping: separation + contact
            _object("goblin", 400.0, 100.0),  # far: chases, then fights
        ],
    )
    data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={"Entities": entities},
        config=LevelConfig(death_border_bottom=0.0),
    )
    level = Level(pygame.display.get_surface(), data, mock_input_manager)
    _seed_entities(level)
    return level


def _seed_entities(level: Level) -> None:
    """Make the level's random state reproducible across builds.

    ``Entity.__init__`` falls back to ``random.Random()``, which seeds itself
    from ``os.urandom`` and therefore ignores ``random.seed()``.  Enemies use
    that generator once, to pick ``patrol_direction``.  Both levels must start
    from the same draws, otherwise they diverge for reasons unrelated to the
    grid.  Re-seed every entity per insertion index and recompute the value
    that was already drawn during construction.
    """
    for index, entity in enumerate(level.groups.entity_sprites):
        entity.rng = random.Random(SEED + index)
        if hasattr(entity, "patrol_direction"):
            entity.patrol_direction = 1 if entity.rng.random() > 0.5 else -1


def _force_exhaustive_pairing(level: Level) -> None:
    """Re-route the three pairing systems to their legacy exhaustive mode."""
    loop = level.gameplay_loop
    separation = loop.separation_system
    original_separation = separation.process
    separation.process = lambda group, grid=None: original_separation(group, None)  # type: ignore

    combat = loop.combat_system
    original_attacks = combat.process_attacks
    combat.process_attacks = lambda c, grid=None: original_attacks(c, None)  # type: ignore

    contact = level.contact_damage_system
    original_contact = contact.process
    contact.process = lambda group, grid=None: original_contact(group, None)  # type: ignore


def _snapshot(level: Level):
    """Per-entity state keyed by *insertion order* (not entity.id: the global
    id counter keeps advancing across builds, so ids differ between the two
    levels even though the simulations are identical)."""
    player = level.player
    others = [
        (index, tuple(entity.hitbox), entity.health)
        for index, entity in enumerate(level.groups.entity_sprites)
        if entity is not player
    ]
    return (tuple(player.hitbox), player.health, tuple(others))


def _run(level: Level, use_grid: bool) -> list:
    if not use_grid:
        _force_exhaustive_pairing(level)
    frames: list = []
    for _ in range(TICKS):
        level.update(1 / 60)
        frames.append(_snapshot(level))
    return frames


def test_grid_pairing_simulates_identically_to_exhaustive(mock_input_manager) -> None:
    with_grid = _make_level(mock_input_manager)
    exhaustive = _make_level(mock_input_manager)

    grid_frames = _run(with_grid, use_grid=True)
    exhaustive_frames = _run(exhaustive, use_grid=False)

    assert len(grid_frames) == TICKS
    assert grid_frames == exhaustive_frames, (
        "The entity grid changed simulation results — pair pruning must be "
        "order-preserving and may only drop never-overlapping pairs."
    )


def test_grid_tick_actually_exercises_interactions(mock_input_manager) -> None:
    """Guard: the equivalence test above must not pass on a trivial scenario."""
    level = _make_level(mock_input_manager)
    _run(level, use_grid=True)

    # The overlapping goblin got pushed away from its spawn...
    pushed = [
        entity
        for entity in level.groups.entity_sprites
        if entity is not level.player and entity.hitbox.x > 110.0
    ]
    assert pushed, "no separation happened: the scenario exercises nothing"
    # ...and the chase goblin moved toward the player (AI ran).
    chasers = [
        entity
        for entity in level.groups.entity_sprites
        if entity is not level.player and entity.hitbox.x < 400.0
    ]
    assert chasers, "no chase happened: the AI never engaged"
