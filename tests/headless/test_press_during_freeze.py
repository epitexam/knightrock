"""A press made while a hit freezes the world is played once it moves again.

With the real provider: it latches a key tapped between two polls, and the
level does not poll on a frozen tick, so the press waits in the latch instead
of being spent on a tick that cannot see it.
"""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import patch

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.sprites import Sprite
from tests.headless.arena import DATA, DT, PLAYER_X, foe


def _level(provider: LocalInputProvider) -> Level:
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
        InputManager(provider),
        gameplay_data=DATA,
    )
    floor = Sprite(
        (0.0, 400.0), surf=pygame.Surface((5000, 64)), groups=(level.groups.collision_sprites,)
    )
    level.spatial_hash.add(floor)
    level.player.animator = None
    return level


def _tap(provider: LocalInputProvider, key: int) -> None:
    provider.note_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    provider.note_event(pygame.event.Event(pygame.KEYUP, key=key))


def test_a_slash_tapped_during_the_freeze_of_a_hit_continues_the_chain() -> None:
    provider = LocalInputProvider()
    slash = provider._bindings.gameplay.keyboard[InputAction.ATTACK_1]
    assert isinstance(slash, int)
    # A mapping that answers False for every keycode: under DEBUG=1 the level's
    # spawner and the provider both index this with arbitrary keycodes, which a
    # plain {} would refuse and a fixed-length list could not cover.
    with patch.object(pygame.key, "get_pressed", lambda: defaultdict(bool)):
        level = _level(provider)
        foe(level, "goblin", PLAYER_X + 52.0, guards=False, vision_range=0.0, chase_speed=0.0)
        for _ in range(60):
            level.update(DT)
        player = level.player
        started: list[str] = []
        start = player.combat.start_attack

        def record(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            refusal = start(name, *args, **kwargs)
            if refusal.name == "NONE":
                started.append(str(name))
            return refusal

        player.combat.start_attack = record  # type: ignore[method-assign]

        _tap(provider, slash)
        frozen = False
        for _ in range(30):
            level.update(DT)
            if level.gameplay_loop.combat_system.in_hit_stop:
                frozen = True
                break
        assert frozen, "the first slash landed and froze the world"
        assert started == ["slash_high_1"]

        _tap(provider, slash)  # pressed and released inside the freeze
        for _ in range(20):
            level.update(DT)

    assert started == ["slash_high_1", "slash_high_2"]
