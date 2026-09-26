"""What the game can find out about the setup it is running on.

Everything here that takes a ``desktop`` argument is a pure function of it, on
purpose. The desktop queries need a display, so they are the only part that
cannot be exercised headlessly; the decisions built on top of them can, and
those are the ones that used to be wrong. ``pygame.display.get_desktop_sizes``
answers under the dummy video driver, but a policy that has to be re-tested on
a real screen is a policy nobody re-tests.

Note what is *not* here any more: a catalogue of window sizes. The game used to
offer five resolutions per machine and store the one it picked, which made a
video setting into a claim about the player's monitor, and the claim was wrong
as often as it was right -- in borderless the window is the desktop's size
whatever the file says. The window is now the only source of truth and the
picture is derived from it, so there is nothing left to offer and nothing left
to store.
"""

import pygame

from .framing import Framing
from .mode import DisplayMode

#: Room left around the desktop for the title bar and the taskbar, so the
#: window the game opens at is still a window the player can move.
DESKTOP_MARGIN = (80, 96)

#: The smallest window worth opening, used when the desktop is unknown -- a
#: headless run, or a driver that cannot answer.
FALLBACK_WINDOW = (1440, 900)

#: How far the desktop's aspect may sit from the framing's before the letterbox
#: stops being invisible and starts being two black stripes.
ASPECT_TOLERANCE = 0.05


def desktop_sizes() -> tuple[tuple[int, int], ...]:
    """Every attached display, as ``(width, height)``.

    Only sizes: SDL's display bounds -- the origin of each screen on the
    virtual desktop -- are not exposed by pygame, which is why the window is
    positioned against the primary screen rather than a chosen one.
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


def desktop_refresh_rates() -> tuple[int, ...]:
    """The refresh rates a display reports, in Hz, best first.

    ``pygame.display.get_current_refresh_rate`` looks like the obvious call and
    is not usable here: it raises ``error: No open window`` before the display
    exists, and it only ever reports the *current* display. This one works
    before the window is created.

    The rates are the **primary** display's, and there is no way to ask for
    another's: ``get_desktop_refresh_rates`` takes no arguments in pygame 2.5,
    while ``get_desktop_sizes`` does. So this is a single display's answer
    wearing a plural name, and a machine with a 180Hz primary and a 60Hz
    secondary gets the primary's numbers either way.

    That is acceptable here only because the window is placed on display 0
    (:mod:`src.core.display.stage`); a game that let the window sit on another
    screen would be reading the wrong panel's rate, and the honest fix would
    have to be SDL, not pygame.
    """
    try:
        rates = pygame.display.get_desktop_refresh_rates()
    except pygame.error:
        return ()
    return tuple(sorted((int(rate) for rate in rates), reverse=True))


def initial_window_size(desktop: tuple[int, int]) -> tuple[int, int]:
    """The size to open a windowed game at, from the desktop alone.

    Not a setting, and not remembered: a starting size, decided from the machine
    at launch and gone at exit. The catalogue of resolutions this replaces was
    seven claims about the player's monitor that the game had no way to check,
    and it still ended up disagreeing with the window it had opened -- in
    borderless the size on screen is the desktop's whatever the file says, and
    nothing wrote the difference back, so the menu displayed a number the game
    was not using.

    So the game no longer has an opinion about how big the window should be. It
    opens as large as it can without hiding its own title bar, the player drags
    it to whatever they like, and the picture follows: the render target is the
    window, so every size is a first-class one.
    """
    if desktop[0] <= 0 or desktop[1] <= 0:
        return FALLBACK_WINDOW
    # The bigger of "as large as possible" and "the default", then capped at the
    # desktop itself: on a 1366x768 laptop the margin is larger than the
    # default, and a window wider than the screen is not a starting size.
    return tuple(  # type: ignore[return-value]
        max(1, min(desktop[axis], max(FALLBACK_WINDOW[axis], desktop[axis] - DESKTOP_MARGIN[axis])))
        for axis in (0, 1)
    )


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
