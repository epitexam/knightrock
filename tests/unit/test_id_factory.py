"""Identifiers are injectable, so independent worlds do not share a sequence."""

from pygame.sprite import Group

from src.entities.entity import Entity
from src.entities.id_factory import IdFactory
from src.entities.projectile import Projectile


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


def test_default_construction_still_uses_the_shared_sequence() -> None:
    first = Projectile()
    second = Projectile()

    assert first.id.startswith("p")
    assert second.id.startswith("p")
    assert int(second.id[1:]) == int(first.id[1:]) + 1
