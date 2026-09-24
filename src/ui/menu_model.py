from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.core.input.input_actions import InputAction


@dataclass(frozen=True)
class MenuItem:
    action: str
    label: str
    enabled: bool = True


class MenuAction(StrEnum):
    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    HOVER = "hover"
    ACTIVATE = "activate"


class MenuModel:
    def __init__(
        self, items: list[MenuItem] | tuple[MenuItem, ...] = (), *, wrap: bool = False
    ) -> None:
        self._wrap = wrap
        self._items: tuple[MenuItem, ...] = ()
        self._current = -1
        self._hovered = -1
        self.set_items(items)

    @property
    def items(self) -> tuple[MenuItem, ...]:
        return self._items

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def hovered_index(self) -> int:
        return self._hovered

    @property
    def current_item(self) -> MenuItem | None:
        return self._items[self._current] if 0 <= self._current < len(self._items) else None

    def set_items(self, items: list[MenuItem] | tuple[MenuItem, ...], selected: int = 0) -> None:
        self._items = tuple(items)
        if not self._items:
            self._current = -1
            self._hovered = -1
            return
        self._current = self._nearest_enabled(selected)
        self._hovered = self._current

    def move(self, direction: int) -> str | None:
        if not self._items:
            return None
        start = self._current if self._current >= 0 else 0
        for offset in range(1, len(self._items) + 1):
            index = start + direction * offset
            if self._wrap:
                index %= len(self._items)
            elif not 0 <= index < len(self._items):
                break
            if self._items[index].enabled:
                self._current = index
                return MenuAction.MOVE_UP if direction < 0 else MenuAction.MOVE_DOWN
        return None

    def hover(self, position: tuple[int, int], rects: list[pygame.Rect]) -> str | None:
        self._hovered = -1
        for index, rect in enumerate(rects):
            if (
                index < len(self._items)
                and self._items[index].enabled
                and rect.collidepoint(position)
            ):
                self._hovered = index
                self._current = index
                return MenuAction.HOVER
        return None

    def activate(self, index: int | None = None) -> str | None:
        target = self._hovered if index is None and self._hovered >= 0 else index
        if target is None:
            target = self._current
        if not 0 <= target < len(self._items) or not self._items[target].enabled:
            return None
        self._current = target
        return self._items[target].action

    def handle_routed(
        self,
        action: InputAction,
        position: tuple[int, int] | None,
        rects: list[pygame.Rect],
        variant: str | None = None,
    ) -> tuple[str | None, str | None]:
        if variant == "release":
            # Le relâchement du stick ne doit jamais déplacer le curseur :
            # sans ce garde, chaque press (move +1) était suivi d'un
            # second move au release -> double-pas / sensation de lag.
            return None, variant
        if action is InputAction.UI_UP:
            return self.move(-1), variant
        if action is InputAction.UI_DOWN:
            return self.move(1), variant
        if action is InputAction.UI_POINTER_MOVE and position is not None:
            return self.hover(position, rects), variant
        if action is InputAction.UI_POINTER_DOWN and position is not None:
            for index, rect in enumerate(rects):
                if rect.collidepoint(position):
                    return self.activate(index), variant
            return None, variant
        if action is InputAction.UI_CONFIRM:
            if variant == "new_game":
                return "new_game", variant
            return self.activate(self._current), variant
        return None, variant

    def _nearest_enabled(self, selected: int) -> int:
        if not self._items:
            return -1
        if 0 <= selected < len(self._items) and self._items[selected].enabled:
            return selected
        for offset in range(1, len(self._items) + 1):
            index = (selected + offset) % len(self._items)
            if self._items[index].enabled:
                return index
        return -1
