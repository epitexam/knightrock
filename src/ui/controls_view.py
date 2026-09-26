"""Two-column keyboard/mouse and gamepad bindings view.

The panel itself belongs to :class:`~src.ui.grid_view.GridView`, which the
resolution picker shares; what stays here is this screen's own vocabulary: its
two columns, its row kinds and its binding cells.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.ui.grid_view import CellHit, GridCell, GridRow, GridView

__all__ = [
    "GAMEPAD_COLUMN",
    "KEYBOARD_COLUMN",
    "BindingCell",
    "BindingRow",
    "CellHit",
    "ControlsView",
    "RowKind",
]

KEYBOARD_COLUMN = 0
GAMEPAD_COLUMN = 1


class RowKind(StrEnum):
    REBIND = "rebind"
    BACK = "back"


class BindingCell(GridCell):
    """A key/button cell; the panel paints it like any other grid cell."""


@dataclass(frozen=True)
class BindingRow:
    """One binding line: a label, its keyboard cell and its gamepad cell."""

    label: str
    keyboard: BindingCell | None = None
    gamepad: BindingCell | None = None
    kind: RowKind = RowKind.REBIND

    @property
    def rebindable(self) -> bool:
        """Whether a click starts a capture, as opposed to activating the row."""
        return self.kind is RowKind.REBIND

    def as_grid_row(self) -> GridRow:
        """This row in the shared panel's vocabulary.

        ``rebindable`` becomes the panel's own ``activatable``: the panel only
        reports whether a click should *act*, and the screen decides that
        "act" means "arm a capture" for a binding and "act" for a switch.
        """
        return GridRow(self.label, (self.keyboard, self.gamepad), self.rebindable)


class ControlsView:
    """The bindings panel: a label gutter and one cell per input device.

    Built on :class:`~src.ui.grid_view.GridView` rather than being one: the
    panel is shared with the resolution picker, and this class is the adapter
    that turns binding rows into grid rows and names the two columns.
    """

    COLUMN_HEADERS = ("KEYBOARD / MOUSE", "GAMEPAD")

    def __init__(self, scale: float = 1.0) -> None:
        self._grid = GridView(scale)
        self._rows_source: Sequence[BindingRow] | None = None
        self._grid_rows: list[GridRow] = []

    @property
    def row_rects(self) -> list[pygame.Rect]:
        return self._grid.row_rects

    def cell_at(self, position: tuple[int, int]) -> CellHit | None:
        return self._grid.cell_at(position)

    def set_surface(self, surface: pygame.Surface) -> None:
        self._grid.set_surface(surface)

    def set_scale(self, scale: float) -> None:
        self._grid.set_scale(scale)

    def draw(
        self,
        surface: pygame.Surface,
        title: str,
        subtitle: str,
        rows: Sequence[BindingRow],
        *,
        selected_row: int,
        selected_column: int,
        top: int,
        footers: tuple[str, ...] = (),
    ) -> pygame.Rect:
        return self._grid.draw(
            surface,
            title,
            subtitle,
            self.COLUMN_HEADERS,
            self._project(rows),
            selected_row=selected_row,
            selected_column=selected_column,
            top=top,
            footers=footers,
        )

    def _project(self, rows: Sequence[BindingRow]) -> list[GridRow]:
        """Adapt the binding rows, memoised on the caller's list identity.

        The scene hands over the same list object on every frame it does not
        rebuild (``ControlsScene.rows`` is memoised for the same reason), so the
        projection runs once per rebuild instead of once per frame — and it is
        per frame that this view is measured.
        """
        if self._rows_source is not rows:
            self._rows_source = rows
            self._grid_rows = [row.as_grid_row() for row in rows]
        return self._grid_rows
