"""What the game can find out about the displays it is running on.

Functions taking a ``desktop`` or ``topology`` are pure, so the decisions can be
tested headless; only the queries need a display. :func:`topology` prefers the
SDL probe (:mod:`src.core.display.sdl_probe`: origins, usable areas, names) and
falls back to pygame's sizes, and ``Topology.named`` says which answered.
"""

import logging

import pygame

from . import sdl_probe
from .monitors import Monitor, Topology, degraded

logger = logging.getLogger(__name__)


def desktop_sizes() -> tuple[tuple[int, int], ...]:
    """Every attached display, as ``(width, height)``; no origins (see the SDL probe)."""
    try:
        return tuple((int(w), int(h)) for w, h in pygame.display.get_desktop_sizes())
    except pygame.error:
        # No video system: "we do not know", which every caller survives.
        return ()


def desktop_size(index: int = 0) -> tuple[int, int]:
    """One display's size, clamped to a real index.

    A saved index from a bigger desk would otherwise make pygame raise on the
    first frame.
    """
    sizes = desktop_sizes()
    if not sizes:
        return (0, 0)
    return sizes[index if 0 <= index < len(sizes) else 0]


def topology() -> Topology:
    """Every display, as well as the platform can describe it.

    The SDL probe when it works, pygame's sizes otherwise. Called on every
    topology poll, so it never raises and stays cheap.
    """
    geometry = sdl_probe.probe()
    if geometry:
        return Topology(tuple(Monitor.from_geometry(found) for found in geometry), named=True)
    return degraded(desktop_sizes())


def desktop_refresh_rates() -> tuple[int, ...]:
    """One rate per display, best first.

    One rate per *display*, not per mode, and it works before a window exists
    (``get_current_refresh_rate`` does not). The rate of the window's own
    screen is :attr:`src.core.display.monitors.Monitor.refresh_rate`.
    """
    try:
        rates = pygame.display.get_desktop_refresh_rates()
    except pygame.error:
        return ()
    return tuple(sorted((int(rate) for rate in rates), reverse=True))
