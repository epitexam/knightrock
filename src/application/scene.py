"""Shared base of the application scenes (audit F8.1, Phase 2 #4)."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

from src.core.input.event_router import RoutedInput

if TYPE_CHECKING:
    from src.core.game import Game


class Scene(ABC):
    """Application state: Menu, Gameplay, Pause, Game Over.

    A scene owns its lifecycle (``enter``/``exit``), receives Pygame events,
    advances the simulation at a fixed step via ``update`` and produces its
    rendering via ``draw``.  Following the entity pattern, ``draw`` returns
    the dirty rects to present, or ``None`` for a full-screen refresh.
    """

    def __init__(self, game: Game) -> None:
        self.game = game

    def enter(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene becomes active."""

    def exit(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene is replaced or popped."""

    def handle_event(self, event: pygame.event.Event) -> None:  # noqa: B027
        """Process a single Pygame event."""

    def handle_routed(self, routed_input: RoutedInput) -> str | None:  # noqa: B027
        """Process a routed input action; report what was performed.

        The report is the scene's own truth about itself, and it is the only
        thing the interface layer needs: ``None`` means *this screen did not
        act*, and that is what makes the silence structural rather than a
        setting. The gameplay scene answers ``None`` to the arrows it shares
        with the menus, and the controls screen answers ``None`` to a press
        swallowed by a rebinding capture — neither has to know that anything is
        listening.

        A screen returns ``MenuAction.BACK`` when it dismissed itself, a
        ``MenuAction`` movement value when the focus moved, and the
        ``MenuItem`` action otherwise.
        """

    @abstractmethod
    def update(self, delta_time: float) -> None:
        """Advance the scene by one fixed tick."""

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Draw the scene into ``surface``, the fixed-size render target.

        The surface is handed in rather than fetched from
        ``pygame.display.get_surface()``: the window is not what anything is
        drawn into any more, and a scene that reached for it would be drawing
        into a surface whose size depends on the player's video settings.
        """
