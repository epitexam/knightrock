"""The gameplay values come from the data bundle, wherever an enemy is made (audit C4).

The enemy-type check and the debug bench used to read a Python copy of
``enemies.json``: an enemy added only to the file was ignored by the level,
and a goblin rebalanced in the file was still the old goblin on the bench.
"""

from __future__ import annotations

from dataclasses import replace

from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.data.provider import GameplayData, shipped_gameplay_data
from tests.headless.conftest import make_viewport


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


def _level_with_an_orc() -> Level:
    """A level whose bundle knows an ``orc`` that exists nowhere in code."""
    shipped = shipped_gameplay_data()
    orc = replace(shipped.enemies["goblin"], health=7.0, max_health=7.0)
    data = GameplayData(
        attack_sets=shipped.attack_sets,
        enemies={**shipped.enemies, "orc": orc, "goblin": replace(orc, health=6.0)},
        player=shipped.player,
        levels=shipped.levels,
    )
    level_data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={
            "Entities": ObjectLayerData(
                name="Entities", objects=[_object("player", 100.0), _object("orc", 400.0)]
            )
        },
        config=LevelConfig(),
    )
    return Level(make_viewport().surface, level_data, InputManager(), gameplay_data=data)


def test_an_enemy_known_only_to_the_data_is_placed() -> None:
    level = _level_with_an_orc()

    orcs = [e for e in level.groups.entity_sprites if getattr(e, "enemy_type", None) == "orc"]

    assert len(orcs) == 1
    assert orcs[0].health == 7.0


def test_the_debug_bench_spawns_from_the_same_bundle() -> None:
    level = _level_with_an_orc()

    level.spawn_system._spawn_enemy("goblin", level.player)

    goblins = [e for e in level.groups.entity_sprites if getattr(e, "enemy_type", None) == "goblin"]
    assert [goblin.health for goblin in goblins] == [6.0]
