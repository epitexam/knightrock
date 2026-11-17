"""The pixel-art pieces every panel of the interface is drawn with.

The menus, the controls table and the debug panels share one look: a frame with
cut corners, a dark outline and a light rim, all on the pixel grid of the menu
font, and text spaced with the leading the pixel font does not carry itself.
"""

from __future__ import annotations

import pygame

from src.ui.styles import PANEL_BG, PANEL_BORDER

#: The panel's outline, darker than its fill.
FRAME_OUTLINE = (8, 9, 12)
#: How opaque a panel's fill is by default.
FRAME_ALPHA = 240


def pixel_frame(
    width: int,
    height: int,
    unit: int,
    fill: tuple[int, int, int, int] | None = None,
) -> pygame.Surface:
    """A panel of ``width`` x ``height``: fill, outline and rim, corners cut by ``unit``."""
    frame = pygame.Surface((width, height), pygame.SRCALPHA)
    frame.fill((0, 0, 0, 0))
    u = max(1, unit)
    frame.fill(FRAME_OUTLINE, pygame.Rect(u, 0, width - 2 * u, height))
    frame.fill(FRAME_OUTLINE, pygame.Rect(0, u, width, height - 2 * u))
    frame.fill(PANEL_BORDER, pygame.Rect(2 * u, u, width - 4 * u, height - 2 * u))
    frame.fill(PANEL_BORDER, pygame.Rect(u, 2 * u, width - 2 * u, height - 4 * u))
    inner = fill if fill is not None else (*PANEL_BG[:3], FRAME_ALPHA)
    frame.fill(inner, pygame.Rect(2 * u, 2 * u, width - 4 * u, height - 4 * u))
    return frame


def line_step(font: pygame.font.Font) -> int:
    """One line of text and its leading: the pixel font has none of its own."""
    return font.get_linesize() + max(2, font.get_linesize() // 2)


def font_unit(font: pygame.font.Font) -> int:
    """One pixel of the menu font's 8-pixel grid, at this font's size."""
    return max(1, font.get_height() // 8)
