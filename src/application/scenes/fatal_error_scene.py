"""The last screen: a scrollable traceback and two ways out.

The fatal log is the artifact a player can send; this screen is the courtesy on
top of it. It is a real scene, so it gets the same render target, event routing
and scaling as every menu, but it never touches the crashed world underneath.

The traceback is rendered as one surface with pygame-ce's ``wraplength`` (which
also honours the newlines ``traceback.format_exception`` writes). Scrolling is
a pixel window into that surface, independent of the menu model: only the two
buttons below are menu rows.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.colors import Colors
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.fonts import menu_font, menu_font_size
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import DESIGN_ITEM, DESIGN_TITLE, MenuView
from src.ui.pixel import line_step
from src.ui.styles import PANEL_BG, TEXT_CRIT, TEXT_MUTED
from src.ui.text import t

if TYPE_CHECKING:
    from src.application.scene_context import SceneContext

#: Gap between the box's edges and its contents, in target pixels.
GAP = 8


class FatalErrorScene(Scene):
    """A standalone error scene; ``on_quit``/``on_menu`` are terminal actions."""

    opaque = True
    covers_panels_below = True
    halts_simulation = True

    def __init__(
        self,
        game: SceneContext,
        text: str,
        *,
        on_quit: Callable[[], None],
        on_menu: Callable[[], None],
        grace: float = 0.0,
    ) -> None:
        super().__init__(game)
        self.text = text.expandtabs(4)
        self._on_quit = on_quit
        self._on_menu = on_menu
        # The key that caused the crash may still be repeating when the screen
        # opens. Ignore a brief moment of input so it cannot press "quit" for us.
        self._grace = grace
        self.model = MenuModel(
            (
                MenuItem("quit", t("row.quit_game")),
                MenuItem("menu", t("row.back_to_main_menu")),
            )
        )
        self.view: MenuView = MenuView(game.ui_scale)
        self._scroll = 0
        self._trace: pygame.Surface | None = None
        self._trace_key: tuple[int, int] | None = None
        self._area: pygame.Rect | None = None
        self._rail: pygame.Rect | None = None

    # ----------------------------------------------------------- scaling

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)
        self._trace = None

    def set_surface(self, surface: pygame.Surface) -> None:
        self.view.set_surface(surface)
        self._trace = None

    def _font(self) -> pygame.font.Font:
        return menu_font(menu_font_size(DESIGN_ITEM, self.game.ui_scale))

    # ----------------------------------------------------------- routing

    def handle_routed(self, routed: RoutedInput) -> str | None:
        if self._grace > 0.0:
            return None
        if routed.variant == "device_removed":
            return None
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            self._on_quit()
            return MenuAction.BACK

        if routed.action in (
            InputAction.UI_SCROLL,
            InputAction.UI_SCROLL_UP,
            InputAction.UI_UP,
            InputAction.UI_DOWN,
            InputAction.UI_PAGE_UP,
            InputAction.UI_PAGE_DOWN,
        ):
            return self._scroll_by(routed)

        if (
            routed.action is InputAction.UI_POINTER_DOWN
            and routed.position is not None
            and self._rail is not None
            and self._rail.collidepoint(routed.position)
        ):
            page = max(1, self._area.height if self._area else 1)
            direction = -1 if routed.position[1] < self._rail.centery else 1
            self._scroll = max(0, self._scroll + direction * page)
            return MenuAction.MOVE_UP if direction < 0 else MenuAction.MOVE_DOWN

        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action == "quit":
            self._on_quit()
        elif action == "menu":
            self._on_menu()
        return action

    def _scroll_by(self, routed: RoutedInput) -> str:
        step = line_step(self._font())
        if routed.action is InputAction.UI_SCROLL:
            step *= max(1, int(routed.value or 1))
        elif routed.action in (InputAction.UI_SCROLL_UP, InputAction.UI_PAGE_UP, InputAction.UI_UP):
            step = -step
        elif routed.action is InputAction.UI_PAGE_DOWN:
            step *= max(1, self._area.height // step if self._area else 1)
        up = step < 0
        self._scroll = max(0, self._scroll + step)
        return MenuAction.MOVE_UP if up else MenuAction.MOVE_DOWN

    # ------------------------------------------------------------- draw

    def update(self, delta_time: float) -> None:
        self._grace = max(0.0, self._grace - delta_time)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(Colors.dark_grey)
        self.view.set_scale(self.game.ui_scale)

        margin = max(4, round(min(surface.get_size()) * 0.02))
        width = max(1, min(surface.get_width() - margin * 2, round(surface.get_width() * 0.86)))
        height = max(1, min(surface.get_height() - margin * 2, round(surface.get_height() * 0.82)))
        box = pygame.Rect(
            (surface.get_width() - width) // 2,
            (surface.get_height() - height) // 2,
            width,
            height,
        )
        pygame.draw.rect(surface, PANEL_BG, box)
        pygame.draw.rect(surface, TEXT_CRIT, box, width=2)

        title_font = menu_font(menu_font_size(DESIGN_TITLE / 2, self.game.ui_scale))
        title = title_font.render(t("title.fatal_error"), False, TEXT_CRIT)
        surface.blit(title, (box.x + margin, box.y + margin))
        title_bottom = box.y + margin + title.get_height()

        # The action rows sit inside the box, not at the bottom of the window.
        buttons_top = box.bottom - max(margin + 60, round(surface.get_height() * 0.16))
        for _ in range(3):
            placed = self.view.layout(
                surface,
                "",
                self.model,
                top=self.view.design_y(buttons_top, surface),
                highlight_color=TEXT_CRIT,
            )
            buttons = placed.panel
            if buttons.bottom <= box.bottom - margin:
                break
            buttons_top -= buttons.bottom - (box.bottom - margin)
        self.view.paint(surface, placed)

        text_width = max(1, box.width - margin * 2 - 6)
        area = pygame.Rect(
            box.x + margin,
            title_bottom + GAP,
            text_width,
            max(line_step(self._font()), buttons.top - GAP - title_bottom - GAP),
        )
        self._area = area
        pygame.draw.rect(surface, (28, 14, 18), area)
        pygame.draw.rect(surface, TEXT_CRIT, area, width=1)

        trace = self._traceback_surface(text_width - 8)
        maximum = max(0, trace.get_height() - area.height)
        self._scroll = min(self._scroll, maximum)
        visible = min(area.height, trace.get_height() - self._scroll)
        if visible > 0:
            source = pygame.Rect(0, self._scroll, text_width - 8, visible)
            surface.blit(trace, (area.x + 4, area.y + 4), source)

        self._rail = None
        if maximum:
            rail = pygame.Rect(area.right - 4, area.y, 4, area.height)
            thumb_h = max(4, round(area.height * area.height / trace.get_height()))
            thumb_y = rail.y + round((rail.height - thumb_h) * self._scroll / maximum)
            pygame.draw.rect(surface, Colors.dark_red, rail)
            pygame.draw.rect(surface, TEXT_CRIT, pygame.Rect(rail.x, thumb_y, rail.width, thumb_h))
            self._rail = rail

    def _traceback_surface(self, width: int) -> pygame.Surface:
        """Render the whole traceback once per size/scale; scroll blits a slice."""
        font = self._font()
        key = (font.get_height(), max(1, width))
        if self._trace is None or self._trace_key != key:
            self._trace = font.render(
                self.text,
                False,
                TEXT_MUTED,
                wraplength=max(1, width),
            )
            self._trace_key = key
            self._scroll = 0
        return self._trace
