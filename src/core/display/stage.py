"""The window: its size, its position and its vsync.

Deliberately the only module in the game that calls ``set_mode``. Everything
else draws into a ``Viewport`` and never learns that a window exists.

One mode, and it is a window
----------------------------
There used to be three -- a window, a borderless window, and exclusive
fullscreen -- and the three names dressed up two flags. ``BORDERLESS`` and
``FULLSCREEN`` both passed ``pygame.FULLSCREEN``, so the mode whose own docstring
promised "no mode change, nothing to restore" was in fact asking the driver for
one, which is exactly what blacks out a hybrid-GPU laptop. ``FULLSCREEN`` asked
for a real mode and then had to put the old one back.

None of that earns its keep. The game is a resizable window, the player chooses
its size from the video menu, and the window manager owns where it sits. So there
is one path: ``RESIZABLE``, a size, and a centre on the display the caller built
for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pygame

from .monitors import (
    MIN_WINDOW,
    Monitor,
    centre_on,
    fit_size,
    opening_size,
    sits_within,
)

logger = logging.getLogger(__name__)

#: How many times the window is asked for the size it was given before the
#: refusal is believed. One is not enough: measured, the platform can answer a
#: ``set_mode`` with a size other than the one asked for -- the window manager
#: clamps it, or the OS "forcibly resizes" it -- and asking again costs nothing
#: next to a window at the wrong size.
SIZE_ATTEMPTS = 2

#: The window's own flags. ``pygame.SCALED`` is deliberately absent: it was doing
#: the letterboxing, which the render target does itself, and pygame's own
#: documentation calls it an experimental API.
WINDOW_FLAGS = pygame.RESIZABLE


@dataclass(frozen=True)
class WindowSpec:
    """What the player asked for, before the platform has its say.

    A plain value rather than ``UserSettings``, so this module stays free of the
    application layer and can be driven straight from a test.

    ``size`` is the size the player chose from the video menu (or the size the
    window already has), clamped to the monitor it opens on. ``None`` means "let
    the machine decide", which is a first launch and a reset, not a default the
    file ever holds.
    """

    vsync: bool = False
    size: tuple[int, int] | None = None


class Stage:
    """The OS window the game is presented in.

    Two rules earn their keep here:

    * **The surface is measured, never assumed.** The size actually granted is
      read back off the surface rather than trusted from the request, because with
      high-DPI windows the two differ and every layout downstream would be quietly
      wrong.
    * **Placement is computed from real display bounds.** Centring needs the
      monitor's origin on the virtual desktop, which
      :mod:`src.core.display.sdl_probe` supplies; a guess puts the window on the
      other monitor, which is worse than not placing it at all.
    """

    def __init__(self, spec: WindowSpec, monitor: Monitor) -> None:
        self.spec = spec
        self.monitor = monitor
        self.surface = self._create(spec, monitor)

    @property
    def size(self) -> tuple[int, int]:
        """The window's granted size, read back from the surface."""
        return self.surface.get_size()

    def rebuild(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Recreate the window for a new specification and return its surface.

        The three fields this touches -- ``spec``, ``monitor``, ``surface`` --
        are committed together or not at all. ``set_mode`` is the one call that
        can fail in the middle of a rebuild -- a driver refusing the vsync flag,
        a panel that vanished between the topology poll and the request -- and
        without the rollback, the stage would be left explaining a window that
        was never created, with ``self.surface`` still pointing at the one the
        platform has just taken away. Restoring the previous triple on failure
        is the difference between an error the caller can handle and a frame
        that Blits into memory the display no longer presents.
        """
        previous = (self.spec, self.monitor, self.surface)
        try:
            self.spec = spec
            self.monitor = monitor
            self.surface = self._create(spec, monitor)
        except Exception:
            self.spec, self.monitor, self.surface = previous
            raise
        return self.surface

    def _create(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Open the window, and place it.

        Order matters: the size is asked for first, because a windowed placement
        depends on how big the window turned out to be, and ``set_mode`` is what
        tells us that. Placing afterwards means the clamp works against the real
        size rather than the requested one.

        **And the size is asked for more than once when the platform refuses it.**
        Measured on the development machine, the platform can answer a
        ``set_mode`` with a size other than the one asked for -- ``Requested window
        size: (1600, 900) / New window size: (2560, 1440)`` -- and the next,
        identical call is honoured. Measuring the granted size and asking again is
        the whole fix, and it is what "measured, never assumed" has to mean when
        the assumption can be dropped on the floor.
        """
        asked = self._window_size(spec, monitor)
        surface = self._set_mode(spec, monitor, asked)
        for _ in range(SIZE_ATTEMPTS - 1):
            if surface.get_size() == asked:
                break
            logger.info(
                "The platform granted %s instead of %s; asking again",
                surface.get_size(),
                asked,
            )
            surface = self._set_mode(spec, monitor, asked)
        # Assigned before either step below, because both read ``self.size`` off
        # it and the granted size is what placement clamps against. Assigning it
        # after would work until something replaced the display surface behind
        # us, and then raise an AttributeError on the very first frame -- which
        # is the window-creation frame, with no fallback in reach.
        self.surface = surface
        self._place(spec, monitor)
        self._limit_size()
        return surface

    def _set_mode(
        self, spec: WindowSpec, monitor: Monitor, size: tuple[int, int]
    ) -> pygame.Surface:
        """One ``set_mode`` for this specification, at ``size``.

        Assigned to ``self.surface`` as it goes, so that every caller between this
        and :meth:`_place` sees the current one rather than the previous frame's.
        """
        surface = pygame.display.set_mode(
            size,
            WINDOW_FLAGS,
            0,
            monitor.index,
            1 if spec.vsync else 0,
        )
        self.surface = surface
        return surface

    @staticmethod
    def _window_size(spec: WindowSpec, monitor: Monitor) -> tuple[int, int]:
        """The size to ask for.

        The size the player chose if there is one, else as large as fits. A
        starting point and a preference respectively; the player drags the window
        to whatever they like and the render target follows.

        ``fit_size`` raises to the floor, and a chosen size of zero is not a size:
        a window under ``MIN_WINDOW`` cannot be laid out, so asking for one would
        buy a window the interface cannot be drawn in.
        """
        if spec.size is not None:
            return fit_size(spec.size, monitor)
        return opening_size(monitor)

    def _place(self, spec: WindowSpec, monitor: Monitor) -> None:
        """Re-centre the window on the panel, and only when it has nowhere left.

        One request, and no verification -- that half did not change. What changed
        is *when* the request happens. A windowed placement ran after every
        ``set_mode``, and ``set_mode`` runs for every size change, so a size
        -- change walked the window back to the opening panel's centre: on a
        two-panel desk the player resizes and the window teleports across, which
        is both a surprise the menu did not announce and the exact mismatch that
        made the size list describe a panel the window had just left.

        The rule now (D6): keep the position the window already has whenever the
        new rectangle still fits inside the panel (Rule W's monitor is the one
        holding the window, so "fits" is tested against the panel the player
        put it on), and re-centre only when it does not -- first launch, a
        platform that moved the window under us, and a window the new size puts
        partly off its panel. A keep is a no-op by construction, which is also
        why there is no attempt to *preserve* a position across the panel: the
        window never left its panel, and a move the player never asked for is
        the bug, not the cure.
        """
        window = self._window_handle()
        if window is None:
            return
        try:
            position = window.position
            current = (int(position[0]), int(position[1]))
        except pygame.error, AttributeError:
            logger.debug("No window position readable; centring")
            window.position = centre_on(monitor, self.size)
            return
        if sits_within(current, monitor, self.size):
            return
        window.position = centre_on(monitor, self.size)

    @staticmethod
    def _window_handle() -> pygame.Window | None:
        """The window behind the display surface, when this build has one.

        Reaching for it is deprecated, and correctly so: ``pygame.display`` and
        ``pygame.Window`` are two APIs the library intends to separate. The
        alternative is not doing the thing at all, and the failure mode of a
        handle that stopped working is a window left where the window manager put
        it -- worse-looking, not broken.
        """
        try:
            return pygame.Window.from_display_module()
        except pygame.error, AttributeError:
            logger.debug("No Window handle; leaving the window where the WM put it")
            return None

    def _limit_size(self) -> None:
        """Refuse a window too small to hold the interface.

        The interface refuses to shrink its text past a floor, so a window
        smaller than that floor is a window the player cannot read the menus in
        and cannot drag back out of. Measured here: at 640x480 only one of the
        five placeable debug panels finds a slot, which is why the panel ladder
        goes to 0.4; the window floor is the same idea one level up.

        Best effort. A window manager that refuses the constraint is a cosmetic
        problem, not a reason to fail the launch.
        """
        window = self._window_handle()
        if window is None:
            return
        try:
            window.minimum_size = MIN_WINDOW
        except pygame.error, AttributeError:
            logger.debug("The platform refused a minimum window size")

    def __repr__(self) -> str:
        return f"Stage(monitor={self.monitor.index}, size={self.size})"


__all__ = [
    "Stage",
    "WindowSpec",
    "SIZE_ATTEMPTS",
]
