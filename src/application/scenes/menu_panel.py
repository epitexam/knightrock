"""Panneaux de menu partagés par les scènes (Phase 2 #4 bis : UI unifiée).

Les scènes applicatives (menu / pause / game over) dessinaient leur texte
avec ``pygame.font.Font(None, ...)`` brut, alors que les outils de debug
(``PanelRenderer``) ont un habillage dédié : fond semi-transparent,
bordure, titre, cache de glyphes.  Ce module factorise un panneau de
menu centré construit sur :class:`PanelRenderer` pour unifier le style —
avec un espacement généreux (titre 48 px, interligne 40 px) afin que les
options ne se chevauchent pas à la différence des panneaux debug
compacts (24 px / 22 px).
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
    """Dessine un panneau de menu centré (titre + lignes), thème debug.

    Le dimensionnement réutilise le cache de glyphes du renderer ; le
    dessin effectif est délégué à :meth:`PanelRenderer.draw_panel` avec
    un espacement plus aéré que les panneaux debug.

    Returns
    -------
    pygame.Rect
        Le rectangle occupé par le panneau (utile aux tests headless).
    """
    title_font = pygame.font.SysFont("Consolas", title_size, bold=True)
    title_surf = renderer.render_text(title, title_font, title_color)
    rendered = [renderer.render_text(line, renderer.debug_font, text_color) for line in lines]

    panel_w = max([s.get_width() for s in rendered] + [title_surf.get_width()]) + padding * 2
    if panel_w % 2:
        panel_w += 1  # centrage exact : un rect pair donne centerx entier
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
