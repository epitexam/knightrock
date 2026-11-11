from collections.abc import Sequence
from dataclasses import dataclass, field

import pygame

from src.core.display.framing import DEFAULT_FRAMING
from src.ui.fonts import menu_font, menu_font_size
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.metrics import Metrics
from src.ui.scale import FONT_CACHE_ENTRIES, checked_ui_scale
from src.ui.styles import (
    GOLD,
    PANEL_BG,
    PANEL_BORDER,
    SELECTION_BG,
    SELECTION_FLASH,
    SELECTION_TEXT,
    TEXT_MUTED,
    TEXT_TITLE,
    TEXT_WARN,
)

#: The menu's text sizes, in design pixels of a 648-tall picture.
DESIGN_TITLE = 32
DESIGN_ITEM = 16
DESIGN_SMALL = 12
#: How many lines a row's description may take, and the narrowest it wraps at.
DESCRIPTION_LINES = 2
DESCRIPTION_MIN_WIDTH = 480


#: The panel's outline, darker than its fill.
FRAME_OUTLINE = (8, 9, 12)


def _pixel_frame(width: int, height: int, unit: int) -> pygame.Surface:
    """A panel of ``width`` x ``height``: fill, outline and rim, corners cut."""
    frame = pygame.Surface((width, height), pygame.SRCALPHA)
    frame.fill((0, 0, 0, 0))
    u = max(1, unit)
    # The outline: the whole panel less its four corner units.
    frame.fill(FRAME_OUTLINE, pygame.Rect(u, 0, width - 2 * u, height))
    frame.fill(FRAME_OUTLINE, pygame.Rect(0, u, width, height - 2 * u))
    # The rim, one unit in, corners cut the same way.
    frame.fill(PANEL_BORDER, pygame.Rect(2 * u, u, width - 4 * u, height - 2 * u))
    frame.fill(PANEL_BORDER, pygame.Rect(u, 2 * u, width - 2 * u, height - 4 * u))
    # The fill, inside the rim.
    frame.fill((*PANEL_BG[:3], 240), pygame.Rect(2 * u, 2 * u, width - 4 * u, height - 4 * u))
    return frame


def _line_step(font: pygame.font.Font) -> int:
    """One line of small text and its leading: the pixel font has none of its own."""
    return font.get_linesize() + max(2, font.get_linesize() // 2)


def _decorated(item: MenuItem, selected: bool) -> str:
    """A row's value with what pressing it does: ``›`` opens, ``◀ ▶`` changes.

    The arrows are drawn on the selected row only, and spaces stand in for them
    elsewhere, so the column keeps its width as the selection moves.
    """
    if item.kind in ("list", "page"):
        return f"{item.value} ›" if item.value else "›"
    if item.kind == "toggle":
        return f"◀ {item.value} ▶" if selected else f"  {item.value}  "
    return item.value


@dataclass(frozen=True)
class PlacedRow:
    """One row as laid out: its rect, its text, and its bar colour if selected."""

    rect: pygame.Rect
    label: pygame.Surface
    value: pygame.Surface | None
    bar: tuple[int, int, int] | None


@dataclass(frozen=True)
class MenuLayout:
    """Everything :meth:`MenuView.paint` blits, already placed.

    Text pieces are ``(surface, topleft)`` pairs.
    """

    panel: pygame.Rect
    frame: pygame.Surface
    title: tuple[pygame.Surface, tuple[int, int]]
    rows: list[PlacedRow]
    bar_inflate: int
    rail: pygame.Rect | None
    thumb: pygame.Rect | None
    description: tuple[pygame.Surface, tuple[int, int]] | None
    footers: list[tuple[pygame.Surface, tuple[int, int]]] = field(default_factory=list)


@dataclass(frozen=True)
class _Bands:
    """The vertical budget of one layout: row height, shown rows, footer bands."""

    item_height: int
    first: int
    visible: int
    footer_step: int
    description_height: int


@dataclass(frozen=True)
class _Content:
    """The rendered text of one layout and the panel width that holds it."""

    title: pygame.Surface
    labels: list[pygame.Surface]
    values: list[pygame.Surface | None]
    description: pygame.Surface | None
    footers: list[pygame.Surface]
    panel_width: int


class MenuView:
    def __init__(self, scale: float = 1.0) -> None:
        self._metrics = Metrics.for_scale(scale)
        self._scale = self._metrics.scale
        self._item_rects: list[pygame.Rect] = []
        self._fonts: dict[tuple[int, int, int], tuple[pygame.font.Font, ...]] = {}
        self._panel_cache: pygame.Surface | None = None
        self._panel_cache_size: tuple[int, ...] = (0, 0)
        self._surface_size: tuple[int, int] = (0, 0)
        # The scroll rail's geometry from the last draw, or None when
        # the list fit and nothing scrolls. Kept rather than painted
        # blind so a caller can ask "is there more below" the same way
        # it asks for the row rects.
        self._scroll_rail: pygame.Rect | None = None
        self._scroll_thumb: pygame.Rect | None = None
        # The description's width after being fitted, from the last draw.
        self._description_width = 0
        # The widest the panel has been for the rows it is showing, so it only
        # ever grows while the same screen is up. See ``draw``.
        self._width_key: tuple[object, ...] | None = None
        self._sticky_width = 0
        # Rendered-text cache. One .render() per frame per item allocates a
        # Surface and triggers GC, which shows up as micro-freezes at 60fps.
        # Keyed by (font id, text, colour); invalidated on selection change.
        self._text_cache: dict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = {}
        self._text_cache_key: (
            tuple[tuple[str, ...], tuple[str, ...], int, float, str, int] | None
        ) = None

    @property
    def item_rects(self) -> Sequence[pygame.Rect]:
        """Live item rectangles from the last draw.

        Returned without copying: the list is rebuilt in ``draw`` and no caller
        mutates it, so copying it on every routed input only allocated.
        """
        return self._item_rects

    @property
    def scroll_rail(self) -> pygame.Rect | None:
        """The rail of a list that scrolls, or ``None`` when it fits.

        The rail says "there is more" without the player having to
        scroll and find out -- a list cut off with no mark is a list
        whose last visible row reads as the last row.
        """
        return self._scroll_rail

    @property
    def scroll_thumb(self) -> pygame.Rect | None:
        """The thumb inside :attr:`scroll_rail`, at the position in force.

        Its height is the visible fraction of the list and its place
        is the scrolled-to fraction, so it answers "how much is left"
        and "how far in" in one shape.
        """
        return self._scroll_thumb

    @property
    def description_width(self) -> int:
        """How wide the description was drawn, after being fitted.

        The description is the one line of prose that can outgrow its
        panel, and this is the width it was *given* rather than the
        one it asked for -- which is the number that says whether a
        note was cut.
        """
        return self._description_width

    @staticmethod
    def scaled_top(top: int, surface: pygame.Surface) -> int:
        """A panel's ``top``, given in design pixels of a 648-tall picture.

        Scaled with the target's height, so a menu sits at the same place on a
        640x360 picture and on a 3840x2160 one instead of eating half of the first
        and hugging the top of the second.
        """
        return round(top * surface.get_height() / DEFAULT_FRAMING.height)

    @staticmethod
    def design_y(y: int, surface: pygame.Surface) -> int:
        """The inverse of :meth:`scaled_top`: a target y in design pixels."""
        return round(y * DEFAULT_FRAMING.height / max(1, surface.get_height()))

    def set_scale(self, scale: float) -> None:
        """Set the UI scale, discarding caches only when it really changed.

        Several scenes call this from ``draw()`` with the current setting on
        every frame. Invalidating the font/panel/text caches unconditionally
        rebuilt two ``SysFont`` objects and re-rendered every label each frame
        (0.82ms instead of 0.07ms at 1920x1080), so an unchanged scale must
        be a no-op.
        """
        scale = self._valid_scale(scale)
        if scale == self._scale:
            return
        self._scale = scale
        self._metrics = Metrics.for_scale(scale)
        self.reset_cache()

    def set_surface(self, surface: pygame.Surface) -> None:
        size = surface.get_size()
        if size == self._surface_size:
            return
        self._surface_size = size
        self.reset_cache()

    def draw(
        self,
        surface: pygame.Surface,
        title: str,
        model: MenuModel,
        *,
        top: int,
        title_color: tuple[int, int, int] = TEXT_TITLE,
        highlighted: int = -1,
        highlight_color: tuple[int, int, int] = GOLD,
        footers: tuple[str, ...] = (),
        description: str = "",
        scroll: int = 0,
        scrollable: bool = False,
    ) -> pygame.Rect:
        """Lay the panel out, paint it, and return its rect.

        The two halves are :meth:`layout`, which measures and places everything
        and paints nothing, and :meth:`paint`, which blits what the layout
        placed and decides nothing. See :meth:`layout` for the arguments.
        """
        placed = self.layout(
            surface,
            title,
            model,
            top=top,
            title_color=title_color,
            highlighted=highlighted,
            highlight_color=highlight_color,
            footers=footers,
            description=description,
            scroll=scroll,
            scrollable=scrollable,
        )
        self.paint(surface, placed)
        return placed.panel

    def layout(
        self,
        surface: pygame.Surface,
        title: str,
        model: MenuModel,
        *,
        top: int,
        title_color: tuple[int, int, int] = TEXT_TITLE,
        highlighted: int = -1,
        highlight_color: tuple[int, int, int] = GOLD,
        footers: tuple[str, ...] = (),
        description: str = "",
        scroll: int = 0,
        scrollable: bool = False,
    ) -> MenuLayout:
        """Measure and place the panel for ``surface``; paint nothing.

        It also publishes what a hit-test needs -- :attr:`item_rects` and the
        scroll rail -- because a click is measured against the layout, not
        against the pixels.

        ``top`` is where the panel prefers to sit, in design pixels of a
        648-tall picture; a panel too tall for that is pulled up.

        ``highlighted`` lights one row in ``highlight_color`` for a moment,
        which is how a value row reports a change the player just made.

        ``footers`` are hint lines under the rows, and ``description`` is a note
        of up to :data:`DESCRIPTION_LINES` lines above them. Both are reserved in
        the panel's height, so they never land on a row.

        ``scroll`` is the first row shown, and only counts when ``scrollable``
        is set: a list that cannot scroll grows past the window rather than
        losing its last rows -- a Back row cut off is a menu you cannot leave.
        Rows out of view keep an empty rect in :attr:`item_rects`, so the rects
        stay index-aligned with ``model.items``.
        """
        if self._surface_size != surface.get_size():
            self._surface_size = surface.get_size()
            self.reset_cache()
        top = self.scaled_top(top, surface)
        bands = self._bands(surface, model, footers, description, scroll, scrollable)
        content = self._content(
            surface,
            title,
            title_color,
            model,
            bands,
            highlighted,
            highlight_color,
            footers,
            description,
        )
        return self._place(surface, top, model, bands, content, highlighted)

    def _bands(
        self,
        surface: pygame.Surface,
        model: MenuModel,
        footers: tuple[str, ...],
        description: str,
        scroll: int,
        scrollable: bool,
    ) -> _Bands:
        """The vertical budget: how tall a row is and which rows are shown.

        Measured against the whole window, not from ``top`` down: a panel too
        tall for ``top`` is pulled up towards the margin.
        """
        title_font, item_font, footer_font = self._fonts_for(self._scale)
        metrics = self._metrics
        row_count = len(model.items)
        footer_step = _line_step(footer_font) + metrics.gap // 2
        # Always two lines when there is a note, whatever its length, so the
        # panel's height does not follow the note from row to row.
        description_height = (
            _line_step(footer_font) * DESCRIPTION_LINES + metrics.gap // 2 if description else 0
        )
        row_budget = (
            max(metrics.px(120), surface.get_height() - metrics.margin * 2)
            - metrics.panel_padding * 2
            - title_font.get_linesize()
            - metrics.panel_title_gap
            - description_height
            - footer_step * len(footers)
        )
        item_height = max(
            item_font.get_linesize(),
            min(metrics.panel_row, row_budget // max(1, row_count)),
        )
        visible = row_count
        if scrollable:
            visible = max(1, min(row_count, row_budget // max(1, item_height)))
        first = max(0, min(scroll, row_count - visible)) if scrollable else 0
        return _Bands(item_height, first, visible, footer_step, description_height)

    def _content(
        self,
        surface: pygame.Surface,
        title: str,
        title_color: tuple[int, int, int],
        model: MenuModel,
        bands: _Bands,
        highlighted: int,
        highlight_color: tuple[int, int, int],
        footers: tuple[str, ...],
        description: str,
    ) -> _Content:
        """Every piece of text, rendered once, and the panel width that holds it.

        The content decides the width and the window caps it; a row still too
        wide is cut, value first.
        """
        title_font, item_font, footer_font = self._fonts_for(self._scale)
        metrics = self._metrics
        padding = metrics.panel_padding
        labels = [item.label for item in model.items]
        values = [
            _decorated(item, index == model.current_index) for index, item in enumerate(model.items)
        ]
        shown = range(bands.first, bands.first + bands.visible)
        cache_key = (
            tuple(labels[bands.first : bands.first + bands.visible]),
            tuple(values[bands.first : bands.first + bands.visible]),
            model.current_index,
            self._scale,
            description,
            bands.first,
        )
        if cache_key != self._text_cache_key:
            self._text_cache.clear()
            self._text_cache_key = cache_key
        title_surface = self._render_cached(title_font, title, title_color)
        label_surfaces = [
            self._render_cached(
                item_font, labels[index], self._color(index, model, highlighted, highlight_color)
            )
            for index in shown
        ]
        value_surfaces: list[pygame.Surface | None] = [
            self._render_cached(
                item_font,
                values[index],
                self._value_color(index, model, highlighted, highlight_color),
            )
            if values[index]
            else None
            for index in shown
        ]
        window_text_width = surface.get_width() - metrics.margin * 2 - padding * 2
        footer_surfaces = [
            self._fit_text(footer_font, text, TEXT_MUTED, window_text_width) for text in footers
        ]
        label_width = max(
            [rendered.get_width() for rendered in label_surfaces] + [title_surface.get_width()]
        )
        value_width = max(
            (rendered.get_width() for rendered in value_surfaces if rendered), default=0
        )
        rows_width = label_width + (metrics.value_gap + value_width if value_width else 0)
        description_surface = (
            self._wrap_text(
                footer_font,
                description,
                TEXT_MUTED,
                min(
                    window_text_width,
                    max(
                        rows_width,
                        metrics.px(DESCRIPTION_MIN_WIDTH),
                        # Wide enough for the note to fit on its lines.
                        footer_font.size(description)[0] // DESCRIPTION_LINES
                        + footer_font.size("M" * 6)[0],
                    ),
                ),
            )
            if description
            else None
        )
        self._description_width = description_surface.get_width() if description_surface else 0
        footer_width = max((footer.get_width() for footer in footer_surfaces), default=0)
        content_width = max(rows_width, self._description_width, footer_width)
        panel_width = self._panel_width(content_width + padding * 2, model, title, surface)
        self._cut_rows_to_fit(
            label_surfaces,
            value_surfaces,
            labels,
            values,
            bands.first,
            panel_width - padding * 2,
            item_font,
            model,
            highlighted,
            highlight_color,
        )
        return _Content(
            title_surface,
            label_surfaces,
            value_surfaces,
            description_surface,
            footer_surfaces,
            panel_width,
        )

    def _place(
        self,
        surface: pygame.Surface,
        top: int,
        model: MenuModel,
        bands: _Bands,
        content: _Content,
        highlighted: int,
    ) -> MenuLayout:
        """Position the panel and every piece in it, and publish the hit-test rects."""
        _, item_font, footer_font = self._fonts_for(self._scale)
        metrics = self._metrics
        padding, title_gap = metrics.panel_padding, metrics.panel_title_gap
        title_surface, panel_width = content.title, content.panel_width
        footer_height = bands.footer_step * len(content.footers)
        panel_height = (
            padding * 2
            + title_surface.get_height()
            + title_gap
            + bands.item_height * bands.visible
            + bands.description_height
            + footer_height
        )
        panel = pygame.Rect(
            (surface.get_width() - panel_width) // 2,
            min(top, max(metrics.margin, surface.get_height() - panel_height - metrics.margin)),
            panel_width,
            panel_height,
        )
        item_top = panel.y + padding + title_surface.get_height() + title_gap
        self._item_rects = [pygame.Rect(0, 0, 0, 0) for _ in model.items]
        rows: list[PlacedRow] = []
        for offset in range(bands.visible):
            index = bands.first + offset
            rect = pygame.Rect(
                panel.x + padding,
                item_top + offset * bands.item_height,
                panel_width - padding * 2,
                bands.item_height,
            )
            self._item_rects[index] = rect
            bar = None
            if index == model.current_index:
                # One mark for "a press acts here", whichever device moved it;
                # the flash after a change is the same bar, lit.
                bar = SELECTION_FLASH if index == highlighted else SELECTION_BG
            rows.append(PlacedRow(rect, content.labels[offset], content.values[offset], bar))
        self._scroll_rail, self._scroll_thumb = self._rail_geometry(
            panel.right - padding,
            padding,
            item_top,
            bands.item_height * bands.visible,
            bands.first,
            bands.visible,
            len(model.items),
        )
        footer_y = panel.bottom - padding - footer_height
        # A help line's leading goes above it, between it and the rows, rather
        # than below it, where the padding already is.
        footer_leading = bands.footer_step - footer_font.get_linesize()
        placed_description = None
        if content.description is not None:
            placed_description = (
                content.description,
                (
                    panel.x + (panel_width - content.description.get_width()) // 2,
                    footer_y - bands.description_height + footer_leading + metrics.gap // 4,
                ),
            )
        placed_footers = [
            (
                footer,
                (
                    panel.x + (panel_width - footer.get_width()) // 2,
                    footer_y + footer_leading + n * bands.footer_step,
                ),
            )
            for n, footer in enumerate(content.footers)
        ]
        return MenuLayout(
            panel=panel,
            frame=self._panel_for(panel_width, panel_height, max(1, item_font.get_height() // 8)),
            title=(
                title_surface,
                (panel.x + (panel_width - title_surface.get_width()) // 2, panel.y + padding),
            ),
            rows=rows,
            bar_inflate=padding // 2,
            rail=self._scroll_rail,
            thumb=self._scroll_thumb,
            description=placed_description,
            footers=placed_footers,
        )

    @staticmethod
    def paint(surface: pygame.Surface, placed: MenuLayout) -> None:
        """Blit a layout. Every decision was made by :meth:`layout`."""
        surface.blit(placed.frame, placed.panel.topleft)
        surface.blit(*placed.title)
        for row in placed.rows:
            if row.bar is not None:
                surface.fill(row.bar, row.rect.inflate(placed.bar_inflate, 0))
            surface.blit(row.label, (row.rect.x, row.rect.centery - row.label.get_height() // 2))
            if row.value is not None:
                # Right-aligned, so the values make a column.
                surface.blit(
                    row.value,
                    (
                        row.rect.right - row.value.get_width(),
                        row.rect.centery - row.value.get_height() // 2,
                    ),
                )
        if placed.rail is not None and placed.thumb is not None:
            pygame.draw.rect(surface, PANEL_BORDER, placed.rail, border_radius=2)
            pygame.draw.rect(surface, TEXT_MUTED, placed.thumb, border_radius=2)
        if placed.description is not None:
            surface.blit(*placed.description)
        for footer in placed.footers:
            surface.blit(*footer)

    def _panel_width(
        self, natural: int, model: MenuModel, title: str, surface: pygame.Surface
    ) -> int:
        """The panel's width: its content's, floored, sticky, and capped by the window.

        Sticky while the same rows are on the same target: a value that changes
        length (VSync, Frame limit) must not make the panel breathe and slide the
        rows out from under the pointer.
        """
        metrics = self._metrics
        natural = max(natural, metrics.panel_min_width)
        key = (tuple(item.action for item in model.items), title, surface.get_size(), self._scale)
        if key == self._width_key:
            natural = max(natural, self._sticky_width)
        self._width_key = key
        self._sticky_width = natural
        return min(natural, max(1, surface.get_width() - metrics.margin * 2))

    def _cut_rows_to_fit(
        self,
        label_surfaces: list[pygame.Surface],
        value_surfaces: list[pygame.Surface | None],
        labels: list[str],
        values: list[str],
        first: int,
        inner_width: int,
        item_font: pygame.font.Font,
        model: MenuModel,
        highlighted: int,
        highlight_color: tuple[int, int, int],
    ) -> None:
        """Cut, value first, every row too wide for the panel, in place.

        Rather than painting its label and its value over each other.
        """
        gap = self._metrics.value_gap
        for offset, label_surface in enumerate(label_surfaces):
            index = first + offset
            value_surface = value_surfaces[offset]
            value_w = value_surface.get_width() + gap if value_surface else 0
            if label_surface.get_width() + value_w <= inner_width:
                continue
            if value_surface is not None:
                room = max(inner_width // 3, inner_width - label_surface.get_width() - gap)
                value_surface = self._fit_text(
                    item_font,
                    values[index],
                    self._value_color(index, model, highlighted, highlight_color),
                    room,
                )
                value_surfaces[offset] = value_surface
                value_w = value_surface.get_width() + gap
            label_surfaces[offset] = self._fit_text(
                item_font,
                labels[index],
                self._color(index, model, highlighted, highlight_color),
                max(1, inner_width - value_w),
            )

    def _value_color(
        self,
        index: int,
        model: MenuModel,
        highlighted: int = -1,
        highlight_color: tuple[int, int, int] = GOLD,
    ) -> tuple[int, int, int]:
        """The value column, dimmer than the label.

        The label is the row's identity and the value is its state, and the eye
        should land on the former while scanning a menu and on the latter while
        changing one.
        """
        if not model.items[index].enabled:
            return TEXT_MUTED
        if index == model.current_index:
            return SELECTION_TEXT
        if index == highlighted:
            return highlight_color
        return TEXT_MUTED

    def _color(
        self,
        index: int,
        model: MenuModel,
        highlighted: int = -1,
        highlight_color: tuple[int, int, int] = GOLD,
    ) -> tuple[int, int, int]:
        item = model.items[index]
        if item.kind == "header":
            return TEXT_WARN
        if not item.enabled:
            return TEXT_MUTED
        if index == model.current_index:
            return SELECTION_TEXT
        if index == highlighted:
            return highlight_color
        return TEXT_TITLE

    def _render_cached(
        self, font: pygame.font.Font, text: str, color: tuple[int, int, int]
    ) -> pygame.Surface:
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            # No antialiasing: a pixel font blurred at its edges is not one.
            cached = font.render(text, False, color)
            self._text_cache[key] = cached
        return cached

    def _wrap_text(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        max_width: int,
    ) -> pygame.Surface:
        """``text`` on up to :data:`DESCRIPTION_LINES` lines, the last one cut if it must."""
        words = text.split()
        lines: list[str] = []
        while words and len(lines) < DESCRIPTION_LINES - 1:
            line = words.pop(0)
            while words and font.size(f"{line} {words[0]}")[0] <= max_width:
                line = f"{line} {words.pop(0)}"
            lines.append(line)
        if words:
            lines.append(" ".join(words))
        rendered = [self._fit_text(font, line, color, max_width) for line in lines]
        if len(rendered) == 1:
            return rendered[0]
        width = max(painted.get_width() for painted in rendered)
        step = _line_step(font)
        block = pygame.Surface((width, step * len(rendered)), pygame.SRCALPHA)
        for row, painted in enumerate(rendered):
            block.blit(painted, ((width - painted.get_width()) // 2, row * step))
        return block

    def _fit_text(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        max_width: int,
    ) -> pygame.Surface:
        """Render ``text`` no wider than ``max_width``, cut with an ellipsis.

        The ellipsis is inside the measurement, so the result never overhangs.
        Cached on the text drawn.
        """
        surface = self._render_cached(font, text, color)
        if surface.get_width() <= max_width:
            return surface
        # Binary search for the longest prefix that fits with the marker
        # on the end: linear trimming re-measures a whole paragraph's
        # worth of characters when one will do.
        low, high = 0, len(text)
        marker = "…"
        while low < high:
            middle = (low + high + 1) // 2
            if font.size(text[:middle] + marker)[0] <= max_width:
                low = middle
            else:
                high = middle - 1
        return self._render_cached(font, text[:low].rstrip() + marker, color)

    def _fonts_for(self, scale: float) -> tuple[pygame.font.Font, ...]:
        """Title, item and footer fonts for a scale, built once per scale.

        Building a font rasterises its metrics, so all three live in the same
        cache entry: a call site that builds its own is a per-frame font build,
        which is what this cache exists to prevent.
        """
        # Keyed on the pixel sizes, not on the scale: a drag of the window
        # produces a new scale every frame, and a dict keyed on those grows by
        # three font objects per frame of the drag and never gives them back.
        # The sizes are quantised, so a drag that does not move a font size by a
        # whole pixel reuses the fonts it already has.
        key = (
            menu_font_size(DESIGN_TITLE, scale),
            menu_font_size(DESIGN_ITEM, scale),
            menu_font_size(DESIGN_SMALL, scale),
        )
        cached = self._fonts.get(key)
        if cached is None:
            cached = (menu_font(key[0]), menu_font(key[1]), menu_font(key[2]))
            if len(self._fonts) >= FONT_CACHE_ENTRIES:
                # A drag through a hundred densities is not a thing to keep.
                self._fonts.clear()
            self._fonts[key] = cached
        return cached

    def _rail_geometry(
        self,
        gutter_left: int,
        gutter_width: int,
        rows_top: int,
        rows_height: int,
        first: int,
        visible: int,
        total: int,
    ) -> tuple[pygame.Rect | None, pygame.Rect | None]:
        """The scroll rail and its thumb, or ``(None, None)`` when the list fits.

        The rail sits in the right padding gutter, which no label or value
        reaches. The thumb's height is the visible fraction of the list and its
        place the scrolled-to fraction. Nothing is shown for a list that fits:
        a rail beside a complete list is a lie about it.
        """
        if total <= visible or rows_height <= 0:
            return None, None
        metrics = self._metrics
        width = max(2, metrics.px(4))
        rail = pygame.Rect(gutter_left + (gutter_width - width) // 2, rows_top, width, rows_height)
        # Floored, so a nearly whole list still shows a thumb and not a line.
        thumb_height = max(max(1, metrics.px(12)), round(rail.height * visible / total))
        travel = max(0, rail.height - thumb_height)
        thumb_y = rail.top + round(travel * first / max(1, total - visible))
        return rail, pygame.Rect(rail.x, thumb_y, rail.width, thumb_height)

    def _panel_for(self, width: int, height: int, unit: int = 1) -> pygame.Surface:
        """The panel, painted once per size: a pixel-art frame on the font's grid.

        ``unit`` is one pixel of the font's grid, so the frame's lines are as
        thick as a stroke of a letter: corners cut by one unit, a dark outline,
        and a light rim just inside it. Reused until the size changes.
        """
        key = (width, height, unit)
        if self._panel_cache is None or self._panel_cache_size != key:
            self._panel_cache = _pixel_frame(width, height, unit)
            self._panel_cache_size = key
        return self._panel_cache

    @staticmethod
    def _valid_scale(scale: float) -> float:
        return checked_ui_scale(scale)

    def reset_cache(self) -> None:
        """Drop the cached fonts and surfaces (display changed)."""
        self._fonts.clear()
        self._panel_cache = None
        self._panel_cache_size = (0, 0)
        self._text_cache.clear()
        self._text_cache_key = None
        # The rects from the last draw describe rows that are gone: a click
        # queued behind a window rebuild must hit nothing rather than the wrong
        # row (it was measured 244px off once).
        self._scroll_rail = None
        self._scroll_thumb = None
        self._item_rects = []
