"""Sprite facts and annotation placement — the vocabulary the other overlay modules share.

Extracted from ``world_ui.py`` as the first step of the split, and deliberately
first because it is a leaf: ``world_overlay_geo``, ``_cards`` and ``_panels``
all need to answer "what is this sprite" and "where may I put this rectangle"
before they can do anything else. Everything below is either a fact read off a
sprite or a rectangle adjusted against the display, with no drawing, no
per-frame state and no dependency on any of the three.

**Two unrelated things in one module, on purpose.** The sprite facts (faction,
name, colours) and the annotation placement (clamp, dodge) have nothing to do
with each other, and the reason they share a file is the *direction* of the
dependencies rather than the subject matter: both are leaves, and both are
needed by the same three callers. Folding them into ``_geo`` instead would
have made the geometry module the thing everything imports, which is how a
leaf stops being a leaf.

**Stateless, like ``world_overlay_bars``.** ``clamp_annotation`` and
``dodge_annotation`` need the display width and the tier gap, so they take
them as arguments instead of holding a surface. Same trade as the bars made,
same reason: a module that owns a surface has a lifecycle to maintain at every
resize, and the caller already has to pass the surface.

``dodge_annotation`` is currently unreachable — the attack header is always
placed clear of the only obstacle it is ever handed, its own entity's tiers.
It is kept because it is the documented contract of the placement rule, not
because a test needs it: neutering it leaves the entire suite green.
"""

from __future__ import annotations

from collections.abc import Iterable

import pygame

from src.core.colors import Color, Colors
from src.ui.world_overlay_metrics import ANNOTATION_MAX_DODGES

__all__ = [
    "clamp_annotation",
    "debug_reference",
    "display_name",
    "dodge_annotation",
    "faction",
    "hitbox_color",
    "label_color",
]


def debug_reference(sprite: pygame.sprite.Sprite) -> pygame.FRect | None:
    """The rectangle that stands for this sprite on screen, or ``None``.

    The hitbox if it has one, else the rect. When the sprite is mid-attack its
    attack boxes, swept boxes and anchor points are unioned in, because a
    sprite whose body is still where it was but whose attack has moved on is
    culled and labelled against the wrong rectangle.

    This is also the overlay's culling test: a sprite whose reference is off
    screen costs nothing further, and a level's ~840 terrain tiles reach it
    only when the ``statics`` layer is on.
    """
    reference = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
    if reference is None:
        return None
    combat = getattr(sprite, "combat", None)
    rectangles = [pygame.FRect(reference)]
    for name in ("attack_boxes", "swept_attack_boxes"):
        values = getattr(combat, name, ())
        if isinstance(values, tuple):
            rectangles.extend(pygame.FRect(value) for value in values if value is not None)
    anchors = getattr(combat, "attack_anchors", ())
    if isinstance(anchors, tuple):
        rectangles.extend(pygame.FRect(anchor[0], anchor[1], 0.0, 0.0) for anchor in anchors)
    return rectangles[0].unionall(rectangles[1:]) if len(rectangles) > 1 else rectangles[0]


def display_name(sprite: pygame.sprite.Sprite) -> str:
    """Header name: the enemy registry type for foes, the class otherwise.

    Every foe shares the ``Enemy`` class, so the class name says nothing —
    the stored ``enemy_type`` (``"goblin"``, ``"slime"``, ...) does. Other
    factions keep their class name, and typeless enemies fall back to it.
    """
    if faction(sprite) == "enemy":
        return getattr(sprite, "enemy_type", None) or type(sprite).__name__
    return type(sprite).__name__


def faction(sprite: pygame.sprite.Sprite) -> str | None:
    return getattr(sprite, "faction", None)


def hitbox_color(sprite: pygame.sprite.Sprite) -> Color:
    """Outline tint: the faction, so a frame reads at a glance."""
    sprite_faction = faction(sprite)
    if sprite_faction == "enemy":
        return Colors.red
    if sprite_faction == "player":
        return Colors.debug_hitbox
    return Colors.light_grey


def label_color(sprite: pygame.sprite.Sprite) -> Color:
    """Card accent: the faction, except projectiles which have no state machine."""
    if getattr(sprite, "state_machine", None) is None:
        return Colors.yellow  # projectiles
    sprite_faction = faction(sprite)
    if sprite_faction == "enemy":
        return Colors.light_red
    if sprite_faction == "player":
        return Colors.light_green
    return Colors.text_muted


def clamp_annotation(rect: pygame.Rect, screen_width: int) -> pygame.Rect:
    """Shift an annotation rect back inside the display (never clipped)."""
    if rect.right > screen_width:
        rect.right = screen_width
    if rect.left < 0:
        rect.left = 0
    if rect.top < 0:
        rect.top = 0
    return rect


def dodge_annotation(
    rect: pygame.Rect,
    obstacles: Iterable[pygame.Rect],
    *,
    tier_gap: int,
    screen_width: int,
) -> pygame.Rect:
    """Shift ``rect`` up until it clears every tier drawn below/behind it.

    Each step parks the rect ``ANNOTATION_TIER_GAP`` above the obstacle
    it hit; a step always moves strictly upward, so the loop ends at
    the screen edge where the rect is clamped and drawn anyway — a
    cramped annotation beats a hidden one.

    ``obstacles`` is the caller's own tier stack, not the frame's: two entities
    attacking side by side draw their headers on the same band and neither one
    moves, which is the intended reading (each is labelled over its own body)
    and not an oversight to be tidied up here.
    """
    obstacles = list(obstacles)
    for _ in range(ANNOTATION_MAX_DODGES):
        hit = next((obstacle for obstacle in obstacles if rect.colliderect(obstacle)), None)
        if hit is None:
            break
        rect.bottom = hit.top - tier_gap
        if rect.top < 0:
            rect.top = 0
            break
    return clamp_annotation(rect, screen_width)
