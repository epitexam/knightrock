"""Shared base of the application scenes."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

from src.core.input.event_router import RoutedInput
from src.ui.scale import ScaledView

if TYPE_CHECKING:
    from src.application.game import Game


class Scene(ABC):
    """Application state: Menu, Gameplay, Pause, Game Over.

    A scene owns its lifecycle (``enter``/``exit``), receives events, advances
    at a fixed step in ``update`` and repaints the whole target in ``draw``.
    """

    view: ScaledView | None = None
    """The scene's view, or ``None`` for a scene that draws the world.

    The stack pushes new targets and scales through every scene, and asks this
    rather than catching an ``AttributeError``.
    """

    #: Paints every pixel of the target, so nothing below it needs drawing.
    opaque: bool = False
    #: A full menu page: the menu panels under it are not drawn, only the
    #: backdrop (the world, if there is one) under a veil, so two panels never
    #: show through each other.
    covers_panels_below: bool = False
    #: What a covering page is drawn over: the world, not another menu.
    is_backdrop: bool = False

    def __init__(self, game: Game) -> None:
        self.game = game

    def enter(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene becomes active."""

    def set_surface(self, surface: pygame.Surface) -> None:  # noqa: B027
        """Adopt a new render target after a resize.

        A no-op here: a scene with a view gets the target through :attr:`view`,
        and the world is handed the target on every :meth:`draw`. Declared, not
        looked up with ``getattr``, so a scene cannot skip it in silence.
        """

    def set_ui_scale(self, scale: float) -> None:  # noqa: B027
        """Adopt a new interface scale. A no-op, like :meth:`set_surface`."""

    @property
    def halts_simulation(self) -> bool:
        """Whether this scene stops the world while it is on top.

        The camera interpolates between the last two ticks, and only a tick
        closes that gap: with no ticks, every frame re-blends it with another
        fraction and the frozen world slides behind the menu. A scene that
        stops the world says so here, and the loop stops interpolating.
        """
        return False

    def exit(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene is replaced or popped."""

    def handle_event(self, event: pygame.event.Event) -> None:  # noqa: B027
        """Process a single Pygame event."""

    def handle_routed(self, routed_input: RoutedInput) -> str | None:  # noqa: B027
        """Process a routed input action and report what was performed.

        ``None`` means the screen did not act, which keeps the interface quiet
        (a capture swallowing a press, gameplay ignoring a menu arrow).
        Otherwise: ``MenuAction.BACK`` when the screen dismissed itself, a
        ``MenuAction`` movement when the focus moved, or the ``MenuItem``
        action.
        """

    @abstractmethod
    def update(self, delta_time: float) -> None:
        """Advance the scene by one fixed tick."""

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Draw the scene into ``surface``, the render target it is handed.

        Never into ``pygame.display.get_surface()``: the window is not the
        render target.
        """
