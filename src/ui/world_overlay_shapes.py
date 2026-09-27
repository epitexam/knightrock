"""Drawing a collision pose, and the dashed outlines that are not one.

Split out of ``world_overlay_geo.py``. Everything here turns a *shape* into
pixels: the three advanced poses the physics side can produce, and the dashed
rectangle used for a broad-phase bound and for a swing's ghost.

**A leaf, and the only module that knows what a pose is.** The box pass asks it
"draw this circle, capsule or turned box" and "draw this dashed rectangle", and
never asks it anything about a sprite, a phase or a frame. That is why it can be
its own file: the reverse question -- what shape does this sprite have -- is
answered somewhere else entirely, in the combat state, and this module never
looks at it.

**The rectangle fallback is deliberate.** A pose kind this module does not model
is drawn as an axis-aligned box of the pose's own size. Drawing something
approximately right beats drawing nothing: an overlay that silently skips a
hitbox is the one failure mode a debug layer cannot have, and the approximation
is visible as a box, which tells the reader the code did not know what it was
looking at.
"""

from __future__ import annotations

import math

import pygame

from src.combat.shapes import ShapeKind, ShapePose
from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_metrics import SWEEP_GHOST_WIDTH

__all__ = ["ShapeLayer", "dashed_edges"]


class ShapeLayer:
    """Paints collision poses and dashed outlines onto the overlay surface.

    Constructed once by ``GeoLayer`` and kept for the session.
    """

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer

    @property
    def surface(self) -> pygame.Surface:
        """The live render target, read through so a resize needs no push."""
        return self.renderer.surface

    def draw_shape(self, shape: ShapePose, color: Color, camera: Camera, width: int = 2) -> None:
        self.draw_shape_once(shape, Colors.debug_shape_outline, camera, width + 2)
        self.draw_shape_once(shape, color, camera, width)

    def draw_shape_once(
        self,
        shape: ShapePose,
        color: Color,
        camera: Camera,
        width: int,
    ) -> None:
        center = camera.apply(
            pygame.FRect(
                shape.position[0] - shape.size[0] / 2.0,
                shape.position[1] - shape.size[1] / 2.0,
                shape.size[0],
                shape.size[1],
            )
        ).center
        if shape.kind is ShapeKind.CIRCLE:
            pygame.draw.circle(self.surface, color, center, int(shape.size[0] / 2.0), width)
            return
        if shape.kind is ShapeKind.CAPSULE:
            radians = math.radians(shape.angle)
            half_length = shape.size[0] / 2.0
            offset = (
                math.cos(radians) * half_length,
                math.sin(radians) * half_length,
            )
            start = (round(center[0] - offset[0]), round(center[1] - offset[1]))
            end = (round(center[0] + offset[0]), round(center[1] + offset[1]))
            diameter = max(1, int(shape.size[1]))
            pygame.draw.line(self.surface, color, start, end, diameter)
            radius = diameter / 2.0
            pygame.draw.circle(self.surface, color, start, max(1, int(radius)), width)
            pygame.draw.circle(self.surface, color, end, max(1, int(radius)), width)
            return
        if shape.kind is ShapeKind.OBB:
            radians = math.radians(shape.angle)
            cosine = math.cos(radians)
            sine = math.sin(radians)
            half_width = shape.size[0] / 2.0
            half_height = shape.size[1] / 2.0
            points = []
            for local_x, local_y in (
                (-half_width, -half_height),
                (half_width, -half_height),
                (half_width, half_height),
                (-half_width, half_height),
            ):
                points.append(
                    (
                        int(round(center[0] + local_x * cosine - local_y * sine)),
                        int(round(center[1] + local_x * sine + local_y * cosine)),
                    )
                )
            pygame.draw.polygon(self.surface, color, points, width)
            return
        pygame.draw.rect(
            self.surface,
            color,
            camera.apply(
                pygame.FRect(
                    shape.position[0] - shape.size[0] / 2.0,
                    shape.position[1] - shape.size[1] / 2.0,
                    shape.size[0],
                    shape.size[1],
                )
            ),
            width=width,
        )

    def draw_dashed_rect(self, screen: pygame.FRect, color: Color) -> None:
        x, y, width, height = screen.x, screen.y, screen.width, screen.height
        for start, end in dashed_edges(x, y, width, height):
            pygame.draw.line(self.surface, color, start, end, SWEEP_GHOST_WIDTH)


def dashed_edges(
    x: float, y: float, width: float, height: float
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    step = 2 * SWEEP_GHOST_WIDTH + 2
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    cursor = x
    while cursor < x + width:
        end = min(cursor + SWEEP_GHOST_WIDTH + 2, x + width)
        edges.append(((cursor, y), (end, y)))
        edges.append(((cursor, y + height), (end, y + height)))
        cursor += step
    cursor = y
    while cursor < y + height:
        end = min(cursor + SWEEP_GHOST_WIDTH + 2, y + height)
        edges.append(((x, cursor), (x, end)))
        edges.append(((x + width, cursor), (x + width, end)))
        cursor += step
    return tuple(edges)
