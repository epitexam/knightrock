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
from src.core.colors import Colors

if TYPE_CHECKING:
    from src.core.game import Game


class SceneManager:
    """Application state machine with a scene stack."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self._stack: list[Scene] = []
        self._veil: pygame.Surface | None = None
        #: The target the last draw painted, and the frame a transition fades
        #: out of with how far it is through. See :meth:`_begin_transition`.
        self._target: pygame.Surface | None = None
        self._leaving: pygame.Surface | None = None
        self._fade = 0.0
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
        if self._stack:
            self._begin_transition()
        for scene_ in reversed(self._stack):
            scene_.exit()
        self._stack.clear()
        self.input_dispatcher.router.reset()
        self._push(scene)

    def push(self, scene: Scene) -> None:
        """Suspend the current scene and start ``scene`` on top."""
        self._begin_transition()
        self.input_dispatcher.router.reset()
        self._push(scene)

    def pop(self) -> None:
        """Remove the top scene; the scene below resumes (or the game ends)."""
        if not self._stack:
            return
        if len(self._stack) > 1:
            self._begin_transition()
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
        if self._leaving is not None:
            self._fade += delta_time
            if self._fade >= self.TRANSITION_SECONDS:
                self._leaving = None
        if self.current is not None:
            self.current.update(delta_time)

    #: The veil a covering menu page is drawn over, on top of the world.
    VEIL = (8, 10, 14, 190)
    #: How long the last frame takes to fade out when the stack changes.
    TRANSITION_SECONDS = 0.15
    #: The old frame's opacity on the first frame of a fade: below full, so the
    #: new page shows on the very frame after the press.
    TRANSITION_START_ALPHA = 192

    def _begin_transition(self) -> None:
        """Keep the frame on screen now, to fade it out over the next one.

        A page that replaces another in one frame reads as a flicker; a short
        cross-fade reads as a page turning. Nothing to fade before the first
        draw, so a stack built before anything was shown just appears.
        """
        if self._target is None:
            return
        self._leaving = self._target.copy()
        self._fade = 0.0

    def _draw_transition(self, surface: pygame.Surface) -> None:
        leaving = self._leaving
        if leaving is None:
            return
        if leaving.get_size() != surface.get_size():
            # The window changed mid-fade: that frame no longer lines up.
            self._leaving = None
            return
        remaining = 1.0 - self._fade / self.TRANSITION_SECONDS
        leaving.set_alpha(max(0, min(255, round(self.TRANSITION_START_ALPHA * remaining))))
        surface.blit(leaving, (0, 0))

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the stack into the render target, bottom to top.

        Only what is visible is drawn. Drawing starts at the highest opaque
        scene, since everything below it is painted over anyway. A menu page
        that covers the panels below it (Options, Video, a list...) is drawn on
        its own, over the world if there is one -- under a veil -- or over a
        plain background otherwise, so two menu panels never overlap.
        """
        self._target = surface
        if not self._stack:
            return
        self._draw_stack(surface)
        self._draw_transition(surface)

    def _draw_stack(self, surface: pygame.Surface) -> None:
        cover = next(
            (i for i in range(len(self._stack) - 1, -1, -1) if self._stack[i].covers_panels_below),
            None,
        )
        if cover is None:
            base = next(
                (i for i in range(len(self._stack) - 1, -1, -1) if self._stack[i].opaque), 0
            )
            for scene in self._stack[base:]:
                scene.draw(surface)
            return
        backdrop = next((i for i in range(cover - 1, -1, -1) if self._stack[i].is_backdrop), None)
        if backdrop is None:
            surface.fill(Colors.dark_grey)
        else:
            self._stack[backdrop].draw(surface)
            surface.blit(self._veil_for(surface.get_size()), (0, 0))
        for scene in self._stack[cover:]:
            scene.draw(surface)

    def _veil_for(self, size: tuple[int, int]) -> pygame.Surface:
        if self._veil is None or self._veil.get_size() != size:
            self._veil = pygame.Surface(size, pygame.SRCALPHA)
            self._veil.fill(self.VEIL)
        return self._veil

    def _push(self, scene: Scene) -> None:
        self._stack.append(scene)
        scene.enter()
        self.set_ui_scale(self.game.ui_scale)
