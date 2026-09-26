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
def test_every_offered_size_fits_on_the_desktop_that_offers_it(desktop) -> None:
    """The bug this replaces: 2560x1440 was offered to a 1366x768 laptop."""
    choices = detection.window_size_choices(desktop)
    assert choices, f"a {desktop[0]}x{desktop[1]} desktop must offer at least one size"
    for size in choices:
        assert detection.fits_on_desktop(size, desktop), f"{size} does not fit {desktop}"


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_choices_are_ordered_and_unique(desktop) -> None:
    choices = detection.window_size_choices(desktop)
    assert list(choices) == sorted(choices)
    assert len(choices) == len(set(choices))


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_biggest_choice_stays_under_the_desktop(desktop) -> None:
    biggest = detection.largest_window_size(desktop)
    assert biggest[0] <= desktop[0] and biggest[1] <= desktop[1]


def test_a_desktop_too_small_for_any_fraction_still_yields_a_size() -> None:
    """Refusing to open a window is not a recovery."""
    tiny = (100, 80)
    assert detection.window_size_choices(tiny) == ()
    size = detection.largest_window_size(tiny)
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


def test_a_borderless_window_is_the_desktop_own_size() -> None:
    """Borderless means the desktop's size, whatever the settings say."""
    from src.core.display.stage import Stage, WindowSpec

    stage = Stage.__new__(Stage)
    assert Stage._window_size(
        WindowSpec(width=800, height=600, mode=DisplayMode.BORDERLESS), (1920, 1080)
    ) == (1920, 1080)
    assert Stage._window_size(
        WindowSpec(width=800, height=600, mode=DisplayMode.WINDOW), (1920, 1080)
    ) == (800, 600)
    assert stage is not None


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
