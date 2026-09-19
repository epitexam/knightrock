"""PhysicsSystem: entity integration stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/physics_system``).
"""

from src.core.fx import (
    DIZZY_VORTEX_SPAWN_EVERY,
    MAX_FX_SPRITES,
    spawn_dash_burst,
    spawn_dash_streak,
    spawn_dizzy_vortex,
    spawn_landing_dust,
    spawn_sweat_drops,
)
from src.core.settings import Dust, Sweat
from src.core.sprite_groups import SpriteGroups
from src.physics.movement import apply_moving_platform

__all__ = ["PhysicsSystem"]


def _is_dashing(entity: object) -> bool:
    """Whether the entity is currently in its dash state (dash streaks)."""
    state_machine = getattr(entity, "state_machine", None)
    return getattr(state_machine, "current_state_name", None) == "dash"


def _in_dash_penalty(entity: object) -> bool:
    """Whether the entity drained every dash charge and sits out the penalty."""
    dash = getattr(entity, "dash", None)
    return (
        dash is not None
        and getattr(dash, "charges", 1) <= 0
        and getattr(dash, "penalty_timer", 0.0) > 0.0
    )


def _is_dizzy(entity: object) -> bool:
    """Whether the entity is currently in a dizzy state."""
    state_machine = getattr(entity, "state_machine", None)
    current = getattr(state_machine, "current_state_name", None)
    return current is not None and "dizzy" in current


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
        # Per-entity sweat emission countdown (droplets every SPAWN_EVERY).
        self._sweat_timers: dict[int, float] = {}
        # Per-entity dizzy vortex emission countdown.
        self._dizzy_timers: dict[int, float] = {}

    def process(self, delta_time: float) -> None:
        """Apply the platform carry, then integrate entities and effects."""
        for entity in self.groups.entity_sprites:
            apply_moving_platform(entity, self.groups.moving_platforms)
        self.groups.entity_sprites.update(delta_time)
        self._spawn_impact_fx(delta_time)
        self.groups.fx_sprites.update(delta_time)

    def _spawn_impact_fx(self, delta_time: float) -> None:
        """Turn hard landings, dashes, dash penalties, and dizzy state into render-only FX.

        The puffs join ``fx_sprites`` (no collision, never snapshotted):
        landing fans use the fall speed ``Entity`` recorded on the landing
        tick, dash streaks trail dashing entities one puff per tick, a
        burst kicks out once when a dash starts, a fully drained dasher
        sweats droplets every ``Sweat.SPAWN_EVERY`` seconds while its
        penalty runs, and a dizzy entity spawns purple vortex swirls every
        ``DIZZY_VORTEX_SPAWN_EVERY`` seconds. The landing hint is consumed
        here so a dead-or-frozen entity cannot re-emit it on later ticks;
        spawning stops past ``MAX_FX_SPRITES`` as a particle-budget guard.
        """
        dashing_ids: set[int] = set()
        sweating_ids: set[int] = set()
        dizzy_ids: set[int] = set()
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
            if _in_dash_penalty(entity):
                sweating_ids.add(id(entity))
                self._tick_sweat(entity, delta_time)
            if _is_dizzy(entity):
                dizzy_ids.add(id(entity))
                self._tick_dizzy_vortex(entity, delta_time)
            if hasattr(entity, "landed_impact"):
                entity.landed_impact = 0.0
        self._dashing_ids = dashing_ids
        # Drop timers of entities no longer sweating (or gone) so stale ids
        # cannot leak into a later entity reusing the same memory address.
        self._sweat_timers = {
            entity_id: timer
            for entity_id, timer in self._sweat_timers.items()
            if entity_id in sweating_ids
        }
        # Clean up dizzy timers for entities that are no longer dizzy.
        self._dizzy_timers = {
            entity_id: timer
            for entity_id, timer in self._dizzy_timers.items()
            if entity_id in dizzy_ids
        }

    def _tick_sweat(self, entity: object, delta_time: float) -> None:
        """Emit sweat droplets on the ``Sweat.SPAWN_EVERY`` cadence."""
        timer = self._sweat_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            # The budget guard runs outside the shared impact check so a
            # full fx group delays drops instead of dropping the cadence.
            if len(self.groups.fx_sprites) < MAX_FX_SPRITES:
                spawn_sweat_drops(self.groups.fx_sprites, entity)
            timer = Sweat.SPAWN_EVERY
        self._sweat_timers[id(entity)] = timer

    def _tick_dizzy_vortex(self, entity: object, delta_time: float) -> None:
        """Emit purple vortex swirls on the ``DIZZY_VORTEX_SPAWN_EVERY`` cadence."""
        timer = self._dizzy_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            if len(self.groups.fx_sprites) < MAX_FX_SPRITES:
                spawn_dizzy_vortex(self.groups.fx_sprites, entity)
            timer = DIZZY_VORTEX_SPAWN_EVERY
        self._dizzy_timers[id(entity)] = timer
