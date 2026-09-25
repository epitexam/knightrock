from collections.abc import Sequence

import pygame

from src.ui.menu_model import MenuModel
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
        self._scale = self._valid_scale(scale)
        self._item_rects: list[pygame.Rect] = []
        self._fonts: dict[float, tuple[pygame.font.Font, pygame.font.Font]] = {}
        self._panel_cache: pygame.Surface | None = None
        self._panel_cache_size: tuple[int, int] = (0, 0)
        self._surface_size: tuple[int, int] = (0, 0)
        # Cache des textes rendus : un .render() par frame et par item
        # alloue une Surface + déclenche du GC -> micro-freezes à 60fps.
        # Clé = (font-id, texte, couleur) ; invalidé au changement de sélection.
        self._text_cache: dict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = {}
        self._text_cache_key: tuple[tuple[str, ...], int, float] | None = None

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
        self.reset_cache()

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        size = display_surface.get_size()
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
    ) -> pygame.Rect:
        """Draw the panel and return its rect.

        ``highlighted`` paints one row in ``highlight_color`` for a limited
        time, which is how a value row reports a change the player just made.
        It is a separate colour because the selected row is already amber, so
        reusing that would hide the flash on the very row that changed.
        """
        if self._surface_size != surface.get_size():
            self._surface_size = surface.get_size()
            self.reset_cache()
        scale = self._scale
        title_font, item_font = self._fonts_for(scale)
        labels = [
            f"> {item.label}" if index == model.current_index else item.label
            for index, item in enumerate(model.items)
        ]
        cache_key = (tuple(labels), model.current_index, scale)
        if cache_key != self._text_cache_key:
            self._text_cache.clear()
            self._text_cache_key = cache_key
        title_surface = self._render_cached(title_font, title, title_color)
        item_surfaces = [
            self._render_cached(
                item_font, label, self._color(index, model, highlighted, highlight_color)
            )
            for index, label in enumerate(labels)
        ]
        padding = max(8, int(28 * scale))
        title_gap = max(4, int(16 * scale))
        available_height = max(120, surface.get_height() - top - 16)
        item_height = min(
            max(20, int(40 * scale)),
            max(
                20,
                (available_height - padding * 2 - title_surface.get_height() - title_gap)
                // max(1, len(labels)),
            ),
        )
        content_width = max(
            [surface.get_width() for surface in item_surfaces] + [title_surface.get_width()]
        )
        panel_width = min(content_width + padding * 2, max(240, surface.get_width() - 24))
        panel_height = (
            padding * 2 + title_surface.get_height() + title_gap + item_height * len(labels)
        )
        panel_x = (surface.get_width() - panel_width) // 2
        panel_y = min(top, max(8, surface.get_height() - panel_height - 8))
        panel = self._panel_for(panel_width, panel_height)
        panel.fill((*PANEL_BG[:3], 230))
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), max(1, int(2 * scale)))
        surface.blit(panel, (panel_x, panel_y))
        surface.blit(title_surface, (panel_x + padding, panel_y + padding))
        item_top = panel_y + padding + title_surface.get_height() + title_gap
        self._item_rects = []
        for index, item_surface in enumerate(item_surfaces):
            rect = pygame.Rect(
                panel_x + padding,
                item_top + index * item_height,
                panel_width - padding * 2,
                item_height,
            )
            surface.blit(item_surface, (rect.x, rect.centery - item_surface.get_height() // 2))
            self._item_rects.append(rect)
        return pygame.Rect(panel_x, panel_y, panel_width, panel_height)

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

    def _fonts_for(self, scale: float) -> tuple[pygame.font.Font, pygame.font.Font]:
        """Cache les Font par scale : SysFont coûte cher à chaque frame."""
        cached = self._fonts.get(scale)
        if cached is None:
            cached = (
                pygame.font.SysFont("Consolas", max(1, int(48 * scale)), bold=True),
                pygame.font.SysFont("Consolas", max(1, int(32 * scale))),
            )
            self._fonts[scale] = cached
        return cached

    def _panel_for(self, width: int, height: int) -> pygame.Surface:
        """Réutilise la surface du panneau au lieu d'en allouer une/frame."""
        if self._panel_cache is None or self._panel_cache_size != (width, height):
            self._panel_cache = pygame.Surface((width, height), pygame.SRCALPHA)
            self._panel_cache_size = (width, height)
        return self._panel_cache

    @staticmethod
    def _valid_scale(scale: float) -> float:
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("UI scale must be 0.8, 1.0 or 1.2")
        return scale

    def reset_cache(self) -> None:
        """Vide les fonts/surfaces cachées (changement de display)."""
        self._fonts.clear()
        self._panel_cache = None
        self._panel_cache_size = (0, 0)
        self._text_cache.clear()
        self._text_cache_key = None
