"""The option picker: one screen, and the behaviour every list shares.

This is the component four settings screens now go through, so the tests here
are about *the picker's* contract rather than about any one setting's values.
What has to hold for every list, because getting it wrong is invisible until a
player hits it:

- every option is reachable by key, by mouse and by gamepad;
- selecting applies and closes, and closing alone applies nothing;
- the list opens with the cursor on the option already in force;
- an entry that cannot be applied is refused *visibly*, not swallowed;
- a list taller than the window scrolls, and the last entry stays reachable.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((1152, 648))

from src.application.scenes.option_screen import Option, OptionScreen  # noqa: E402
from src.core.input.event_router import InputDevice, RoutedInput  # noqa: E402
from src.core.input.input_actions import InputAction  # noqa: E402
from src.core.settings import Input as InputSettings  # noqa: E402
from src.ui.menu_model import MenuItem, MenuModel  # noqa: E402
from src.ui.menu_view import MenuView  # noqa: E402


class FakeGame(SimpleNamespace):
    """A runtime stand-in with a real scene stack, so push and pop are real."""

    def __init__(self) -> None:
        self.pushed: list[object] = []
        self.popped = 0
        self.settings_stub = None
        super().__init__(
            ui_scale=1.0,
            scene_manager=SimpleNamespace(
                push=self.pushed.append,
                pop=self._pop,
            ),
        )

    def _pop(self) -> None:
        self.popped += 1
        if self.pushed:
            self.pushed.pop()


def _screen(game: FakeGame, options, *, selected=None, apply=None, **kwargs) -> OptionScreen:
    return OptionScreen(
        game,
        kwargs.pop("title", "TEST"),
        options,
        apply or (lambda value: None),
        selected=selected,
        **kwargs,
    )


def _drawn(screen: OptionScreen, size=(1152, 648)) -> pygame.Surface:
    surface = pygame.Surface(size)
    screen.draw(surface)
    return surface


def _key(action: InputAction, device=InputDevice.KEYBOARD) -> RoutedInput:
    return RoutedInput(action, device)


def _options(n: int, start: int = 0):
    return tuple(Option(f"Option {i}", start + i) for i in range(n))


# --- the basic contract ----------------------------------------------------


def test_the_list_shows_every_option_and_a_back_row() -> None:
    """Every option is listed, not a window onto the options.

    That is the whole reason this component exists: 28 modes behind 27 keypresses
    is a value that exists and no player will find.
    """
    screen = _screen(FakeGame(), _options(5))

    assert len(screen.model.items) == 6, "five options plus Back"
    assert screen.model.items[-1].action == "back"


def test_the_option_in_force_is_marked() -> None:
    """The check is a leading mark on the label, so the eye lands on it."""
    screen = _screen(FakeGame(), _options(5), selected=3)

    marked = [i.action for i in screen.model.items if i.label.startswith("●")]
    assert marked == ["option:3"]


def test_the_list_opens_with_the_cursor_on_the_current_option() -> None:
    """Opening a list and having to hunt for where you already were is a cost.

    The one fact the list is showing is which one is in force, so the cursor
    starts there rather than at the top.
    """
    screen = _screen(FakeGame(), _options(8), selected=6)

    assert screen.model.current_index == 6


def test_a_value_that_is_not_in_the_list_opens_at_the_top() -> None:
    """A stored value the list no longer offers must not crash the search."""
    screen = _screen(FakeGame(), _options(4), selected="something-else")

    assert screen.model.current_index == 0


def test_selecting_applies_and_closes() -> None:
    game = FakeGame()
    applied: list[object] = []
    screen = _screen(game, _options(5), selected=0, apply=applied.append)
    game.pushed.append(screen)

    for _ in range(2):
        screen.handle_routed(_key(InputAction.UI_DOWN))
    screen.handle_routed(_key(InputAction.UI_CONFIRM))

    assert applied == [2]
    assert game.popped == 1, "picking a value must return to the screen that opened the list"


def test_the_pointer_selects_the_row_it_landed_on() -> None:
    """The mouse path is a real path, and it has to work.

    This bug has been in this menu before: six of nine rows highlighted on click
    and changed nothing, because the click returned an action nobody consumed.
    """
    game = FakeGame()
    applied: list[object] = []
    screen = _screen(game, _options(5), selected=0, apply=applied.append)
    screen.draw(pygame.Surface((1152, 648)))

    rect = screen.view.item_rects[3]
    result = screen.handle_routed(_click_at(rect.center, InputDevice.MOUSE))

    assert result is not None
    assert applied == [3]


def _click_at(position, device):
    return RoutedInput(InputAction.UI_POINTER_DOWN, device, position=position)


def test_closing_applies_nothing() -> None:
    """Esc and Back leave the setting alone.

    The counterpart to apply-on-selection: a list a player backs out of must not
    have changed anything, or the choice is not one they made.
    """
    game = FakeGame()
    applied: list[object] = []
    screen = _screen(game, _options(5), selected=0, apply=applied.append)
    game.pushed.append(screen)
    screen.handle_routed(_key(InputAction.UI_DOWN))

    screen.handle_routed(_key(InputAction.UI_BACK))

    assert applied == []
    assert game.popped == 1


def test_a_lost_controller_does_not_close_the_list() -> None:
    """A device being unplugged is not the player pressing Back.

    Every screen here reads that variant the same way, and the list is where it
    matters most: closing on it would drop a half-made choice with no undo.
    """
    game = FakeGame()
    screen = _screen(game, _options(3))
    game.pushed.append(screen)

    screen.handle_routed(
        RoutedInput(InputAction.UI_BACK, InputDevice.GAMEPAD, variant="device_removed")
    )

    assert game.popped == 0


def test_moving_the_highlight_applies_nothing() -> None:
    """Browsing is not choosing.

    Apply-on-selection is the reason this screen exists in this shape, so it is
    the thing worth holding: a player scrolling a 28-entry list must not end up
    in whatever they scrolled past.
    """
    game = FakeGame()
    applied: list[object] = []
    screen = _screen(game, _options(10), selected=0, apply=applied.append)

    for _ in range(8):
        screen.handle_routed(_key(InputAction.UI_DOWN))

    assert screen.model.current_index == 8
    assert applied == []


# --- entries that cannot be applied -----------------------------------------


def test_a_disabled_entry_cannot_be_selected_by_any_route() -> None:
    """An entry that cannot be applied is refused, by key and by pointer alike.

    Two separate guards, and both are needed. The focus walk skips a disabled row,
    so no sequence of arrow keys can land on it -- and the pointer path checks
    ``enabled`` again, because a click arrives at a row directly by index and
    never goes through the walk at all.

    The pair matters because the symptom of only having the first is a menu that
    appears to skip an entry when the player reaches for it, and the symptom of
    only having the second is a key press that lands on the row below.
    """
    game = FakeGame()
    applied: list[object] = []
    screen = _screen(
        game,
        (
            Option("usable", 1),
            Option("unavailable", 2, enabled=False),
        ),
        selected=0,
        apply=applied.append,
    )
    game.pushed.append(screen)

    # By key: the walk steps over it, so it is never the focused row.
    focused = [screen.model.current_index]
    for _ in range(3):
        screen.handle_routed(_key(InputAction.UI_DOWN))
        focused.append(screen.model.current_index)
    assert 1 not in focused, "the focus landed on a disabled entry"

    # By pointer: aimed straight at its rect, as a click is.
    _drawn(screen)
    rect = screen.view.item_rects[1]
    screen.handle_routed(_click_at(rect.center, InputDevice.MOUSE))

    assert applied == []
    assert game.popped == 0, "a click on a refused entry acted anyway"


def test_a_disabled_entry_is_drawn_as_unusable() -> None:
    screen = _screen(FakeGame(), (Option("nope", 1, enabled=False),))

    assert not screen.model.items[0].enabled


# --- descriptions -----------------------------------------------------------


def test_only_the_focused_entry_explains_itself() -> None:
    """One description, the one the player is looking at.

    A block of prose under every row is a wall, and the entry they are about to
    choose is the only one whose text they need.
    """
    screen = _screen(
        FakeGame(),
        (
            Option("first", 1, "the first one"),
            Option("second", 2, "the second one"),
        ),
        selected=0,
    )

    assert screen._description_for(screen.model.current_item) == "the first one"
    screen.handle_routed(_key(InputAction.UI_DOWN))
    assert screen._description_for(screen.model.current_item) == "the second one"


def test_the_description_is_drawn_and_the_panel_grows_for_it() -> None:
    """Reserved, not painted over whatever happens to be below."""
    surface = pygame.Surface((1152, 648))
    without = MenuView(1.0)
    plain = MenuModel((MenuItem("a", "A"), MenuItem("back", "Back")))
    without.draw(surface, "TITLE", plain, top=180)
    plain_height = without.draw(surface, "TITLE", plain, top=180).height

    with_text = MenuView(1.0)
    screen = _screen(FakeGame(), (Option("first", 1, "an explanation"),), selected=0)
    described = with_text.draw(
        surface, "TITLE", screen.model, top=180, description="an explanation"
    )

    assert described.height > plain_height, "the band is not accounted for"


# --- scrolling --------------------------------------------------------------


@pytest.mark.parametrize("size", [(1152, 648), (800, 600), (640, 480)])
@pytest.mark.parametrize("scale", [0.8, 1.0, 1.2])
def test_a_list_taller_than_the_window_still_fits_and_stays_reachable(
    size: tuple[int, int], scale: float
) -> None:
    """The worst case is 28 modes in a small window, and it has to work.

    A row is never shorter than its text, so a list that does not fit cannot be
    squeezed into place -- it has to scroll. Without this the panel simply ran off
    the bottom and the entries below could never be reached at all.
    """
    game = FakeGame()
    game.ui_scale = scale
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface(size)

    for _ in range(len(screen.model.items) + 2):
        screen.draw(surface)
        if screen.model.current_index == 27:
            break
        screen.handle_routed(_key(InputAction.UI_DOWN))

    assert screen.model.current_index == 27, "the last option was unreachable"
    drawn = [rect for rect in screen.view.item_rects if rect.width > 0]
    assert drawn, "nothing was painted"
    assert screen.view.item_rects[-2].width > 0, "the last option has no rect to click"


def test_a_list_that_fits_is_not_clipped() -> None:
    """Scrolling is opt-in, and a screen that did not ask must not lose rows.

    This is the regression that came out of building the picker: clipping applied
    to every menu, so the video screen's Back row fell past the fold, stopped
    being drawn, and became unclickable with the mouse.
    """
    view = MenuView(1.0)
    model = MenuModel(tuple(MenuItem(f"r{i}", f"Row {i}") for i in range(10)))
    surface = pygame.Surface((640, 480))
    view.set_surface(surface)

    view.draw(surface, "TITLE", model, top=140)

    assert all(rect.width > 0 for rect in view.item_rects), "rows were dropped without asking"


def test_scrolled_out_rows_keep_their_place_in_the_rect_list() -> None:
    """Index alignment is what makes a click land on the row it looks like.

    The rects are indexed the same way as ``model.items``, so a row that is out of
    view holds an empty rect rather than dropping out of the list -- otherwise the
    pointer path would index a shifted list and answer the wrong row.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    assert len(screen.view.item_rects) == len(screen.model.items)
    assert sum(1 for rect in screen.view.item_rects if rect.width > 0) < len(screen.model.items), (
        "the fixture did not overflow"
    )

    # Scrolled to the middle, the rows above it are gone from the screen but are
    # still *present* in the rect list, at their own index.
    for _ in range(10):
        screen.handle_routed(_key(InputAction.UI_DOWN))
    screen.draw(surface)
    assert screen.view.item_rects[0].width == 0, "row 0 is above the fold"
    assert screen.view.item_rects[10].width > 0, "row 10 is the cursor"
    assert screen.view.item_rects[27].width == 0, "row 27 is below the fold"


# --- the value comparison ---------------------------------------------------


def test_the_mark_matches_a_tuple_and_an_enum() -> None:
    """Compared by equality, so a rebuilt list does not move the mark."""
    assert Option("a", (1920, 1080)).matches((1920, 1080))
    assert not Option("a", (1920, 1080)).matches((1920, 1200))
    assert Option("a", None).matches(None)


def test_a_value_whose_comparison_raises_is_not_a_crash() -> None:
    """An odd ``__eq__`` is a nuisance, not a reason to fail the launch."""

    class Awkward:
        def __eq__(self, other: object) -> bool:
            raise RuntimeError("no")

    screen = _screen(FakeGame(), (Option("a", Awkward()),), selected="other")

    assert screen.model.current_index == 0


# --- the pointer and the wheel --------------------------------------------


def test_a_stationary_pointer_lands_on_the_same_row() -> None:
    """One mouse position selected four different rows, and the cause is
    worth writing down.

    The scroll used to follow the keyboard cursor with a margin above
    it, so when the pointer hovered the last drawn row the list jumped
    down, which changed the row under the pointer, which jumped the
    list again. A hand moving steadily down selected rows 7, 13, 19, 25
    in turn without the cursor moving at all -- the pointer was moving
    the list and the list was moving the pointer, each one amplifying
    the other.

    The rule now: the list scrolls only to keep the pointed-at row on
    screen, so a still pointer is a still list.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    rows = [rect for rect in screen.view.item_rects if rect.width > 0]
    assert len(rows) < len(screen.model.items), "the fixture did not overflow"
    # Park on the last drawn row, the row that used to run away.
    parked_y = rows[-1].centery

    seen: set[int] = set()
    for _ in range(8):
        screen.handle_routed(
            RoutedInput(
                InputAction.UI_POINTER_MOVE,
                InputDevice.MOUSE,
                position=(320, parked_y),
            )
        )
        screen.draw(surface)
        under = screen._row_at(parked_y)
        assert under is not None, "the pointer left the rows without moving"
        seen.add(under)

    assert len(seen) == 1, f"a stationary pointer selected {sorted(seen)}: the list moved under it"


def test_the_wheel_moves_the_cursor_one_row_per_notch() -> None:
    """The wheel navigates; it does not select.

    Routing it as a selection would change a setting per notch, and a
    trackpad's fractional ``y`` would apply half a value.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    assert screen.model.current_index == 0
    for _ in range(3):
        screen.handle_routed(RoutedInput(InputAction.UI_SCROLL, InputDevice.MOUSE, value=1.0))
    assert screen.model.current_index == 3

    # A wide notch steps by more than one row, and is still navigation.
    screen.handle_routed(RoutedInput(InputAction.UI_SCROLL, InputDevice.MOUSE, value=4.0))
    assert screen.model.current_index == 7

    for _ in range(3):
        screen.handle_routed(RoutedInput(InputAction.UI_SCROLL_UP, InputDevice.MOUSE, value=1.0))
    assert screen.model.current_index == 4


def test_a_key_takes_the_list_back_from_the_pointer() -> None:
    """The remembered pointer y must not outvote the row just walked to.

    Left in place, a press of the arrow key would scroll the list to
    the cursor and then straight back to where the mouse last was --
    the cursor moving up one line while the list slides down.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=20)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    # The pointer is parked near the top of the list.
    rows = [rect for rect in screen.view.item_rects if rect.width > 0]
    screen.handle_routed(
        RoutedInput(
            InputAction.UI_POINTER_MOVE,
            InputDevice.MOUSE,
            position=(320, rows[0].centery),
        )
    )
    screen.draw(surface)
    assert screen._pointer_y is not None

    # A key press takes over, and the scroll follows the cursor.
    screen.handle_routed(_key(InputAction.UI_UP))
    screen.draw(surface)
    assert screen._pointer_y is None, "a key press left the pointer in charge"
    assert screen._scroll == max(0, screen.model.current_index - 1)


def test_the_list_keys_move_a_long_list() -> None:
    """A 28-entry list is 27 arrow keys without the list keys.

    Page down moves by what the window shows, end jumps to the
    last row, and home comes back -- the difference between
    reading a long list and walking it.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    visible = sum(1 for rect in screen.view.item_rects if rect.width > 0)
    assert visible < len(screen.model.items), "the fixture did not overflow"

    screen.handle_routed(_key(InputAction.UI_PAGE_DOWN))
    assert screen.model.current_index == visible

    screen.handle_routed(_key(InputAction.UI_END))
    assert screen.model.current_index == len(screen.model.items) - 1

    screen.handle_routed(_key(InputAction.UI_HOME))
    assert screen.model.current_index == 0


def test_a_held_page_down_key_repeats() -> None:
    """The key is meant to be held, so the repeat the router
    arms for it has to reach the list.
    """
    from src.core.input.event_router import EventRouter

    now = [100.0]
    router = EventRouter(clock=lambda: now[0])
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    screen.handle_routed(router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN)))
    first = screen.model.current_index

    # Past the repeat delay, the held key reports itself again.
    now[0] += InputSettings.UI_REPEAT_INITIAL_DELAY + 0.01
    repeated = router.poll_repeats()
    assert repeated, "a held page-down key armed no repeat"
    for routed in repeated:
        screen.handle_routed(routed)
    assert screen.model.current_index > first, "the repeat did not move the list"


# --- the rail answers a click ---------------------------------------------


def _press(screen: OptionScreen, target: tuple[int, int]) -> str | None:
    return screen.handle_routed(
        RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=target)
    )


def test_a_press_in_the_rail_strip_pages() -> None:
    """The strip beside the rows was dead space.

    No row is clickable there, so a press in it did nothing at all
    -- and it is where a scrollbar has lived in every interface
    anyone has used, so a player who has clicked one will click
    this one. Below the thumb pages forward, above pages back.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    rail = screen.view.scroll_rail
    assert rail is not None, "the fixture did not overflow"
    below = (rail.centerx, rail.bottom - 2)

    _press(screen, below)
    first = screen.model.current_index
    assert first > 0, "a press below the thumb did not page"

    redraw = surface
    screen.draw(redraw)
    rail = screen.view.scroll_rail
    above = (rail.centerx, rail.top + 2)
    _press(screen, above)
    assert screen.model.current_index < first, "a press above the thumb did not page back"


def test_a_press_on_the_thumb_itself_does_nothing() -> None:
    """Dragging the thumb is a separate interaction, not this one.

    A press that both grabbed and paged would jump the list the
    moment it was caught, which is the opposite of what the
    player asked for.
    """
    game = FakeGame()
    screen = _screen(game, _options(28), selected=0)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    screen.handle_routed(RoutedInput(InputAction.UI_PAGE_DOWN, InputDevice.KEYBOARD))
    screen.draw(surface)
    rail = screen.view.scroll_rail
    thumb = screen.view.scroll_thumb
    assert rail is not None and thumb is not None

    before = screen.model.current_index
    _press(screen, (rail.centerx, thumb.centery))

    assert screen.model.current_index == before, "a press on the thumb moved the list"


def test_a_press_on_a_row_still_selects_it() -> None:
    """The strip must not swallow a press that lands on a row.

    It runs from the rail's left edge rightward, and the rows end
    to the left of that -- so a row's own click is untouched.
    """
    applied: list[object] = []
    game = FakeGame()
    screen = _screen(game, _options(28), selected=10, apply=applied.append)
    surface = pygame.Surface((640, 480))
    screen.draw(surface)

    rows = [rect for rect in screen.view.item_rects if rect.width > 0]
    _press(screen, (rows[0].centerx, rows[0].centery))

    assert screen.model.current_index == 0, "the row under the press was not selected"
    assert applied == [0], "the press on the row did not apply that option"
    assert game.popped == 1, "the screen did not close as it would on a row press"


def test_a_press_in_the_strip_of_a_list_that_fits_does_nothing() -> None:
    """No rail, no strip: a list that fits has nothing to page."""
    game = FakeGame()
    screen = _screen(game, _options(4), selected=0)
    surface = pygame.Surface((1152, 648))
    screen.draw(surface)

    assert screen.view.scroll_rail is None
    assert screen._page_from_rail((600, 300)) is None
