"""Stacked scene manager (audit F8.1, Phase 2 #4).

Replaces the infinite ``Game.run`` loop with Menu / Play / Pause / Game Over
states: ``switch`` replaces the whole stack, ``push`` piles a transient scene
(pause, game over) above the frozen scene, ``pop`` removes it.  Only the top
scene is updated; rendering stacks every scene (pause overlay above the
frozen world).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.input_dispatcher import InputDispatcher
from src.application.scene import Scene

if TYPE_CHECKING:
    from src.core.game import Game


class SceneManager:
    """Application state machine with a scene stack."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self._stack: list[Scene] = []
        self.input_dispatcher = InputDispatcher(game.input_router, game.events)

    @property
    def current(self) -> Scene | None:
        """The active (top) scene, or None when the stack is empty."""
        return self._stack[-1] if self._stack else None

    def switch(self, scene: Scene) -> None:
        """Replace the whole stack with ``scene``."""
        for scene_ in reversed(self._stack):
            scene_.exit()
        self._stack.clear()
        self.input_dispatcher.router.reset()
        self._push(scene)

    def push(self, scene: Scene) -> None:
        """Suspend the current scene and start ``scene`` on top."""
        self.input_dispatcher.router.reset()
        self._push(scene)

    def pop(self) -> None:
        """Remove the top scene; the scene below resumes (or the game ends)."""
        if not self._stack:
            return
        self._stack.pop().exit()
        self.input_dispatcher.router.reset()
        if not self._stack:
            self.game.running = False

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward an event to the active scene."""
        if self.current is not None:
            self.input_dispatcher.dispatch(self.current, event)

    def poll_held_repeats(self) -> None:
        """Forward les repeats joystick (stick tenu sans nouvel event)."""
        if self.current is not None:
            self.input_dispatcher.poll_held_repeats(self.current)

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        for scene in self._stack:
            setter = getattr(scene, "set_display_surface", None)
            if callable(setter):
                setter(display_surface)
            view = getattr(scene, "view", None)
            view_setter = getattr(view, "set_display_surface", None)
            if callable(view_setter):
                view_setter(display_surface)
            view_scale = getattr(view, "set_scale", None)
            if callable(view_scale):
                view_scale(self.game.settings.ui_scale)

    def set_ui_scale(self, scale: float) -> None:
        for scene in self._stack:
            setter = getattr(scene, "set_ui_scale", None)
            if callable(setter):
                setter(scale)
            view = getattr(scene, "view", None)
            view_setter = getattr(view, "set_scale", None)
            if callable(view_setter):
                view_setter(scale)

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
        self.set_ui_scale(self.game.settings.ui_scale)
