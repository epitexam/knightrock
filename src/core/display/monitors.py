"""What the machine's displays are: their bounds, their usable area, their rate.

Pure on purpose. The queries that find out need a display to exist
(:mod:`src.core.display.detection`); everything that *decides* is a function of
a :class:`Topology` and can therefore be exercised on a desk with one monitor, or
none, or four, from a table.

There is no "which screen did the player pick" here any more. The game is a
window; the player moves it, and the platform owns where it sits. The one
question the rest of the game still asks of this module is *which panel is the
window on*, so the VSync row can report that panel's rate rather than the
primary's.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sdl_probe import DisplayGeometry

#: Room left around the usable area for the title bar and the window frame, so
#: a window the game opens is still a window the player can move.
WINDOW_MARGIN = (80, 96)

#: The size to open at when no display can be described at all: a headless run,
#: or a driver that answers nothing. Not a claim about anyone's monitor.
FALLBACK_WINDOW = (1440, 900)

#: A window narrower or shorter than this cannot show the interface, which the
#: metrics layer refuses to shrink past its text floor. Enforced on the window
#: itself so the player cannot drag the game into an unusable state.
MIN_WINDOW = (640, 480)


@dataclass(frozen=True)
class Monitor:
    """One display, described in a way the rest of the game can rely on.

    ``bounds`` is the whole panel in virtual-desktop coordinates, so ``x`` and
    ``y`` may be negative -- the leftmost monitor is not at the origin of a
    Linux desktop whose primary is elsewhere, which is what put a window on the
    wrong screen the last time this was computed by hand. ``usable`` is bounds
    less whatever the desktop reserves, and is what a borderless window should
    fill so it does not sit under a taskbar.

    ``scale`` is the compositor's own scale factor, 1.0 when it reports none.
    It is a system preference rather than something this game chose, so it is
    read when available and never invented.
    """

    index: int
    name: str
    bounds: tuple[int, int, int, int]
    usable: tuple[int, int, int, int]
    refresh_rate: int = 0
    scale: float = 1.0

    @classmethod
    def from_geometry(cls, geometry: DisplayGeometry) -> Monitor:
        return cls(
            index=geometry.index,
            name=geometry.name,
            bounds=geometry.bounds,
            usable=geometry.usable,
            refresh_rate=geometry.refresh_rate,
            scale=geometry.scale,
        )

    @property
    def size(self) -> tuple[int, int]:
        return (self.bounds[2], self.bounds[3])

    @property
    def usable_size(self) -> tuple[int, int]:
        """The area a borderless window may fill.

        Falls back to the panel when the driver reported a usable area smaller
        than nothing -- a usable rectangle of zero would size a window to zero,
        which is worse than covering the panel.
        """
        width, height = self.usable[2], self.usable[3]
        return (width, height) if width > 0 and height > 0 else self.size

    @property
    def usable_origin(self) -> tuple[int, int]:
        return (self.usable[0], self.usable[1])


@dataclass(frozen=True)
class Topology:
    """Every display this machine has, in the platform's own order.

    Index 0 is the primary by SDL's definition, which is the display the
    compositor considers the main one -- not necessarily the leftmost, and not
    necessarily the first the platform enumerates on a hotplug.
    """

    monitors: tuple[Monitor, ...] = ()
    named: bool = False

    @property
    def primary(self) -> Monitor:
        """The display to fall back to.

        The first one, which is index 0 in any list SDL built and therefore the
        primary. A fabricated 1x1 monitor when the list is empty, so every
        caller has a monitor to read and none of them has to check.
        """
        if self.monitors:
            return self.monitors[0]
        return Monitor(index=0, name="", bounds=(0, 0, 1, 1), usable=(0, 0, 1, 1))

    @property
    def indices(self) -> tuple[int, ...]:
        return tuple(monitor.index for monitor in self.monitors)

    @property
    def has_geometry(self) -> bool:
        return bool(self.monitors)

    def containing(self, position: tuple[int, int]) -> Monitor | None:
        """Which display holds a point of the virtual desktop.

        Used to check that a remembered window position still lands somewhere
        the player can reach it.
        """
        x, y = position
        for monitor in self.monitors:
            left, top, width, height = monitor.bounds
            if left <= x < left + width and top <= y < top + height:
                return monitor
        return None

    def nearest(self, position: tuple[int, int]) -> Monitor:
        """The display closest to a point, for a position on no display at all.

        A gap between two panels with different heights is not a gap on any
        desktop, but a remembered coordinate can still land in one -- a monitor
        removed, a layout changed. Nearest-by-centre is enough to get the window
        back somewhere visible, and closer is always better than the primary.
        """
        containing = self.containing(position)
        if containing is not None:
            return containing
        if not self.monitors:
            return self.primary
        x, y = position

        def squared_distance(monitor: Monitor) -> int:
            left, top, width, height = monitor.bounds
            centre_x, centre_y = left + width // 2, top + height // 2
            return (centre_x - x) ** 2 + (centre_y - y) ** 2

        return min(self.monitors, key=squared_distance)


def opening_size(monitor: Monitor) -> tuple[int, int]:
    """The size to open a windowed game at, from one display alone.

    As large as it can be while leaving room for a title bar. A starting size
    and not a remembered one: the player drags it to whatever they like from
    here.

    The two bounds are in tension on a panel too small for both, and the order
    settles it. ``MIN_WINDOW`` is what the interface needs to be usable, and the
    usable area is what the player can actually reach -- so the area wins, and a
    window is opened exactly as large as the screen rather than partly off it.
    Measured: on a 640x400 report the arithmetic answers 640x400, *below* the
    floor and against its own margin -- on purpose. Below the floor,
    :meth:`Presentation.recompute` refuses the window and keeps the last
    drawable target, which is a rule about resizing that an opening size borrows
    honestly: a platform this small gets the largest window that genuinely fits
    rather than one invented to be comfortable.

    The guard is on the raw *report* -- the panel's own size and the raw usable
    rectangle -- rather than on :attr:`usable_size`, and the reason is in that
    property: it falls back to the panel when the usable area is degenerate, so
    a guard in front of it can never fire -- dead code wearing a comment. The
    rows the guard still catches are the fiction a broken driver can produce: a
    panel that reports zero width or height, raw or usable, has no arithmetic
    answer and gets ``FALLBACK_WINDOW``, which is a size chosen for use rather
    than derived from junk.

    The *fabricated* fallback that lives in :attr:`Topology.primary` -- a 1x1
    panel built when no list at all came back -- passes this guard, with one
    pixel on each axis, and no correction is coming: the arithmetic gives it
    back a request of 1x1, which a real window manager floors through
    :meth:`Stage._limit_size` and a headless call shrugs at. The docstring used
    to claim such a monitor received the fallback size; it never did, and
    writing what the code does is worth more here than keeping a promise the
    code never kept.
    """
    panel = monitor.size
    raw_usable = (monitor.usable[2], monitor.usable[3])
    if (panel[0] < 1 or panel[1] < 1) or (raw_usable[0] < 1 or raw_usable[1] < 1):
        return FALLBACK_WINDOW
    available = monitor.usable_size
    return tuple(  # type: ignore[return-value]
        max(1, min(available[axis], max(MIN_WINDOW[axis], available[axis] - WINDOW_MARGIN[axis])))
        for axis in (0, 1)
    )


def fit_size(size: tuple[int, int], monitor: Monitor) -> tuple[int, int]:
    """A requested window size, shrunk until it fits the display it opens on.

    A remembered size from a 4K desk has to survive arriving at a laptop, and
    the two rules here are different. Below the usable area, the request is
    clamped to it -- a window wider than its screen cannot be moved. At or above
    it, the request is honoured, and the floor is only ever raised. On a panel
    that cannot hold ``MIN_WINDOW`` at all the two collide, and the floor wins:
    a window under the interface floor is a window nothing can be drawn in, and
    the tension is resolved in favour of the drawing.
    """
    available = monitor.usable_size
    return (
        max(MIN_WINDOW[0], min(size[0], available[0])),
        max(MIN_WINDOW[1], min(size[1], available[1])),
    )


def centre_on(monitor: Monitor, size: tuple[int, int]) -> tuple[int, int]:
    """The top-left corner that centres ``size`` on ``monitor``."""
    origin_x, origin_y = monitor.usable_origin
    return (
        origin_x + max(0, (monitor.usable_size[0] - size[0]) // 2),
        origin_y + max(0, (monitor.usable_size[1] - size[1]) // 2),
    )


def sits_within(position: tuple[int, int], monitor: Monitor, size: tuple[int, int]) -> bool:
    """Whether a window at ``position`` would sit wholly inside the panel.

    The rectangle the window occupies at ``size``, from its top-left corner at
    ``position``, tested against the area the player can reach -- not the panel's
    bounds, because a window squatting on the taskbar or under the frame
    reservation is a window the player would have to drag out, and the one thing
    re-centring exists to prevent. Origins are honoured, because a left-hand
    panel's usable area starts at a negative ``x`` -- the virtual desktop's
    origin is wherever the compositor put it.

    It answers what a placement is about to do, which is why it takes the *new*
    size and the *current* position: a resized window can be kept where it was
    when the new rectangle still fits, which is every shrink and most sideways
    grows on a panel with room to the right.
    """
    x, y = position
    origin_x, origin_y = monitor.usable_origin
    width, height = monitor.usable_size
    return (
        origin_x <= x
        and origin_y <= y
        and x + size[0] <= origin_x + width
        and y + size[1] <= origin_y + height
    )


def degraded(sizes: tuple[tuple[int, int], ...] = ()) -> Topology:
    """A topology built from what pygame alone can say.

    Sizes and count, no origin and no name -- which is exactly what the game had
    before any of this, and what every caller still receives when the SDL probe
    cannot be reached. ``named`` is False, so nothing downstream claims to know
    a panel's name.
    """
    return Topology(
        monitors=tuple(
            Monitor(
                index=index, name="", bounds=(0, 0, width, height), usable=(0, 0, width, height)
            )
            for index, (width, height) in enumerate(sizes)
        ),
        named=False,
    )
