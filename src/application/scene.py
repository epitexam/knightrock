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
    rendering via ``draw``, which paints into the render target it is handed.
    Nothing is reported back: every frame is a complete repaint, so there is no
    partial presentation for a scene to take part in.
    """

    def __init__(self, game: Game) -> None:
        self.game = game

    def enter(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene becomes active."""

    @property
    def halts_simulation(self) -> bool:
        """Whether this scene stops the world while it is on top.

        A scene that overrides ``update`` to do nothing does not merely freeze
        the picture -- it breaks an assumption the renderer relies on. The
        camera interpolates between the position the last tick started from and
        the one it ended at, and only a tick can close that gap. With no ticks,
        the gap stays open and every frame re-blends it with a *different*
        fraction, so the world does not stand still: it slides.

        That reads as the game trembling behind the pause menu, and it is
        invisible to any test that checks the pause screen's own pixels, because
        the moving part is the scene underneath it.

        So a scene that stops the world says so here, and the loop stops
        interpolating: the picture is then exactly where the simulation is, and
        it stays there. A scene that forgets to declare this gets the sliding
        world back, which is why this is one property rather than a special case
        for the pause screen.
        """
        return False

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
