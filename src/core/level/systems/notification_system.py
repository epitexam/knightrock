"""NotificationSystem: event-bus tail of the level pipeline (audit F1.2, Phase 3 #2).

Runs after respawn/progression so the bus observes the tick's final state.
Emissions are notifications only — subscribers must never mutate the
simulation (Phase 2 #5).  The one-shot latches (``player_dead_emitted`` /
``completed_emitted``) live here, next to the rule that reads them, and are
captured by the rollback snapshots so a rewind re-arms them.
"""

from src.application.events import EventBus, LevelCompleted, PlayerDied
from src.core.level.level_data import LevelData
from src.entities.player import Player

__all__ = ["NotificationSystem"]


class NotificationSystem:
    """Publish ``PlayerDied``/``LevelCompleted`` once per occurrence."""

    def __init__(self, events: EventBus | None, level_id: int, level_data: LevelData) -> None:
        self.events = events
        self.level_id = level_id
        self.level_data = level_data
        self.player_dead_emitted = False
        self.completed_emitted = False

    def process(self, player: Player, *, deaths: int, exit_reached: bool) -> None:
        """Emit bus events for the app layer (never mutates simulation)."""
        if self.events is None:
            return

        if player.is_dead and not self.player_dead_emitted:
            self.player_dead_emitted = True
            self.events.emit(PlayerDied(entity_id=player.id, deaths=deaths))
        elif not player.is_dead:
            self.player_dead_emitted = False

        if exit_reached and not self.completed_emitted:
            self.completed_emitted = True
            self.events.emit(
                LevelCompleted(
                    level_id=self.level_id,
                    unlock_level_id=self.level_data.config.level_unlock,
                )
            )
