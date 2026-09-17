"""PhysicsSystem: entity integration stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/physics_system``).
"""

from src.core.fx import (
    MAX_FX_SPRITES,
    spawn_dash_burst,
    spawn_dash_streak,
    spawn_landing_dust,
)
from src.core.settings import Dust
from src.core.sprite_groups import SpriteGroups
from src.physics.movement import apply_moving_platform

__all__ = ["PhysicsSystem"]


def _is_dashing(entity: object) -> bool:
    """Whether the entity is currently in its dash state (dash streaks)."""
    state_machine = getattr(entity, "state_machine", None)
    return getattr(state_machine, "current_state_name", None) == "dash"


class PhysicsSystem:
    """Carry platform riders, then run the entity and effect update passes.

    Order matters: ``apply_moving_platform`` reads the *current* platform
    rectangles, so it must run after :class:`PlatformSystem` moved them and
    before the entities integrate their own movement for the tick.
    """

    def __init__(self, groups: SpriteGroups) -> None:
        self.groups = groups
        # Dashers seen on the previous tick (rising-edge burst, once per dash).
        self._dashing_ids: set[int] = set()

    def process(self, delta_time: float) -> None:
        """Apply the platform carry, then integrate entities and effects."""
        for entity in self.groups.entity_sprites:
            apply_moving_platform(entity, self.groups.moving_platforms)
        self.groups.entity_sprites.update(delta_time)
        self._spawn_impact_fx()
        self.groups.fx_sprites.update(delta_time)

    def _spawn_impact_fx(self) -> None:
        """Turn hard landings and dashes into render-only dust puffs.

        The puffs join ``fx_sprites`` (no collision, never snapshotted):
        landing fans use the fall speed ``Entity`` recorded on the landing
        tick, dash streaks trail dashing entities one puff per tick, and a
        burst kicks out once when a dash starts. The landing hint is
        consumed here so a dead-or-frozen entity cannot re-emit it on later
        ticks; spawning stops past ``MAX_FX_SPRITES`` as a particle-budget
        guard.
        """
        dashing_ids: set[int] = set()
        for entity in self.groups.entity_sprites:
            dashing = _is_dashing(entity)
            if dashing:
                dashing_ids.add(id(entity))
            if len(self.groups.fx_sprites) < MAX_FX_SPRITES:
                impact = float(getattr(entity, "landed_impact", 0.0) or 0.0)
                if impact >= Dust.MIN_FALL_SPEED:
                    spawn_landing_dust(self.groups.fx_sprites, entity)
                elif dashing:
                    if id(entity) not in self._dashing_ids:
                        spawn_dash_burst(self.groups.fx_sprites, entity)
                    else:
                        spawn_dash_streak(self.groups.fx_sprites, entity)
            if hasattr(entity, "landed_impact"):
                entity.landed_impact = 0.0
        self._dashing_ids = dashing_ids
