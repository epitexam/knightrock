"""The vocabulary the other overlay modules share.

Three kinds of thing, all leaves: facts read off a sprite (faction, name,
colours), rectangles adjusted against the display (clamp, dodge), and the
per-frame `AnnotationSink` that lets the box pass and the card pass talk without
importing each other.

The sprite facts and the placement rule have nothing to do with each other and
share a file anyway, because the direction of the dependencies is what matters:
both are leaves, and both are needed by the same three callers. Folding them
into `_geo` would make the geometry module the thing everything imports.

Stateless, like the bars: `clamp_annotation` and `dodge_annotation` take the
display width and the tier gap as arguments rather than holding a surface,
because a module that owns a surface has a resize lifecycle to maintain and the
caller already has the surface to pass.

`dodge_annotation` is currently unreachable — the attack header is always placed
clear of the only obstacle it is ever handed. It stays because it is the
documented contract of the placement rule: neutering it leaves the suite green."""

from __future__ import annotations

from collections.abc import Iterable

import pygame

from src.core.colors import Color, Colors
from src.ui.world_overlay_metrics import ANNOTATION_MAX_DODGES

__all__ = [
    "AnnotationSink",
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
    """The sprite's faction, or None when it has none."""
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


class AnnotationSink:
    """The rectangles the box pass has claimed this frame, for the card pass to read.

    The overlay runs in two phases over the same sprite list. The box pass
    draws a hitbox, a zone seal, an attack header and a row of anchor dots, and
    each of those occupies screen space. The card pass then places a label per
    sprite and has to know what to avoid, both to dodge the annotations
    (``sink.obstacles``) and to reserve the band they occupy
    (``sink.for_sprite``).

    A one-way channel: the box pass registers, the card pass consults. It is
    one class rather than two dictionaries passed around because the direction
    is the invariant worth naming. When these were two attributes on
    ``WorldUI`` there was nothing stopping a label from writing to the list it
    was reading, and a card that claimed space the next sprite reads as taken
    is exactly how a label ends up underneath a health bar with nothing to
    explain it.

    Owned by the facade and cleared once per frame, so the layers never have to
    be told when a frame starts.
    """

    def __init__(self) -> None:
        self._rects: dict[int, list[pygame.Rect]] = {}
        self._obstacles: list[pygame.Rect] = []

    def clear(self) -> None:
        """Drop the previous frame's rectangles.

        Called in place rather than by rebinding, because the layers were
        handed *this* object: a fresh dict here would leave them writing to an
        orphan the card pass never reads.
        """
        self._rects.clear()
        self._obstacles.clear()

    def register(self, sprite: pygame.sprite.Sprite, rects: list[pygame.Rect]) -> None:
        """Record the annotations drawn for ``sprite`` this frame.

        ``id(sprite)`` is the key, and that is deliberate: it is the same key
        the physics side uses for its spatial hash, and the alternative --
        keying on the sprite itself -- means the overlay has to be handed the
        bookkeeping that says a sprite is dead, which is the one thing this
        pass deliberately does not look at.
        """
        if not rects:
            return
        self._rects[id(sprite)] = list(rects)
        self._obstacles.extend(rects)

    def for_sprite(self, sprite: pygame.sprite.Sprite) -> list[pygame.Rect]:
        """The annotations drawn for ``sprite``, or an empty list."""
        return self._rects.get(id(sprite), [])

    @property
    def rects(self) -> dict[int, list[pygame.Rect]]:
        """Per-sprite annotations, keyed by ``id(sprite)``.

        The whole table, for a caller that wants to walk every sprite's
        annotations rather than one. The card placer looks a sprite up with
        :meth:`for_sprite`, which is the read that matters per frame. Writing
        to this would break the one-way contract, so everything that registers
        goes through :meth:`register`.
        """
        return self._rects

    @property
    def obstacles(self) -> list[pygame.Rect]:
        """Every annotation rect drawn this frame, in draw order."""
        return self._obstacles
