"""Panneaux de menu partagés par les scènes (Phase 2 #4 bis : UI unifiée).

Les scènes applicatives (menu / pause / game over) dessinaient leur texte
avec ``pygame.font.Font(None, ...)`` brut, alors que les outils de debug
(``PanelRenderer``) ont un habillage dédié : fond semi-transparent,
bordure, titre, cache de glyphes.  Ce module factorise un panneau de
menu centré construit sur :class:`PanelRenderer` pour unifier le style.
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
) -> pygame.Rect:
    """Dessine un panneau de menu centré (titre + lignes), thème debug.

    Le dimensionnement réutilise le cache de glyphes du renderer ; le
    dessin effectif est délégué à :meth:`PanelRenderer.draw_panel`.

    Returns
    -------
    pygame.Rect
        Le rectangle occupé par le panneau (utile aux tests headless).
    """
    title_surf = renderer.render_text(title, renderer.title_font, title_color)
    rendered = [renderer.render_text(line, renderer.debug_font, text_color) for line in lines]

    padding = 12
    panel_w = max([s.get_width() for s in rendered] + [title_surf.get_width()]) + padding * 2
    x = (surface.get_width() - panel_w) // 2
    height = renderer.draw_panel(x, top, lines, title=title)
    return pygame.Rect(x, top, panel_w, height - 12)
