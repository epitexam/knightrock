import os

import pygame
import pytest

from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


def test_menu_view_returns_item_rects_inside_panel() -> None:
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView()

    panel = view.draw(surface, "TITLE", model, top=120)

    assert panel.width > 0
    assert len(view.item_rects) == 2
    assert all(panel.contains(rect) for rect in view.item_rects)


def test_menu_view_recalculates_geometry_after_surface_change() -> None:
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView()
    first_surface = pygame.Surface((640, 480))
    second_surface = pygame.Surface((1280, 720))
    view.draw(first_surface, "TITLE", model, top=120)
    first_rects = view.item_rects
    second_panel = view.draw(second_surface, "TITLE", model, top=120)
    second_rects = view.item_rects

    assert first_rects != second_rects
    assert all(second_panel.contains(rect) for rect in second_rects)
    assert not all(second_panel.contains(rect) for rect in first_rects)


def test_menu_view_changes_geometry_with_scale() -> None:
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One")])

    normal = MenuView().draw(surface, "TITLE", model, top=120)
    large = MenuView(1.2).draw(surface, "TITLE", model, top=120)

    assert large.width >= normal.width
    assert large.height >= normal.height


# --- the scroll rail -------------------------------------------------------


def test_a_list_that_fits_paints_no_rail() -> None:
    """A rail beside a complete list is a lie about it.

    The rail exists to say "there is more below"; painted next
    to a list that fits, it would send the player scrolling
    into nothing.
    """
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(5)])
    view = MenuView()

    view.draw(surface, "TITLE", model, top=120, scrollable=True)

    assert view.scroll_rail is None
    assert view.scroll_thumb is None


def test_a_list_that_scrolls_paints_a_rail_in_the_gutter() -> None:
    """The last visible row of a cut-off list reads as the last row.

    The rail answers "there is more" before the player scrolls
    and finds out. It sits in the padding gutter -- right of the
    rows, left of the panel's border -- so it never overlaps a
    label, a value, or the border itself.
    """
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(28)])
    view = MenuView()

    panel = view.draw(surface, "TITLE", model, top=120, scrollable=True)

    rail = view.scroll_rail
    thumb = view.scroll_thumb
    assert rail is not None and thumb is not None
    assert panel.contains(rail)
    drawn = [rect for rect in view.item_rects if rect.width > 0]
    assert all(rect.right <= rail.left for rect in drawn), "the rail overlaps a row"
    assert rail.right <= panel.right - 1, "the rail crosses the panel border"


def test_the_thumb_says_how_much_is_visible_and_how_far_in() -> None:
    """Its height is the visible fraction; its place is the scrolled-to
    fraction. Those two facts are the whole point of the shape.
    """
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(28)])
    view = MenuView()

    view.draw(surface, "TITLE", model, top=120, scroll=0, scrollable=True)
    rail, thumb = view.scroll_rail, view.scroll_thumb
    visible = sum(1 for rect in view.item_rects if rect.width > 0)

    assert thumb.top == rail.top, "at the top of the list, the thumb is at the top"
    expected = round(rail.height * visible / len(model.items))
    assert abs(thumb.height - expected) <= 1, (
        f"the thumb is {thumb.height}px for {visible} of {len(model.items)} rows"
    )

    last = len(model.items) - visible
    view.draw(surface, "TITLE", model, top=120, scroll=last, scrollable=True)
    assert view.scroll_thumb.bottom == view.scroll_rail.bottom, (
        "at the end of the list, the thumb is at the bottom"
    )

    middle = last // 2
    view.draw(surface, "TITLE", model, top=120, scroll=middle, scrollable=True)
    thumb = view.scroll_thumb
    travel = view.scroll_rail.height - thumb.height
    assert 0 < thumb.top - view.scroll_rail.top < travel, (
        "halfway down the list, the thumb is neither at the top nor the bottom"
    )


def test_the_rail_follows_the_window() -> None:
    """A rail is a claim about the current window, not the last one.

    The geometry is dropped when the caches are, so a window that
    grows until the list fits does not keep claiming there is
    more below.
    """
    small = pygame.Surface((640, 480))
    large = pygame.Surface((1152, 648))
    model = MenuModel([MenuItem(f"row {i}", str(i)) for i in range(28)])
    view = MenuView()

    view.draw(small, "TITLE", model, top=120, scrollable=True)
    assert view.scroll_rail is not None, "the fixture did not overflow"

    view.draw(large, "TITLE", model, top=120, scrollable=True)
    drawn = sum(1 for rect in view.item_rects if rect.width > 0)
    if drawn == len(model.items):
        assert view.scroll_rail is None, "the list fits, but the rail is still painted"
    else:
        assert view.scroll_rail is not None


# --- the fitted description ------------------------------------------------


def test_a_long_description_is_cut_rather_than_left_to_spill() -> None:
    """Free-form prose is the one line that can outgrow its panel.

    Measured: 190 characters render 1158px wide against a 616px panel,
    and the centred text spills out over both sides -- a note the
    player cannot read the end of. Cut with a marker instead, because
    the band's height is reserved as one line and wrapping it would
    make the panel's height a function of the note's length, which is
    the reflow a scrolling list is meant not to have.
    """
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One")])
    view = MenuView()
    long_note = "A much longer description that wraps across several lines of text. " * 3

    panel = view.draw(surface, "TITLE", model, top=120, description=long_note)

    assert view.description_width > 0
    assert view.description_width + 2 * 28 <= panel.width, (
        f"the description is {view.description_width}px wide in a {panel.width}px panel"
    )


def test_a_short_description_is_untouched() -> None:
    """Cutting only where it has to: a note that fits is drawn whole,
    with no marker on the end.
    """
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One")])
    view = MenuView()
    note = "shows the whole picture; black bars on the sides"
    long_note = note + " and a great many more words than any panel on this screen can hold"
    footer_font = view._fonts_for(1.0)[2]

    view.draw(surface, "TITLE", model, top=120, description=note)
    assert view.description_width == footer_font.size(note)[0], "the short note was cut"

    raw = footer_font.size(long_note)[0]
    view.draw(surface, "TITLE", model, top=120, description=long_note)
    assert view.description_width < raw, "the long note was not cut"
    assert view.description_width <= surface.get_width() - 24, "the cut note still spills"


def test_the_description_fitted_the_same_way_in_a_small_window() -> None:
    """The limit is the *screen's*, not the panel's: the panel is sized
    partly from the description, so fitting it to the panel would be
    fitting it to a number that depends on it.
    """
    small = pygame.Surface((400, 320))
    model = MenuModel([MenuItem("one", "One")])
    view = MenuView()
    view.set_surface(small)
    long_note = "A much longer description that wraps across several lines of text. " * 3

    panel = view.draw(small, "TITLE", model, top=120, description=long_note)

    assert view.description_width <= small.get_width() - 24
    assert panel.width <= small.get_width()
