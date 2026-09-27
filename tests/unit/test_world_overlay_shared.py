"""``world_overlay_shared``: the sprite facts and the placement rule.

The geometry of the whole overlay is pinned in ``test_world_overlay_golden``,
against a scene that goes through the real draw path. These are the direct
tests, for the two things a scene cannot reach:

- sprites with a ``rect`` and no ``hitbox`` -- hazards, moving platforms, exits.
  Nothing in the golden scene is one, and the whole suite passed with the
  fallback deleted, which is how it stayed untested for this long.
- ``dodge_annotation``, which the draw path never actually calls. The attack
  header is always placed clear of the only obstacle it is handed, so
  neutering the function leaves every test green. It is kept because it is the
  documented rule of annotation placement; these tests are what make it a
  contract rather than a hope.
"""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import Colors
from src.ui.world_overlay_shared import (
    clamp_annotation,
    debug_reference,
    display_name,
    dodge_annotation,
    faction,
    hitbox_color,
    label_color,
)

TIER_GAP = 4
SCREEN_WIDTH = 400


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((SCREEN_WIDTH, 300))


def _named(name: str, **attrs) -> SimpleNamespace:
    return type(name, (SimpleNamespace,), {})(**attrs)


def test_debug_reference_is_none_without_a_rect() -> None:
    """Nothing to place against, so nothing to cull against either."""
    assert debug_reference(_named("Bare")) is None


def test_debug_reference_falls_back_to_the_rect() -> None:
    """Hazards, moving platforms and exits carry a ``rect`` and no ``hitbox``.

    Dropping this fallback draws them without a hitbox outline, and the
    overlay's own culling test — which asks for the reference first — starts
    treating them as sprites with nothing on screen.
    """
    rect = pygame.FRect(10, 20, 30, 40)
    assert debug_reference(_named("Platform", rect=rect)) == rect


def test_debug_reference_prefers_the_hitbox() -> None:
    rect = pygame.FRect(10, 20, 30, 40)
    hitbox = pygame.FRect(12, 22, 20, 30)
    assert debug_reference(_named("Goblin", rect=rect, hitbox=hitbox)) == hitbox


def test_debug_reference_unions_the_attack_boxes() -> None:
    """A sprite whose attack has moved on is not represented by its body.

    Unioning the boxes and the anchors is what keeps a mid-swing attacker from
    being culled against the rectangle it occupied when it wound up. One test
    per source, so dropping one of them cannot be masked by the other two.
    """
    reference = debug_reference(
        _named(
            "Slime",
            hitbox=pygame.FRect(100, 100, 20, 20),
            combat=SimpleNamespace(attack_boxes=(pygame.FRect(200, 100, 10, 10),)),
        )
    )
    assert reference == pygame.FRect(100, 100, 110, 20)


def test_debug_reference_unions_the_swept_attack_boxes() -> None:
    """The swept box reaches back where the swing came from."""
    reference = debug_reference(
        _named(
            "Slime",
            hitbox=pygame.FRect(100, 100, 20, 20),
            combat=SimpleNamespace(swept_attack_boxes=(pygame.FRect(100, 200, 10, 10),)),
        )
    )
    assert reference == pygame.FRect(100, 100, 20, 110)


def test_debug_reference_unions_the_anchor_points() -> None:
    """Anchors are points, and a point still has to keep its entity on screen."""
    reference = debug_reference(
        _named(
            "Slime",
            hitbox=pygame.FRect(100, 100, 20, 20),
            combat=SimpleNamespace(attack_anchors=((300.0, 100.0),)),
        )
    )
    assert reference == pygame.FRect(100, 100, 200, 20)


def test_debug_reference_skips_a_none_inside_a_box_tuple() -> None:
    """An attack box can be absent for a frame; the rest still count."""
    reference = debug_reference(
        _named(
            "Slime",
            hitbox=pygame.FRect(100, 100, 20, 20),
            combat=SimpleNamespace(attack_boxes=(None, pygame.FRect(200, 100, 10, 10))),
        )
    )
    assert reference == pygame.FRect(100, 100, 110, 20)


def test_debug_reference_ignores_a_non_tuple_combat_field() -> None:
    """A live ``attack_boxes`` list is not this function's contract to read.

    ``CombatState`` is expected to expose tuples. Reading a list here would
    consume a container another system may still be mutating mid-frame.
    """
    reference = debug_reference(
        _named(
            "Slime",
            hitbox=pygame.FRect(100, 100, 20, 20),
            combat=SimpleNamespace(attack_boxes=[pygame.FRect(500, 500, 10, 10)]),
        )
    )
    assert reference == pygame.FRect(100, 100, 20, 20)


def test_display_name_prefers_the_registry_type_for_foes() -> None:
    """Every foe is an ``Enemy``, so the class name says nothing there."""
    sprite = _named("Enemy", faction="enemy", enemy_type="goblin")
    assert display_name(sprite) == "goblin"


def test_display_name_falls_back_to_the_class_for_a_typeless_foe() -> None:
    assert display_name(_named("Enemy", faction="enemy")) == "Enemy"


def test_display_name_ignores_the_registry_type_outside_the_enemy_faction() -> None:
    """A player carrying a stale ``enemy_type`` still reads as its class."""
    sprite = _named("Player", faction="player", enemy_type="goblin")
    assert display_name(sprite) == "Player"
    assert faction(sprite) == "player"


@pytest.mark.parametrize(
    ("sprite_faction", "expected"),
    [
        ("enemy", Colors.red),
        ("player", Colors.debug_hitbox),
        ("neutral", Colors.light_grey),
        (None, Colors.light_grey),
    ],
)
def test_hitbox_color_follows_the_faction(sprite_faction: str | None, expected: object) -> None:
    assert hitbox_color(_named("Thing", faction=sprite_faction)) == expected


def test_label_color_flags_projectiles_by_their_missing_state_machine() -> None:
    """A projectile has no state machine, which is the only thing telling them apart."""
    assert label_color(_named("Shard", faction="enemy")) == Colors.yellow


@pytest.mark.parametrize(
    ("sprite_faction", "expected"),
    [
        ("enemy", Colors.light_red),
        ("player", Colors.light_green),
        ("neutral", Colors.text_muted),
    ],
)
def test_label_color_follows_the_faction(sprite_faction: str, expected: object) -> None:
    sprite = _named("Goblin", faction=sprite_faction, state_machine=object())
    assert label_color(sprite) == expected


def test_clamp_annotation_pulls_a_rect_back_inside() -> None:
    """Never clipped: an annotation that hangs off the edge is still drawn.

    Only the right, left and top are pulled in. There is no bottom clamp,
    because a tier that runs off the bottom of the screen has nothing below it
    to be confused with.
    """
    rect = pygame.Rect(380, 250, 40, 20)
    clamped = clamp_annotation(rect, SCREEN_WIDTH)
    assert clamped.right == SCREEN_WIDTH
    assert clamped.bottom == 270
    assert clamp_annotation(pygame.Rect(-10, -5, 40, 20), SCREEN_WIDTH).topleft == (0, 0)


def test_clamp_annotation_leaves_a_rect_that_fits_alone() -> None:
    rect = pygame.Rect(10, 10, 40, 20)
    assert clamp_annotation(rect, SCREEN_WIDTH) == rect


def test_dodge_annotation_steps_above_each_obstacle_it_hits() -> None:
    """One tier gap clear of the last obstacle, having cleared the first.

    Two tiers, one rect: the loop walks up one obstacle at a time and stops as
    soon as the rect fits. The rect is bounded by ``ANNOTATION_MAX_DODGES`` and
    every step moves it strictly upward, so a stack cannot spin forever.
    """
    lower = pygame.Rect(0, 100, 50, 20)
    upper = pygame.Rect(0, 60, 50, 20)
    rect = dodge_annotation(
        pygame.Rect(0, 110, 50, 20),
        [lower, upper],
        tier_gap=TIER_GAP,
        screen_width=SCREEN_WIDTH,
    )
    assert rect.bottom == upper.top - TIER_GAP
    assert not rect.colliderect(lower)
    assert not rect.colliderect(upper)


def test_dodge_annotation_gives_up_at_the_top_of_the_screen() -> None:
    """A cramped annotation beats a hidden one, so it stops at the edge.

    The step parks the rect four pixels above the obstacle, which puts its top
    above zero; the rect is then moved down to the edge, which costs it half
    the gap. It still clears the tier, just by less than it asked for -- and
    keeping it on screen at all is the point of stopping here.
    """
    obstacle = pygame.Rect(0, 22, 50, 20)
    rect = dodge_annotation(
        pygame.Rect(0, 30, 50, 20),
        [obstacle],
        tier_gap=TIER_GAP,
        screen_width=SCREEN_WIDTH,
    )
    assert rect.topleft == (0, 0)
    assert rect.size == (50, 20), "the top-edge step must move the rect, not resize it"
    assert not rect.colliderect(obstacle)
    assert obstacle.top - rect.bottom == TIER_GAP // 2


def test_dodge_annotation_leaves_a_clear_rect_untouched() -> None:
    rect = pygame.Rect(0, 200, 50, 20)
    assert (
        dodge_annotation(
            rect, [pygame.Rect(0, 100, 50, 20)], tier_gap=TIER_GAP, screen_width=SCREEN_WIDTH
        )
        == rect
    )


def test_dodge_annotation_only_responds_to_a_real_overlap() -> None:
    """Same column, no collision: an obstacle beside the rect is not in its way.

    ``colliderect`` is a strict overlap test, so a tier that shares the x range
    but sits clear above the rect leaves it alone.
    """
    rect = pygame.Rect(0, 200, 50, 20)
    assert (
        dodge_annotation(
            rect, [pygame.Rect(0, 100, 50, 20)], tier_gap=TIER_GAP, screen_width=SCREEN_WIDTH
        )
        == rect
    )
    edge = pygame.Rect(50, 200, 50, 20)
    assert dodge_annotation(rect, [edge], tier_gap=TIER_GAP, screen_width=SCREEN_WIDTH) == rect
