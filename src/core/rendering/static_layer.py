"""Pre-painted frozen tile planes.

A level's terrain never moves, yet the renderer used to cull and blit its ~884
tiles every frame. :class:`BakedStaticLayer` paints each frozen plane once, at
the camera's density, into a level-sized surface; drawing a frame is then one
blit of the viewport slice. :class:`TileChunkIndex` stays the fallback for
levels whose baked surfaces would be too large, and for every test that wants
to inspect the plane sprite by sprite.

The baked surface is opaque and filled with the world's background colour:
that is exactly what ``Renderer.draw`` already put under the plane, so a
full-viewport copy composites identically without paying for alpha blending.

Positions are rounded the same way the camera rounds a blit: the source pixel
of a world coordinate is ``floor(x * density)`` and a sprite's scaled size is
``ceil(w * density)``. Adjacent tiles therefore share or overlap a pixel and
never open a seam.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Protocol

import pygame

#: Four bytes per pixel, and a ceiling per plane. A 2560x1920 level at the
#: density of a 1920x1080 window bakes to ~54 MB; at 2560x1440 it would be
#: ~123 MB, so that window keeps the chunk index instead. The fallback is a
#: correctness-preserving choice, not a refusal to draw the level.
MAX_BAKED_BYTES = 64 * 1024 * 1024

#: Opt-in, and deliberately off in the shipped build. Measured on this machine
#: with alternating A/B runs, a level-sized slice costs more to copy than the
#: ~115 tiles the chunk index leaves in a typical viewport: 7.4 ms vs 4.3 ms
#: per draw at 1920x1080, 3.4 ms vs 2.5 ms at 1152x648. The producer and its
#: tests stay in the tree so the measurement can be repeated on a machine with
#: a faster large-surface copy; see `docs/audit/performance-2026-11.md`.
ENABLE_BAKED_PLANES = False


class _FrozenSprite(Protocol):
    rect: pygame.Rect | pygame.FRect | None
    image: pygame.Surface | None


class BakedStaticLayer:
    """One frozen plane, painted once, in world-to-target pixel coordinates."""

    __slots__ = ("density", "surface")

    def __init__(self, surface: pygame.Surface, density: float) -> None:
        self.surface = surface
        self.density = density

    def slice(
        self, viewport: pygame.FRect, shift: tuple[float, float]
    ) -> tuple[pygame.Surface, pygame.Rect] | None:
        """The viewport-sized piece to blit, and where it lands on the target.

        ``shift`` is the camera's per-frame offset (``-offset + shake``). The
        source origin is rounded independently from the destination, exactly as
        the camera rounds each sprite, so the picture cannot drift by a Pixel
        when the camera crosses a fractional boundary.
        """
        density = self.density
        dest_x = math.floor((viewport.x + shift[0]) * density)
        dest_y = math.floor((viewport.y + shift[1]) * density)
        # The slice must land on the same pixel the camera would give each
        # sprite: floor((x + shift) * d). A baked pixel for x sits at
        # floor(x * d), so the source origin has to absorb floor(shift * d)
        # instead of rounding the viewport independently. Rounding the source
        # from the viewport shifts the whole terrain by a pixel whenever the
        # interpolated camera crosses a fraction.
        source_x = dest_x - math.floor(shift[0] * density)
        source_y = dest_y - math.floor(shift[1] * density)
        width = max(1, math.ceil(viewport.width * density))
        height = max(1, math.ceil(viewport.height * density))

        surface_w, surface_h = self.surface.get_size()
        left = max(0, source_x)
        top = max(0, source_y)
        right = min(surface_w, source_x + width)
        bottom = min(surface_h, source_y + height)
        if left >= right or top >= bottom:
            return None
        area = pygame.Rect(left, top, right - left, bottom - top)
        dest = pygame.Rect(
            dest_x + left - source_x, dest_y + top - source_y, area.width, area.height
        )
        return self.surface.subsurface(area), dest


def bake_static_layer(
    sprites: Iterable[_FrozenSprite],
    *,
    size: tuple[float, float],
    density: float,
    background: tuple[int, int, int],
    scale: Callable[[pygame.Surface], pygame.Surface],
    enabled: bool | None = None,
) -> BakedStaticLayer | None:
    """Paint ``sprites`` in draw order, or return ``None`` when too large.

    ``scale`` is the renderer's own magnifier: the baked plane and the moving
    sprites must use the identical nearest-neighbour scaling rule, or the world
    would be sharp in one plane and resampled in the other.
    """
    if (ENABLE_BAKED_PLANES if enabled is None else enabled) is False:
        return None
    sprites = tuple(sprites)
    if not sprites:
        return None
    width, height = math.ceil(size[0] * density), math.ceil(size[1] * density)
    if width * height * 4 > MAX_BAKED_BYTES:
        return None
    surface = pygame.Surface((width, height))
    # A converted plane copies to the converted target without a per-pixel
    # format conversion. Without a display (pure headless callers) there is no
    # format to follow, and the plain surface blits with the usual fallback.
    if pygame.display.get_surface() is not None:
        surface = surface.convert()
    surface.fill(background)
    for sprite in sprites:
        rect, image = sprite.rect, sprite.image
        if rect is None or image is None:
            continue
        surface.blit(scale(image), (math.floor(rect.x * density), math.floor(rect.y * density)))
    return BakedStaticLayer(surface, density)
