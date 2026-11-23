"""Publish the animator's surface as the sprite's picture, out of ``Entity``.

The state-to-art mapping stays where it belongs -- each fighter's
``_animation_name`` override. This component only ticks the animator and
copies its scaled surface to the entity; it owns no game state.
"""

from __future__ import annotations

from typing import Any, Protocol

import pygame

from src.combat.frame_data import PhaseState
from src.core.animation.animator import Animator

#: Clips whose pose belongs to the frame data, not to a wall-clock timer.
ATTACK_ANIMATIONS = frozenset({"attack", "air_attack"})


def _attack_frame(state: Any) -> int | None:
    """Phase-driven pose: windup / impact / follow-through."""
    if not state.is_attacking:
        return None
    sub_state = state.sub_state
    if sub_state is PhaseState.STARTUP:
        return 0
    if sub_state is PhaseState.ACTIVE:
        return 1
    if sub_state is PhaseState.RECOVERY:
        return 2
    return None


class AnimationOwner(Protocol):
    """What the publisher reads and writes on its fighter."""

    animator: Animator | None
    rect: pygame.FRect
    facing_right: bool
    image: pygame.Surface
    combat: Any
    _phase_driven_attack_art: bool

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
        combat = owner.combat
        state = combat.state
        frame = (
            _attack_frame(state)
            if (
                owner._phase_driven_attack_art
                and owner.animator.current in ATTACK_ANIMATIONS
                and state is not None
            )
            else None
        )
        if frame is None:
            owner.animator.update(delta_time)
        else:
            owner.animator.set_frame(frame)
        surface = owner.animator.surface(
            (round(owner.rect.width), round(owner.rect.height)),
            owner.facing_right,
        )
        if surface is not None:
            owner.image = surface
