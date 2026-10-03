"""CameraSystem: camera-follow tail of the level pipeline (audit F1.2, Phase 3 #2).

Runs after the simulation stages, once every entity has integrated: the
camera follows the living player's final position for the tick.  A dead
player freezes the framing, exactly like the pre-facade ``Level.update``
-- but holding is not the same as skipping, so the work a tick owes the
camera is delegated to :meth:`Camera.hold` rather than dropped: the impact
shake keeps decaying, and the pending-tick interpolation the last
``follow`` left behind is settled instead of left standing.
"""

from src.core.rendering.camera import Camera
from src.entities.player import Player

__all__ = ["CameraSystem"]


class CameraSystem:
    """Follow the living player with the level camera."""

    def __init__(self, camera: Camera) -> None:
        self.camera = camera

    def process(self, delta_time: float, player: Player) -> None:
        """Track the player when alive; hold the framing still when dead.

        Holding is deliberate and only about the framing: a dead body does not
        move, so there is nothing to follow. Everything else a tick owes the
        camera still has to happen, which is what makes the dead branch a
        :meth:`Camera.hold` rather than an early return -- see that method for
        what dropping the tick used to cost.
        """
        if player.is_dead:
            self.camera.hold(delta_time)
        else:
            self.camera.follow(player.hitbox, delta_time)

    def add_trauma(self, amount: float) -> None:
        """Feed impact shake to the camera (heavy launches shake the most)."""
        self.camera.add_trauma(amount)
