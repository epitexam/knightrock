"""What the machine's displays are, and which one the player meant.

Pure on purpose. The queries that find out need a display to exist
(:mod:`src.core.display.detection`); everything that *decides* is a function of
a :class:`Topology` and can therefore be exercised on a desk with one monitor, or
none, or four, from a table.

The rule the rest of the subsystem inherits: **a monitor is identified by its
name, and a name that cannot be found is reported, never rewritten.** Storing an
index would look simpler and would be the old mistake again -- indices are
reordered by the platform between boots, so a settings file carrying "1" is a
claim about a machine nobody can check. Carrying ``DP-1 27"`` and answering
"that screen is gone, using the primary" is a claim the game can settle every
launch, and the answer reaches the player as a line on the menu instead of as a
window on the wrong monitor.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

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

    @property
    def origin(self) -> tuple[int, int]:
        """Where this display sits on the virtual desktop.

        May be negative: a Linux desktop whose primary is not leftmost puts the
        left monitor there, and assuming otherwise is what once placed a window
        on the wrong panel.
        """
        return (self.bounds[0], self.bounds[1])

    @property
    def detail(self) -> str:
        """The resolution and rate, for a menu row that has a column for it."""
        rate = f" @ {self.refresh_rate} Hz" if self.refresh_rate > 0 else ""
        return f"{self.size[0]}x{self.size[1]}{rate}"


class ResolutionReason(StrEnum):
    """Why a stored monitor name resolved to the monitor it did.

    Carried rather than logged and discarded, because "the screen you chose is
    gone" is the one outcome a player has to be told about: it is the difference
    between the game adapting and the game being wrong.
    """

    MATCHED = "matched"
    NONE_CHOSEN = "none chosen"
    MISSING = "that screen is gone"
    UNNAMED = "this setup reports no screen names"
    AMBIGUOUS = "two screens share that name"


@dataclass(frozen=True)
class Resolution:
    """The monitor to use, and what it cost to choose it."""

    monitor: Monitor
    reason: ResolutionReason
    fallback: Monitor

    @property
    def honoured(self) -> bool:
        """Whether the player's own choice is what got used.

        False whenever the game decided, which is the case the menu reports and
        the case a test asserts against. ``NONE_CHOSEN`` counts as honoured
        because nothing was overridden: the player never expressed a preference.
        """
        return self.reason in (ResolutionReason.MATCHED, ResolutionReason.NONE_CHOSEN)


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

    def label_for(self, monitor: Monitor) -> str:
        """A name to show, made unambiguous when the machine has two of a kind.

        Two identical panels both report the same EDID name, and picking
        between two rows reading ``DP-1`` would be a coin toss presented as a
        menu. The index is appended only when it has to be.
        """
        if not monitor.name:
            return f"Screen {monitor.index + 1}"
        duplicates = Counter(m.name for m in self.monitors)[monitor.name]
        return monitor.name if duplicates < 2 else f"{monitor.name} ({monitor.index + 1})"

    def resolve(self, wanted: str | None) -> Resolution:
        """The monitor a stored name means, and why it is that one.

        A name is matched exactly and then, so a monitor the platform renames
        is a miss rather than a near-miss. Near-matching would let ``DP-1``
        quietly become ``DP-2`` after a cable moves, which is the same silent
        substitution this module exists to prevent.

        ``wanted`` is never written back here. The caller keeps the player's
        name, and re-asks every launch, so a screen that comes back is used
        again without the player doing anything.
        """
        primary = self.primary
        if wanted is None:
            return Resolution(primary, ResolutionReason.NONE_CHOSEN, primary)
        if not self.named:
            # The names a player picked came from a file written on a machine
            # that could read them. Nothing here can be matched against.
            return Resolution(primary, ResolutionReason.UNNAMED, primary)
        matches = [monitor for monitor in self.monitors if monitor.name == wanted]
        if len(matches) == 1:
            return Resolution(matches[0], ResolutionReason.MATCHED, primary)
        if len(matches) > 1:
            # Two panels reporting one EDID name. Taking the first would be a
            # coin toss that reads as a decision, and it would not be stable:
            # the platform's enumeration order can swap between boots. The
            # primary is as good a guess as any and at least it is a named one.
            return Resolution(primary, ResolutionReason.AMBIGUOUS, primary)
        return Resolution(primary, ResolutionReason.MISSING, primary)

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

    A monitor that reports no size at all gets ``FALLBACK_WINDOW`` instead of
    being run through the same arithmetic. That is the headless case and a driver
    that answered nothing, and the arithmetic would hand it a 1x1 window: a
    window no menu fits into and no player can use, from a code path whose whole
    job is to produce a window someone can work with.
    """
    available = monitor.usable_size
    if available[0] <= 0 or available[1] <= 0:
        return FALLBACK_WINDOW
    return tuple(  # type: ignore[return-value]
        max(1, min(available[axis], max(MIN_WINDOW[axis], available[axis] - WINDOW_MARGIN[axis])))
        for axis in (0, 1)
    )


def fit_size(size: tuple[int, int], monitor: Monitor) -> tuple[int, int]:
    """A requested window size, shrunk until it fits the display it opens on.

    A remembered size from a 4K desk has to survive arriving at a laptop, and
    the two rules here are different. Below the usable area, the request is
    clamped to it -- a window wider than its screen cannot be moved. At or above
    it, the request is honoured, and the floor is only ever raised.
    """
    available = monitor.usable_size
    return (
        max(MIN_WINDOW[0], min(size[0], available[0])),
        max(MIN_WINDOW[1], min(size[1], available[1])),
    )


def fit_position(
    position: tuple[int, int], size: tuple[int, int], monitor: Monitor
) -> tuple[int, int]:
    """A remembered position, moved until the window's title bar is reachable.

    Measured on the window's *top* edge rather than its whole rectangle: a
    window taller than the panel is a legitimate thing for a player to ask for,
    and refusing it because it cannot fit would be the game overriding a choice
    the player can see they made. What has to stay true is that the window can
    be grabbed and dragged back.
    """
    origin_x, origin_y = monitor.usable_origin
    left, top = position
    return (
        max(origin_x, min(left, origin_x + monitor.usable_size[0] - min(size[0], 64))),
        max(origin_y, min(top, origin_y + monitor.usable_size[1] - 32)),
    )


def centre_on(monitor: Monitor, size: tuple[int, int]) -> tuple[int, int]:
    """The top-left corner that centres ``size`` on ``monitor``."""
    origin_x, origin_y = monitor.usable_origin
    return (
        origin_x + max(0, (monitor.usable_size[0] - size[0]) // 2),
        origin_y + max(0, (monitor.usable_size[1] - size[1]) // 2),
    )


def degraded(sizes: tuple[tuple[int, int], ...] = ()) -> Topology:
    """A topology built from what pygame alone can say.

    Sizes and count, no origin and no name -- which is exactly what the game had
    before any of this, and what every caller still receives when the SDL probe
    cannot be reached. ``named`` is False, and :meth:`Topology.resolve` then
    refuses every stored name with a reason rather than pretending to match.
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
