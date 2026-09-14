"""PlayerRespawnSystem: respawn delay, death tally and death border (audit F1.2).

Extracted from ``Level.update`` (audit §4: respawn/progression stages).
"""

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

    def process(self, delta_time: float) -> None:
        """Advance the death/respawn state by one simulation tick."""
        if self.player.is_dead:
            self.respawn_timer += delta_time
            if self.respawn_timer >= Respawn.DELAY_S:
                self.player.respawn()
                self.respawn_timer = 0.0
                self.deaths += 1
        else:
            self.respawn_timer = 0.0

        self._check_death_border()

    def _check_death_border(self) -> None:
        """Kill the player when it falls below the level's death border (BUG-06).

        A non-positive border disables the rule, which is how levels without
        a pit opt out (``death_border_bottom = 0.0``).
        """
        border = self.level_data.config.death_border_bottom
        if border > 0 and self.player.hitbox.top > border:
            self.player.die()
