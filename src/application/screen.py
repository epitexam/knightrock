"""The window, the picture drawn into it, and the screens the window can sit on.

``Game`` used to hold all of this next to the loop, the input and the scenes.
Here it is one object with one job: keep the window and the picture in step and
answer questions about them. It decides nothing about the settings file or the
scenes; it reports what changed (a resize, a screen gone) and the runtime
reacts.
"""

from __future__ import annotations

import logging

import pygame

from src.application.settings_store import UserSettings
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy
from src.core.display.monitors import Monitor, Topology
from src.core.display.presentation import Presentation
from src.core.display.stage import Stage, WindowSpec
from src.core.display.window_watch import DisplayChange, Resize, WindowWatch, monitor_at

logger = logging.getLogger(__name__)

#: Pointer events whose position the interface hit-tests against.
POINTER_EVENTS = frozenset({pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP})
#: The subset that *acts*. A press on a letterbox bar is a press on nothing.
POINTER_PRESSES = frozenset({pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP})


class Screen:
    """The OS window (:class:`Stage`), the picture (:class:`Presentation`), and
    the watch over both (:class:`WindowWatch`)."""

    def __init__(self) -> None:
        self.stage: Stage | None = None
        self.presentation: Presentation | None = None
        #: The window's last known size and the display list, and the rules
        #: that turn their changes into decisions.
        self.window = WindowWatch()

    # ------------------------------------------------------------- questions

    @property
    def is_open(self) -> bool:
        return self.stage is not None and self.presentation is not None

    @property
    def target(self) -> pygame.Surface:
        """The surface every scene draws into."""
        assert self.presentation is not None, "the display is not initialized"
        return self.presentation.surface

    def topology(self, *, refresh: bool = False) -> Topology:
        """The machine's displays, cached between polls (see :class:`WindowWatch`)."""
        return self.window.topology(refresh=refresh)

    def window_monitor(self) -> Monitor | None:
        """The screen the window is on, or ``None`` when nobody can say.

        Not the primary: on a two-screen desk the two differ as soon as the
        player drags the window across, and the VSync row reports this screen's
        rate.
        """
        try:
            x, y = pygame.display.get_window_position()
        except pygame.error:
            return None
        size = self.presentation.window_size if self.presentation is not None else (0, 0)
        return monitor_at(self.topology(), (int(x), int(y)), size)

    def monitor(self) -> Monitor:
        """The screen the game is built on: the window's, else the primary (Rule W)."""
        held = self.window_monitor()
        if held is not None:
            return held
        return self.topology().primary

    def asked_size(self, settings: UserSettings) -> tuple[int, int] | None:
        """The size to ask for: the chosen size; else the windowed size while
        fullscreen; else, on a rebuild, the size the window has now (so a drag
        survives a settings change); else the size the last session closed at;
        else ``None``, which opens at ``opening_size``.
        """
        if settings.window_size is not None:
            return settings.window_size
        if self.stage is not None and self.stage.fullscreen and self.stage.windowed_size:
            return self.stage.windowed_size
        if self.stage is not None and self.presentation is not None:
            return self.presentation.window_size
        return settings.last_window_size

    def spec(self, settings: UserSettings) -> WindowSpec:
        """The window the settings ask for, with an unchosen size kept as it is."""
        return WindowSpec(
            vsync=settings.vsync,
            size=self.asked_size(settings),
            fullscreen=settings.fullscreen,
        )

    # --------------------------------------------------------------- changes

    def open(self, spec: WindowSpec, fit: FitPolicy) -> None:
        """Build the window and the picture drawn into it, once."""
        self.stage = Stage(spec, self.monitor())
        self.window.built(self.stage.size)
        self.presentation = Presentation(self.stage.surface, DEFAULT_FRAMING, fit=fit, convert=True)

    def refit(self) -> bool:
        """Fit the picture to the window again; whether the target is new."""
        assert self.presentation is not None
        return self.presentation.recompute()

    def rebuild(self, spec: WindowSpec) -> None:
        """Recreate the window for ``spec`` and refit the picture to it."""
        assert self.stage is not None and self.presentation is not None
        self.stage.rebuild(spec, self.monitor())
        self.window.built(self.stage.size)
        self.presentation.retarget(self.stage.surface)

    def set_fullscreen(self, on: bool) -> None:
        """Cover the screen or leave it, and refit the picture to the result."""
        assert self.stage is not None and self.presentation is not None
        surface = self.stage.set_fullscreen(on)
        # The size change that follows is the game's, not the player's.
        self.window.built(self.stage.size)
        self.presentation.retarget(surface)

    def resized(self) -> Resize | None:
        """The window's size change since the last frame, if any."""
        if not self.is_open:
            return None
        assert self.presentation is not None
        return self.window.resized(self.presentation.window_size)

    def poll(self, frame_delta: float) -> DisplayChange | None:
        """A screen arriving or leaving since the last poll, if any."""
        stage = self.stage
        if stage is None:
            return None
        return self.window.poll(frame_delta, lambda: self.window_monitor() or stage.monitor)

    def present(self) -> None:
        """Put the finished frame on the screen."""
        assert self.presentation is not None, "the display is not initialized"
        self.presentation.present()

    # --------------------------------------------------------------- pointer

    def to_target(self, event: pygame.event.Event) -> pygame.event.Event | None:
        """Rewrite a pointer event's position into render-target coordinates.

        A press on a letterbox bar is dropped rather than clamped: clamping
        would fire whatever row is nearest the edge. Motion is clamped, so the
        cursor keeps a sensible position while it crosses a bar.
        """
        if self.presentation is None or event.type not in POINTER_EVENTS:
            return event
        position = getattr(event, "pos", None)
        if position is None:
            return event
        if not self.presentation.pointer_in_viewport(position):
            if event.type in POINTER_PRESSES:
                return None
            rect = self.presentation.rect
            position = (
                min(max(position[0], rect.left), rect.right - 1),
                min(max(position[1], rect.top), rect.bottom - 1),
            )
        event.pos = self.presentation.pointer_to_viewport(position)
        return event
