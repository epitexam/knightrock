"""A screen that lists options and applies one on selection.

Every settings choice with more than a handful of values gets one of these
rather than a ←/→ cycle: a cycle hides every value but the current one, and
needs a press per step to reach the one wanted. A list shows every option, marks
the one in force, and takes one press.

**Apply on selection, not on highlight.** Moving the highlight through the list
changes nothing; picking an entry applies it and closes. The alternative --
applying as the highlight moves -- looks better and is a trap: scrolling through
the ladder would rebuild the window on every step, and a player browsing would
leave the game in whatever they happened to scroll past. Highlight is a cursor,
selection is a choice, and only the second one is a decision the player made.

One class rather than one per setting, deliberately. Four bespoke pickers is four
places for the keyboard, the mouse and the gamepad to disagree about what Enter
does, and that class of bug has already cost this menu twice -- six of nine rows
answered a click and none of them changed anything. Every picker here gets the
same behaviour because there is only one implementation of it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.application.scenes.menu_page import MenuPage
from src.ui.menu_model import MenuItem
from src.ui.text import t

if TYPE_CHECKING:
    from src.core.game import Game


@dataclass(frozen=True)
class Option:
    """One choice, with enough context to choose it without guessing.

    ``detail`` is what makes the list usable rather than merely navigable: two
    fit policies are words, and "fills the window, cropping the edges" is the
    difference between a player picking one on purpose and picking whichever came
    first.

    ``value`` is compared against ``selected`` to draw the check. It is compared
    by equality rather than by index, so a list can be filtered or reordered
    without the mark drifting onto the wrong entry -- the failure a fixed index
    has whenever the source list is rebuilt, which is every frame the topology
    changes.
    """

    label: str
    value: Any
    detail: str = ""
    enabled: bool = True

    def matches(self, selected: Any) -> bool:
        """Whether this is the option in force.

        ``is`` for the sentinels and ``==`` for the rest, because a tuple of
        ints compares fine while a freshly built enum member does not always
        identify by value across a rebuild.
        """
        if self.value is selected:
            return True
        try:
            return bool(self.value == selected)
        except Exception:  # noqa: BLE001 - an odd __eq__ is not worth a crash
            return False


class OptionScreen(MenuPage):
    """A list of options; picking one applies it and returns.

    ``apply`` is called with the chosen option's ``value``. It is expected to do
    the work immediately -- that is the contract that makes apply-on-selection
    honest -- and this screen does not wait for it or check its result. A setting
    that cannot be honoured says so in its own row, which is a better place for
    that than a modal would be.

    ``on_back`` is called before the screen closes, by a choice or by Back, so
    the opener can rebuild its rows and keep its focus on the row that opened it.
    """

    scrollable = True

    def __init__(
        self,
        game: Game,
        title: str,
        options: Sequence[Option],
        apply: Callable[[Any], None],
        *,
        selected: Any = None,
        footer: str = "footer.page",
        subtitle: str = "",
        on_back: Callable[[], None] | None = None,
    ) -> None:
        self.options = tuple(options)
        self.selected = selected
        super().__init__(game, self._items(), selected=self._index_of(selected))
        self.title = title
        self.apply = apply
        self.footer = footer
        self.subtitle = subtitle
        self.on_back = on_back

    # ------------------------------------------------------------------ rows

    def _items(self) -> tuple[MenuItem, ...]:
        """The options as rows, plus a Back row.

        The mark is a leading ``●`` on the label rather than a column, because
        the value column is right-aligned and a right-aligned checkmark reads as
        the end of a long value at a glance.
        """
        rows = [
            MenuItem(
                f"option:{index}",
                ("● " if option.matches(self.selected) else "") + option.label,
                enabled=option.enabled,
            )
            for index, option in enumerate(self.options)
        ]
        rows.append(MenuItem("back", t("row.back")))
        return tuple(rows)

    def _index_of(self, selected: Any) -> int:
        """Where the cursor starts: on the option in force."""
        for index, option in enumerate(self.options):
            if option.matches(selected):
                return index
        return 0

    def _rebuild(self, selected: Any) -> None:
        """Rebuild the rows around a new ``selected``, keeping the cursor put."""
        cursor = self.model.current_index
        self.selected = selected
        self.model.set_items(self._items(), cursor)

    # --------------------------------------------------------------- routing

    def act(self, action: str) -> None:
        if action.startswith("option:"):
            self._choose(int(action.partition(":")[2]))

    def _choose(self, index: int) -> None:
        """Apply the option and go back to the screen that opened this one.

        Applied *before* the pop, so the opener sees the change while it is still
        on the stack. A disabled entry refuses, visibly, rather than closing.
        """
        if not 0 <= index < len(self.options):
            return
        option = self.options[index]
        if not option.enabled:
            return
        self.apply(option.value)
        self.leave()

    def leave(self) -> str | None:
        if self.on_back is not None:
            self.on_back()
        return super().leave()

    # ------------------------------------------------------------------ draw

    def description(self) -> str:
        return self._description_for(self.model.current_item)

    def _description_for(self, focused: MenuItem | None) -> str:
        """The focused option's note: one line, for the row being looked at."""
        if focused is None or not focused.action.startswith("option:"):
            return ""
        index = int(focused.action.partition(":")[2])
        if not 0 <= index < len(self.options):
            return ""
        return self.options[index].detail
