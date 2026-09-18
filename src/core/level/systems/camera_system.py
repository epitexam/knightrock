"""CameraSystem: camera-follow tail of the level pipeline (audit F1.2, Phase 3 #2).

Runs after the simulation stages, once every entity has integrated: the
camera follows the living player's final position for the tick.  A dead
player freezes the camera, exactly like the pre-facade ``Level.update``.
"""

from src.core.rendering.camera import Camera
from src.entities.player import Player

__all__ = ["CameraSystem"]


class CameraSystem:
    """Follow the living player with the level camera."""

    def __init__(self, camera: Camera) -> None:
        self.camera = camera

    def process(self, delta_time: float, player: Player) -> None:
        """Track the player when alive; freeze the frame when dead."""
        if not player.is_dead:
            self.camera.follow(player.hitbox, delta_time)

    def add_trauma(self, amount: float) -> None:
        """Feed impact shake to the camera (heavy launches shake the most)."""
        self.camera.add_trauma(amount)
