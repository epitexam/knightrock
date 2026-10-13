import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel


def test_menu_model_moves_with_wrap_and_skips_disabled_items() -> None:
    model = MenuModel(
        [
            MenuItem("one", "One"),
            MenuItem("locked", "Locked", enabled=False),
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

    model = MenuModel([MenuItem("one", "One"), MenuItem("locked", "Locked", enabled=False)])
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
    model = MenuModel([MenuItem("one", "One"), MenuItem("locked", "Locked", enabled=False)])
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


@pytest.mark.parametrize("scale", [0.0, -1.0, 100.0, float("nan")])
def test_menu_model_rejects_an_unusable_scale(scale: float) -> None:
    """Bounded, not a fixed set of three.

    The scale the views are handed is the player's preference times the target's
    pixel density, and the density is a fraction on most displays -- 1.889 on a
    2176x1224 window -- so a ladder of ``(0.8, 1.0, 1.2)`` would refuse the value
    the game itself computes. What still has to be refused is a scale that would
    make the interface invisible or larger than the screen, and a NaN, which
    would quietly produce zero-sized rects everywhere.
    """
    from src.ui.menu_view import MenuView

    with pytest.raises(ValueError, match="interface scale"):
        MenuView(scale=scale)


@pytest.mark.parametrize("scale", [0.5, 0.8, 1.0, 1.25, 1.511, 1.8889, 2.4, 4.0])
def test_menu_model_accepts_the_scales_the_game_actually_produces(scale: float) -> None:
    from src.ui.menu_view import MenuView

    assert MenuView(scale=scale)._scale == scale


# --- pages and edges -------------------------------------------------------


def test_a_page_is_how_many_rows_the_window_shows() -> None:
    """A page is the window's, not a fixed count.

    The point of the key is "where I am looking now", so a
    smaller window must mean a smaller page -- otherwise the
    key lands somewhere the player cannot see, which is
    worse than not having it.
    """
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(30)])
    rects = [pygame.Rect(0, 0, 10, 10) for _ in range(5)]

    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    assert model.current_index == 5
    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    assert model.current_index == 10

    # A window showing two rows pages by two.
    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects[:2])
    assert model.current_index == 12


def test_a_page_clamps_at_the_end_of_the_list() -> None:
    """A page that would run off the end lands on the last row.

    The alternative is refusing to move, which leaves the
    player one page short of the end with no way to close
    the gap except row by row.
    """
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(12)])
    rects = [pygame.Rect(0, 0, 10, 10) for _ in range(5)]

    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    assert model.current_index == 11


def test_a_page_lands_on_the_nearest_row_the_way_it_was_going() -> None:
    """The row a page lands on may be locked; the page still means
    something, which is the nearest row the way it was going -- the
    same reading a single step gives.
    """
    model = MenuModel(
        [
            MenuItem("row 0", "0"),
            MenuItem("row 1", "1"),
            MenuItem("locked", "", enabled=False),
            MenuItem("row 3", "3"),
            MenuItem("row 4", "4"),
            MenuItem("row 5", "5"),
        ]
    )
    rects = [pygame.Rect(0, 0, 10, 10) for _ in range(2)]

    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    # A page of two from row 0 lands on row 2, which is locked, so
    # the page continues to row 3.
    assert model.current_index == 3


def test_home_and_end_jump_to_the_edges_of_the_list() -> None:
    """The whole list in one press, in both directions."""
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(30)])
    rects = [pygame.Rect(0, 0, 10, 10) for _ in range(5)]

    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects)
    model.handle_routed(InputAction.UI_END, None, rects)
    assert model.current_index == 29
    model.handle_routed(InputAction.UI_HOME, None, rects)
    assert model.current_index == 0


def test_home_and_end_skip_a_locked_edge() -> None:
    """A locked first row must not make Home refuse: the scan works
    inward from the edge, so the key lands on the first row that
    can be.
    """
    model = MenuModel(
        [
            MenuItem("locked first", "", enabled=False),
            MenuItem("first usable", "1"),
            MenuItem("middle", "2"),
            MenuItem("last usable", "3"),
            MenuItem("locked last", "", enabled=False),
        ]
    )
    rects = [pygame.Rect(0, 0, 10, 10)]

    model.handle_routed(InputAction.UI_HOME, None, rects)
    assert model.current_index == 1
    model.handle_routed(InputAction.UI_END, None, rects)
    assert model.current_index == 3


def test_a_page_takes_the_selection_from_the_pointer() -> None:
    """A page is a keyboard move, so the pointer must stop being
    treated as the thing that moved the selection -- the same rule
    as an arrow key, or the two devices fight over the row.

    The observable half of that rule: hovering the row the pointer
    is already on reports a change again, because the keyboard
    forgot where the pointer was.
    """
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(10)])
    rects = [pygame.Rect(0, i * 10, 10, 10) for i in range(10)]

    model.hover((5, 55), rects)
    assert model.hovered_index == 5
    model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects[:2])
    assert model.current_index == 7
    # The pointer is on row 5 and has not moved, yet the hover
    # reports a change: the keyboard move cleared its memory.
    assert model.hover((5, 55), rects) == "hover"


def test_a_page_moves_an_empty_list_nowhere() -> None:
    model = MenuModel()
    rects: list[pygame.Rect] = []

    assert model.handle_routed(InputAction.UI_PAGE_DOWN, None, rects) == (
        None,
        None,
    )
    assert model.handle_routed(InputAction.UI_END, None, rects) == (None, None)
    assert model.current_index == -1
