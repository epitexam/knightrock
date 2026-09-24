import pygame

from src.ui.menu_model import MenuModel
from src.ui.styles import PANEL_BG, PANEL_BORDER, TEXT_MUTED, TEXT_OK, TEXT_TITLE, TEXT_WARN


class MenuView:
    def __init__(self, scale: float = 1.0) -> None:
        self._scale = self._valid_scale(scale)
        self._item_rects: list[pygame.Rect] = []

    @property
    def item_rects(self) -> list[pygame.Rect]:
        return list(self._item_rects)

    def set_scale(self, scale: float) -> None:
        self._scale = self._valid_scale(scale)

    def draw(
        self,
        surface: pygame.Surface,
        title: str,
        model: MenuModel,
        *,
        top: int,
        title_color: tuple[int, int, int] = TEXT_TITLE,
    ) -> pygame.Rect:
        scale = self._scale
        title_font = pygame.font.SysFont("Consolas", max(1, int(48 * scale)), bold=True)
        item_font = pygame.font.SysFont("Consolas", max(1, int(32 * scale)))
        labels = [
            f"> {item.label}" if index == model.current_index else item.label
            for index, item in enumerate(model.items)
        ]
        title_surface = title_font.render(title, True, title_color)
        item_surfaces = [
            item_font.render(label, True, self._color(index, model))
            for index, label in enumerate(labels)
        ]
        padding = max(8, int(28 * scale))
        title_gap = max(4, int(16 * scale))
        item_height = max(20, int(40 * scale))
        content_width = max(
            [surface.get_width() for surface in item_surfaces] + [title_surface.get_width()]
        )
        panel_width = content_width + padding * 2
        panel_height = (
            padding * 2 + title_surface.get_height() + title_gap + item_height * len(labels)
        )
        panel_x = (surface.get_width() - panel_width) // 2
        panel_y = top
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
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

    def _color(self, index: int, model: MenuModel) -> tuple[int, int, int]:
        item = model.items[index]
        if not item.enabled:
            return TEXT_MUTED
        return TEXT_WARN if index == model.current_index else TEXT_OK

    @staticmethod
    def _valid_scale(scale: float) -> float:
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("UI scale must be 0.8, 1.0 or 1.2")
        return scale
