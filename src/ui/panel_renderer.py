import pygame

from src.core.settings import Debug
from src.ui.styles import PANEL_BG, PANEL_BORDER, TEXT_MUTED, TEXT_TITLE


class PanelLayout:
    """Column-flow placement for debug panels (responsive by construction).

    Panels stack downward from the top-left margin; a panel that would
    overflow the bottom edge wraps to a new column on the right instead
    of being cut off. Every position is clamped inside the display, so
    the stack stays fully visible at any window size and with any amount
    of panel content (combat lines come and go during play).
    """

    def __init__(self, width: int, height: int, *, margin: int = 10, gutter: int = 8) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.margin = margin
        self.gutter = gutter
        self._column_x = margin
        self._cursor_y = margin
        self._column_right = margin

    def _clamp_x(self, x: int, w: int) -> int:
        """Keep a panel inside the display horizontally."""
        max_x = self.width - self.margin - w
        if max_x <= self.margin:
            return self.margin
        return max(self.margin, min(x, max_x))

    def place(self, w: int, h: int) -> tuple[int, int]:
        """Reserve the next stacked slot for a ``w`` x ``h`` panel."""
        x, y = self._column_x, self._cursor_y
        if y > self.margin and y + h > self.height - self.margin:
            self._column_x = self._column_right + self.gutter
            x, y = self._column_x, self.margin
        x = self._clamp_x(x, w)
        self._column_right = max(self._column_right, x + w)
        self._cursor_y = y + h + self.gutter
        return x, y

    def place_top_right(self, w: int, h: int) -> tuple[int, int]:
        """Pin a panel (performance) to the top-right corner, clamped."""
        return self._clamp_x(self.width - self.margin - w, w), self.margin


class PanelRenderer:
    """Render debug panels and cache fonts."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface

        self.debug_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE)
        self.title_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE, bold=True)
        self.label_font = pygame.font.SysFont("Consolas", Debug.LABEL_FONT_SIZE)
        # World-space entity cards: compact fonts so the floating labels
        # stay readable without covering the sprites they describe.
        self.world_title_font = pygame.font.SysFont(
            "Consolas", Debug.WORLD_TITLE_FONT_SIZE, bold=True
        )
        self.world_label_font = pygame.font.SysFont("Consolas", Debug.WORLD_LABEL_FONT_SIZE)

        self._text_cache: dict[tuple, pygame.Surface] = {}

    def render_text(
        self, text: str, font: pygame.font.Font, color: tuple[int, int, int]
    ) -> pygame.Surface:
        """Render text and cache it."""
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]

    def measure_panel(
        self,
        lines: list[str],
        title: str | None = None,
        title_font: pygame.font.Font | None = None,
        line_height: int | None = None,
        padding: int = 12,
        title_gap: int = 8,
    ) -> tuple[int, int]:
        """Measure a panel without drawing it (layout pass before ``draw``)."""
        title_font = title_font or self.title_font
        line_height = line_height if line_height is not None else self.debug_font.get_linesize()

        max_w = 0
        for line in lines:
            max_w = max(max_w, self.render_text(line, self.debug_font, TEXT_MUTED).get_width())
        title_block_h = 0
        if title:
            title_surf = self.render_text(title, title_font, TEXT_TITLE)
            max_w = max(max_w, title_surf.get_width())
            title_block_h = title_surf.get_height() + title_gap + 1 + title_gap

        panel_w = max_w + padding * 2
        panel_h = title_block_h + len(lines) * line_height + padding * 2
        return panel_w, panel_h

    def draw_panel(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: tuple[int, int, int, int] = PANEL_BG,
        text_color: tuple[int, int, int] = TEXT_MUTED,
        title: str | None = None,
        line_colors: dict[int, tuple[int, int, int]] | None = None,
        title_font: pygame.font.Font | None = None,
        line_height: int | None = None,
        padding: int = 12,
        title_gap: int = 8,
        layout: PanelLayout | None = None,
    ) -> int:
        """Draw a semi-transparent debug panel with optional title and colored lines.

        The ``title_font`` / ``line_height`` / ``padding`` / ``title_gap``
        parameters let menu scenes breathe: the debug overlays keep the
        compact defaults while full-screen menus use larger spacing and a
        dedicated title font. ``line_height`` defaults to the font's own
        line advance so rows never overlap. With ``layout``, the ``x``/``y``
        hint is ignored: the panel is measured, placed by the column flow,
        and drawn there.
        """
        line_colors = line_colors or {}
        title_font = title_font or self.title_font
        line_height = line_height if line_height is not None else self.debug_font.get_linesize()

        if layout is not None:
            panel_w, panel_h = self.measure_panel(
                lines,
                title=title,
                title_font=title_font,
                line_height=line_height,
                padding=padding,
                title_gap=title_gap,
            )
            x, y = layout.place(panel_w, panel_h)

        rendered_lines = [
            self.render_text(line, self.debug_font, line_colors.get(i, text_color))
            for i, line in enumerate(lines)
        ]

        max_w = max((s.get_width() for s in rendered_lines), default=0)
        title_surf = None
        title_block_h = 0

        if title:
            title_surf = self.render_text(title, title_font, TEXT_TITLE)
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
            pygame.draw.line(
                self.display_surface,
                PANEL_BORDER,
                (x + padding, content_y),
                (x + panel_w - padding, content_y),
                1,
            )
            content_y += title_gap + 1

        for i, surf in enumerate(rendered_lines):
            self.display_surface.blit(surf, (x + padding, content_y + i * line_height))

        return panel_h + padding

    def get_panel_width(self, lines: list[str]) -> int:
        """Compute panel width for positioning (e.g., performance panel on the right)."""
        max_w = max(
            self.render_text(line, self.debug_font, TEXT_MUTED).get_width() for line in lines
        )
        return max_w + 24
