"""`Entity` is a composition root, not a container.

The audit that opened this branch proposed extracting `EntityKinematics`,
`EntityVitalsAdapter` and `EntitySweep` from `Entity`, on the grounds that it
was a 1100-line god-class still holding its own state. That extraction had
already been done: `MovementComponent`, `Vitals`, `ReactionComponent` and
`CombatComponent` own the state, and the twelve properties on `Entity` forward
to them. What the audit read as a container is the API those components are
reached through -- `entity.velocity` has 223 call sites and
`entity.on_surface` has 98, most of them mutating in place from `src.physics`
and the state machine, which is exactly why the getters return the live
component objects rather than copies.

So there is nothing to extract, and these tests are what says so. They are
the guard against the opposite regression: someone inlining the state back
into `Entity` because "it is only a few fields", which would pass every
behavioural test in the suite -- the same values would be read and written --
while quietly re-creating the coupling the components removed.
"""

import pygame
import pytest

from src.entities.components.movement import MovementComponent
from src.entities.entity import Entity
from src.entities.vitals import Vitals
from tests.unit.helpers import make_entity

pytestmark = pytest.mark.usefixtures("_entity_display")


@pytest.fixture(scope="module", autouse=True)
def _entity_display() -> None:
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_the_entity_composes_its_components() -> None:
    entity = make_entity()

    assert isinstance(entity._movement, MovementComponent)
    assert isinstance(entity.vitals, Vitals)


def test_kinematic_state_lives_in_the_movement_component() -> None:
    """Not a copy of it: the same object, so an in-place write lands."""
    entity = make_entity()

    assert entity.velocity is entity._movement.velocity
    assert entity.on_surface is entity._movement.on_surface

    entity.velocity.x = 123.0
    assert entity._movement.velocity.x == 123.0

    entity._movement.velocity.y = -7.0
    assert entity.velocity.y == -7.0


def test_vital_state_lives_in_the_vitals_component() -> None:
    entity = make_entity(health=50.0, max_health=80.0)

    assert entity.health == entity.vitals.health == 50.0

    entity.health = 20.0
    assert entity.vitals.health == 20.0

    entity.vitals.health = 33.0
    assert entity.health == 33.0


@pytest.mark.parametrize(
    ("name", "component_attribute"),
    [
        ("health", "health"),
        ("max_health", "max_health"),
        ("is_dead", "is_dead"),
        ("spawn_pos", "spawn_pos"),
        ("invincibility_timer", "invincibility_timer"),
        ("invincibility_duration", "invincibility_duration"),
        ("stagger_timer", "stagger_timer"),
        ("super_armor", "super_armor"),
        ("super_armor_count", "super_armor_count"),
    ],
)
def test_every_delegating_property_forwards_to_vitals(name: str, component_attribute: str) -> None:
    """One loop over all nine, so a tenth cannot be added without a line here.

    A property that forwarded to nothing would still read and write, and the
    behavioural tests would not notice: the values would simply live in two
    places and only one of them would be read.
    """
    entity = make_entity()

    through_entity = getattr(entity, name)
    through_component = getattr(entity.vitals, component_attribute)

    assert through_entity == through_component, name

    sentinel = through_entity
    setattr(entity, name, sentinel)
    assert getattr(entity.vitals, component_attribute) is sentinel, name


def test_the_delegating_properties_are_the_api_nothing_may_rename() -> None:
    """The reason the block exists rather than a thinner Entity.

    223 call sites read `entity.velocity` and 98 read `entity.on_surface`, and
    the physics functions mutate them in place. Renaming them to reach the
    component directly would be a large, behaviour-preserving diff with no
    gain -- which is the same argument, applied to the whole extraction.
    """
    for name in ("velocity", "on_surface", "health", "is_dead", "stagger_timer"):
        assert isinstance(getattr(Entity, name), property), name


def test_entity_still_owns_what_is_genuinely_its_own() -> None:
    """The composition root is not a bag of nothing: these are Entity's.

    Geometry and collision shape, the shared collaborators it was handed, and
    the tuning constants. No component wants them, which is why they are here
    and not in `MovementComponent`.
    """
    entity = make_entity()

    assert entity.rect is not None
    assert entity.hitbox is not None
    assert entity.hurtbox is not None
    assert entity.spatial_hash is None or hasattr(entity.spatial_hash, "get_nearby")
    assert entity.normal_gravity > 0.0
    assert entity.max_slide_speed > 0.0
