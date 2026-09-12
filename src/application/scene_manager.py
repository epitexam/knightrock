"""Gestionnaire de scènes à pile (audit F8.1, Phase 2 #4).

Remplace la boucle infinie de ``Game.run`` par des états Menu / Play /
Pause / Game Over : ``switch`` remplace toute la pile, ``push`` empile
une scène transitoire (pause, game over) au-dessus de la scène gelée,
``pop`` la retire.  Seule la scène du sommet est mise à jour ; le rendu
empile toutes les scènes (overlay de pause par-dessus le monde gelé).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene

if TYPE_CHECKING:
    from src.core.game import Game


class SceneManager:
    """State machine d'application avec pile de scènes."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self._stack: list[Scene] = []

    @property
    def current(self) -> Scene | None:
        """The active (top) scene, or None when the stack is empty."""
        return self._stack[-1] if self._stack else None

    def switch(self, scene: Scene) -> None:
        """Replace the whole stack with ``scene``."""
        for scene_ in reversed(self._stack):
            scene_.exit()
        self._stack.clear()
        self._push(scene)

    def push(self, scene: Scene) -> None:
        """Suspend the current scene and start ``scene`` on top."""
        self._push(scene)

    def pop(self) -> None:
        """Remove the top scene; the scene below resumes (or the game ends)."""
        if not self._stack:
            return
        self._stack.pop().exit()
        if not self._stack:
            self.game.running = False

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward an event to the active scene."""
        if self.current is not None:
            self.current.handle_event(event)

    def update(self, delta_time: float) -> None:
        """Advance only the active scene (scenes below stay frozen)."""
        if self.current is not None:
            self.current.update(delta_time)

    def draw(self) -> list[pygame.Rect] | None:
        """Draw the stack; dirty rects of the top scene, or None.

        A stack of several scenes (pause overlay) redraws everything:
        the overlay must repaint pixels the frozen scene below owns.
        """
        if not self._stack:
            return None
        if len(self._stack) > 1:
            for scene in self._stack:
                scene.draw()
            return None
        top = self.current
        assert top is not None
        return top.draw()

    def _push(self, scene: Scene) -> None:
        self._stack.append(scene)
        scene.enter()
