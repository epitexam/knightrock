"""What the machine's displays are: their bounds, usable area and rate.

Pure: the queries live in :mod:`src.core.display.detection`, and everything
here is a function of a :class:`Topology`, so it is tested from tables.
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

#: The smallest window the interface can be laid out in; asked of the window
#: manager too, so the player cannot drag the game below it.
MIN_WINDOW = (640, 480)


@dataclass(frozen=True)
class Monitor:
    """One display.

    ``bounds`` is the panel in virtual-desktop coordinates (``x``/``y`` may be
    negative); ``usable`` is bounds less taskbars and the like. ``scale`` is the
    compositor's scale factor, 1.0 when it reports none.
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
        """The area a window may fill; the whole panel if the driver reported none."""
        width, height = self.usable[2], self.usable[3]
        return (width, height) if width > 0 and height > 0 else self.size

    @property
    def usable_origin(self) -> tuple[int, int]:
        return (self.usable[0], self.usable[1])


@dataclass(frozen=True)
class Topology:
    """Every display, in SDL's order; index 0 is the primary."""

    monitors: tuple[Monitor, ...] = ()
    named: bool = False

    @property
    def primary(self) -> Monitor:
        """The primary, or a 1x1 stand-in when there is no display at all."""
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
        """Which display holds a point of the virtual desktop, if any."""
        x, y = position
        for monitor in self.monitors:
            left, top, width, height = monitor.bounds
            if left <= x < left + width and top <= y < top + height:
                return monitor
        return None

    def nearest(self, position: tuple[int, int]) -> Monitor:
        """The display holding a point, or the one whose centre is nearest."""
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
    """The size to open at: the usable area less room for a title bar.

    The usable area beats ``MIN_WINDOW`` on a screen too small for both, so the
    window is never partly off it. A panel reporting a zero size, raw or usable,
    gets ``FALLBACK_WINDOW``.
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
    """A requested size, clamped to the usable area and raised to ``MIN_WINDOW``.

    The floor wins on a screen too small for both.
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
    """Whether a window of ``size`` at ``position`` sits wholly in the usable area.

    Takes the *new* size and the *current* position: a resized window that
    still fits stays where it is.
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
    """A topology from pygame alone: sizes, no origins, no names (``named=False``)."""
    return Topology(
        monitors=tuple(
            Monitor(
                index=index, name="", bounds=(0, 0, width, height), usable=(0, 0, width, height)
            )
            for index, (width, height) in enumerate(sizes)
        ),
        named=False,
    )
