"""CameraSystem: camera-follow tail of the level pipeline (audit F1.2, Phase 3 #2).

Runs after the simulation stages, once every entity has integrated: the
camera follows the living player's final position for the tick.  A dead
player freezes the framing, exactly like the pre-facade ``Level.update``
-- but the impact shake keeps decaying, since freezing it would hold the
whole frame displaced for the whole death window.
"""

from src.core.rendering.camera import Camera
from src.entities.player import Player

__all__ = ["CameraSystem"]


class CameraSystem:
    """Follow the living player with the level camera."""

    def __init__(self, camera: Camera) -> None:
        self.camera = camera

    def process(self, delta_time: float, player: Player) -> None:
        """Track the player when alive; freeze the framing when dead, not the shake.

        Freezing the frame is deliberate and only about the framing: a dead body
        does not move, so there is nothing to follow. The shake is a separate
        concern with its own lifetime -- it must age on every tick, or the
        trauma the killing blow just fed stays frozen at full amplitude and the
        whole frame sits displaced for the length of the death window.
        """
        if player.is_dead:
            self.camera.advance_shake(delta_time)
        else:
            self.camera.follow(player.hitbox, delta_time)

    def add_trauma(self, amount: float) -> None:
        """Feed impact shake to the camera (heavy launches shake the most)."""
        self.camera.add_trauma(amount)
