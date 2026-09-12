"""Base commune des scènes d'application (audit F8.1, Phase 2 #4)."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from src.core.game import Game


class Scene(ABC):
    """État d'application : Menu, Gameplay, Pause, Game Over.

    Une scène possède son cycle de vie (``enter``/``exit``), reçoit les
    événements Pygame, avance la simulation à pas fixe via ``update`` et
    produit son rendu via ``draw``.  Conformément au pattern des entités,
    ``draw`` renvoie les rects sales à présenter, ou ``None`` pour un
    rafraîchissement plein écran.
    """

    def __init__(self, game: Game) -> None:
        self.game = game

    def enter(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene becomes active."""

    def exit(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called when the scene is replaced or popped."""

    def handle_event(self, event: pygame.event.Event) -> None:  # noqa: B027
        """Process a single Pygame event."""

    @abstractmethod
    def update(self, delta_time: float) -> None:
        """Advance the scene by one fixed tick."""

    @abstractmethod
    def draw(self) -> list[pygame.Rect] | None:
        """Render the scene; return dirty rects or None for full refresh."""
