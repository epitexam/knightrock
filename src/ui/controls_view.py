"""Two-column keyboard/mouse and gamepad bindings view."""

from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.ui.styles import (
    PANEL_BG,
    PANEL_BORDER,
    TEXT_CRIT,
    TEXT_MUTED,
    TEXT_OK,
    TEXT_TITLE,
    TEXT_WARN,
)

KEYBOARD_COLUMN = 0
GAMEPAD_COLUMN = 1


class RowKind(StrEnum):
    REBIND = "rebind"
    BACK = "back"


@dataclass(frozen=True)
class BindingCell:
    text: str
    warn: bool = False
    muted: bool = False


@dataclass(frozen=True)
class BindingRow:
    label: str
    keyboard: BindingCell | None = None
    gamepad: BindingCell | None = None
    kind: RowKind = RowKind.REBIND

    @property
    def rebindable(self) -> bool:
        return self.kind is RowKind.REBIND


@dataclass(frozen=True)
class CellHit:
    row: int
    column: int
    rect: pygame.Rect
    rebindable: bool = True
    """Whether a click here starts a capture, as opposed to only focusing.

    Non-rebindable rows (the invert-Y toggle, Reset, Back) must still be
    hoverable, otherwise the pointer focus silently skips them: ``cell_at``
    is what the scene queries on hover, and a row missing from ``_cells``
    can never receive the focus highlight.
    """


class ControlsView:
    COLUMN_HEADERS = ("KEYBOARD / MOUSE", "GAMEPAD")
    TEXT_CACHE_LIMIT = 512

    def __init__(self, scale: float = 1.0) -> None:
        self._scale = self._valid_scale(scale)
        self._fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font] | None = None
        self._font_key: float | None = None
        self._surface_size: tuple[int, int] = (0, 0)
        self._cells: list[CellHit] = []
        self._row_rects: list[pygame.Rect] = []
        self._panel_cache: pygame.Surface | None = None
        self._panel_size: tuple[int, int] = (0, 0)
        self._strip_cache: pygame.Surface | None = None
        self._strip_size: tuple[int, int] = (0, 0)
        self._text_cache: dict[tuple[int, str, tuple[int, int, int], int], pygame.Surface] = {}

    @property
    def row_rects(self) -> list[pygame.Rect]:
        return self._row_rects

    def cell_at(self, position: tuple[int, int]) -> CellHit | None:
        return next((cell for cell in self._cells if cell.rect.collidepoint(position)), None)

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        self._surface_size = display_surface.get_size()
        self._cells = []
        self._row_rects = []

    def set_scale(self, scale: float) -> None:
        self._scale = self._valid_scale(scale)

    def draw(
        self,
        surface: pygame.Surface,
        title: str,
        subtitle: str,
        rows: list[BindingRow],
        *,
        selected_row: int,
        selected_column: int,
        top: int,
        footers: tuple[str, ...] = (),
    ) -> pygame.Rect:
        layout = self._layout(surface, subtitle, rows, top, footers)
        self._ensure_fonts()
        assert self._fonts is not None
        title_font, item_font, small_font = self._fonts
        panel_rect, x, y, columns, cell_width, label_width, row_height = layout
        padding, gap = 18, 18

        panel = self._panel_for(panel_rect.size)
        surface.blit(panel, panel_rect)
        surface.blit(
            self._render_cached(title_font, title, TEXT_TITLE, panel_rect.width),
            (x, panel_rect.y + padding),
        )
        if subtitle:
            surface.blit(
                self._render_cached(small_font, subtitle, TEXT_MUTED, panel_rect.width),
                (x, y),
            )
            y += small_font.get_height() + 8

        for cell_x, header in zip(columns, self.COLUMN_HEADERS, strict=True):
            surface.blit(
                self._render_cached(small_font, header, TEXT_MUTED, cell_width), (cell_x, y)
            )

        self._cells = []
        self._row_rects = []
        focus_rect: pygame.Rect | None = None
        for index, row in enumerate(rows):
            row_y = y + 26 + index * row_height
            row_rect = pygame.Rect(x, row_y, panel_rect.width - padding * 2, row_height)
            self._row_rects.append(row_rect)
            if index == selected_row:
                surface.blit(self._strip_for(row_rect.size), row_rect)
            surface.blit(
                self._render_cached(item_font, row.label, TEXT_OK, label_width - gap), (x, row_y)
            )
            cells = ((KEYBOARD_COLUMN, row.keyboard), (GAMEPAD_COLUMN, row.gamepad))
            for column, cell in cells:
                if cell is None:
                    continue
                cell_x = columns[column]
                color = TEXT_CRIT if cell.warn else TEXT_MUTED if cell.muted else TEXT_OK
                surface.blit(
                    self._render_cached(item_font, cell.text, color, cell_width - 8),
                    (cell_x, row_y),
                )
                hit = pygame.Rect(cell_x - 4, row_y - 2, cell_width, row_height)
                if index == selected_row and column == selected_column:
                    focus_rect = hit
                # Every drawn cell is registered: hovering a non-rebindable row
                # (invert Y, Reset, Back) must still move the focus. The
                # ``rebindable`` flag then tells the scene whether a click
                # starts a capture or activates the row.
                self._cells.append(CellHit(index, column, hit, row.rebindable))

        if focus_rect is not None:
            pygame.draw.rect(surface, TEXT_WARN, focus_rect, 1)

        footer_y = panel_rect.bottom - gap - 20 * len(footers)
        for footer in footers:
            surface.blit(
                self._render_cached(small_font, footer, TEXT_WARN, panel_rect.width),
                (x, footer_y),
            )
            footer_y += 20
        return panel_rect

    def _layout(
        self,
        surface: pygame.Surface,
        subtitle: str,
        rows: list[BindingRow],
        top: int,
        footers: tuple[str, ...],
    ) -> tuple[pygame.Rect, int, int, tuple[int, int], int, int, int]:
        self._ensure_fonts()
        assert self._fonts is not None
        _, _, small_font = self._fonts
        scale = self._scale
        margin, padding, gap = 12, 18, 18
        width = min(surface.get_width() - margin * 2, 900)
        head = 102 + (small_font.get_height() if subtitle else 0)
        available = max(80, surface.get_height() - top - 8)
        row_height = max(
            14,
            min(
                34,
                int(30 * scale),
                (available - head - gap - 20 * len(footers)) // max(1, len(rows)),
            ),
        )
        height = head + row_height * len(rows) + gap + 20 * len(footers)
        panel = pygame.Rect(
            (surface.get_width() - width) // 2,
            min(top, max(8, surface.get_height() - height - 8)),
            width,
            height,
        )
        x = panel.x + padding
        y = panel.y + padding + self._fonts[0].get_height()
        label_width = int(width * 0.34)
        cell_width = (width - padding * 2 - label_width - gap) // 2
        columns = (x + label_width, x + label_width + cell_width + gap)
        return panel, x, y, columns, cell_width, label_width, row_height

    def _ensure_fonts(self) -> None:
        if self._fonts is not None and self._font_key == self._scale:
            return
        self._fonts = (
            pygame.font.SysFont("Consolas", max(1, int(42 * self._scale)), bold=True),
            pygame.font.SysFont("Consolas", max(1, int(22 * self._scale))),
            pygame.font.SysFont("Consolas", max(1, int(18 * self._scale))),
        )
        self._font_key = self._scale

    def _panel_for(self, size: tuple[int, int]) -> pygame.Surface:
        """Return the filled panel background, rebuilt only when resized.

        Allocating and filling a full-panel ``SRCALPHA`` surface every frame
        was the single most expensive part of this view.
        """
        if self._panel_cache is None or self._panel_size != size:
            panel = pygame.Surface(size, pygame.SRCALPHA)
            panel.fill((*PANEL_BG[:3], 235))
            pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2)
            self._panel_cache = panel
            self._panel_size = size
        return self._panel_cache

    def _strip_for(self, size: tuple[int, int]) -> pygame.Surface:
        """Return the focus highlight strip, rebuilt only when resized."""
        if self._strip_cache is None or self._strip_size != size:
            strip = pygame.Surface(size, pygame.SRCALPHA)
            strip.fill((*TEXT_WARN[:3], 35))
            self._strip_cache = strip
            self._strip_size = size
        return self._strip_cache

    def _render_cached(
        self, font: pygame.font.Font, text: str, color: tuple[int, int, int], max_width: int
    ) -> pygame.Surface:
        """Render truncated text, memoised on (font, text, colour, width).

        The binding grid issues roughly 30 ``render`` calls per frame; without
        this each one allocated a Surface, which showed up as micro-freezes.
        """
        key = (id(font), text, color, max_width)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = self._fit(font, text, max_width, color)
            if len(self._text_cache) >= self.TEXT_CACHE_LIMIT:
                self._text_cache.clear()
            self._text_cache[key] = cached
        return cached

    @staticmethod
    def _fit(
        font: pygame.font.Font, text: str, max_width: int, color: tuple[int, int, int]
    ) -> pygame.Surface:
        """Render ``text`` truncated to ``max_width`` with a trailing ellipsis.

        The longest fitting prefix is found by binary search: a prefix's width
        grows monotonically with its length, and the previous
        shrink-one-character-at-a-time loop re-measured the whole remaining
        string on every iteration, which is quadratic and cost 0.83ms for a
        single long label.
        """
        if not text or font.size(text)[0] <= max_width:
            return font.render(text, True, color)
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.size(text[:middle])[0] <= max_width:
                low = middle
            else:
                high = middle - 1
        if low == 0:
            return font.render("", True, color)
        return font.render(f"{text[: low - 1]}…", True, color)

    @staticmethod
    def _valid_scale(scale: float) -> float:
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("UI scale must be 0.8, 1.0 or 1.2")
        return scale
