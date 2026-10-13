from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.core.input.input_actions import InputAction


@dataclass(frozen=True)
class MenuItem:
    """One row: what it is called, what it currently reads, and whether it acts.

    ``value`` is the row's *state*, in its own column rather than glued to the
    label. A settings screen is a table, and a column of values is what makes it
    readable: with the state appended to the label, "Borderless" and
    "Window size 1600 x 900 (auto)" are different widths of text and the eye
    has to find the change. The same reasoning the resolution picker's ``STATE``
    column gave.
    """

    action: str
    label: str
    value: str = ""
    enabled: bool = True


class MenuAction(StrEnum):
    """What the model did with an input, in the model's own vocabulary.

    ``HOVER``/``MOVE_UP``/``MOVE_DOWN`` mean *the focus moved*; anything else is
    a ``MenuItem.action``. ``BACK`` is the one value a model never returns: it
    is what a **screen** reports when it dismissed itself, so that the
    interface can tell a closure from a confirmation without a convention.
    """

    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    HOVER = "hover"
    ACTIVATE = "activate"
    BACK = "back"


#: The routed actions that move the focus, and nothing else.
#: One module-level set rather than six ``is`` tests inside
#: ``handle_routed``, which is what kept that method readable
#: as the list vocabulary grew.
_NAVIGATION_ACTIONS = frozenset(
    {
        InputAction.UI_UP,
        InputAction.UI_DOWN,
        InputAction.UI_PAGE_UP,
        InputAction.UI_PAGE_DOWN,
        InputAction.UI_HOME,
        InputAction.UI_END,
    }
)


class MenuModel:
    @staticmethod
    def is_release(variant: str | None) -> bool:
        """Whether a routed input is a stick/hat *release*.

        The router emits one release event when a held direction goes back to
        neutral, carrying the action that was active. Acting on it would add a
        second step for a single press (the very "double pas" the UI report
        described), so every consumer must check this before moving.
        """
        return variant == "release"

    def __init__(
        self,
        items: list[MenuItem] | tuple[MenuItem, ...] = (),
        *,
        wrap: bool = False,
        selected: int = 0,
    ) -> None:
        self._wrap = wrap
        self._items: tuple[MenuItem, ...] = ()
        self._current = -1
        self._hovered = -1
        # Where the pointer was on the last sample, kept apart from the
        # selection on purpose. The selection also moves with the keyboard, and
        # merging the two would make the pointer silent exactly when it
        # contradicts the keyboard: the highlight is on row 3, the pointer
        # arrives on row 0, and row 0 was already "the hovered one" as far as
        # the selection is concerned.
        self._pointer_row: int | None = None
        self.set_items(items, selected)

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
        # The pointer's row is forgotten, because the rows it was pointing at
        # are new objects with new rects. Kept across a rebuild it becomes an
        # index into a list that may no longer have that row, and the next
        # hover onto a row at that index reports "no change" -- so the cursor
        # sits over a row that does nothing until the player moves it off and
        # back on.
        self._pointer_row = None
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
                self._select(index)
                return MenuAction.MOVE_UP if direction < 0 else MenuAction.MOVE_DOWN
        return None

    def move_page(self, direction: int, page: int) -> str | None:
        """Move by a page, which is how many rows the window shows.

        A page is the window's, not a fixed count, because the
        point of the key is "where I am looking now": a smaller
        window means a smaller page, and the player's eyes never
        have to leave the panel to know where they landed.

        The row a page lands on may be disabled, and the nearest
        enabled row the way the page was going is the one a page
        means -- the same reading :meth:`move` gives one step.
        """
        if not self._items:
            return None
        start = self._current if self._current >= 0 else 0
        target = max(0, min(start + direction * max(1, page), len(self._items) - 1))
        for offset in range(len(self._items)):
            index = target + direction * offset
            if not 0 <= index < len(self._items):
                break
            if self._items[index].enabled:
                self._select(index)
                return MenuAction.MOVE_UP if direction < 0 else MenuAction.MOVE_DOWN
        return None

    def jump(self, direction: int) -> str | None:
        """To the first or last row: the whole list in one press.

        ``direction`` is the way the list runs, as in
        :meth:`move`: down (positive) is the last row. The
        scan starts at the edge asked for and works inward,
        so a disabled edge row lands on the first row that
        can be, rather than refusing because the edge
        itself cannot.
        """
        if not self._items:
            return None
        order = range(len(self._items) - 1, -1, -1) if direction > 0 else range(len(self._items))
        for index in order:
            if self._items[index].enabled:
                self._select(index)
                return MenuAction.MOVE_UP if direction < 0 else MenuAction.MOVE_DOWN
        return None

    def _select(self, index: int) -> None:
        """Move the cursor, and take the selection from the pointer.

        The keyboard has taken the selection from the pointer, so
        the pointer stops being treated as the thing that moved it.

        Without this the two fight and the pointer loses badly. Hover
        reports a change only when it lands on a row other than the
        one it last landed on, so after one arrow key the selection
        was somewhere the cursor was not, and every subsequent mouse
        move inside the *original* row reported "no change" -- the
        keyboard's row stayed drawn as selected, the cursor pointed
        at another, and nothing moved until the pointer crossed a line.
        Measured: hover row 1, press DOWN, wiggle one pixel on row 1,
        and the selection stayed on row 2 while the cursor sat on row 1.
        """
        self._current = index
        self._pointer_row = None

    def hover(self, position: tuple[int, int], rects: Sequence[pygame.Rect]) -> str | None:
        """Focus the item under the pointer; report only when the focus moved.

        A pointer is routed on every mouse sample, so returning ``HOVER`` for
        all of them describes the *motion*, not the *interaction* — and the
        motion is not something a screen, or anything listening to it, can act
        on. Returning the move only when the pointer lands on a row it was not
        on makes this the exact counterpart of :meth:`move`, which already
        returns None when the selection is blocked.

        Leaving the rows reports nothing and forgets the position, so coming
        back onto one reports again.
        """
        self._hovered = -1
        row: int | None = None
        for index, rect in enumerate(rects):
            if (
                index < len(self._items)
                and self._items[index].enabled
                and rect.collidepoint(position)
            ):
                row = index
                break
        moved = row is not None and row != self._pointer_row
        self._pointer_row = row
        if row is None:
            return None
        self._hovered = row
        self._current = row
        return MenuAction.HOVER if moved else None

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
        rects: Sequence[pygame.Rect],
        variant: str | None = None,
    ) -> tuple[str | None, str | None]:
        if self.is_release(variant):
            # Releasing the stick must never move the cursor: without this
            # guard every press (move +1) was followed by a second move on
            # release -- a double step, which reads as lag.
            return None, variant
        if action in _NAVIGATION_ACTIONS:
            return self._navigate(action, rects), variant
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

    def _navigate(self, action: InputAction, rects: Sequence[pygame.Rect]) -> str | None:
        """The six ways a list moves: one row, a page, or an edge.

        Kept apart from :meth:`handle_routed` because the
        router's vocabulary grew past what one method reads
        like: a page is a move with the window's row count
        in it, and an edge is a move that starts at the
        end, but both are still "the focus moved".
        """
        if action is InputAction.UI_UP:
            return self.move(-1)
        if action is InputAction.UI_DOWN:
            return self.move(1)
        if action is InputAction.UI_PAGE_UP:
            return self.move_page(-1, self._page_size(rects))
        if action is InputAction.UI_PAGE_DOWN:
            return self.move_page(1, self._page_size(rects))
        if action is InputAction.UI_HOME:
            return self.jump(-1)
        if action is InputAction.UI_END:
            return self.jump(1)
        return None

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

    @staticmethod
    def _page_size(rects: Sequence[pygame.Rect]) -> int:
        """How many rows are on screen, which is what a page is.

        The rects the view painted, one per item: a row scrolled
        out of view keeps its place with an empty rect, so the
        painted ones are exactly the visible ones.
        """
        return max(1, sum(1 for rect in rects if rect.width > 0))
