"""The window-size list: what it offers, and what it must never offer.

The sizes are derived from the panel rather than written down, which is what
keeps the row from being the resolution catalogue this project deleted -- but it
also means the arithmetic is ours, and every step of it can be wrong in a way
that only shows on somebody else's screen.

The properties pinned here, over four panel shapes:

- every offered size fits the panel's *usable* area, and is above the floor the
  interface needs;
- the ladder descends, because ``opening_size`` is already the largest the frame
  allows and a rung above it would be filtered out rather than shown;
- a remembered size this panel cannot take is listed and disabled, never dropped
  and never silently applied;
- no size is offered that the window manager would immediately correct.
"""

from __future__ import annotations

import pytest

from src.application.scenes.video_options import _largest_fitting, window_size_options
from src.core.display.monitors import MIN_WINDOW, Monitor, opening_size

#: The panels worth checking, as ``(size, usable rect)``: the development
#: machine's 1080p with a panel at the top, a laptop with nothing to dodge, a 4K
#: desk, and something too small for the interface's floor.
PANELS = [
    ((1920, 1080), (0, 32, 1920, 1048)),
    ((1366, 768), (0, 0, 1366, 768)),
    ((3840, 2160), (0, 40, 3840, 2080)),
    ((1024, 600), (0, 0, 1024, 600)),
    # A panel below the interface floor: the ladder's first rung already sits
    # under the readable minimum, so the honest list has nothing derived in it.
    ((640, 400), (0, 0, 640, 400)),
    # An ultra-wide panel, where a fraction of the width is miles of pixels and
    # the same fraction of the height is already floored.
    ((3440, 1440), (0, 0, 3440, 1440)),
]


def _ladder(entry, current=None):
    """The options for one PANELS entry, and the monitor they came from.

    PANELS rows are ``(size, usable)`` and both are needed: the size is the panel
    and the usable rect is what the window has to fit inside. Passing the whole
    row where a size pair is expected is an easy mistake, so the helper takes the
    row and unpacks it here, once.
    """
    size, usable = entry
    monitor = Monitor(
        index=0,
        name="DP-1",
        bounds=(0, 0, size[0], size[1]),
        usable=usable,
    )
    return monitor, window_size_options(monitor, current, opening_size(monitor))


@pytest.mark.parametrize("panel", PANELS, ids=lambda p: f"{p[0]}x{p[1]}")
def test_every_offered_size_fits_the_panel_and_can_be_read(
    panel: tuple[tuple[int, int], tuple[int, int, int, int]],
) -> None:
    """A window bigger than the screen cannot be moved, and a tiny one cannot be read.

    Both bounds are the ones the rest of the display system uses -- the usable
    area rather than the panel, because a window that covers a taskbar is not
    usable either -- so a size that fails here is one the stage would clamp and
    the menu would still be showing.
    """
    usable = panel[1]
    _, options = _ladder(panel)

    for option in options:
        if option.value is None:
            continue
        width, height = option.value
        assert width <= usable[2], f"{option.label} is wider than the usable area"
        assert height <= usable[3], f"{option.label} is taller than the usable area"
        assert width >= MIN_WINDOW[0], f"{option.label} is too narrow to read"
        assert height >= MIN_WINDOW[1], f"{option.label} is too short to read"


@pytest.mark.parametrize("panel", PANELS, ids=lambda p: f"{p[0]}x{p[1]}")
def test_the_ladder_descends(panel: tuple[tuple[int, int], tuple[int, int, int, int]]) -> None:
    """Largest first, so the list reads as a scale.

    Not a style preference: ``opening_size`` is already the largest the frame
    allows, so a "three quarters" rung computed from it would land *above* it and
    be filtered out as too big -- which is exactly what happened while writing
    this, and it showed as a missing rung rather than as an error.
    """
    _, options = _ladder(panel)

    sizes = [option.value for option in options if option.value is not None]
    areas = [width * height for width, height in sizes]
    assert areas == sorted(areas, reverse=True), f"the ladder does not descend: {sizes}"


@pytest.mark.parametrize("panel", PANELS, ids=lambda p: f"{p[0]}x{p[1]}")
def test_the_list_is_short_enough_to_read(
    panel: tuple[tuple[int, int], tuple[int, int, int, int]],
) -> None:
    """A list is only usable if it fits.

    The first version offered the driver's whole mode list, which on this machine
    is 26 entries -- down to 320x240. That is not a set of choices, it is
    something to scroll through, and it hands a 1366x768 laptop a 320x240 window
    as though it were a reasonable thing to want.
    """
    _, options = _ladder(panel)

    assert len(options) <= 6, f"{len(options)} entries is a list to scroll, not to choose from"
    assert all(option.value is None or option.value[0] >= MIN_WINDOW[0] for option in options), (
        "a size below the readable floor was offered"
    )


@pytest.mark.parametrize("panel", PANELS, ids=lambda p: f"{p[0]}x{p[1]}")
def test_the_largest_entry_is_what_the_game_opens_at(
    panel: tuple[tuple[int, int], tuple[int, int, int, int]],
) -> None:
    """The top rung and the opening size are the same number, by construction.

    They have to be: the game opens at :func:`opening_size` and this list's
    largest entry is what the player gets back by choosing the head of the
    ladder. Two different numbers would make the menu unable to return the game
    to the state it starts in. On the panel below the interface floor the claim
    reverses on purpose: :func:`opening_size` derives its fallback there -- a
    size bigger than the panel -- and the list's per-axis clamp is what keeps
    the head of the ladder a size the panel can hold, so the assertions say
    which of the two numbers a panel like this is using.
    """
    monitor, options = _ladder(panel)
    sizes = [option.value for option in options if option.value is not None]

    if not sizes:
        assert panel[0][0] < MIN_WINDOW[0] or panel[0][1] < MIN_WINDOW[1], (
            "a derived ladder went empty on a panel the floor cannot explain"
        )
        return

    assert _largest_fitting(monitor) in sizes


@pytest.mark.parametrize("panel", PANELS, ids=lambda p: f"{p[0]}x{p[1]}")
def test_a_size_this_panel_cannot_take_is_listed_and_disabled(
    panel: tuple[tuple[int, int], tuple[int, int, int, int]],
) -> None:
    """A 4K window arriving at a laptop is visible, refused, and explained.

    Dropping it silently would leave the player unable to see that something they
    chose is not available here -- the stored preference is still honoured at
    launch, clamped, so the row and the window would disagree without saying so.
    """
    _, options = _ladder(panel, current=(3840, 2160))

    offered = [option for option in options if option.value == (3840, 2160)]
    assert offered, "the remembered size vanished"
    assert not offered[0].enabled, "an unshowable size was offered as choosable"
    assert offered[0].detail, "the refusal says nothing about why"


def test_the_current_size_is_marked_where_it_is_offered() -> None:
    """A list that shows six sizes and does not say which is in force is a guess."""
    monitor, options = _ladder(((1920, 1080), (0, 32, 1920, 1048)))
    granted = opening_size(monitor)

    marked = [option for option in options if "current" in option.detail]
    assert len(marked) == 1, f"{len(marked)} entries claim to be the current size"
    assert marked[0].value == granted


def test_a_floored_rung_says_so() -> None:
    """A rung the readable minimum changed is described as the size it is.

    On a usable area of 2480x1344, "a third of the largest" is a rung 448 tall
    -- below the 480 the interface needs -- so the code raises it and the note
    has to follow, or the list once again describes a size the window is not
    going to have. The head of the ladder is exempt: it sits above the floor by
    construction, so no note on it, and the "half" rung here clears the floor
    without help on both axes -- which is why they are asserted side by side.
    """
    _, options = _ladder(((2560, 1440), (0, 0, 2560, 1440)))

    thirds = [option for option in options if option.value == (826, 480)]
    halves = [option for option in options if option.value == (1240, 672)]

    assert halves and "floored" not in halves[0].detail, "the half rung was never floored"
    assert thirds and "floored at the readable minimum" in thirds[0].detail


def test_choosing_to_follow_the_drag_clears_the_preference() -> None:
    """The first entry is ``None``, and ``None`` means "no remembered size".

    Which is the honest answer for a setting whose whole point is that the window
    manager owns the window: a player who resizes by dragging should get the same
    window next launch, and that works by having nothing to restore.
    """
    _, options = _ladder(((1920, 1080), (0, 32, 1920, 1048)))

    first = options[0]
    assert first.value is None
    assert first.detail, "the entry that clears the preference does not say so"


def test_a_size_the_window_manager_would_correct_is_not_offered() -> None:
    """Requesting the usable area exactly comes back short.

    Measured on the development machine: a request of 1920x1048 -- the panel's
    usable area -- is granted as 1920x1011, because the frame is subtracted. Any
    rung at the usable area would therefore be a number the window will not have,
    and the row would be reporting a size the player cannot see.
    """
    usable = (0, 32, 1920, 1048)
    _, options = _ladder(((1920, 1080), usable))

    exact = [option for option in options if option.value == (usable[2], usable[3])]
    assert not exact, (
        f"the usable area {usable[2]}x{usable[3]} is offered, and the window "
        "manager will not grant it"
    )
