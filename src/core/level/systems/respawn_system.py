"""PlayerRespawnSystem: respawn delay, death tally and death border (audit F1.2).

Extracted from ``Level.update`` (audit §4: respawn/progression stages).
"""

from collections.abc import Iterable
from typing import Any

from src.core.level.level_data import LevelData
from src.core.settings import Respawn
from src.entities.player import Player

__all__ = ["PlayerRespawnSystem"]


class PlayerRespawnSystem:
    """Own the respawn countdown, the death tally and the out-of-bounds rule.

    The system owns the mutable state (``respawn_timer``, ``deaths``) that
    used to live on ``Level``; the level re-exposes both as properties so the
    scene layer (``GameplayScene``), the rollback snapshots and the tests keep
    their access path.
    """

    def __init__(self, player: Player, level_data: LevelData) -> None:
        self.player = player
        self.level_data = level_data
        self.respawn_timer = 0.0
        self.deaths = 0

    def process(self, delta_time: float, entity_sprites: Iterable[Any] | None = None) -> None:
        """Advance the death/respawn state by one simulation tick.

        Fallen non-player entities below the death border die too: without
        this, a launched enemy over a pit falls forever, locked in its
        knockback state with its velocity intact (infinite knockback).
        They are reaped by ``remove_dead_entities`` on the following tick.
        """
        if self.player.is_dead:
            self.respawn_timer += delta_time
            if self.respawn_timer >= Respawn.DELAY_S:
                self.player.respawn()
                self.respawn_timer = 0.0
                self.deaths += 1
        else:
            self.respawn_timer = 0.0

        self._check_death_border()
        if entity_sprites is not None:
            self._reap_fallen_entities(entity_sprites)

    def _check_death_border(self) -> None:
        """Kill the player when it falls below the level's death border (BUG-06).

        A non-positive border disables the rule, which is how levels without
        a pit opt out (``death_border_bottom = 0.0``).
        """
        border = self.level_data.config.death_border_bottom
        if border > 0 and self.player.hitbox.top > border:
            self.player.die()

    def _reap_fallen_entities(self, entity_sprites: Iterable[Any]) -> None:
        """Kill live non-player entities below the death border."""
        border = self.level_data.config.death_border_bottom
        if border <= 0:
            return
        for entity in tuple(entity_sprites):
            if entity is self.player or getattr(entity, "is_dead", False):
                continue
            hitbox = getattr(entity, "hitbox", None)
            if hitbox is not None and hitbox.top > border:
                entity.die()
