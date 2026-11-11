"""A screen that lists options and applies one on selection.

Used for every setting with more than a handful of values: a list shows all of
them, marks the one in force, and takes one press. Moving the highlight changes
nothing; picking applies and closes -- applying on highlight would rebuild the
window at every step of a scroll. One class for every picker, so keyboard,
mouse and pad cannot disagree about what Enter does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.application.scenes.menu_page import MenuPage
from src.ui.menu_model import MenuItem
from src.ui.text import t

if TYPE_CHECKING:
    from src.application.game import Game


@dataclass(frozen=True)
class Option:
    """One choice: a label, the value it applies, and a note on what it does.

    The mark is placed by comparing ``value`` with the selected value, not by
    index, so a rebuilt or filtered list keeps it on the right entry.
    """

    label: str
    value: Any
    detail: str = ""
    enabled: bool = True

    def matches(self, selected: Any) -> bool:
        """Whether this is the option in force: ``is`` first, then ``==``."""
        if self.value is selected:
            return True
        try:
            return bool(self.value == selected)
        except Exception:  # noqa: BLE001 - an odd __eq__ is not worth a crash
            return False


#: The mark on the option in force. A glyph the menu font has: it has no "●".
SELECTED_MARK = "•"


class OptionScreen(MenuPage):
    """A list of options; picking one applies it and returns.

    ``apply`` gets the chosen ``value`` and is expected to act at once.
    ``on_back`` runs before the screen closes, by a choice or by Back, so the
    opener can rebuild its rows and keep its focus.
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
        """The options as rows, plus Back; the one in force carries :data:`SELECTED_MARK`."""
        rows = [
            MenuItem(
                f"option:{index}",
                (f"{SELECTED_MARK} " if option.matches(self.selected) else "") + option.label,
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
