"""Velocity previews: the vector a sprite is moving along, and why.

Split out of ``world_overlay_geo.py``, and one of the files the original audit
named. It is a leaf by a wide margin -- five functions that touch nothing but
the surface, and that nothing in the box pass calls back into.

**The colour is the content.** This is the one part of the world overlay whose
job is answering a question rather than drawing a shape: a vector tells you
whether an entity is walking, being knocked back, or guarding against a parry,
and the colour is how it says so. The two predicates here are what turn a
position into an explanation, and both are cases the game actually produces --
there is no "unknown" to fall back on, which is why they are not one function
with a default.

**A class for the painter, functions for the predicates.** ``draw_velocity``
and ``draw_velocity_arrow`` share the surface, so they are a class with a
surface; the predicates read a sprite and reach for nothing, so they are plain
functions. That is the same split ``world_overlay_shared`` already draws, and it
is why they are callable as ``is_parry_flash(sprite)`` rather than through the
class.
"""

from __future__ import annotations

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.entities.components.reaction import VELOCITY_KINDS, ReactionKind, ReactionStatus
from src.states.reaction_states import KNOCKBACK_STATE
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_metrics import (
    VELOCITY_HEAD_MAX,
    VELOCITY_HEAD_MIN,
    VELOCITY_HEAD_RATIO,
    VELOCITY_HEAD_WIDTH_CAP,
    VELOCITY_HEAD_WIDTH_RATIO,
    VELOCITY_MIN_LENGTH,
    VELOCITY_MIN_SPEED,
    VELOCITY_NECK_WIDTH,
    VELOCITY_OUTLINE,
    VELOCITY_OUTLINE_WIDTH,
    VELOCITY_PREVIEW_S,
    VELOCITY_TAIL_RADIUS,
    VELOCITY_TAIL_WIDTH,
)

__all__ = [
    "VelocityLayer",
    "arrow_outline",
    "is_parry_flash",
    "is_reaction_push",
]


class VelocityLayer:
    """Draws one velocity preview per sprite, tinted by what caused it.

    Constructed once by ``GeoLayer`` and kept for the session.
    """

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer

    @property
    def surface(self) -> pygame.Surface:
        """The live render target, read through so a resize needs no push."""
        return self.renderer.surface

    def draw_velocity(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        velocity = getattr(sprite, "velocity", None)
        if velocity is None:
            return
        try:
            vx, vy = float(velocity.x), float(velocity.y)
        except AttributeError, TypeError:
            return
        if vx * vx + vy * vy < VELOCITY_MIN_SPEED * VELOCITY_MIN_SPEED:
            return
        origin = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
        if origin is None:
            return
        color = Colors.debug_velocity
        if is_parry_flash(sprite):
            color = Colors.gold
        elif is_reaction_push(sprite):
            color = Colors.red  # reaction push vector, not locomotion
        self.draw_velocity_arrow(Vector2(camera.apply(origin).center), Vector2(vx, vy), color)

    def draw_velocity_arrow(self, start: Vector2, velocity: Vector2, color: Color) -> None:
        """Paint one velocity preview: rim, filled tapered shaft and arrowhead.

        Geometry recap — the tail leaves the entity thinner than the neck, the
        barbs flare at ``head_length`` from the tip, and the pivot dot marks
        where the sprite actually is. The dark rim is stroked first, then the
        colour fill covers its inner half, and an anti-aliased pass smooths the
        fill boundary on top (debug-only cost: a handful of visible sprites).
        """
        delta = velocity * VELOCITY_PREVIEW_S
        length = delta.length()
        if length <= 0.0:
            return
        direction = delta / length
        drawn_length = max(length, VELOCITY_MIN_LENGTH)
        head_length = min(
            max(drawn_length * VELOCITY_HEAD_RATIO, VELOCITY_HEAD_MIN),
            VELOCITY_HEAD_MAX,
            drawn_length,
        )
        points = arrow_outline(
            start,
            direction,
            drawn_length,
            head_length,
            min(head_length * VELOCITY_HEAD_WIDTH_RATIO, drawn_length * VELOCITY_HEAD_WIDTH_CAP),
        )
        pygame.draw.polygon(self.surface, VELOCITY_OUTLINE, points, width=VELOCITY_OUTLINE_WIDTH)
        pygame.draw.polygon(self.surface, color, points)
        pygame.gfxdraw.aapolygon(self.surface, points, color)

        pivot = (round(start.x), round(start.y))
        pygame.draw.circle(
            self.surface,
            VELOCITY_OUTLINE,
            pivot,
            VELOCITY_TAIL_RADIUS + VELOCITY_OUTLINE_WIDTH // 2,
        )
        pygame.draw.circle(self.surface, color, pivot, VELOCITY_TAIL_RADIUS)
        pygame.gfxdraw.aacircle(self.surface, *pivot, VELOCITY_TAIL_RADIUS, color)


def arrow_outline(
    start: Vector2,
    direction: Vector2,
    length: float,
    head_length: float,
    head_half_width: float,
) -> list[tuple[int, int]]:
    """Silhouette of a velocity arrow: a tapered shaft plus a triangular head.

    One single seven-point polygon (tail, neck, barb, tip, barb, neck, tail)
    so the shaft and the head can never leave a seam. ``direction`` must be a
    unit vector, ``start`` the screen-space pivot and ``length`` the drawn
    length (already floored to ``VELOCITY_MIN_LENGTH``).
    """
    normal = Vector2(-direction.y, direction.x)
    tip = start + direction * length
    neck = tip - direction * head_length
    corners = (
        start + normal * (VELOCITY_TAIL_WIDTH / 2.0),
        neck + normal * (VELOCITY_NECK_WIDTH / 2.0),
        neck + normal * head_half_width,
        tip,
        neck - normal * head_half_width,
        neck - normal * (VELOCITY_NECK_WIDTH / 2.0),
        start - normal * (VELOCITY_TAIL_WIDTH / 2.0),
    )
    return [(round(corner.x), round(corner.y)) for corner in corners]


def is_parry_flash(sprite: pygame.sprite.Sprite) -> bool:
    status = getattr(sprite, "reaction_status", None)
    if not isinstance(status, ReactionStatus):
        return False
    if status.kind is not ReactionKind.PARRIED:
        return False
    return float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0.0


def is_reaction_push(sprite: pygame.sprite.Sprite) -> bool:
    """Whether the vector is a hit reaction's push (red), not locomotion.

    The typed ``ReactionStatus`` cause stays the gate — a bare state name
    can never colour a vector — but it qualifies through two windows:

    - *fresh cause* (``reaction_age > 0``): the hit just landed, so the
      vector is the impulse it applied;
    - *carried by the cause*: the entity is still in ``KNOCKBACK_STATE``
      with a velocity-kind cause. A launch stays airborne far longer than
      the ``ReactionMark`` freshness window (up to
      ``Combat.KNOCKBACK_MAX_DURATION``) and its vector still comes from
      that knockback — wall bounce, directional influence and friction
      all rewrite it without re-arming the cause.

    Walking, dashing, an AI chase or the tail of a resolved knockback read
    as locomotion (yellow).
    """
    status = getattr(sprite, "reaction_status", None)
    if not isinstance(status, ReactionStatus) or status.kind not in VELOCITY_KINDS:
        return False
    if float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0.0:
        return True
    state_machine = getattr(sprite, "state_machine", None)
    return getattr(state_machine, "current_state_name", None) == KNOCKBACK_STATE
