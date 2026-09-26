import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel


def test_menu_model_moves_with_wrap_and_skips_disabled_items() -> None:
    model = MenuModel(
        [
            MenuItem("one", "One"),
            MenuItem("locked", "Locked", False),
            MenuItem("two", "Two"),
        ],
        wrap=True,
    )

    assert model.current_index == 0
    assert model.move(1) == "move_down"
    assert model.current_index == 2
    assert model.move(1) == "move_down"
    assert model.current_index == 0
    assert model.move(-1) == "move_up"
    assert model.current_index == 2


def test_menu_model_does_not_wrap_up_or_down_by_default() -> None:
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])

    assert model.move(-1) is None
    assert model.current_index == 0
    assert model.move(1) == "move_down"
    assert model.current_index == 1
    assert model.move(1) is None
    assert model.current_index == 1


def test_menu_model_handles_hover_activation_and_empty_state() -> None:
    empty = MenuModel()
    assert empty.current_item is None
    assert empty.move(1) is None

    model = MenuModel([MenuItem("one", "One"), MenuItem("locked", "Locked", False)])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    assert model.hover((1, 1), rects) == "hover"
    assert model.activate() == "one"
    assert model.hover((1, 15), rects) is None
    assert model.activate() == "one"


def test_menu_model_reports_a_hover_only_when_the_pointer_moves() -> None:
    """One report per row the pointer lands on, however it got there.

    A pointer is routed on every mouse sample, so reporting the motion would
    say nothing a screen could act on — and would machine-gun anything listening.
    This is the counterpart of ``move`` returning None when it is blocked.
    """
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    assert model.hover((5, 5), rects) == "hover"  # lands on the first row
    assert model.hover((7, 5), rects) is None  # still on it
    assert model.hover((5, 15), rects) == "hover"  # the second row
    assert model.hover((5, 5), rects) == "hover"  # back to the first
    assert model.hover((500, 500), rects) is None  # off the rows
    assert model.hover((5, 5), rects) == "hover"  # and back again


def test_hovering_a_locked_item_reports_nothing() -> None:
    """A disabled row is not a place the focus can land, so it is not a move."""
    model = MenuModel([MenuItem("one", "One"), MenuItem("locked", "Locked", False)])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    assert model.hover((5, 5), rects) == "hover"
    assert model.hover((5, 15), rects) is None
    assert model.hovered_index == -1


def test_the_pointer_reports_even_over_the_row_the_keyboard_already_selected() -> None:
    """The pointer's position is its own state, apart from the selection.

    Merging the two made the pointer silent exactly when it contradicted the
    keyboard: the highlight sits on row 2, the pointer arrives on row 0, and
    row 0 was already the hovered one as far as the selection is concerned —
    so the visible jump came with no report at all.
    """
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    assert model.move(1) == "move_down"  # the keyboard moves the selection
    assert model.hover((5, 5), rects) == "hover"

    assert model.current_index == 0


def test_menu_model_routes_pointer_down_and_confirm() -> None:
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    action, _ = model.handle_routed(InputAction.UI_POINTER_DOWN, (1, 15), rects)
    assert action == "two"

    model.set_items([MenuItem("one", "One"), MenuItem("two", "Two")])
    action, _ = model.handle_routed(InputAction.UI_CONFIRM, None, rects)
    assert action == "one"


def test_menu_model_rejects_invalid_scale() -> None:
    from src.ui.menu_view import MenuView

    with pytest.raises(ValueError, match="UI scale"):
        MenuView(scale=2.0)
