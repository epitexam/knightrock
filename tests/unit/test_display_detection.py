"""Setup detection: the decisions that used to be made against a fixed list.

Every function here that takes a ``desktop`` is a pure function of it, so all of
it is exercised without a screen. That is the point of the split: the desktop
*queries* need a display, but the *policy* built on them is where the bugs
were, and a policy that can only be tested on a real screen is a policy that
does not get tested.
"""

import pytest

from src.core.display import detection
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.mode import DisplayMode

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
def test_auto_settings_are_complete_and_consistent(desktop) -> None:
    """One function owns the defaults, so the two call sites cannot disagree."""
    settings = detection.auto_settings(DEFAULT_FRAMING, desktop)
    assert set(settings) == {
        "display",
        "width",
        "height",
        "size_mode",
        "framing",
        "render_scale",
        "smoothing",
        "vsync",
        "frame_limit",
    }
    assert settings["size_mode"] == "auto"
    assert settings["framing"] == "keep"
    assert settings["display"] in {mode.value for mode in DisplayMode}
    if settings["display"] == DisplayMode.BORDERLESS.value:
        assert (settings["width"], settings["height"]) == desktop
    else:
        assert detection.fits_on_desktop((settings["width"], settings["height"]), desktop)  # type: ignore[arg-type]


def test_centring_on_the_primary_screen() -> None:
    assert detection.centered_on_primary((800, 600), (1024, 768)) == (112, 84)
    assert detection.centered_on_primary((300, 200), (1920, 1080)) == (810, 440)


def test_centring_a_window_bigger_than_the_screen_is_bounded_at_zero() -> None:
    """Unbounded, this opens a window whose title bar is under the taskbar."""
    assert detection.centered_on_primary((1728, 972), (1024, 768)) == (0, 0)
    assert detection.centered_on_primary((4000, 3000), (1920, 1080)) == (0, 0)


def test_the_queries_answer_under_a_headless_driver() -> None:
    """They have to, or none of the policy above is testable in CI."""
    sizes = detection.desktop_sizes()
    assert sizes and all(len(size) == 2 for size in sizes)
    # An index from a three-monitor settings file must not crash the launch.
    assert detection.desktop_size(0) == sizes[0]
    assert detection.desktop_size(7) == sizes[0]
    assert detection.desktop_size(-1) == sizes[0]
    assert all(rate > 0 for rate in detection.desktop_refresh_rates())
