from collections.abc import Sequence

import pygame

from src.ui.menu_model import MenuModel
from src.ui.metrics import DESIGN_VALUE_GAP, Metrics
from src.ui.scale import FONT_CACHE_ENTRIES, checked_ui_scale, font_size
from src.ui.styles import (
    GOLD,
    PANEL_BG,
    PANEL_BORDER,
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
        # Rendered-text cache. One .render() per frame per item allocates a
        # Surface and triggers GC, which shows up as micro-freezes at 60fps.
        # Keyed by (font id, text, colour); invalidated on selection change.
        self._text_cache: dict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = {}
        self._text_cache_key: tuple[tuple[str, ...], tuple[str, ...], int, float] | None = None

    @property
    def item_rects(self) -> Sequence[pygame.Rect]:
        """Live item rectangles from the last draw.

        Returned without copying: the list is rebuilt in ``draw`` and no caller
        mutates it, so copying it on every routed input only allocated.
        """
        return self._item_rects

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

    #: Gap between the label column and the value column. Kept as a class
    #: attribute because scenes and tests read it; the value now comes from the
    #: shared metrics so it grows with the window like every other gap.
    VALUE_GAP = DESIGN_VALUE_GAP

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
    ) -> pygame.Rect:
        """Draw the panel and return its rect.

        ``highlighted`` paints one row in ``highlight_color`` for a limited
        time, which is how a value row reports a change the player just made.
        It is a separate colour because the selected row is already amber, so
        reusing that would hide the flash on the very row that changed.

        ``footers`` are hint lines under the last row, as on the grid panel.
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
        cache_key = (tuple(labels), tuple(values), model.current_index, scale)
        if cache_key != self._text_cache_key:
            self._text_cache.clear()
            self._text_cache_key = cache_key
        title_surface = self._render_cached(title_font, title, title_color)
        label_surfaces = [
            self._render_cached(
                item_font, label, self._color(index, model, highlighted, highlight_color)
            )
            for index, label in enumerate(labels)
        ]
        value_surfaces = [
            self._render_cached(
                item_font,
                value,
                self._value_color(index, model, highlighted, highlight_color),
            )
            if value
            else None
            for index, value in enumerate(values)
        ]
        footer_surfaces = [self._render_cached(footer_font, text, TEXT_WARN) for text in footers]
        metrics = self._metrics
        padding, title_gap = metrics.panel_padding, metrics.panel_title_gap
        available_height = max(metrics.px(120), surface.get_height() - top - metrics.margin)
        # A row is never shorter than the text inside it. Compressing the text is
        # the alternative, and the panel simply grows taller otherwise.
        item_height = max(
            item_font.get_linesize(),
            min(
                metrics.panel_row,
                (available_height - padding * 2 - title_surface.get_height() - title_gap)
                // max(1, len(labels)),
            ),
        )
        label_width = max(
            [rendered.get_width() for rendered in label_surfaces if rendered]
            + [title_surface.get_width()]
        )
        value_width = max(
            (rendered.get_width() for rendered in value_surfaces if rendered), default=0
        )
        footer_step = footer_font.get_linesize() + metrics.gap // 2
        footer_height = footer_step * len(footer_surfaces)
        content_width = label_width + (metrics.value_gap + value_width if value_width else 0)
        panel_width = min(
            content_width + padding * 2,
            max(metrics.panel_min_width, surface.get_width() - metrics.margin * 2),
        )
        panel_height = (
            padding * 2
            + title_surface.get_height()
            + title_gap
            + item_height * len(labels)
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
        self._item_rects = []
        for index, label_surface in enumerate(label_surfaces):
            rect = pygame.Rect(
                panel_x + padding,
                item_top + index * item_height,
                panel_width - padding * 2,
                item_height,
            )
            if label_surface is not None:
                surface.blit(
                    label_surface,
                    (rect.x, rect.centery - label_surface.get_height() // 2),
                )
            value_surface = value_surfaces[index]
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
            self._item_rects.append(rect)
        footer_y = panel_y + panel_height - padding - footer_height
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

    def _fonts_for(self, scale: float) -> tuple[pygame.font.Font, ...]:
        """Title, item and footer fonts for a scale, built once per scale.

        ``SysFont`` scans the system font list on every call, so all three live
        in the same cache entry: a call site that builds its own is a per-frame
        font lookup, which is what this cache exists to prevent.
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
                pygame.font.SysFont("Consolas", key[0], bold=True),
                pygame.font.SysFont("Consolas", key[1]),
                pygame.font.SysFont("Consolas", key[2]),
            )
            if len(self._fonts) >= FONT_CACHE_ENTRIES:
                # A drag through a hundred densities is not a thing to keep.
                self._fonts.clear()
            self._fonts[key] = cached
        return cached

    def _panel_for(self, width: int, height: int) -> pygame.Surface:
        """Reuse the panel surface instead of allocating one per frame."""
        if self._panel_cache is None or self._panel_cache_size != (width, height):
            self._panel_cache = pygame.Surface((width, height), pygame.SRCALPHA)
            self._panel_cache_size = (width, height)
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
