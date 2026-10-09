"""BUG-03: hazards (saw/spike/floor_spike) must deal damage on overlap."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame

from src.core.level.systems.hazard_damage import HazardDamageSystem


def make_entity(
    hitbox: pygame.FRect, *, is_dead: bool = False, entity_id: str = "e1"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=entity_id,
        is_dead=is_dead,
        hitbox=hitbox,
        velocity=pygame.Vector2(0, 0),
        receive_damage=Mock(return_value=None),
    )


class FakeHazard:
    def __init__(
        self,
        rect: pygame.FRect,
        *,
        damage: float = 25.0,
        knockback=None,
    ) -> None:
        self.rect = rect
        self.damage = damage
        self.knockback = knockback


class _MovingHazard:
    def __init__(self, previous: pygame.FRect, current: pygame.FRect) -> None:
        self.rect = current
        self._previous = previous
        self.damage = 25.0

    def swept_contact_rect(self) -> pygame.FRect:
        from src.combat.sweep import swept_box

        return swept_box(self._previous, self.rect)


def test_moving_hazard_sweeps_target_between_positions() -> None:
    """A moving hazard catches a target crossed between discrete positions."""
    target = make_entity(pygame.FRect(100, 100, 40, 40))
    hazard = _MovingHazard(pygame.FRect(90, 100, 20, 40), pygame.FRect(150, 100, 20, 40))
    system = HazardDamageSystem()

    system.process([target], [hazard])

    target.receive_damage.assert_called_once()


def test_hazard_applies_configured_damage() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_called_once()
    kwargs = entity.receive_damage.call_args.kwargs
    assert kwargs["amount"] == 25.0
    assert kwargs["interrupt"] is False
    assert kwargs["source_center_x"] == pygame.FRect(10, 10, 64, 64).centerx


def test_hazard_uses_default_damage_when_unspecified() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = SimpleNamespace(rect=pygame.FRect(10, 10, 64, 64))
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    assert entity.receive_damage.call_args.kwargs["amount"] == (HazardDamageSystem.DEFAULT_DAMAGE)


def test_hazard_ignores_non_overlapping_entities() -> None:
    entity = make_entity(pygame.FRect(600, 600, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_not_called()


def test_hazard_ignores_dead_entities() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40), is_dead=True)
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_not_called()


def test_hazard_defaults_are_non_zero_threat() -> None:
    assert HazardDamageSystem.DEFAULT_DAMAGE > 0
    assert HazardDamageSystem.DEFAULT_KNOCKBACK.power != (0.0, 0.0)


def test_a_hazard_damages_the_same_target_once_per_cooldown() -> None:
    """A saw re-emits its box every tick; the target may not be damaged by it.

    An enemy configures no invincibility window, so without a per-target
    cooldown a twenty-damage saw kills a hundred-hit-point enemy in five ticks.
    """
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    for _ in range(60):
        system.process([entity], [hazard])

    calls = entity.receive_damage.call_count
    assert calls <= 3, f"{calls} hits in one second of contact: the cooldown is not holding"


def test_the_cooldown_is_per_target_and_not_global() -> None:
    """A saw that stops damaging one target still damages the next."""
    first = make_entity(pygame.FRect(0, 0, 40, 40), entity_id="e1")
    second = make_entity(pygame.FRect(0, 0, 40, 40), entity_id="e2")
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([first], [hazard])
    assert first.receive_damage.call_count == 1
    assert second.receive_damage.call_count == 0

    system.process([first, second], [hazard])
    assert second.receive_damage.call_count == 1


def test_the_cooldown_forgets_a_hazard_that_left_the_level() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])
    assert system._cooldowns

    system.process([entity], [])
    assert not system._cooldowns


# -- the per-hazard box cache -------------------------------------------------
#
# The boxes are built once and their geometry refreshed, because a hazard's
# damage and knockback never change and a HitProperties costs 2.9us to build.
# Each of these is a way that reuse could hand back a stale answer.


def test_the_same_hazard_gets_the_same_box_object_across_ticks() -> None:
    """Reuse is the point; a fresh object per tick is the old cost back."""
    system = HazardDamageSystem()
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)

    first = system.produce_boxes([], [hazard])[0]
    second = system.produce_boxes([], [hazard])[0]

    assert first is second


def test_a_reused_box_follows_the_hazard_when_it_moves() -> None:
    """The cached geometry must be rewritten, not left at the first sighting."""
    system = HazardDamageSystem()
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system.produce_boxes([], [hazard])

    hazard.rect = pygame.FRect(300, 10, 64, 64)
    moved = system.produce_boxes([], [hazard])[0]

    assert moved.box == pygame.FRect(300, 10, 64, 64)


def test_a_reused_box_picks_up_a_sweep_on_the_first_tick_too() -> None:
    """The regression this guards is a hazard that only sweeps from the second
    tick on, because the build path filled the geometry differently from the
    refresh path."""
    system = HazardDamageSystem()
    hazard = _MovingHazard(pygame.FRect(90, 100, 20, 40), pygame.FRect(150, 100, 20, 40))

    first = system.produce_boxes([], [hazard])[0]

    assert first.swept[0] != first.box, "the first tick must sweep like every later one"


def test_two_hazards_do_not_share_a_box() -> None:
    """Cached by identity, not by position or by damage."""
    system = HazardDamageSystem()
    near = FakeHazard(pygame.FRect(0, 0, 64, 64), damage=10.0)
    far = FakeHazard(pygame.FRect(0, 0, 64, 64), damage=10.0)

    boxes = system.produce_boxes([], [near, far])

    assert boxes[0] is not boxes[1]
    assert boxes[0].hit is not boxes[1].hit


def test_a_hazard_that_leaves_the_level_releases_its_box() -> None:
    """The cache holds the hazard, so a stale entry is a leak, not just waste."""
    system = HazardDamageSystem()
    kept = FakeHazard(pygame.FRect(0, 0, 64, 64))
    gone = FakeHazard(pygame.FRect(0, 0, 64, 64))
    system.produce_boxes([], [kept, gone])

    remaining = system.produce_boxes([], [kept])

    assert len(remaining) == 1
    assert len(system._boxes) == 1


def test_the_cache_survives_an_unhashable_producer() -> None:
    """Producers are duck-typed, and a stand-in need not be hashable."""
    system = HazardDamageSystem()
    hazard = SimpleNamespace(rect=pygame.FRect(10, 10, 64, 64), damage=25.0)

    first = system.produce_boxes([], [hazard])
    second = system.produce_boxes([], [hazard])

    assert first[0] is second[0]
