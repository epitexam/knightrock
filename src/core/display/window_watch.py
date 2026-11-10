"""What the game knows about its own window between two frames.

The window changes under the game: the player drags or snaps it, the window
manager settles a size it was just asked for, a screen is plugged in or pulled
out. This module turns those observations into decisions -- *the player resized
the window*, *the screen holding the window is gone* -- and leaves the
consequences (refit the picture, forget a stored size, rebuild the window) to
the runtime. It holds no pygame state, so every rule here runs from a table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from time import perf_counter

from . import detection
from .monitors import Monitor, Topology


@dataclass(frozen=True)
class Resize:
    """The window is no longer the size it was built at."""

    size: tuple[int, int]
    #: Whether the player did it. A size change in the moments after the game
    #: built the window is the window manager settling it (a tiling WM, a
    #: clamp, a late "forced" resize), and must not overrule a size just chosen.
    by_player: bool


class DisplayChange(Enum):
    #: The screen holding the window is gone: the window has to be rebuilt.
    WINDOW_SCREEN_GONE = auto()
    #: A screen was added or removed elsewhere: worth telling the player.
    SCREEN_COUNT_CHANGED = auto()


class WindowWatch:
    """The window's last known size, the display list, and the rules on them."""

    #: How long after a build a size change is the window manager's, not a drag.
    RESIZE_GRACE_SECONDS = 1.0
    #: Seconds between two reads of the display list. SDL reports no event for
    #: a screen being added or removed, so the list has to be asked again.
    DISPLAY_POLL_SECONDS = 0.75

    def __init__(
        self,
        read_topology: Callable[[], Topology] = detection.topology,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._read_topology = read_topology
        self._clock = clock
        #: The size the window was last built at, or last seen at.
        self.built_size: tuple[int, int] | None = None
        #: Until when a size change is taken for the window manager's.
        self.grace_until = 0.0
        self._topology: Topology | None = None
        self._topology_age = 0.0

    # -------------------------------------------------------------- window

    def built(self, size: tuple[int, int]) -> None:
        """The game has just (re)built the window, and the platform granted ``size``."""
        self.built_size = size
        self.grace_until = self._clock() + self.RESIZE_GRACE_SECONDS

    def resized(self, live: tuple[int, int]) -> Resize | None:
        """Compare the window's live size with the last one known.

        Read off the window every frame rather than off an event: which of
        pygame-ce's resize events a gesture produces depends on the platform and
        on the gesture, and a snap produces none of the obvious ones.
        """
        if live == self.built_size:
            return None
        self.built_size = live
        return Resize(live, by_player=self._clock() >= self.grace_until)

    # ------------------------------------------------------------ displays

    def topology(self, *, refresh: bool = False) -> Topology:
        """The display list, cached between polls."""
        if self._topology is None or refresh:
            self._topology = self._read_topology()
            self._topology_age = 0.0
        return self._topology

    def poll(self, elapsed: float, held: Callable[[], Monitor]) -> DisplayChange | None:
        """Read the display list again when it is due, and say what changed.

        ``held`` is the screen holding the window, asked of the *previous* list
        and only when the poll is due -- reading the window's position is not a
        per-frame cost worth paying.
        """
        self._topology_age += elapsed
        if self._topology_age < self.DISPLAY_POLL_SECONDS:
            return None
        self._topology_age = 0.0
        current = self._read_topology()
        previous = self._topology
        if current == previous:
            return None
        window_screen = held()
        self._topology = current
        if not any(same_panel(window_screen, monitor) for monitor in current.monitors):
            return DisplayChange.WINDOW_SCREEN_GONE
        if previous is None or len(current.monitors) != len(previous.monitors):
            return DisplayChange.SCREEN_COUNT_CHANGED
        # A taskbar moving or a refresh rate changing also changes the list,
        # and is no news for the player.
        return None


def same_panel(a: Monitor, b: Monitor) -> bool:
    """Whether two reports describe the same panel. SDL renumbers on a hotplug."""
    return a.name == b.name and a.bounds == b.bounds


def monitor_at(
    topology: Topology, position: tuple[int, int], size: tuple[int, int]
) -> Monitor | None:
    """The screen a window at ``position`` of ``size`` is on, or ``None``.

    The window's centre decides, so a window mostly on one panel whose corner
    pokes onto the next is on the first; ``nearest`` covers a centre that falls
    in a gap between panels. ``None`` when the list has no geometry (a degraded
    topology knows sizes but no origins), so a caller prints nothing rather than
    another screen's refresh rate.
    """
    if not topology.has_geometry:
        return None
    return topology.nearest((position[0] + size[0] // 2, position[1] + size[1] // 2))
