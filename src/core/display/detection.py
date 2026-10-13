"""What the game can find out about the setup it is running on.

Everything here that takes a ``desktop`` or a ``topology`` argument is a pure
function of it, on purpose. The desktop queries need a display, so they are the
only part that cannot be exercised headlessly; the decisions built on top of them
can, and those are the ones that used to be wrong. ``pygame.display.get_desktop_sizes``
answers under the dummy video driver, but a policy that has to be re-tested on
a real screen is a policy nobody re-tests.

The queries come in two grades. pygame alone gives sizes, and a count, and that
was the whole of it for a long time -- which is why the window was pinned to the
primary display, on the grounds that the origins of the others were unknowable.
They are not unknowable, they are one layer down: :mod:`src.core.display.sdl_probe`
reaches into the libSDL2 pygame already links and gets them, along with the
usable area of each panel and what the platform calls it. So :func:`topology`
prefers that and degrades to pygame's answer when the probe cannot be reached,
and the two are told apart by ``Topology.named`` rather than by guesswork.

Note what is *not* here any more: a catalogue of window sizes. The game used to
offer five resolutions per machine and store the one it picked, which made a
video setting into a claim about the player's monitor, and the claim was wrong
as often as it was right -- in borderless the window is the desktop's size
whatever the file says. The window is now the only source of truth and the
picture is derived from it, so there is nothing left to offer and nothing left
to store.
"""

import logging

import pygame

from . import sdl_probe
from .framing import Framing
from .mode import DisplayMode
from .monitors import Monitor, Topology, degraded

logger = logging.getLogger(__name__)

#: How far the desktop's aspect may sit from the framing's before the letterbox
#: stops being invisible and starts being two black stripes.
ASPECT_TOLERANCE = 0.05


def desktop_sizes() -> tuple[tuple[int, int], ...]:
    """Every attached display, as ``(width, height)``.

    Only sizes: the origins of each screen on the virtual desktop are not
    exposed by pygame, which is what :mod:`src.core.display.sdl_probe` is for.
    """
    try:
        return tuple((int(w), int(h)) for w, h in pygame.display.get_desktop_sizes())
    except pygame.error:
        # No video system: headless test runs, or a driver that cannot answer.
        # An empty answer is the honest one, and every caller treats it as
        # "we do not know", which is a state the code has to survive anyway.
        return ()


def desktop_size(index: int = 0) -> tuple[int, int]:
    """One display's size, clamped to a real index.

    A ``settings.json`` written on a three-monitor desk and then opened on a
    laptop has no index 2 to go to, and pygame answers an out-of-range one with
    ``error: displayIndex must be in the range 0 - 0`` -- a crash on the very
    first frame, on the machine least able to cope with it.
    """
    sizes = desktop_sizes()
    if not sizes:
        return (0, 0)
    return sizes[index if 0 <= index < len(sizes) else 0]


def topology() -> Topology:
    """Every display on this machine, described as well as the platform allows.

    The SDL probe when it works, pygame's sizes when it does not. Reached on
    every launch and on every topology poll, so it must not raise and must not
    be expensive: the probe's handle is cached, and a machine with no video
    system answers with the primary's size and no name.
    """
    geometry = sdl_probe.probe()
    if geometry:
        return Topology(tuple(Monitor.from_geometry(found) for found in geometry), named=True)
    return degraded(desktop_sizes())


def desktop_refresh_rates() -> tuple[int, ...]:
    """The refresh rates a display reports, in Hz, best first.

    ``pygame.display.get_current_refresh_rate`` looks like the obvious call and
    is not usable here: it raises ``error: No open window`` before the display
    exists, and it only ever reports the *current* display. This one works
    before the window is created.

    The rates are the **primary** display's, and there is no way to ask for
    another's: ``get_desktop_refresh_rates`` takes no arguments in pygame 2.5,
    while ``get_desktop_sizes`` does. So this is a single display's answer
    wearing a plural name. Per-display rates come from the SDL probe instead,
    and a display the game is actually on has its own in
    :attr:`src.core.display.monitors.Monitor.refresh_rate`.
    """
    try:
        rates = pygame.display.get_desktop_refresh_rates()
    except pygame.error:
        return ()
    return tuple(sorted((int(rate) for rate in rates), reverse=True))


def initial_window_size(desktop: tuple[int, int]) -> tuple[int, int]:
    """The size to open a windowed game at, from a bare desktop size.

    A thin wrapper kept for the callers that only have sizes -- headless tests
    and the degraded topology. The real answer comes from
    :func:`src.core.display.monitors.opening_size`, which knows about the taskbar
    and the panel's origin and can therefore place the window rather than only
    size it.
    """
    from .monitors import Monitor, opening_size

    return opening_size(Monitor(index=0, name="", bounds=(0, 0, *desktop), usable=(0, 0, *desktop)))


def auto_display_mode(framing: Framing, desktop: tuple[int, int]) -> DisplayMode:
    """Resolve ``DisplayMode.AUTO`` for this machine. Never returns AUTO.

    Borderless when the desktop already has the shape of the framing, because
    then the letterbox collapses to nothing and the game fills the screen with
    nothing to configure. Otherwise a window, sized generously: on a screen
    whose shape does not match, the player should be able to *see* the bars and
    the desktop around them, which reads as deliberate rather than broken.
    """
    if desktop[0] <= 0 or desktop[1] <= 0:
        return DisplayMode.WINDOW
    if abs(desktop[0] / desktop[1] - framing.aspect) / framing.aspect < ASPECT_TOLERANCE:
        return DisplayMode.BORDERLESS
    return DisplayMode.WINDOW
