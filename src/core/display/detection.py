"""What the game can find out about the setup it is running on.

Everything here that takes a ``desktop`` argument is a pure function of it, on
purpose. The desktop queries need a display, so they are the only part that
cannot be exercised headlessly; the decisions built on top of them can, and
those are the ones that used to be wrong. ``pygame.display.get_desktop_sizes``
answers under the dummy video driver, but a policy that has to be re-tested on
a real screen is a policy nobody re-tests.
"""

import pygame

from .framing import Framing
from .mode import DisplayMode

#: Room left around the desktop for the title bar and the taskbar, so a
#: "full screen" window is still a window the player can move.
DESKTOP_MARGIN = (80, 96)

#: The window sizes offered, as fractions of the player's own desktop.
#:
#: Relative rather than absolute, and that is the whole difference from a fixed
#: catalogue of resolutions. A list of absolute sizes is a claim about the
#: player's monitor that the game has no way to check, so it ends up offering
#: 2560x1440 to a 1366x768 laptop. A list of fractions is meaningful on every
#: screen, and the "does it fit" filter below removes the entries that do not.
WINDOW_SIZE_FRACTIONS = (0.40, 0.55, 0.70, 0.85, 0.95)

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


def fits_on_desktop(size: tuple[int, int], desktop: tuple[int, int]) -> bool:
    """Whether a window of ``size`` can be shown on ``desktop`` and moved.

    The margin is what stops a "whole desktop" entry from producing a window
    whose title bar is off the bottom of the screen.
    """
    margin_w, margin_h = DESKTOP_MARGIN
    return size[0] <= max(0, desktop[0] - margin_w) and size[1] <= max(0, desktop[1] - margin_h)


def window_size_choices(desktop: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    """The window sizes to offer for this desktop, smallest first.

    Entries that cannot fit are dropped rather than disabled: a size the
    player's screen cannot show is not a choice, and listing it only produces a
    row that fails when it is applied.
    """
    sizes = {
        (round(desktop[0] * fraction), round(desktop[1] * fraction))
        for fraction in WINDOW_SIZE_FRACTIONS
    }
    return tuple(sorted(size for size in sizes if fits_on_desktop(size, desktop)))


def largest_window_size(desktop: tuple[int, int]) -> tuple[int, int]:
    """The biggest window that fits, falling back to a usable minimum.

    A desktop too small for even the smallest fraction still has to produce a
    size, because refusing to open a window is not a recovery.
    """
    choices = window_size_choices(desktop)
    if choices:
        return choices[-1]
    return (max(1, desktop[0] // 2), max(1, desktop[1] // 2))


def auto_display_mode(framing: Framing, desktop: tuple[int, int]) -> DisplayMode:
    """Resolve ``DisplayMode.AUTO`` for this machine. Never returns AUTO."""
    """Pick the display mode for a machine we have never seen before.

    Borderless when the desktop is already the shape of the framing, because
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
