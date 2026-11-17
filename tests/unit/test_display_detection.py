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

from src.core.display import detection, monitors  # noqa: E402

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


def _monitor(desktop: tuple[int, int]) -> monitors.Monitor:
    """A monitor whose usable area is the whole desktop, for size policy tests."""
    return monitors.Monitor(index=0, name="", bounds=(0, 0, *desktop), usable=(0, 0, *desktop))


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_opening_window_fits_and_leaves_room_when_it_can(desktop) -> None:
    """The bug this replaces: 2560x1440 was offered to a 1366x768 laptop.

    There is no longer a list of sizes to check -- the catalogue was seven claims
    about the player's monitor, and the game could check none of them. What is
    left is one starting size, derived from the panel, and per axis it has to
    fit and leave the title bar's room whenever there is room to leave it.
    """
    size = monitors.opening_size(_monitor(desktop))

    for axis in (0, 1):
        span = desktop[axis]
        margin = monitors.WINDOW_MARGIN[axis]
        floor = monitors.MIN_WINDOW[axis]
        assert 1 <= size[axis] <= span, f"axis {axis} does not fit the panel"
        if span - margin >= floor:
            assert size[axis] == span - margin, f"axis {axis} ignored the margin"
        else:
            # Too tight for both: the window takes the whole span, because a
            # window that does not fit is worse than one with no title bar.
            assert size[axis] == span


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_a_bigger_desktop_opens_a_bigger_window(desktop) -> None:
    size = monitors.opening_size(_monitor(desktop))
    for wider, taller in ((desktop[0] + 320, desktop[1]), (desktop[0], desktop[1] + 200)):
        grown = monitors.opening_size(_monitor((wider, taller)))
        assert grown[0] >= size[0] and grown[1] >= size[1]


def test_a_desktop_too_small_for_the_floor_still_yields_a_size() -> None:
    """Refusing to open a window is not a recovery.

    The size has to stay inside the panel even then, or the player gets a
    window they cannot move, which is the outcome the margin exists to prevent.
    """
    tiny = (100, 80)
    size = monitors.opening_size(_monitor(tiny))
    assert size[0] > 0 and size[1] > 0
    assert size[0] <= tiny[0] and size[1] <= tiny[1]


def test_an_unknown_desktop_opens_a_usable_window() -> None:
    """Headless runs, and drivers that cannot answer, still get a window.

    The fallback is a real size rather than a zero, and not a 1x1 either: run
    through the margin arithmetic a 0x0 monitor produces a window smaller than
    any menu, which is a worse answer than having no monitor at all.
    """
    unknown = monitors.Monitor(index=0, name="", bounds=(0, 0, 0, 0), usable=(0, 0, 0, 0))
    size = monitors.opening_size(unknown)
    assert size == monitors.FALLBACK_WINDOW
    assert size[0] >= monitors.MIN_WINDOW[0] and size[1] >= monitors.MIN_WINDOW[1]


def test_the_opening_size_leaves_a_taskbar_alone() -> None:
    """The size is taken from the *usable* area, so a bar is not covered.

    Measured on the development machine: the panel reports 1920x1080 and the
    usable area 1920x1048, a 32px panel at the top. Sizing the window from the
    panel would put the game's own title bar under whatever the desktop put
    there.
    """
    panel = _monitor((1920, 1080))
    with_bar = monitors.Monitor(
        index=0, name="", bounds=(0, 0, 1920, 1080), usable=(0, 32, 1920, 1048)
    )
    assert monitors.opening_size(with_bar)[1] < monitors.opening_size(panel)[1]


def test_the_topology_answers_even_with_no_displays_to_describe() -> None:
    """A topology with nothing in it is still a topology.

    ``Topology.primary`` fabricates a panel rather than returning ``None``, so
    every caller that wants a size has one to read and none of them has to test
    for the degenerate case first. It is 1x1 on purpose: the smallest rectangle
    that is still a rectangle.
    """
    empty = monitors.Topology()
    assert empty.primary.size == (1, 1)
    assert empty.containing((0, 0)) is None
    assert empty.nearest((99, 99)).size == (1, 1)


def test_the_topology_the_game_reads_agrees_with_pygame() -> None:
    """Whatever the probe says, display 0's size is the one pygame reports.

    This is the seam between the two grades of query. If they ever disagree, the
    probe is answering about a video subsystem that is not the one running the
    game -- and the game would then place its window using a machine that does
    not exist.
    """
    topology = detection.topology()
    assert topology.primary.size == detection.desktop_size(0)
    assert topology.indices == tuple(range(len(topology.monitors)))


@pytest.mark.parametrize("desktop", DESKTOPS)
def test_the_window_size_never_names_a_resolution_the_game_invented(desktop) -> None:
    """The window asks the platform for a size; it does not name one.

    The window used to be built from a size in the settings file, and in
    borderless it was built from the desktop while the file kept saying
    something else -- so the menu displayed a number the game was not using.
    With no size in the request the game can do that to itself no longer: either
    the player chose a size, and it is honoured, or there is none and the panel
    decides.
    """
    from src.core.display.stage import Stage, WindowSpec

    monitor = _monitor(desktop)
    assert Stage._window_size(WindowSpec(size=None), monitor) == monitors.opening_size(monitor)

    chosen = (1600, 900)
    asked = Stage._window_size(WindowSpec(size=chosen), monitor)
    assert 0 < asked[0] <= desktop[0] and 0 < asked[1] <= desktop[1]
    assert asked[0] <= desktop[0] and asked[1] <= desktop[1]


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


def test_the_module_has_no_display_mode_to_resolve() -> None:
    """A regression guard on the deletion itself.

    ``auto_display_mode`` resolved ``AUTO`` into one of four ways to occupy the
    screen, and it resolved to the one that asked the driver for a mode change
    on every 16:9 desktop. The game is a window now and there is nothing to
    resolve.
    """
    assert not hasattr(detection, "auto_display_mode")


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


# -- without the SDL probe -----------------------------------------------------
#
# The probe reaches into libSDL2 through ctypes. A pygame built on another SDL,
# or a libSDL2 that cannot be found, leaves pygame's own answers: sizes and
# refresh rates, no origins, no names.


def test_a_desk_known_by_size_alone_keeps_its_refresh_rates() -> None:
    desk = monitors.degraded(((2560, 1440), (1920, 1080)), (180, 144))

    assert [monitor.refresh_rate for monitor in desk.monitors] == [180, 144]
    assert not desk.named


def test_a_missing_rate_reads_as_unknown() -> None:
    desk = monitors.degraded(((2560, 1440), (1920, 1080)), (180,))

    assert [monitor.refresh_rate for monitor in desk.monitors] == [180, 0]


def test_two_screens_known_by_size_alone_cannot_place_a_point() -> None:
    """Both claim the origin, so a lookup by position would always name the first.

    ``monitor_at`` then answers ``None`` and the caller falls back to the
    primary, instead of reporting the first screen's rate for a window sitting
    on the second.
    """
    from src.core.display.window_watch import monitor_at

    desk = monitors.degraded(((2560, 1440), (1920, 1080)))

    assert not desk.has_geometry
    assert monitor_at(desk, (3000, 200), (640, 360)) is None


def test_one_screen_known_by_size_alone_is_still_the_screen() -> None:
    from src.core.display.window_watch import monitor_at

    desk = monitors.degraded(((1920, 1080),))

    assert desk.has_geometry
    assert monitor_at(desk, (100, 100), (640, 360)) == desk.primary


def test_the_probe_refuses_a_pygame_built_on_another_sdl(monkeypatch, caplog) -> None:
    """SDL 3 renamed the display calls: the SDL 2 bindings must not be tried on it."""
    import logging

    from src.core.display import sdl_probe

    monkeypatch.setattr(sdl_probe, "_bindings_searched", False)
    monkeypatch.setattr(sdl_probe, "_bindings_cache", None)
    monkeypatch.setattr(pygame, "get_sdl_version", lambda: (3, 2, 0))
    searched: list[object] = []
    monkeypatch.setattr(sdl_probe, "_libraries", lambda: searched.append(1) or iter(()))

    with caplog.at_level(logging.INFO, logger=sdl_probe.__name__):
        assert sdl_probe.probe() == ()

    assert searched == [], "no library may be opened for an SDL the bindings do not speak"
    assert "SDL 3" in caplog.text


def test_the_topology_falls_back_to_pygame_when_the_probe_is_silent(monkeypatch) -> None:
    from src.core.display import sdl_probe

    monkeypatch.setattr(sdl_probe, "probe", lambda: ())
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(2560, 1440), (1920, 1080)])
    monkeypatch.setattr(pygame.display, "get_desktop_refresh_rates", lambda: [180, 144])

    desk = detection.topology()

    assert [monitor.size for monitor in desk.monitors] == [(2560, 1440), (1920, 1080)]
    assert [monitor.refresh_rate for monitor in desk.monitors] == [180, 144]
    assert not desk.named


def test_a_monitor_carries_no_scale() -> None:
    """It used to, read from the panel's physical DPI and used by nothing.

    That number is not the desktop's scale setting -- measured 1.135 on a 27"
    1440p panel and 0.975 on a 24" 1080p one, both at 100% -- so the first
    reader to trust it would have resized the interface on machines that need
    no resizing. A scale comes back when something reads the real one.
    """
    import dataclasses

    names = {field.name for field in dataclasses.fields(monitors.Monitor)}

    assert "scale" not in names


def test_a_display_mode_sdl_refuses_reports_no_refresh_rate() -> None:
    """``SDL_GetDesktopDisplayMode`` answers an int: 0 for success, negative otherwise.

    It was declared as returning a pointer, so its answer could not be read and
    a refused call was judged by whatever the structure happened to hold.
    """
    import ctypes

    from src.core.display import sdl_probe

    class _Lib:
        def __init__(self, status: int) -> None:
            self.status = status

        def SDL_GetDisplayBounds(self, index, rect):  # noqa: N802 - SDL's name
            rect._obj.w, rect._obj.h = 1920, 1080
            return 0

        def SDL_GetDisplayUsableBounds(self, index, rect):  # noqa: N802
            return 0

        def SDL_GetDisplayName(self, index):  # noqa: N802
            return b"panel"

        def SDL_GetDesktopDisplayMode(self, index, mode):  # noqa: N802
            mode._obj.width, mode._obj.height, mode._obj.refresh_rate = 1920, 1080, 144
            return self.status

    def geometry(status: int):
        bindings = sdl_probe._Bindings.__new__(sdl_probe._Bindings)
        bindings.lib = _Lib(status)  # type: ignore[assignment]
        return bindings.display_geometry(0)

    assert ctypes.sizeof(ctypes.c_int) == 4
    assert geometry(0).refresh_rate == 144
    assert geometry(-1).refresh_rate == 0
