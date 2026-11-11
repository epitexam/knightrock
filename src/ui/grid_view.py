"""Framed grid panel: the controls screen's table of bindings.

A titled panel, an optional context line, column headers, one row per entry and
hint lines underneath, in the menus' look: the pixel font, the pixel-art frame
and one gold bar on what a press acts on.

The renderer draws what it is given and publishes what it painted --
``row_rects`` for the rows, ``cell_at`` for the cells -- so the screen can
hit-test them with its own vocabulary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pygame

from src.ui.fonts import MENU_FONT_GRID, menu_font, menu_font_size
from src.ui.menu_view import DESIGN_ITEM, DESIGN_SMALL, DESIGN_TITLE
from src.ui.metrics import (
    MIN_ROW_RATIO,
    MIN_TEXT_RATIO,
    Metrics,
)
from src.ui.pixel import line_step, pixel_frame
from src.ui.styles import (
    SELECTION_BG,
    SELECTION_FLASH,
    SELECTION_TEXT,
    TEXT_CRIT,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_TITLE,
    TEXT_WARN,
)

#: The lowest text scale a table too wide for its window may shrink to: the
#: item text at the pixel font's own grid, 8px, which it is drawn to be read at.
WIDTH_FLOOR = MENU_FONT_GRID / DESIGN_ITEM

#: The focused row's band, behind the solid bar of the focused cell: the row
#: says where you are, the bar says what a press acts on.
ROW_BAND_ALPHA = 40

#: What ``_layout`` hands back: the panel, the label gutter's x and the first
#: row's y, the column x positions, the cell and label widths, the row height and
#: the column-title band's height. Named because the drawing and the head painter
#: both take it, and a list of eight unnamed ints is a signature nobody can read.
Layout = tuple[pygame.Rect, int, int, tuple[int, ...], int, int, int, int]


@dataclass(frozen=True)
class GridCell:
    """One value of a row, with the two states the panel knows how to paint.

    ``warn`` marks a cell that is asking the player for something (the controls
    screen's capture prompt); ``muted`` marks a value that is empty or
    unavailable. Everything else is painted in the plain label colour, so a
    muted neighbour is what makes a real value stand out.
    """

    text: str
    warn: bool = False
    muted: bool = False


@dataclass(frozen=True)
class GridRow:
    """A labelled row of cells; ``cells`` must match the column headers."""

    label: str
    cells: tuple[GridCell | None, ...] = ()
    #: Whether a click *acts* rather than only focusing; the screen decides
    #: what acting means.
    activatable: bool = True
    #: A choice of the screen (invert Y, reset, back) rather than a value. Option
    #: rows open a group with a section gap above them, so they do not read as
    #: more things to assign.
    option: bool = False


@dataclass(frozen=True)
class CellHit:
    row: int
    column: int
    rect: pygame.Rect
    #: Whether a click here acts rather than only focusing. Every drawn cell is
    #: hit-testable either way, so hovering never skips a row.
    activatable: bool = True


class GridView:
    TEXT_CACHE_LIMIT = 512

    def __init__(self, scale: float = 1.0) -> None:
        self._metrics = Metrics.for_scale(scale)
        self._scale = self._metrics.scale
        self._text_scale = self._scale
        self._fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font] | None = None
        self._font_key: float | None = None
        self._surface_size: tuple[int, int] = (0, 0)
        self._cells: list[CellHit] = []
        self._row_rects: list[pygame.Rect] = []
        #: Where the column titles were painted, left to right. Published for the
        #: same reason as ``row_rects``: a screen that wants to align something
        #: with a column, or a test that wants to know two bands do not overlap,
        #: should not have to re-derive the layout.
        self._header_rects: list[pygame.Rect] = []
        #: The panel the last draw painted. Published for the same reason
        #: ``row_rects`` is: a screen that wants to place something against the
        #: panel would otherwise have to re-derive the layout it just asked for.
        self._last_panel_rect: pygame.Rect | None = None
        self._panel_cache: pygame.Surface | None = None
        self._panel_size: tuple[int, ...] = (0, 0)
        self._strip_cache: pygame.Surface | None = None
        self._strip_size: tuple[int, int] = (0, 0)
        self._text_cache: dict[tuple[int, str, tuple[int, int, int], int], pygame.Surface] = {}

    @property
    def row_rects(self) -> list[pygame.Rect]:
        """The row rectangles painted by the last draw, top to bottom.

        One per row, in the same order as the rows passed to ``draw``, which is
        how a screen maps a pointer position back to its own item list.
        """
        return self._row_rects

    @property
    def column_header_rects(self) -> list[pygame.Rect]:
        """Where the column titles were painted, left to right.

        Their bottom edge is the first row's top edge, and that is the whole
        point: the band is reserved in the layout and has to be *consumed* by
        the drawing, or the rows land on the titles.
        """
        return self._header_rects

    def cell_at(self, position: tuple[int, int]) -> CellHit | None:
        return next((cell for cell in self._cells if cell.rect.collidepoint(position)), None)

    def set_surface(self, surface: pygame.Surface) -> None:
        self._surface_size = surface.get_size()
        self._cells = []
        self._row_rects = []

    def set_scale(self, scale: float) -> None:
        self._metrics = Metrics.for_scale(scale)
        self._scale = self._metrics.scale

    def draw(
        self,
        surface: pygame.Surface,
        title: str,
        subtitle: str,
        column_headers: tuple[str, ...],
        rows: Sequence[GridRow],
        *,
        selected_row: int,
        selected_column: int,
        top: int,
        footers: tuple[str, ...] = (),
        reserve: tuple[str, ...] = (),
    ) -> pygame.Rect:
        """Draw the panel. ``reserve`` are texts a cell may show later -- a
        capture prompt -- that the columns are as wide as from the start, so the
        panel does not widen under the player when one appears."""
        layout = self._layout(surface, subtitle, rows, column_headers, top, footers, reserve)
        self._ensure_fonts()
        assert self._fonts is not None
        _, item_font, small_font = self._fonts
        panel_rect, x, y, columns, cell_width, label_width, row_height, _ = layout
        # Everything inside the frame is in the content scale, the one the
        # layout measured with: air taken from the player's scale is air the
        # layout did not count, and with a text that shrank far it adds up to
        # rows hanging out of the panel.
        content = Metrics(self._text_scale)
        metrics = content
        padding, gap = content.padding, content.gap
        section_gap = self._section_gap(content, row_height)

        y = self._draw_head(surface, layout, title, subtitle, column_headers, selected_column)
        self._cells = []
        self._row_rects = []
        # The text sits in the middle of its band, so a row that grew a taller
        # font grew around it instead of pushing it towards the row above.
        text_inset = max(0, (row_height - item_font.get_linesize()) // 2)
        inner_pad = max(1, metrics.px(4))
        for index, row in enumerate(rows):
            # The section gap opens a *group*, so only the first row of one
            # spends it: the rest of the block keeps the list's own rhythm. The
            # height it consumed was added to the panel by ``_layout``, which
            # counted the same boundaries -- otherwise the last row would hang
            # out of the panel by exactly the gap the panel was not told about.
            if row.option and not (index and rows[index - 1].option):
                y += section_gap
            row_rect = pygame.Rect(x, y, panel_rect.width - padding * 2, row_height)
            self._row_rects.append(row_rect)
            focused = index == selected_row
            # An option row is one target, so the bar covers it whole; a binding
            # row is a band, and the bar sits on the cell a press would capture.
            whole_row = focused and row.option
            if whole_row:
                surface.fill(SELECTION_BG, row_rect.inflate(inner_pad * 2, 0))
            elif focused:
                surface.blit(self._strip_for(row_rect.size), row_rect)
            surface.blit(
                self._render_cached(
                    item_font,
                    row.label,
                    SELECTION_TEXT if whole_row else TEXT_TITLE,
                    label_width - content.gap,
                ),
                (x, y + text_inset),
            )
            for column, cell in enumerate(row.cells):
                if cell is None:
                    continue
                cell_x = columns[column]
                # The hit box is the drawn row band, not a box around the glyphs,
                # so two rows never claim the same pixel.
                hit = pygame.Rect(cell_x - inner_pad, y, cell_width, row_height)
                on_bar = whole_row or (focused and column == selected_column)
                if on_bar and not whole_row:
                    # A cell waiting for a press is lit, like a value that changed.
                    surface.fill(SELECTION_FLASH if cell.warn else SELECTION_BG, hit)
                surface.blit(
                    self._render_cached(
                        item_font,
                        cell.text,
                        SELECTION_TEXT if on_bar else self._cell_color(cell, row.option),
                        cell_width - inner_pad,
                    ),
                    (cell_x, y + text_inset),
                )
                # Every drawn cell is registered: hovering a row that cannot be
                # acted on must still move the focus. The ``activatable`` flag
                # then tells the screen whether a click acts or only focuses.
                self._cells.append(CellHit(index, column, hit, row.activatable))
            y += row_height

        # The help line is muted like every menu's; a line above it is news
        # (a capture, a change) and is in the colour that asks to be read.
        step = line_step(small_font) + gap // 2
        footer_y = panel_rect.bottom - padding - small_font.get_linesize()
        for offset, footer in enumerate(reversed(footers)):
            surface.blit(
                self._render_cached(
                    small_font, footer, TEXT_MUTED if offset == 0 else TEXT_WARN, panel_rect.width
                ),
                (_centred_x(panel_rect, small_font.size(footer)[0]), footer_y),
            )
            footer_y -= step
        return panel_rect

    def _draw_head(
        self,
        surface: pygame.Surface,
        layout: Layout,
        title: str,
        subtitle: str,
        column_headers: tuple[str, ...],
        selected_column: int = -1,
    ) -> int:
        """The panel, its title, the subtitle and the column titles; returns the first row's y.

        The focused column's title is lit and the others faint. The header band
        the layout reserved is consumed here, so the first row never lands on
        the titles.
        """
        assert self._fonts is not None
        title_font, item_font, small_font = self._fonts
        panel_rect, _, y, columns, cell_width, _, _, header_height = layout
        content = Metrics(self._text_scale)
        padding, gap = content.padding, content.gap

        # One pixel of the item font's grid, as on the menus' panels.
        unit = max(1, item_font.get_height() // 8)
        surface.blit(self._panel_for(panel_rect.size, unit), panel_rect)
        # The title is centred because every other title in the game is, and a
        # left-aligned one above a centred subtitle reads as a mistake.
        painted = self._render_cached(title_font, title, TEXT_TITLE, panel_rect.width)
        surface.blit(painted, (_centred_x(panel_rect, painted.get_width()), panel_rect.y + padding))
        if subtitle:
            surface.blit(
                self._render_cached(small_font, subtitle, TEXT_MUTED, panel_rect.width),
                (_centred_x(panel_rect, small_font.size(subtitle)[0]), y),
            )
            y += small_font.get_height() + gap

        # Indexed rather than zipped with ``strict``: the layout keeps one column
        # when there are no titles, so a strict zip raised ValueError on a grid
        # that has rows and no headings -- a combination the layout explicitly
        # supports and no caller happened to use yet.
        self._header_rects = []
        for index, header in enumerate(column_headers):
            cell_x = columns[index]
            color = TEXT_WARN if index == selected_column else TEXT_FAINT
            painted_header = self._render_cached(small_font, header, color, cell_width)
            surface.blit(painted_header, (cell_x, y))
            self._header_rects.append(
                pygame.Rect(cell_x, y, painted_header.get_width(), header_height)
            )
        return y + header_height + gap if header_height else y

    def _layout(
        self,
        surface: pygame.Surface,
        subtitle: str,
        rows: Sequence[GridRow],
        column_headers: tuple[str, ...],
        top: int,
        footers: tuple[str, ...],
        reserve: tuple[str, ...] = (),
    ) -> Layout:
        """Panel, label gutter, cell columns, and the header band.

        The text scale is settled first, then the panel is sized around the
        measured text. A row is never shorter than its own glyphs.
        """
        metrics = self._metrics
        margin = metrics.margin
        budget = surface.get_height() - top - margin
        section_gaps = self._section_gap_count(rows)
        self._settle_text_scale(
            surface,
            len(rows),
            top,
            footers,
            budget,
            subtitle,
            column_headers,
            section_gaps,
            rows=rows,
            reserve=reserve,
        )
        self._ensure_fonts()
        assert self._fonts is not None
        title_font, item_font, small_font = self._fonts
        # Inside the frame everything is sized by the *content* scale, so a list
        # that gave up font size also gave up padding. Leaving the inner metrics
        # at the player's scale is what made the panel overflow while the text
        # inside it was still shrinking -- the box did not believe the text.
        content = Metrics(self._text_scale)
        padding, gap = content.padding, content.gap

        columns_count = max(1, len(column_headers))
        label_width, cell_width, width = self._column_widths(
            rows, column_headers, item_font, small_font, margin, padding, gap, surface, reserve
        )

        row_height = self._row_height(item_font, gap)
        height = self._height_of(
            title_font,
            item_font,
            small_font,
            content,
            row_height,
            len(rows),
            len(footers),
            bool(subtitle),
            bool(column_headers),
            section_gaps,
            self._section_gap(content, row_height),
        )
        width = max(width, label_width + cell_width * columns_count + gap * columns_count)
        width = min(width, surface.get_width() - margin * 2)
        panel = pygame.Rect(
            (surface.get_width() - width) // 2,
            min(top, max(margin, surface.get_height() - height - margin)),
            width,
            height,
        )
        x = panel.x + padding
        y = panel.y + padding + title_font.get_height() + content.title_gap
        columns = tuple(
            x + label_width + index * (cell_width + gap) for index in range(columns_count)
        )
        self._last_panel_rect = panel
        header_height = small_font.get_height() if column_headers else 0
        return panel, x, y, columns, cell_width, label_width, row_height, header_height

    def _settle_text_scale(
        self,
        surface: pygame.Surface,
        row_count: int,
        top: int,
        footers: Sequence[str],
        budget: int,
        subtitle: str,
        column_headers: Sequence[str],
        section_gaps: int = 0,
        *,
        rows: Sequence[GridRow] = (),
        reserve: tuple[str, ...] = (),
    ) -> None:
        """The largest text scale whose panel fits the window, found by measuring.

        Height is held to ``budget`` with a floor of :data:`MIN_TEXT_RATIO`;
        width is held to the window with the lower :data:`WIDTH_FLOOR`, because
        a column cut off at the edge is worse than the font at its native 8px.
        Font sizes snap to the pixel grid, so the scale is corrected by the
        measured ratio a few times.
        """
        metrics = self._metrics
        floor = metrics.scale * MIN_TEXT_RATIO
        text_scale = self._text_scale if self._text_scale <= metrics.scale else metrics.scale
        available = surface.get_width() - metrics.margin * 2
        for _ in range(5):
            self._text_scale = text_scale
            self._ensure_fonts()
            assert self._fonts is not None
            title_font, item_font, small_font = self._fonts
            content = Metrics(text_scale)
            height = self._height_of(
                title_font,
                item_font,
                small_font,
                content,
                self._row_height(item_font, content.gap),
                row_count,
                len(footers),
                bool(subtitle),
                bool(column_headers),
                section_gaps,
                self._section_gap(content, self._row_height(item_font, content.gap)),
            )
            _, _, width = self._column_widths(
                rows,
                tuple(column_headers),
                item_font,
                small_font,
                metrics.margin,
                content.padding,
                content.gap,
                surface,
                reserve,
                capped=False,
            )
            tall = height > budget and text_scale > floor
            wide = width > available and text_scale > WIDTH_FLOOR
            if not (tall or wide):
                break
            target = text_scale * 0.95
            if tall:
                target = min(target, text_scale * budget / max(1, height))
            if wide:
                target = min(target, text_scale * available / max(1, width))
            text_scale = max(WIDTH_FLOOR if wide else floor, target)
        self._text_scale = text_scale
        self._ensure_fonts()

    @staticmethod
    def _cell_color(cell: GridCell, option: bool) -> tuple[int, int, int]:
        """The colour one cell is painted in.

        A cell that is asking for something is red whatever row it is on, a
        cell with nothing to say is faint, and a cell on an option row is muted:
        a value painted in the binding colour there would claim to be a binding.
        """
        if cell.warn:
            return TEXT_CRIT
        if cell.muted:
            return TEXT_FAINT
        if option:
            return TEXT_MUTED
        return TEXT_TITLE

    @staticmethod
    def _section_gap_count(rows: Sequence[GridRow]) -> int:
        """How many section gaps ``rows`` asks for: one per group of option rows.

        Counted from the rows so ``draw`` and ``_layout`` spend the same gaps.
        """
        return sum(
            1
            for index, row in enumerate(rows)
            if row.option and not (index and rows[index - 1].option)
        )

    @staticmethod
    def _section_gap(content: Metrics, row_height: int) -> int:
        """The air that opens a group, never less than a row.

        The gap is the only thing marking the group, and the token shrinks with
        the text while the row does not.
        """
        return max(content.section_gap, row_height)

    def _row_height(self, item_font: pygame.font.Font, gap: int) -> int:
        """A band that fits its text with air, and never less than its text.

        ``MIN_ROW_RATIO`` is the floor on the band and the font is the floor on
        the band: the second one wins whenever they disagree, because a band
        shorter than its own glyphs is a band that hits the wrong row.
        """
        content = Metrics(self._text_scale)
        return max(
            round(content.row * MIN_ROW_RATIO),
            item_font.get_linesize() + max(1, gap // 2),
        )

    @staticmethod
    def _height_of(
        title_font: pygame.font.Font,
        item_font: pygame.font.Font,
        small_font: pygame.font.Font,
        content: Metrics,
        row_height: int,
        row_count: int,
        footer_count: int,
        has_subtitle: bool,
        has_headers: bool,
        section_gaps: int = 0,
        section_gap: int = 0,
    ) -> int:
        """The panel height for these fonts, measured rather than assumed.

        ``section_gaps`` groups each cost a section gap on top of their rows --
        the same air ``draw`` spends, so the panel is as tall as the picture it
        is about to paint.
        """
        head = content.padding + title_font.get_height() + content.title_gap
        if has_subtitle:
            head += small_font.get_height() + content.gap
        if has_headers:
            head += small_font.get_height() + content.gap
        return (
            head
            + row_height * row_count
            + section_gap * section_gaps
            + content.gap * (1 + footer_count)
            + line_step(small_font) * footer_count
        )

    def _column_widths(
        self,
        rows: Sequence[GridRow],
        column_headers: tuple[str, ...],
        item_font: pygame.font.Font,
        small_font: pygame.font.Font,
        margin: int,
        padding: int,
        gap: int,
        surface: pygame.Surface,
        reserve: tuple[str, ...] = (),
        *,
        capped: bool = True,
    ) -> tuple[int, int, int]:
        """The gutter, the widest cell, and the panel width that holds them.

        Measured from the text. ``capped=False`` leaves the gutter as wide as
        its longest label, the width the text scale is settled against.
        """
        columns_count = max(1, len(column_headers))
        label_width = max((item_font.size(row.label)[0] for row in rows), default=0)
        for header in column_headers:
            label_width = max(label_width, small_font.size(header)[0])
        # Plus the air the drawing leaves after a label: the first column starts
        # at the end of the gutter, and ``draw`` paints a label in
        # ``gutter - gap``, so a gutter measured without it cut the air out of
        # the longest label instead. Every table lost its own widest label to an
        # ellipsis that way -- "Reset to defau…", "New game short…".
        label_width += gap
        cell_width = 0
        for row in rows:
            for cell in row.cells:
                if cell is not None:
                    cell_width = max(cell_width, item_font.size(cell.text)[0])
        for header in column_headers:
            cell_width = max(cell_width, small_font.size(header)[0])
        for text in reserve:
            cell_width = max(cell_width, item_font.size(text)[0])
        cell_width += small_font.size(" ")[0] * 2
        # A gutter wider than half the panel leaves cells no room, so cap it at
        # a third and give the rest to the values, which are the wider text.
        if capped:
            label_width = min(label_width, self._max_panel_width(surface, margin) // 3)
        width = padding * 2 + label_width + cell_width * columns_count + gap * (columns_count - 1)
        return label_width, cell_width, width

    def _max_panel_width(self, surface: pygame.Surface, margin: int) -> int:
        return max(self._metrics.px(200), surface.get_width() - margin * 2)

    def _ensure_fonts(self) -> None:
        """The three faces at the settled text scale, rebuilt only when it changes.

        The text cache is keyed on ``id(font)``, so it is emptied when the
        fonts are replaced.
        """
        if self._fonts is not None and self._font_key == self._text_scale:
            return
        self._fonts = (
            menu_font(menu_font_size(DESIGN_TITLE, self._text_scale)),
            menu_font(menu_font_size(DESIGN_ITEM, self._text_scale)),
            menu_font(menu_font_size(DESIGN_SMALL, self._text_scale)),
        )
        if self._font_key is not None:
            self._text_cache.clear()
        self._font_key = self._text_scale

    def _panel_for(self, size: tuple[int, int], unit: int = 1) -> pygame.Surface:
        """The menus' pixel-art panel, rebuilt only when its size changes."""
        if self._panel_cache is None or self._panel_size != (*size, unit):
            self._panel_cache = pixel_frame(size[0], size[1], unit)
            self._panel_size = (*size, unit)
        return self._panel_cache

    def _strip_for(self, size: tuple[int, int]) -> pygame.Surface:
        """The focused row's faint band, rebuilt only when resized."""
        if self._strip_cache is None or self._strip_size != size:
            strip = pygame.Surface(size, pygame.SRCALPHA)
            strip.fill((*SELECTION_BG[:3], ROW_BAND_ALPHA))
            self._strip_cache = strip
            self._strip_size = size
        return self._strip_cache

    def _render_cached(
        self, font: pygame.font.Font, text: str, color: tuple[int, int, int], max_width: int
    ) -> pygame.Surface:
        """Render truncated text, memoised on (font, text, colour, width).

        The grid issues roughly 30 ``render`` calls per frame; without this each
        one allocated a Surface, which showed up as micro-freezes.
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
        """Render ``text`` cut to ``max_width``, with a trailing ellipsis.

        The longest fitting prefix is found by binary search, measuring the
        prefix *with* the ellipsis so the result never overhangs.
        """
        # No antialiasing: a pixel font blurred at its edges is not one.
        if not text or font.size(text)[0] <= max_width:
            return font.render(text, False, color)
        marker = "…"
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.size(text[:middle] + marker)[0] <= max_width:
                low = middle
            else:
                high = middle - 1
        if low == 0:
            # Not even the marker fits. An empty cell is honest; a marker that
            # overhangs is the defect this search exists to remove.
            return font.render("", False, color)
        return font.render(f"{text[:low].rstrip()}{marker}", False, color)


def _centred_x(panel: pygame.Rect, width: int) -> int:
    """The x that centres ``width`` pixels inside ``panel``."""
    return panel.x + max(0, (panel.width - width) // 2)
