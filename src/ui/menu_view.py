from collections.abc import Sequence

import pygame

from src.ui.fonts import ui_font
from src.ui.menu_model import MenuModel
from src.ui.metrics import Metrics
from src.ui.scale import FONT_CACHE_ENTRIES, checked_ui_scale, font_size
from src.ui.styles import (
    GOLD,
    PANEL_BG,
    PANEL_BORDER,
    POINTER_OUTLINE,
    TEXT_MUTED,
    TEXT_OK,
    TEXT_TITLE,
    TEXT_WARN,
)


class MenuView:
    def __init__(self, scale: float = 1.0) -> None:
        self._metrics = Metrics.for_scale(scale)
        self._scale = self._metrics.scale
        self._item_rects: list[pygame.Rect] = []
        self._fonts: dict[tuple[int, int, int], tuple[pygame.font.Font, ...]] = {}
        self._panel_cache: pygame.Surface | None = None
        self._panel_cache_size: tuple[int, int] = (0, 0)
        self._surface_size: tuple[int, int] = (0, 0)
        # The scroll rail's geometry from the last draw, or None when
        # the list fit and nothing scrolls. Kept rather than painted
        # blind so a caller can ask "is there more below" the same way
        # it asks for the row rects.
        self._scroll_rail: pygame.Rect | None = None
        self._scroll_thumb: pygame.Rect | None = None
        # The description's width after being fitted, from the last draw.
        self._description_width = 0
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
        """Draw the panel and return its rect.

        ``highlighted`` paints one row in ``highlight_color`` for a limited
        time, which is how a value row reports a change the player just made.
        It is a separate colour because the selected row is already amber, so
        reusing that would hide the flash on the very row that changed.

        ``footers`` are hint lines under the last row, as on the grid panel.

        ``description`` is one line of prose under the list, in a dimmer colour
        and a smaller font. One line, and it is *reserved* in the panel height
        rather than painted over whatever happens to be below -- the panel
        measures its own contents to size itself, so text added without being
        accounted for lands on the footer or outside the border.

        ``scroll`` is the index of the first row to paint, for a list taller than
        the window, and it only does anything when ``scrollable`` is set.

        That second flag is load-bearing. Clipping a list that does not fit is
        right for a list the caller knows can scroll, and *catastrophic* for one
        that cannot: the rows past the fold silently stop being drawn, get an
        empty rect, and become unclickable -- so a menu whose Back row fell past
        the bottom became a menu you could not leave with the mouse. Measured on
        the video screen at 10 rows in a 648px window: rows 9 and 10 painted
        nothing. Scrolling is therefore something a screen opts into rather than
        something that happens to it.

        Rows scrolled out of view keep their place in ``item_rects`` with an
        empty rect rather than dropping out of the list, so the rects stay
        index-aligned with ``model.items``. That matters because the pointer path
        indexes both by the same number, and a list whose rects shifted would make
        a click land on the wrong row.
        """
        if self._surface_size != surface.get_size():
            self._surface_size = surface.get_size()
            self.reset_cache()
        scale = self._scale
        title_font, item_font, footer_font = self._fonts_for(scale)
        labels = [
            f"> {item.label}" if index == model.current_index else item.label
            for index, item in enumerate(model.items)
        ]
        values = [item.value for item in model.items]
        # How much of the list fits, decided before anything is painted rather
        # than after -- the cache key, the rows and the panel height all have to
        # agree on it, and computing it once up front is what makes them agree.
        metrics = self._metrics
        padding, title_gap = metrics.panel_padding, metrics.panel_title_gap
        available_height = max(metrics.px(120), surface.get_height() - top - metrics.margin)
        footer_step = footer_font.get_linesize() + metrics.gap // 2
        description_step = footer_font.get_linesize() + metrics.gap // 2
        description_height = description_step if description else 0
        # The title's own height, measured rather than estimated: it is bold and
        # its rasterised linesize is not the design size the rest of the table is
        # written in.
        row_budget = (
            available_height
            - padding * 2
            - title_font.get_linesize()
            - title_gap
            - description_height
            - footer_step * len(footers)
        )
        item_height = max(
            item_font.get_linesize(),
            min(metrics.panel_row, row_budget // max(1, len(labels))),
        )
        # A list that does not fit is clipped only when its caller asked for
        # scrolling. Otherwise the panel simply grows past the bottom of the
        # window, which is the behaviour every screen here was written against.
        visible_rows = len(labels)
        if scrollable:
            visible_rows = max(1, min(len(labels), row_budget // max(1, item_height)))
        # Never scroll past the end: the last row is always reachable, and a
        # window that cannot scroll all the way down is a window with rows in it
        # that can never be seen.
        first = max(0, min(scroll, len(labels) - visible_rows)) if scrollable else 0
        painted = labels[first : first + visible_rows]
        # The text cache is keyed on what is painted, not on what exists. Keying
        # it on the whole list would render 28 rows a frame for a window showing
        # twelve of them, and the cache would hold surfaces nobody drew.
        cache_key = (
            tuple(painted),
            tuple(values[first : first + visible_rows]),
            model.current_index,
            scale,
            description,
            first,
        )
        if cache_key != self._text_cache_key:
            self._text_cache.clear()
            self._text_cache_key = cache_key
        title_surface = self._render_cached(title_font, title, title_color)
        label_surfaces = [
            self._render_cached(
                item_font, label, self._color(first + offset, model, highlighted, highlight_color)
            )
            for offset, label in enumerate(painted)
        ]
        value_surfaces = [
            self._render_cached(
                item_font,
                values[first + offset],
                self._value_color(first + offset, model, highlighted, highlight_color),
            )
            if values[first + offset]
            else None
            for offset in range(len(painted))
        ]
        footer_surfaces = [self._render_cached(footer_font, text, TEXT_WARN) for text in footers]
        metrics = self._metrics
        padding, title_gap = metrics.panel_padding, metrics.panel_title_gap
        # The description is fitted before the panel is measured, and to
        # the widest the panel can be rather than to the panel: the panel
        # is sized partly from the description, so fitting it to the
        # panel would be fitting it to a number that depends on it.
        description_surface = (
            self._fit_text(
                footer_font,
                description,
                TEXT_MUTED,
                surface.get_width() - metrics.margin * 2 - padding * 2,
            )
            if description
            else None
        )
        self._description_width = (
            description_surface.get_width() if description_surface is not None else 0
        )
        label_width = max(
            [rendered.get_width() for rendered in label_surfaces if rendered]
            + [title_surface.get_width()]
        )
        value_width = max(
            (rendered.get_width() for rendered in value_surfaces if rendered), default=0
        )
        footer_height = footer_step * len(footer_surfaces)
        description_width = description_surface.get_width() if description_surface else 0
        content_width = max(
            label_width + (metrics.value_gap + value_width if value_width else 0),
            description_width,
        )
        panel_width = min(
            content_width + padding * 2,
            max(metrics.panel_min_width, surface.get_width() - metrics.margin * 2),
        )
        panel_height = (
            padding * 2
            + title_surface.get_height()
            + title_gap
            + item_height * len(painted)
            + description_height
            + footer_height
        )
        panel_x = (surface.get_width() - panel_width) // 2
        panel_y = min(
            top, max(metrics.margin, surface.get_height() - panel_height - metrics.margin)
        )
        panel = self._panel_for(panel_width, panel_height)
        panel.fill((*PANEL_BG[:3], 230))
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), metrics.border)
        surface.blit(panel, (panel_x, panel_y))
        # Centred, like the grid's title and the HUD's: a left-aligned title
        # above a right-aligned value column reads as two unrelated screens.
        surface.blit(
            title_surface,
            (panel_x + (panel_width - title_surface.get_width()) // 2, panel_y + padding),
        )
        item_top = panel_y + padding + title_surface.get_height() + title_gap
        # A row under the pointer is outlined, whether or not it is the selected
        # one. The `>` marker and the amber text both say "this is the one a key
        # press will act on"; nothing said "this is where the cursor is", so the
        # two devices disagreed on screen without the disagreement being visible.
        # A player who moved the mouse to a row and then pressed an arrow key
        # could not tell why the highlight had left them -- which is the whole of
        # what made the navigation feel broken.
        pointer_row = self._pointer_row(model)
        # Index-aligned with ``model.items``: the rows scrolled out of view keep
        # their place with an empty rect, so a pointer hit-test and a key press
        # both address the same row number.
        self._item_rects = [pygame.Rect(0, 0, 0, 0) for _ in model.items]
        for offset, label_surface in enumerate(label_surfaces):
            index = first + offset
            rect = pygame.Rect(
                panel_x + padding,
                item_top + offset * item_height,
                panel_width - padding * 2,
                item_height,
            )
            if label_surface is not None:
                surface.blit(
                    label_surface,
                    (rect.x, rect.centery - label_surface.get_height() // 2),
                )
            value_surface = value_surfaces[offset]
            if value_surface is not None:
                # Right-aligned against the panel's padding: the column of
                # values lines up, which is the whole reason it is a column.
                surface.blit(
                    value_surface,
                    (
                        rect.right - value_surface.get_width(),
                        rect.centery - value_surface.get_height() // 2,
                    ),
                )
            self._item_rects[index] = rect
            if index == pointer_row and index != model.current_index:
                # Outlined rather than filled, so it reads as "the cursor is here"
                # and not as "a key press will act here" -- the two are different
                # claims and the keyboard's is the one that changes something.
                pygame.draw.rect(
                    surface, POINTER_OUTLINE, rect, max(1, metrics.px(2)), border_radius=3
                )
        # The rail is painted into the right padding gutter, which is
        # wide enough to hold it without a row's label or value ever
        # reaching it, so nothing has to make room for it.
        self._paint_scroll_rail(
            surface,
            panel_x + panel_width - padding,
            padding,
            item_top,
            item_height * len(painted),
            first,
            len(painted),
            len(labels),
            metrics,
        )
        footer_y = panel_y + panel_height - padding - footer_height
        if description_surface is not None:
            # Directly above the footers, inside the panel: the band is already
            # reserved in the height, so this paints into space that belongs to
            # it rather than over the last row.
            description_y = footer_y - description_height + metrics.gap // 4
            surface.blit(
                description_surface,
                (
                    panel_x + (panel_width - description_surface.get_width()) // 2,
                    description_y,
                ),
            )
        for footer_surface in footer_surfaces:
            surface.blit(
                footer_surface,
                (panel_x + (panel_width - footer_surface.get_width()) // 2, footer_y),
            )
            footer_y += footer_step
        return pygame.Rect(panel_x, panel_y, panel_width, panel_height)

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
        if index == highlighted:
            return highlight_color
        if not model.items[index].enabled:
            return TEXT_MUTED
        if index == model.current_index:
            return TEXT_WARN
        return TEXT_MUTED

    def _color(
        self,
        index: int,
        model: MenuModel,
        highlighted: int = -1,
        highlight_color: tuple[int, int, int] = GOLD,
    ) -> tuple[int, int, int]:
        item = model.items[index]
        if not item.enabled:
            return TEXT_MUTED
        if index == highlighted:
            return highlight_color
        return TEXT_WARN if index == model.current_index else TEXT_OK

    def _render_cached(
        self, font: pygame.font.Font, text: str, color: tuple[int, int, int]
    ) -> pygame.Surface:
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = font.render(text, True, color)
            self._text_cache[key] = cached
        return cached

    def _fit_text(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        max_width: int,
    ) -> pygame.Surface:
        """Render ``text`` no wider than ``max_width``, cutting with a marker.

        The description is free-form prose and the panel is sized to
        everything else, so a long note is the one thing that can
        outgrow it: measured, 190 characters render 1158px wide
        against a 616px panel, and the centred text spills out over
        both sides.

        Cut rather than wrapped, because the band's height is
        reserved as a single line -- wrapping would make the panel's
        height a function of the note's length, which is exactly the
        reflow a scrolling list is meant not to have.

        Cached on the text that was drawn, so a cut note costs one
        measurement the first time and nothing after.
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
        key = (font_size(48, scale), font_size(32, scale), font_size(18, scale))
        cached = self._fonts.get(key)
        if cached is None:
            cached = (
                ui_font(key[0], bold=True),
                ui_font(key[1]),
                ui_font(key[2]),
            )
            if len(self._fonts) >= FONT_CACHE_ENTRIES:
                # A drag through a hundred densities is not a thing to keep.
                self._fonts.clear()
            self._fonts[key] = cached
        return cached

    def _paint_scroll_rail(
        self,
        surface: pygame.Surface,
        gutter_left: int,
        gutter_width: int,
        rows_top: int,
        rows_height: int,
        first: int,
        visible: int,
        total: int,
        metrics: Metrics,
    ) -> None:
        """Mark a list that scrolls, in the padding gutter beside it.

        A list cut off with nothing to say so is a list whose last
        visible row reads as the last row -- the player scrolls once,
        finds more, and has to revise what the panel was telling them.
        The rail answers "there is more" before that, and the thumb
        answers "how much, and how far in": its height is the visible
        fraction of the list and its place is the scrolled-to fraction.

        It lives in the padding rather than over the rows because a
        marker on a row competes with the row for the eye, and the
        padding is wide enough to hold a rail that no label or value
        can reach. Nothing is painted when the list fits, because a
        rail next to a complete list is a lie about it.
        """
        self._scroll_rail = None
        self._scroll_thumb = None
        if total <= visible or rows_height <= 0:
            return

        width = max(2, metrics.px(4))
        # Centred in the gutter, whose left edge is the rows' right
        # edge and whose right edge is the panel's own: the rail keeps
        # its distance from both the text and the border.
        rail = pygame.Rect(
            gutter_left + (gutter_width - width) // 2,
            rows_top,
            width,
            rows_height,
        )
        pygame.draw.rect(surface, PANEL_BORDER, rail, border_radius=2)

        # The thumb's height is the visible fraction, floored so a
        # nearly-whole list still shows a thumb and not a line.
        thumb_height = max(
            max(1, metrics.px(12)),
            round(rail.height * visible / total),
        )
        # Where the thumb sits: the top when the list is at its start,
        # the bottom when it is at its end, in between in proportion.
        travel = max(0, rail.height - thumb_height)
        span = max(1, total - visible)
        thumb_y = rail.top + round(travel * first / span)
        thumb = pygame.Rect(rail.x, thumb_y, rail.width, thumb_height)
        pygame.draw.rect(surface, TEXT_MUTED, thumb, border_radius=2)

        self._scroll_rail = rail
        self._scroll_thumb = thumb

    def _panel_for(self, width: int, height: int) -> pygame.Surface:
        """Reuse the panel surface instead of allocating one per frame."""
        if self._panel_cache is None or self._panel_cache_size != (width, height):
            self._panel_cache = pygame.Surface((width, height), pygame.SRCALPHA)
            self._panel_cache_size = (width, height)
        return self._panel_cache

    @staticmethod
    def _valid_scale(scale: float) -> float:
        return checked_ui_scale(scale)

    @staticmethod
    def _pointer_row(model: MenuModel) -> int:
        """The row the pointer is on, or -1.

        Read from the model rather than tracked here, so there is one answer to
        "where is the cursor" rather than two that can disagree. ``hovered_index``
        is -1 once the pointer has left the rows, which is what makes the outline
        disappear rather than stick to whatever it was on.
        """
        return model.hovered_index

    def reset_cache(self) -> None:
        """Drop the cached fonts and surfaces (display changed)."""
        self._fonts.clear()
        self._panel_cache = None
        self._panel_cache_size = (0, 0)
        self._text_cache.clear()
        self._text_cache_key = None
        # Geometry from a draw whose surfaces are gone: it describes
        # rows that no longer exist at this scale.
        self._scroll_rail = None
        self._scroll_thumb = None
