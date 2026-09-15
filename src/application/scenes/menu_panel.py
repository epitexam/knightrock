"""Menu panels shared by the scenes (Phase 2 #4b: unified UI).

The application scenes (menu / pause / game over) used to draw their text
with raw ``pygame.font.Font(None, ...)`` while the debug tools
(``PanelRenderer``) have dedicated dressing: semi-transparent background,
border, title, glyph cache.  This module factors a centered menu panel built
on :class:`PanelRenderer` to unify the style — with generous spacing (48 px
title, 40 px line height) so options never overlap, unlike the compact debug
panels (24 px / 22 px).
"""

from __future__ import annotations

import pygame

from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_MUTED, TEXT_TITLE


def draw_centered_menu_panel(
    renderer: PanelRenderer,
    surface: pygame.Surface,
    title: str,
    lines: list[str],
    *,
    top: int = 180,
    title_color: tuple[int, int, int] = TEXT_TITLE,
    text_color: tuple[int, int, int] = TEXT_MUTED,
    title_size: int = 48,
    line_height: int = 40,
    padding: int = 28,
    title_gap: int = 16,
) -> pygame.Rect:
    """Draw a centered menu panel (title + lines), debug theme.

    Sizing reuses the renderer glyph cache; the actual drawing is delegated
    to :meth:`PanelRenderer.draw_panel` with airier spacing than debug panels.

    Returns
    -------
    pygame.Rect
        The rect occupied by the panel (useful for headless tests).
    """
    title_font = pygame.font.SysFont("Consolas", title_size, bold=True)
    title_surf = renderer.render_text(title, title_font, title_color)
    rendered = [renderer.render_text(line, renderer.debug_font, text_color) for line in lines]

    panel_w = max([s.get_width() for s in rendered] + [title_surf.get_width()]) + padding * 2
    if panel_w % 2:
        panel_w += 1  # exact centering: an even rect gives an integer centerx
    x = (surface.get_width() - panel_w) // 2
    height = renderer.draw_panel(
        x,
        top,
        lines,
        title=title,
        title_font=title_font,
        line_height=line_height,
        padding=padding,
        title_gap=title_gap,
    )
    return pygame.Rect(x, top, panel_w, height - padding)
