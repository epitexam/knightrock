"""Framed grid panel shared by the menu screens that show columns of values.

The controls screen and the resolution picker are the same picture: a bordered
panel with a title, an optional context line, column headers, one row per entry,
a full-width strip on the focused row and one hint line per footer. Only the
*content* differs, so the panel itself is drawn once, here, and each screen
supplies its own headers and rows.

The renderer is deliberately dumb. It draws what it is given and publishes what
it painted — ``row_rects`` for the rows, ``cell_at`` for the cells — so the
screen can hit-test them with its own vocabulary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pygame

from src.ui.metrics import (
    MIN_ROW_RATIO,
    MIN_TEXT_RATIO,
    Metrics,
)
from src.ui.styles import (
    PANEL_BG,
    PANEL_BORDER,
    TEXT_CRIT,
    TEXT_MUTED,
    TEXT_OK,
    TEXT_TITLE,
    TEXT_WARN,
)

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
    activatable: bool = True
    """Whether clicking this row *acts*, as opposed to only moving the focus.

    The panel does not interpret it: it reports it in :class:`CellHit` and lets
    the screen decide. A toggle or a Back row is ``activatable``; a row whose
    click would open a capture it could never fill is not.
    """
    option: bool = False
    """This row is an *option* of the screen, not one of its values.

    A mapping screen is two kinds of thing in one table: the rows you assign a
    key to, and the rows you pick -- invert the Y axis, reset, go back. Painted
    the same way, the second kind reads as the first, so a player counts
    "Reset to defaults" among the things to be remapped and looks for a key to
    press on it.

    So an option row opens a group: a :attr:`~Metrics.section_gap` above it, and
    its own text in the muted colour. The gap is the part that matters -- it is
    what makes the block read as a block, from the top of the table, without a
    caption.
    """


@dataclass(frozen=True)
class CellHit:
    row: int
    column: int
    rect: pygame.Rect
    activatable: bool = True
    """Whether a click here acts, as opposed to only focusing.

    Non-activatable rows (a toggle, Reset, Back) must still be hoverable,
    otherwise the pointer focus silently skips them: ``cell_at`` is what the
    screen queries on hover, and a row missing from ``_cells`` can never
    receive the focus highlight.
    """


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
        self._panel_size: tuple[int, int] = (0, 0)
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
    ) -> pygame.Rect:
        layout = self._layout(surface, subtitle, rows, column_headers, top, footers)
        self._ensure_fonts()
        assert self._fonts is not None
        _, item_font, small_font = self._fonts
        panel_rect, x, y, columns, cell_width, label_width, row_height, _ = layout
        metrics = self._metrics
        padding, gap = metrics.padding, metrics.gap
        # The gutter was *measured* in the content scale, so the air left after a
        # label has to be counted in that scale too: taking it from the player's
        # scale took a pixel more than the layout gave, and the longest label in
        # the table lost it to an ellipsis.
        content = Metrics(self._text_scale)
        section_gap = self._section_gap(content, row_height)

        y = self._draw_head(surface, layout, title, subtitle, column_headers)
        self._cells = []
        self._row_rects = []
        focus_rect: pygame.Rect | None = None
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
            if index == selected_row:
                surface.blit(self._strip_for(row_rect.size), row_rect)
                # The ring starts as the whole row: on a row that is an option
                # and not a cell, the row *is* the target, and there is no cell
                # to box. A cell in the focused column narrows it, below.
                focus_rect = row_rect
            surface.blit(
                self._render_cached(
                    item_font,
                    row.label,
                    TEXT_MUTED if row.option else TEXT_OK,
                    label_width - content.gap,
                ),
                (x, y + text_inset),
            )
            for column, cell in enumerate(row.cells):
                if cell is None:
                    continue
                cell_x = columns[column]
                surface.blit(
                    self._render_cached(
                        item_font,
                        cell.text,
                        self._cell_color(cell, row.option),
                        cell_width - inner_pad,
                    ),
                    (cell_x, y + text_inset),
                )
                # The hit box is the drawn row band, not a box around the glyphs:
                # it used to start 2px above its own row, which overlapped the
                # row above it, so a click near a boundary acted on whichever of
                # the two rectangles was tested first.
                hit = pygame.Rect(cell_x - inner_pad, y, cell_width, row_height)
                if index == selected_row and column == selected_column:
                    focus_rect = hit
                # Every drawn cell is registered: hovering a row that cannot be
                # acted on must still move the focus. The ``activatable`` flag
                # then tells the screen whether a click acts or only focuses.
                self._cells.append(CellHit(index, column, hit, row.activatable))
            y += row_height

        if focus_rect is not None:
            pygame.draw.rect(surface, TEXT_WARN, focus_rect, 1)

        footer_y = panel_rect.bottom - padding - small_font.get_linesize()
        for footer in reversed(footers):
            surface.blit(
                self._render_cached(small_font, footer, TEXT_WARN, panel_rect.width),
                (_centred_x(panel_rect, small_font.size(footer)[0]), footer_y),
            )
            footer_y -= small_font.get_linesize() + gap // 2
        return panel_rect

    def _draw_head(
        self,
        surface: pygame.Surface,
        layout: Layout,
        title: str,
        subtitle: str,
        column_headers: tuple[str, ...],
    ) -> int:
        """The panel, its title, the subtitle and the column titles.

        Returns the y the first row starts at. The column titles are drawn here
        rather than where they are painted, and *this* is why: the layout
        reserved the height of that band, and the drawing has to consume it or
        the first row lands on the titles -- two texts at the same y, which
        reads as "the title is glued to the column" rather than as the bug it
        is. A layout that reserves space it does not spend is invisible in
        every screenshot and obvious in two numbers.
        """
        assert self._fonts is not None
        title_font, _, small_font = self._fonts
        panel_rect, _, y, columns, cell_width, _, _, header_height = layout
        padding, gap = self._metrics.padding, self._metrics.gap

        surface.blit(self._panel_for(panel_rect.size), panel_rect)
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
            painted_header = self._render_cached(small_font, header, TEXT_MUTED, cell_width)
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
    ) -> Layout:
        """Panel, label gutter, cell columns, and the header band's top and height.

        The order matters and it is the whole of the responsiveness: the *text*
        decides how much room it needs, so it is measured first, at a scale it
        has been given the chance to give up. Only then is the panel sized around
        it -- driven by the content, not by a 900px desktop cap that ignored both
        the window and the text inside it.

        The row height is then the height of the text plus its padding. The old
        version took ``min(34, ...)`` of that and got 34 while the text was 49:
        a clickable band 44% the size of the label it labelled, so clicking the
        row you read selected the row above. A row may be tight; it may not be
        shorter than its own glyphs.
        """
        metrics = self._metrics
        margin = metrics.margin
        budget = surface.get_height() - top - margin
        section_gaps = self._section_gap_count(rows)
        self._settle_text_scale(
            surface, len(rows), top, footers, budget, subtitle, column_headers, section_gaps
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
            rows, column_headers, item_font, small_font, margin, padding, gap, surface
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
    ) -> None:
        """The largest text scale whose panel fits in ``budget``, found by measuring.

        Not computed from the design constants, because they are wrong about the
        font: a 22px Consolas has a line box taller than 22, and on a machine
        without Consolas the fallback has a different one again. So the height is
        *measured* with the real fonts and the scale corrected by the ratio, at
        most three times -- after the first, the answer is within a pixel or two,
        because font height is very nearly linear in size.

        The floor is :data:`MIN_TEXT_RATIO`: a scale the window cannot afford at
        any legible size keeps the legible size and overflows, which is the trade
        this makes on purpose. A label nobody can read is not an option, and a
        window smaller than the interface at the player's own chosen scale is
        theirs to resolve.
        """
        metrics = self._metrics
        floor = metrics.scale * MIN_TEXT_RATIO
        text_scale = self._text_scale if self._text_scale <= metrics.scale else metrics.scale
        for _ in range(3):
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
            if height <= budget or text_scale <= floor:
                break
            text_scale = max(floor, text_scale * budget / max(1, height))
        self._text_scale = text_scale
        self._ensure_fonts()

    @staticmethod
    def _cell_color(cell: GridCell, option: bool) -> tuple[int, int, int]:
        """The colour one cell is painted in.

        A cell that is asking for something is red whatever row it is on, a
        cell with nothing to say is muted, and a cell on an option row is muted
        too: the whole block is one register, and a value painted in the value
        colour inside it would claim to be a binding.
        """
        if cell.warn:
            return TEXT_CRIT
        if cell.muted or option:
            return TEXT_MUTED
        return TEXT_OK

    @staticmethod
    def _section_gap_count(rows: Sequence[GridRow]) -> int:
        """How many section gaps ``rows`` asks for.

        One per *group* of option rows, not one per option row: a block of three
        choices is separated from the values above it once, and keeps the list's
        own row pitch inside itself. Counted from the rows rather than kept as a
        number the caller passes, because ``draw`` and ``_layout`` must spend the
        same gaps or the panel is sized for a list that is not the one it paints.
        """
        return sum(
            1
            for index, row in enumerate(rows)
            if row.option and not (index and rows[index - 1].option)
        )

    @staticmethod
    def _section_gap(content: Metrics, row_height: int) -> int:
        """The air that opens a group, and never less than a row.

        ``content.section_gap`` is a multiple of the *text* scale, and a list
        that does not fit shrinks that scale while the font -- and therefore the
        row -- stays legible. On a small window the token ends up below the row
        it was meant to separate, and the block of options is then not set apart
        at all: the gap is the only thing marking the group, so it is floored on
        the row.
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
            + small_font.get_linesize() * footer_count
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
    ) -> tuple[int, int, int]:
        """The gutter, the widest cell, and the panel width that holds them.

        Measured, not assumed: a fixed 34% gutter leaves a short label a hole the
        size of a long one, and the panel stops being as wide as its own content.
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
        cell_width += small_font.size(" ")[0] * 2
        # A gutter wider than half the panel leaves cells no room, so cap it at
        # a third and give the rest to the values, which are the wider text.
        label_width = min(label_width, self._max_panel_width(surface, margin) // 3)
        width = padding * 2 + label_width + cell_width * columns_count + gap * (columns_count - 1)
        return label_width, cell_width, width

    def _max_panel_width(self, surface: pygame.Surface, margin: int) -> int:
        return max(self._metrics.px(200), surface.get_width() - margin * 2)

    def _ensure_fonts(self) -> None:
        """The three faces at the scale the list can afford, rebuilt only on change.

        The rendered-text cache is keyed on ``id(font)``, so rebuilding these
        every frame -- which a layout pass that wants a fresh font will happily
        do -- would miss the whole cache and re-render thirty strings a frame.
        The key also means a stale entry is worse than a missing one, so the
        cache is emptied at the only moment the fonts change: a resize.
        """
        if self._fonts is not None and self._font_key == self._text_scale:
            return
        self._fonts = (
            pygame.font.SysFont(
                "Consolas", self._metrics.title_text_at(self._text_scale), bold=True
            ),
            pygame.font.SysFont("Consolas", self._metrics.item_text_at(self._text_scale)),
            pygame.font.SysFont("Consolas", self._metrics.small_text_at(self._text_scale)),
        )
        if self._font_key is not None:
            self._text_cache.clear()
        self._font_key = self._text_scale

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


def _centred_x(panel: pygame.Rect, width: int) -> int:
    """The x that centres ``width`` pixels inside ``panel``."""
    return panel.x + max(0, (panel.width - width) // 2)
