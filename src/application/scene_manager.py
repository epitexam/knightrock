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

    @property
    def halts_simulation(self) -> bool:
        """Whether anything on the stack is holding the world still.

        Only the top scene is updated, so one halted scene anywhere above the
        gameplay scene is enough to stop it ticking. The whole stack is drawn
        every frame, though, which is why this matters: the frozen world is
        still being repainted, and a repaint that is not identical to the last
        one is what the player sees move.
        """
        return any(scene.halts_simulation for scene in self._stack)

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

    def handle_event(self, event: pygame.event.Event | None) -> None:
        """Forward an event to the active scene.

        ``None`` is a dropped event -- a pointer press that landed in a
        letterbox bar, which is a press on nothing.
        """
        if event is not None and self.current is not None:
            self.input_dispatcher.dispatch(self.current, event)

    def poll_held_repeats(self) -> None:
        """Forward joystick repeats (stick held with no new event)."""
        if self.current is not None:
            self.input_dispatcher.poll_held_repeats(self.current)

    def set_surface(self, surface: pygame.Surface) -> None:
        """Push a new render target through the whole stack.

        Every scene is told, including the ones below the top: a pause overlay
        sits above a frozen gameplay scene, and a resize has to reach both or
        the frozen frame keeps the old geometry. Both the scene and its view
        implement the hooks, so a scene that has neither is a no-op rather than
        a silent omission.
        """
        for scene in self._stack:
            scene.set_surface(surface)
            view = scene.view
            if view is not None:
                view.set_surface(surface)
                view.set_scale(self.game.ui_scale)

    def set_ui_scale(self, scale: float) -> None:
        """Push a new interface scale through the whole stack, for the same
        reason as :meth:`set_surface`."""
        for scene in self._stack:
            scene.set_ui_scale(scale)
            view = scene.view
            if view is not None:
                view.set_scale(scale)

    def update(self, delta_time: float) -> None:
        """Advance only the active scene (scenes below stay frozen)."""
        if self.current is not None:
            self.current.update(delta_time)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the whole stack into the render target.

        Every scene in the stack is drawn whenever there is more than one: a
        pause overlay sits on top of a frozen gameplay scene and has to repaint
        the pixels that scene owns. With no stack there is nothing to draw and
        the target keeps whatever the previous frame left, which is correct --
        the loop presents it unchanged.
        """
        if not self._stack:
            return
        for scene in self._stack:
            scene.draw(surface)

    def _push(self, scene: Scene) -> None:
        self._stack.append(scene)
        scene.enter()
        self.set_ui_scale(self.game.ui_scale)
