"""Setup detection: the decisions that used to be made against a fixed list.

Every function here that takes a ``desktop`` is a pure function of it, so all of
it is exercised without a screen. That is the point of the split: the desktop
*queries* need a display, but the *policy* built on them is where the bugs
were, and a policy that can only be tested on a real screen is a policy that
does not get tested.
"""

import os

import pygame
import pytest

#: The desktop queries below need a video system. Initialising it here rather
#: than relying on another test module having done it first is the point: an
#: assertion that passes only because of the order pytest happened to collect
#: in is a test that will stop passing for no reason.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))

from src.core.display import detection  # noqa: E402
from src.core.display.framing import DEFAULT_FRAMING  # noqa: E402
from src.core.display.mode import DisplayMode  # noqa: E402

#: Desktops worth caring about: 16:9, 16:10, 21:9, 32:9, a laptop, a netbook.
DESKTOPS = [
    (1920, 1080),
    (1600, 900),
    (1440, 900),
    (1366, 768),
    (3440, 1440),
    (5120, 1440),
    (1024, 600),
]


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_opening_window_fits_and_leaves_room_when_it_can(desktop) -> None:
    """The bug this replaces: 2560x1440 was offered to a 1366x768 laptop.

    There is no longer a list of sizes to check -- the catalogue was seven claims
    about the player's monitor, and the game could check none of them. What is
    left is one starting size, derived from the desktop, and per axis it has to
    fit the screen and leave the title bar's room whenever there is room to
    leave it.
    """
    size = detection.initial_window_size(desktop)

    for axis in (0, 1):
        span = desktop[axis]
        margin = detection.DESKTOP_MARGIN[axis]
        default = detection.FALLBACK_WINDOW[axis]
        assert 1 <= size[axis] <= span, f"axis {axis} does not fit the desktop"
        if span - margin >= default:
            assert size[axis] == span - margin, f"axis {axis} ignored the margin"
        else:
            # Too tight for both: the window takes the whole span, because a
            # window that does not fit is worse than one with no title bar.
            assert size[axis] == span


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_a_bigger_desktop_opens_a_bigger_window(desktop) -> None:
    size = detection.initial_window_size(desktop)
    for wider, taller in ((desktop[0] + 320, desktop[1]), (desktop[0], desktop[1] + 200)):
        grown = detection.initial_window_size((wider, taller))
        assert grown[0] >= size[0] and grown[1] >= size[1]


def test_an_unknown_desktop_opens_the_documented_default() -> None:
    """Headless runs, and drivers that cannot answer, still get a window."""
    assert detection.initial_window_size((0, 0)) == detection.FALLBACK_WINDOW


def test_a_desktop_too_small_for_the_default_still_yields_a_size() -> None:
    """Refusing to open a window is not a recovery.

    The size has to stay inside the screen even then, or the player gets a
    window they cannot move, which is the outcome the margin exists to prevent.
    """
    tiny = (100, 80)
    size = detection.initial_window_size(tiny)
    assert size[0] > 0 and size[1] > 0
    assert size[0] <= tiny[0] and size[1] <= tiny[1]


def test_a_matching_desktop_gets_borderless_and_a_mismatched_one_a_window() -> None:
    """Borderless fills the screen only when the screen already has the shape."""
    assert detection.auto_display_mode(DEFAULT_FRAMING, (1920, 1080)) is DisplayMode.BORDERLESS
    assert detection.auto_display_mode(DEFAULT_FRAMING, (1440, 900)) is DisplayMode.WINDOW


def test_a_dead_desktop_does_not_ask_for_a_zero_sized_borderless_window() -> None:
    assert detection.auto_display_mode(DEFAULT_FRAMING, (0, 0)) is DisplayMode.WINDOW


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_automatic_display_mode_is_always_concrete(desktop) -> None:
    """AUTO defers to the machine; the result must not defer to anything."""
    assert detection.auto_display_mode(DEFAULT_FRAMING, desktop).is_concrete


@pytest.mark.parametrize("mode", list(DisplayMode))
def test_no_mode_asks_for_a_size_the_game_invented(mode: DisplayMode) -> None:
    """Each mode asks the platform for a size; none of them names one.

    The window used to be built from a size in the settings file, and in
    borderless it was built from the desktop while the file kept saying
    something else -- so the menu displayed a number the game was not using.
    There is no size left anywhere in the request, which is the only way to be
    sure no two components can disagree about one.
    """
    from src.core.display.stage import Stage, WindowSpec

    requested = Stage._window_size(WindowSpec(mode=mode), (1920, 1080))
    assert requested in {(0, 0), (1920, 1080), detection.initial_window_size((1920, 1080))}
    assert all(value >= 0 for value in requested)


def test_the_module_no_longer_offers_resolutions() -> None:
    """A regression guard on the deletion itself.

    ``window_size_choices`` was a catalogue of resolutions for a screen the game
    cannot measure, and it is what the resolution picker was built on. A caller
    reaching for it again would be reintroducing the claim.
    """
    assert not hasattr(detection, "window_size_choices")
    assert not hasattr(detection, "largest_window_size")
    assert not hasattr(detection, "fits_on_desktop")
    assert not hasattr(detection, "WINDOW_SIZE_FRACTIONS")


def test_the_module_does_not_pretend_to_place_a_window() -> None:
    """It used to, and the arithmetic was wrong on a real machine.

    Centring needed the primary display's *origin*, and pygame does not expose
    display bounds. The assumption that the primary sits at the origin of the
    virtual desktop is the Windows and macOS convention; on a Linux desktop whose
    primary is not the leftmost monitor it is false, and measured on such a
    machine the computed x put the window on the other screen. SDL resolves
    ``WINDOWPOS_CENTERED`` per display and knows where they are, so the guess is
    gone rather than corrected.
    """
    assert not hasattr(detection, "centered_on_primary")


def test_the_queries_answer_under_a_headless_driver() -> None:
    """They have to, or none of the policy above is testable in CI."""
    sizes = detection.desktop_sizes()
    assert sizes and all(len(size) == 2 for size in sizes)
    # An index from a three-monitor settings file must not crash the launch.
    assert detection.desktop_size(0) == sizes[0]
    assert detection.desktop_size(7) == sizes[0]
    assert detection.desktop_size(-1) == sizes[0]
    assert all(rate > 0 for rate in detection.desktop_refresh_rates())
