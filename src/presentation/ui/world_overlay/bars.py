"""World-space health bars — a production path, not a debug one.

Extracted from ``world_ui.py``, and deliberately first: ``Level.draw`` calls
``renderer.draw_health_bars`` *before* it checks whether ``DEBUG`` is set, so
these bars are painted on every frame of a real game while the ~1800 lines of
debug drawing they were sitting in are not. A production code path inside a
debug module is the kind of boundary that decays quietly — it gets reviewed
with the debug layer's eye, and its tests get counted against the debug
layer's coverage.

**Stateless on purpose.** These four functions take the surface they draw on
rather than owning one. The alternative is a class holding a surface
reference, which brings a lifecycle with it: something to update on every
resize, and something to forget. The caller already has the surface and
already has to pass it, so passing it is the smaller surface area.

The label code depends on this module (``health_bar_rect`` answers "where is
the bar for this sprite", which the card has to dodge around) and this module
depends on nothing here. That direction is the point: the bar is a fact about
the world, and the cards are decoration arranged around it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pygame

from src.core.colors import Color
from src.presentation.rendering.camera import Camera
from src.presentation.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_OK, TEXT_WARN
from src.presentation.ui.world_overlay.metrics import (
    HEALTH_BAR_ANCHOR_GAP,
    HEALTH_BAR_HEIGHT,
    STUN_BAR_HEIGHT,
)

__all__ = [
    "draw_guard_marks",
    "draw_health_bars",
    "has_health_bar",
    "health_bar_rect",
    "health_colour",
    "stun_gauge",
]

#: The stun strip under a health bar: amber while it fills, pale while the
#: fighter is stunned and the strip counts the stun down.
STUN_COLOUR: Color = TEXT_WARN
STUNNED_COLOUR: Color = (255, 245, 170)


def has_health_bar(sprite: pygame.sprite.Sprite) -> bool:
    """Whether :func:`draw_health_bars` will draw a bar for this sprite.

    The player is excluded: its HP is read on the screen HUD (UI-7), and a
    world-space bar above it would be redundant. The gate is here rather than
    at the call site so the debug label cards reserve room for the same set
    of bars the draw pass actually paints — reserve for a bar that is never
    drawn and the card floats a gap above every entity on screen.
    """
    if getattr(sprite, "faction", None) == "player":
        return False
    if getattr(sprite, "is_dead", False):
        return False
    if not getattr(sprite, "max_health", 0):
        return False
    return getattr(sprite, "hitbox", None) is not None or getattr(sprite, "rect", None) is not None


def health_bar_rect(
    surface: pygame.Surface,
    sprite: pygame.sprite.Sprite,
    screen_rect: pygame.Rect | pygame.FRect,
) -> pygame.Rect | None:
    """The bar's rectangle, or ``None`` when this sprite has no bar.

    Responsive width (80% of the sprite's on-screen width, clamped to
    [30, 60] px and to the target) and a fixed vertical rhythm, so the stack
    entity -> bar -> card never overlaps.

    The bar sits above the entity; near the top of the screen, where there is
    no room, it flips below so it stays visible instead of clipping — and if
    there is no room below either, it is not drawn at all, because a bar half
    off the top of the screen is worse than no bar.
    """
    if not has_health_bar(sprite):
        return None
    screen_width = surface.get_width()
    screen_height = surface.get_height()
    bar_width = max(30, min(float(screen_rect.width) * 0.8, 60))
    bar_x = screen_rect.centerx - bar_width / 2
    bar_x = min(max(bar_x, 0), max(0, screen_width - bar_width))
    bar_y = float(screen_rect.top) - HEALTH_BAR_ANCHOR_GAP - HEALTH_BAR_HEIGHT
    if bar_y < 0:
        bar_y = float(screen_rect.bottom) + HEALTH_BAR_ANCHOR_GAP
        if bar_y + HEALTH_BAR_HEIGHT > screen_height:
            return None
    return pygame.Rect(int(bar_x), int(bar_y), int(bar_width), HEALTH_BAR_HEIGHT)


def health_colour(health: float, max_health: float) -> Color:
    """HP tint by remaining ratio: green, then warn orange, then crit red."""
    ratio = health / max_health if max_health else 0.0
    if ratio <= 0.25:
        return TEXT_CRIT
    if ratio <= 0.5:
        return TEXT_WARN
    return TEXT_OK


#: The guard mark: a bar along the front edge of an enemy, on the half it guards.
GUARD_COLOUR: Color = (120, 200, 255)
GUARD_MARK_WIDTH = 3


def guard_mark_rect(
    sprite: pygame.sprite.Sprite, screen_rect: pygame.Rect | pygame.FRect
) -> pygame.Rect | None:
    """Where the guard mark of ``sprite`` goes, or ``None`` if it holds no guard.

    The front edge of the fighter, its upper half for a high guard and its
    lower half for a low one: the half a slash has to avoid.
    """
    guard = getattr(sprite, "guard", None)
    value = getattr(guard, "value", None)
    if value not in ("high", "low"):
        return None
    half = float(screen_rect.height) / 2
    top = float(screen_rect.top) if value == "high" else float(screen_rect.top) + half
    facing_right = bool(getattr(sprite, "facing_right", True))
    x = float(screen_rect.right) if facing_right else float(screen_rect.left) - GUARD_MARK_WIDTH
    return pygame.Rect(int(x), int(top), GUARD_MARK_WIDTH, max(1, int(half)))


def draw_guard_marks(
    surface: pygame.Surface,
    entities: Iterable[pygame.sprite.Sprite],
    camera: Camera,
    screen_rects: Mapping[int, pygame.Rect | pygame.FRect] | None = None,
) -> None:
    """Draw the guard of every enemy holding one, on the half it guards."""
    for entity in entities:
        rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
        if rect is None or getattr(entity, "is_dead", False) or not camera.is_visible(rect):
            continue
        screen_rect = (screen_rects.get(id(entity)) if screen_rects else None) or camera.apply(rect)
        mark = guard_mark_rect(entity, screen_rect)
        if mark is not None:
            pygame.draw.rect(surface, GUARD_COLOUR, mark)


def stun_gauge(sprite: pygame.sprite.Sprite) -> tuple[float, Color] | None:
    """How full the stun strip is, and its colour; ``None`` for no strip.

    While it fills, the strip is the stun gauge. Once the fighter is stunned
    it is the time left to execute it, counting down.
    """
    stun_max = getattr(sprite, "stun_max", None)
    if not stun_max:
        return None
    if getattr(sprite, "is_stunned", False):
        duration = getattr(sprite, "stun_duration", 0.0)
        if duration <= 0.0:
            return None
        left = getattr(sprite, "stagger_timer", 0.0) / duration
        return max(0.0, min(1.0, left)), STUNNED_COLOUR
    ratio = max(0.0, min(1.0, getattr(sprite, "stun", 0.0) / stun_max))
    return (ratio, STUN_COLOUR) if ratio > 0.0 else None


def draw_health_bars(
    surface: pygame.Surface,
    entities: Iterable[pygame.sprite.Sprite],
    camera: Camera,
    screen_rects: Mapping[int, pygame.Rect | pygame.FRect] | None = None,
) -> list[pygame.Rect]:
    """Draw the always-on HP bars; return the rects they occupy.

    ``screen_rects`` maps ``id(sprite)`` to the rect the world pass actually
    blitted that sprite at. The render interpolates between simulation ticks,
    so a sprite is drawn partway towards its next position while
    ``camera.apply`` would place it at the current one. Anchoring the bar to
    the blitted rect keeps it on the sprite it belongs to instead of trailing
    half a tick behind it, which showed up as a horizontal stripe of stale
    bar-coloured pixels.

    The rects come back because a bar is not always inside its sprite's own
    rect — it flips below the entity near the top of the screen, and its
    minimum width is wider than a narrow sprite — so anything reasoning about
    what the bars covered needs them. The presentation does not: the whole
    target is repainted every frame.

    A fighter with a stun gauge gets a thin strip right under its bar, in the
    gap the bar leaves above the fighter (see :func:`stun_gauge`), and one
    holding a guard gets a mark on the half it guards (:func:`guard_mark_rect`).
    """
    drawn: list[pygame.Rect] = []
    fighters = tuple(entities)
    for entity in fighters:
        max_health = getattr(entity, "max_health", 0)
        if not max_health:
            continue

        health = getattr(entity, "health", 0)
        rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
        if rect is None or not camera.is_visible(rect):
            continue

        screen_rect = (screen_rects.get(id(entity)) if screen_rects else None) or camera.apply(rect)
        background_rect = health_bar_rect(surface, entity, screen_rect)
        if background_rect is None:
            continue
        drawn.append(background_rect)
        pygame.draw.rect(surface, (35, 37, 40), background_rect)
        health_ratio = max(0.0, min(1.0, health / max_health))
        health_width = background_rect.width * health_ratio
        color = health_colour(health, max_health)
        if health_width > 0:
            pygame.draw.rect(
                surface,
                color,
                (background_rect.x, background_rect.y, health_width, background_rect.height),
            )
        pygame.draw.rect(surface, PANEL_BORDER, background_rect, width=1)
        gauge = stun_gauge(entity)
        if gauge is not None:
            ratio, stun_colour = gauge
            width = int(background_rect.width * ratio)
            if width > 0:
                pygame.draw.rect(
                    surface,
                    stun_colour,
                    (background_rect.x, background_rect.bottom, width, STUN_BAR_HEIGHT),
                )
    draw_guard_marks(surface, fighters, camera, screen_rects)
    return drawn
