"""Publish the animator's surface as the sprite's picture, out of ``Entity``.

The state-to-art mapping stays where it belongs -- each fighter's
``_animation_name`` override. This component only ticks the animator and
copies its scaled surface to the entity; it owns no game state.
"""

from __future__ import annotations

from typing import Protocol

import pygame

from src.core.animation.animator import Animator


class AnimationOwner(Protocol):
    """What the publisher reads and writes on its fighter."""

    animator: Animator | None
    rect: pygame.FRect
    facing_right: bool
    image: pygame.Surface

    def _animation_name(self) -> str | None: ...


class AnimationPublisher:
    """Tick the optional animator and publish its display surface."""

    def __init__(self, owner: AnimationOwner) -> None:
        self.owner = owner

    def update(self, delta_time: float) -> None:
        """Advance the animation and blit its current frame onto the sprite.

        The display surface is scaled to the sprite rect so the physics rect
        stays authoritative; entities without an animator keep their flat
        colored surface.
        """
        owner = self.owner
        if owner.animator is None:
            return
        name = owner._animation_name()
        if name is not None:
            owner.animator.play(name)
        owner.animator.update(delta_time)
        surface = owner.animator.surface(
            (round(owner.rect.width), round(owner.rect.height)),
            owner.facing_right,
        )
        if surface is not None:
            owner.image = surface
