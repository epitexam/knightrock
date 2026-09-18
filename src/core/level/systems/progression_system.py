"""ProgressionSystem: exit detection for the level (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/progression_system``).

The system owns the mutable ``exit_reached`` flag that used to live on
``Level``; the level re-exposes it as a property so the scene layer, the
rollback snapshots and the tests keep their access path.
"""

import pygame

from src.entities.player import Player

__all__ = ["ProgressionSystem"]


class ProgressionSystem:
    """Flag the level as completed when a living player touches the exit.

    ``pygame.sprite.spritecollide`` is resolved through the ``pygame.sprite``
    module at call time — never imported directly — so tests can monkeypatch
    it and observe the exit probe.
    """

    def __init__(self, exit_sprites: pygame.sprite.Group) -> None:
        self.exit_sprites = exit_sprites
        self.exit_reached = False

    def process(self, player: Player) -> None:
        """Set ``exit_reached`` for every tick a living player touches the exit."""
        if player.is_dead:
            return
        if pygame.sprite.spritecollide(player, self.exit_sprites, False):
            self.exit_reached = True
