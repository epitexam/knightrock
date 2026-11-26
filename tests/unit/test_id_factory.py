"""Identifiers are injectable, so independent worlds do not share a sequence."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from pygame.sprite import Group

from src.simulation.entities.entity import Entity
from src.simulation.entities.id_factory import IdFactory
from src.simulation.entities.projectile import Projectile


def _entity(factory: IdFactory) -> Entity:
    return Entity(
        pos=(0.0, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        id_factory=factory,
    )


def test_two_factories_have_independent_sequences() -> None:
    first = IdFactory()
    second = IdFactory()

    assert [_entity(first).id for _ in range(2)] == ["e0", "e1"]
    assert _entity(second).id == "e0"
    assert [Projectile(first).id for _ in range(2)] == ["p0", "p1"]
    assert Projectile(second).id == "p0"


def test_an_explicit_id_still_wins_over_the_factory() -> None:
    entity = Entity(
        pos=(0.0, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        entity_id="named",
        id_factory=IdFactory(),
    )

    assert entity.id == "named"


def test_two_levels_own_independent_id_sequences() -> None:
    from src.platform.input.input_manager import InputManager
    from src.simulation.level.level import Level
    from src.simulation.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData

    pygame.init()
    pygame.display.set_mode((320, 240))

    def build() -> Level:
        player = ObjectData(
            name="player",
            x=100.0,
            y=100.0,
            width=0.0,
            height=0.0,
            gid=None,
            image=None,
            points=None,
            properties={},
        )
        data = LevelData(
            width=20,
            height=10,
            tile_size=64,
            object_layers={"Entities": ObjectLayerData(name="Entities", objects=[player])},
            config=LevelConfig(),
        )
        return Level(pygame.Surface((1152, 648)), data, InputManager())

    first, second = build(), build()

    assert first.player.id == "e0"
    assert second.player.id == "e0"
    assert first.id_factory is not second.id_factory


def test_default_construction_still_uses_the_shared_sequence() -> None:
    first = Projectile()
    second = Projectile()

    assert first.id.startswith("p")
    assert second.id.startswith("p")
    assert int(second.id[1:]) == int(first.id[1:]) + 1
