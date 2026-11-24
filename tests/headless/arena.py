"""A flat arena with a real ``Player`` and real enemies, driven by a scripted pad.

For the tests that have to play the combat rather than call into it: the level
is a real ``Level`` on a long floor, so every stage of the tick runs.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.sprites import Sprite
from src.data.provider import shipped_gameplay_data
from src.entities.enemies.enemy import Enemy
from src.entities.enemies.factory import create_enemy
from src.entities.player import Player

DT = 1 / 60
DATA = shipped_gameplay_data()

SLASH = InputAction.ATTACK_1
SHOOT = InputAction.SHOOT
BEAT = InputAction.ATTACK_2
DOWN = InputAction.MOVE_DOWN
JUMP = InputAction.JUMP
DASH = InputAction.DASH
GUARD = InputAction.GUARD
DARK_SIDE = InputAction.SPECIAL_ATTACK

#: Where the player stands, and the floor under everyone.
PLAYER_X = 1000.0
FLOOR_Y = 400.0


class Pad(InputProvider):
    """A pad whose held buttons and stick the test sets before each tick."""

    def __init__(self) -> None:
        self.held: frozenset[InputAction] = frozenset()
        self.axis = 0.0

    def poll(self) -> InputState:
        return InputState(move_axis=self.axis, held_actions=self.held)


def arena() -> tuple[Level, Pad, Player]:
    """A level with the player standing on a long floor, settled."""
    pad = Pad()
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
        gameplay_data=DATA,
    )
    floor = Sprite(
        (0.0, FLOOR_Y), surf=pygame.Surface((5000, 64)), groups=(level.groups.collision_sprites,)
    )
    level.spatial_hash.add(floor)
    level.player.animator = None
    return level, pad, level.player


def foe(level: Level, name: str, x: float, **changes: Any) -> Enemy:
    """Put an enemy of type ``name`` in the arena, its config changed by ``changes``."""
    config = replace(DATA.enemies[name], **changes) if changes else DATA.enemies[name]
    enemy = create_enemy(
        name,
        (x, 340.0),
        (level.groups.all_sprites,),
        level.groups.collision_sprites,
        level.player,
        config=config,
        spatial_hash=level.spatial_hash,
        id_factory=level.id_factory,
    )
    enemy.animator = None
    level.groups.add_fighter(enemy)
    return enemy


def settle(level: Level, ticks: int = 60) -> None:
    """Let everyone fall to the floor and stand still."""
    for _ in range(ticks):
        level.update(DT)


def tap(level: Level, pad: Pad, *buttons: InputAction, ticks: int = 1) -> None:
    """Press ``buttons`` for one tick, then release them for ``ticks - 1`` more."""
    pad.held = frozenset(buttons)
    level.update(DT)
    pad.held = frozenset()
    for _ in range(ticks - 1):
        level.update(DT)


def in_hit_stop(level: Level) -> bool:
    return bool(level.gameplay_loop.combat_system.in_hit_stop)


def run_out_hit_stop(level: Level) -> None:
    while in_hit_stop(level):
        level.update(DT)
