"""Menu navigation: the keyboard and the pointer are two devices, not one row.

Every test here is a *sequence*, not a state. A menu's navigation bugs are not
about where the selection is -- it is always somewhere defensible -- but about
what happens when the two ways of moving it interleave, and a test that only
looks at the state after one action cannot see any of them.

The three that were real, and are pinned here:

- **the pointer lost.** ``hover`` reported a change only when it landed on a row
  other than the one it last landed on, so after one arrow key the selection was
  somewhere the cursor was not and every subsequent mouse move inside the
  *original* row reported "no change". The keyboard's row stayed drawn as
  selected, the cursor pointed at another, and nothing moved until the pointer
  crossed a line.
- **a rebuild ate a hover.** The remembered pointer row survived replacing the
  items, so it became an index into a list that might no longer have that row.
- **the two devices looked identical.** The ``>`` marker and the amber text both
  said "a key press acts here", and nothing said "the cursor is here", so the
  disagreement was invisible.
"""

from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((1152, 648))

from src.core.input.input_actions import InputAction  # noqa: E402
from src.ui.menu_model import MenuItem, MenuModel  # noqa: E402
from src.ui.menu_view import MenuView  # noqa: E402
from src.ui.styles import GOLD  # noqa: E402

ROW = 40


def _menu(count: int = 6) -> MenuModel:
    return MenuModel(tuple(MenuItem(f"r{index}", f"Row {index}") for index in range(count)))


def _rects(count: int = 6) -> list[pygame.Rect]:
    return [pygame.Rect(0, index * ROW, 200, ROW) for index in range(count)]


def _hover(model: MenuModel, rects, index: int) -> object:
    return model.handle_routed(InputAction.UI_POINTER_MOVE, (10, index * ROW + 5), rects)[0]


def _click(model: MenuModel, rects, index: int) -> object:
    return model.handle_routed(InputAction.UI_POINTER_DOWN, (10, index * ROW + 5), rects)[0]


def _key(model: MenuModel, action: InputAction) -> object:
    return model.handle_routed(action, None, _rects(len(model.items)))[0]


# --- the pointer losing to the keyboard --------------------------------------


def test_a_keypress_does_not_silence_the_pointer() -> None:
    """The bug, in the order it happened.

    Hover a row, press a key, then move the mouse *within the row it was already
    on*. Before the fix the last step reported no change and the selection stayed
    wherever the key had put it, which left the cursor on a row that a key press
    would not act on and no visual told the player so.
    """
    model, rects = _menu(), _rects()

    _hover(model, rects, 1)
    assert model.current_index == 1

    _key(model, InputAction.UI_DOWN)
    assert model.current_index == 2, "the key moved the selection"

    # The pointer has not left row 1. One pixel of movement, as a hand produces.
    _hover(model, rects, 1)

    assert model.current_index == 1, (
        "the pointer must be able to take the selection back, even without "
        "crossing into a different row"
    )


def test_the_pointer_takes_over_again_and_again() -> None:
    """Not a one-shot: each keypress hands control over, each move takes it back."""
    model, rects = _menu(), _rects()

    for round_number in range(3):
        _hover(model, rects, round_number)
        assert model.current_index == round_number
        _key(model, InputAction.UI_DOWN)
        assert model.current_index == round_number + 1
        _hover(model, rects, round_number)
        assert model.current_index == round_number, f"round {round_number}"


def test_both_devices_report_where_they_are() -> None:
    """Selected and pointed are different facts, and both are readable.

    The model already kept them apart -- ``current_index`` for the selection,
    ``hovered_index`` for the pointer -- and nothing drew the second one. This is
    the fact the outline in :mod:`src.ui.menu_view` is drawn from, so it is worth
    holding that they are genuinely independent.
    """
    model, rects = _menu(), _rects()

    _hover(model, rects, 3)
    assert model.hovered_index == 3

    _key(model, InputAction.UI_DOWN)
    assert model.current_index == 4
    assert model.hovered_index == 3, "the pointer is still where the player left it"

    _hover(model, rects, 3)
    assert model.current_index == 3
    assert model.hovered_index == 3


def test_leaving_the_rows_clears_the_pointer_but_not_the_selection() -> None:
    """The outline disappears when the cursor leaves; the selection stays put.

    Otherwise the row keeps a marker for a cursor that is no longer on it, which
    is the same "looks alive, is not" family as the disabled row this menu has
    already produced twice.
    """
    model, rects = _menu(), _rects()

    _hover(model, rects, 2)
    _hover(model, rects, 99)  # below every row

    assert model.hovered_index == -1
    assert model.current_index == 2


# --- a rebuild eating a hover -----------------------------------------------


def test_a_rebuild_forgets_which_row_the_pointer_was_on() -> None:
    """A rebuild makes the old row number meaningless, so it must be dropped.

    Park the pointer on the last of ten rows, then have the list become four rows
    -- which is what a value change or a narrower window does. The remembered
    index points past the end, and the next hover onto a row at that index
    reports "no change", so the cursor sits over a row that does nothing.
    """
    model = _menu(10)
    rects = _rects(10)
    _hover(model, rects, 9)

    model.set_items(tuple(MenuItem(f"r{i}", f"Row {i}") for i in range(4)), 0)

    _hover(model, _rects(4), 3)
    assert model.current_index == 3, "the first hover after a rebuild was swallowed"


def test_a_rebuild_to_a_different_list_still_hovers() -> None:
    """Same rows, different content: the pointer must not assume anything."""
    model, rects = _menu(), _rects()
    _hover(model, rects, 4)

    model.set_items(
        (MenuItem("a", "A"), MenuItem("b", "B"), MenuItem("c", "C"), MenuItem("d", "D")),
        0,
    )
    _hover(model, _rects(4), 2)

    assert model.current_index == 2


# --- the pointer has to be visible -------------------------------------------


def test_the_pointed_row_is_drawn_distinctly_from_the_selected_one() -> None:
    """The visual half of the fix.

    Two devices disagreeing on screen with no mark between them is what made the
    navigation feel wrong without being identifiable: the player saw a highlight
    on one row, aimed at another, and nothing accounted for the difference.
    """
    view = MenuView(1.0)
    surface = pygame.Surface((1152, 648))
    model = _menu(4)
    rects = _rects(4)

    # Point at row 2, then drive the selection to row 3 with the keyboard.
    _hover(model, rects, 2)
    _key(model, InputAction.UI_DOWN)
    view.draw(surface, "MENU", model, top=100)

    # The outline is drawn on the pointed row's left edge, so the border band is
    # sampled rather than the row body -- the body carries the text, which is
    # there on both rows. Sampled with get_at because this project has no numpy,
    # and a test that needs one would not run in CI.
    def border(rect: pygame.Rect) -> set[tuple[int, int, int]]:
        band = surface.subsurface(pygame.Rect(rect.x - 3, rect.y, rect.width + 6, rect.height))
        return {
            band.get_at((x, y))[:3]
            for x in range(band.get_width())
            for y in (1, 2, band.get_height() - 3, band.get_height() - 2)
        }

    pointed = border(view.item_rects[2])
    selected = border(view.item_rects[3])
    assert pointed != selected, "the pointed row is drawn exactly like the selected one"
    assert any(abs(colour[0] - GOLD[0]) < 24 for colour in pointed), (
        f"the pointed row's border has no accent in it: {sorted(pointed)[:4]}"
    )


def test_the_outline_is_not_drawn_on_the_selected_row() -> None:
    """One mark per row. Outlining the selected row too would say nothing."""
    view = MenuView(1.0)
    surface = pygame.Surface((1152, 648))
    model, rects = _menu(), _rects()
    _hover(model, rects, 1)  # hover alone selects the row too

    view.draw(surface, "MENU", model, top=100)
    drawn_with_pointer = pygame.image.tobytes(surface.subsurface(view.item_rects[1]), "RGB")

    model2 = _menu()
    _key(model2, InputAction.UI_DOWN)  # row 1 selected with no pointer on it
    view.set_scale(1.0)
    view.draw(surface, "MENU", model2, top=100)
    drawn_without = pygame.image.tobytes(surface.subsurface(view.item_rects[1]), "RGB")

    assert drawn_with_pointer != drawn_without, (
        "the selected row looks the same with and without the pointer on it"
    )


def test_the_outline_colour_is_the_shared_accent() -> None:
    """One gold in the interface, not a second yellow nobody else uses."""
    from src.ui.styles import POINTER_OUTLINE

    assert POINTER_OUTLINE == GOLD


# --- clicking ----------------------------------------------------------------


def test_a_click_acts_on_the_row_under_the_cursor_not_the_selected_one() -> None:
    """A click carries its own target, so the selection does not matter.

    This is the reason the pointer and the selection are separate facts at all:
    a player can point at a row without having selected it -- which is the normal
    state right after a keyboard walk -- and the click must answer the row they
    aimed at.
    """
    model, rects = _menu(), _rects()
    _hover(model, rects, 1)
    _key(model, InputAction.UI_DOWN)
    assert model.current_index == 2, "the keyboard moved the selection elsewhere"

    assert _click(model, rects, 1) == "r1"
    assert model.current_index == 1


def test_a_click_outside_every_row_does_nothing() -> None:
    """Past the last row there is no row, so there is nothing to activate."""
    model, rects = _menu(), _rects()

    assert _click(model, rects, 99) is None
    assert model.current_index == 0, "a miss moved the selection"


# --- the rows themselves stay coherent --------------------------------------


@pytest.mark.parametrize("count", [1, 2, 6, 28])
def test_hovering_picks_the_row_the_geometry_says(count: int) -> None:
    """The model and the rects have to agree, over the shapes that are used.

    A 28-entry list is the option screen's worst case, and a one-entry list is
    the simplest screen in the game; both go through the same code, so both are
    worth holding.
    """
    model = _menu(count)
    rects = _rects(count)

    for index in range(count):
        _hover(model, rects, index)
        assert model.current_index == index, f"row {index} of {count}"
