import pygame
from typing import Optional
from src.core.settings import Debug
from src.ui.styles import PANEL_BG, PANEL_BORDER, TEXT_MUTED, TEXT_TITLE


class PanelRenderer:
    """Gère le rendu visuel des panneaux et le cache des polices."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface

        self.debug_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE)
        self.title_font = pygame.font.SysFont(
            "Consolas", Debug.FONT_SIZE, bold=True)
        self.label_font = pygame.font.SysFont(
            "Consolas", Debug.LABEL_FONT_SIZE)

        self._text_cache: dict[tuple, pygame.Surface] = {}

    def render_text(self, text: str, font: pygame.font.Font, color: tuple[int, int, int]) -> pygame.Surface:
        """Render text and cache it."""
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]

    def draw_panel(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: tuple[int, int, int, int] = PANEL_BG,
        text_color: tuple[int, int, int] = TEXT_MUTED,
        title: Optional[str] = None,
        line_colors: Optional[dict[int, tuple[int, int, int]]] = None,
    ) -> int:
        """Draw a semi-transparent debug panel with optional title and colored lines."""
        line_colors = line_colors or {}
        padding = 12
        line_height = 22
        title_gap = 8

        rendered_lines = [
            self.render_text(line, self.debug_font,
                             line_colors.get(i, text_color))
            for i, line in enumerate(lines)
        ]

        max_w = max((s.get_width() for s in rendered_lines), default=0)
        title_surf = None
        title_block_h = 0

        if title:
            title_surf = self.render_text(title, self.title_font, TEXT_TITLE)
            max_w = max(max_w, title_surf.get_width())
            title_block_h = title_surf.get_height() + title_gap + 1 + title_gap

        panel_w = max_w + padding * 2
        panel_h = title_block_h + len(lines) * line_height + padding * 2

        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg, color, (0, 0, panel_w, panel_h))
        pygame.draw.rect(bg, PANEL_BORDER, (0, 0, panel_w, panel_h), width=1)
        self.display_surface.blit(bg, (x, y))

        content_y = y + padding
        if title_surf:
            self.display_surface.blit(title_surf, (x + padding, content_y))
            content_y += title_surf.get_height() + title_gap
            pygame.draw.line(self.display_surface, PANEL_BORDER, (x +
                             padding, content_y), (x + panel_w - padding, content_y), 1)
            content_y += title_gap + 1

        for i, surf in enumerate(rendered_lines):
            self.display_surface.blit(
                surf, (x + padding, content_y + i * line_height))

        return panel_h + 12

    def get_panel_width(self, lines: list[str]) -> int:
        """Calcule la largeur d'un panneau pour le positionnement (ex: panel de performance à droite)."""
        max_w = max(self.render_text(line, self.debug_font,
                    TEXT_MUTED).get_width() for line in lines)
        return max_w + 24
