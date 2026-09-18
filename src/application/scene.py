"""Shared base of the application scenes (audit F8.1, Phase 2 #4)."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

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

    @abstractmethod
    def update(self, delta_time: float) -> None:
        """Advance the scene by one fixed tick."""

    @abstractmethod
    def draw(self) -> list[pygame.Rect] | None:
        """Render the scene; return dirty rects or None for full refresh."""
