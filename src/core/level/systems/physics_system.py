"""PhysicsSystem: entity integration stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/physics_system``).
"""

from typing import Any

from src.core.fx import (
    spawn_dash_dust,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_sweat_drops,
)
from src.core.settings import DashDust, Dust, FxDizzy, Sweat
from src.core.sprite_groups import SpriteGroups
from src.physics.movement import apply_moving_platform

__all__ = ["PhysicsSystem"]


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


def _is_dashing(entity: object) -> bool:
    """Whether the entity is currently in a dash state."""
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
        # Per-entity sweat emission countdown (droplets every SPAWN_EVERY).
        self._sweat_timers: dict[int, float] = {}
        # Per-entity dash trail countdown; also marks that the burst is spent.
        self._dash_timers: dict[int, float] = {}
        # Per-entity dizzy swirl emission countdown.
        self._dizzy_timers: dict[int, float] = {}
        # Per-entity dizzy star emission countdown.
        self._dizzy_star_timers: dict[int, float] = {}

    def process(self, delta_time: float) -> None:
        """Apply the platform carry, then integrate entities and effects."""
        for entity in self.groups.entity_sprites:
            apply_moving_platform(entity, self.groups.moving_platforms)
        self.groups.entity_sprites.update(delta_time)
        self._spawn_impact_fx(delta_time)
        self.groups.fx_sprites.update(delta_time)

    def _spawn_impact_fx(self, delta_time: float) -> None:
        """Turn movement and status into render-only FX.

        The puffs join ``fx_sprites`` (no collision, never snapshotted):
        landing fans use the fall speed ``Entity`` recorded on the landing
        tick, a dashing entity trails dust off its trailing edge, a fully
        drained dasher sweats droplets every ``Sweat.SPAWN_EVERY`` seconds
        while its penalty runs, and a dizzy entity spawns purple vortex swirls
        every ``FxDizzy.VORTEX_SPAWN_EVERY`` seconds.

        The dash carries one mark, not five. It once had a backward fan of
        dust, a ground ring, a speed line every tick, wind lines on a cadence
        and a comet, all on the same 80ms event, and the frame they produced
        was a white cloud under a stretched rectangle with a hoop around it.
        Four of the five marked the path the renderer's afterimages already
        photograph. A trail is the one that was missing, and it is the only
        one that said the fighter had displaced anything.

        The landing hint is consumed here so a dead-or-frozen entity cannot
        re-emit it on later ticks; every spawner is its own particle-budget
        guard, so this system never has to know the cap.
        """
        sweating_ids: set[int] = set()
        dashing_ids: set[int] = set()
        dizzy_ids: set[int] = set()
        for entity in self.groups.entity_sprites:
            self._process_entity_fx(entity, delta_time, sweating_ids, dashing_ids, dizzy_ids)
        self._cleanup_timers(sweating_ids, dashing_ids, dizzy_ids)

    def _process_entity_fx(
        self,
        entity: Any,
        delta_time: float,
        sweating_ids: set[int],
        dashing_ids: set[int],
        dizzy_ids: set[int],
    ) -> None:
        impact = float(getattr(entity, "landed_impact", 0.0) or 0.0)
        if impact >= Dust.MIN_FALL_SPEED:
            spawn_landing_dust(self.groups.fx_sprites, entity, impact)
            spawn_impact_decal(self.groups.fx_sprites, entity, impact)
        if _in_dash_penalty(entity):
            sweating_ids.add(id(entity))
            self._tick_sweat(entity, delta_time)
        if _is_dashing(entity):
            dashing_ids.add(id(entity))
            self._tick_dash_dust(entity, delta_time)
        if _is_dizzy(entity):
            dizzy_ids.add(id(entity))
            self._tick_dizzy_vortex(entity, delta_time)
            self._tick_dizzy_stars(entity, delta_time)
        if hasattr(entity, "landed_impact"):
            entity.landed_impact = 0.0

    def _cleanup_timers(
        self, sweating_ids: set[int], dashing_ids: set[int], dizzy_ids: set[int]
    ) -> None:
        # Drop timers of entities no longer sweating, dashing or dizzy (or
        # gone) so stale ids cannot leak into a later entity reusing the same
        # memory address.
        self._sweat_timers = {
            entity_id: timer
            for entity_id, timer in self._sweat_timers.items()
            if entity_id in sweating_ids
        }
        # The dash timer is also how the burst is remembered as spent, so
        # clearing it on the way out of a dash is what arms the next one.
        self._dash_timers = {
            entity_id: timer
            for entity_id, timer in self._dash_timers.items()
            if entity_id in dashing_ids
        }
        # Clean up dizzy timers for entities that are no longer dizzy.
        self._dizzy_timers = {
            entity_id: timer
            for entity_id, timer in self._dizzy_timers.items()
            if entity_id in dizzy_ids
        }
        self._dizzy_star_timers = {
            entity_id: timer
            for entity_id, timer in self._dizzy_star_timers.items()
            if entity_id in dizzy_ids
        }

    def _tick_dash_dust(self, entity: object, delta_time: float) -> None:
        """Emit the dash trail: a burst on the first tick, puffs after that.

        Which tick is the first is not asked for and needs no flag. A timer
        that is absent means no dash has been seen for this entity, so the
        absence is the signal, and ``_cleanup_timers`` removes it again the
        moment the entity leaves the dash state. That is why the trail costs
        the simulation nothing: no new entity attribute, and no reader of
        ``PlayerDashState._dash_started_this_frame``, which the gameplay loop
        already owns for the dash's camera shake.

        A dash is 0.08s long, which at 60Hz is five ticks and one burst -- so
        the cadence is what draws the ribbon and the burst is the shove at the
        front of it.
        """
        entity_id = id(entity)
        timer = self._dash_timers.get(entity_id)
        if timer is None:
            spawn_dash_dust(self.groups.fx_sprites, entity, burst=True)
            self._dash_timers[entity_id] = DashDust.SPAWN_EVERY
            return
        timer -= delta_time
        if timer <= 0.0:
            spawn_dash_dust(self.groups.fx_sprites, entity)
            timer = DashDust.SPAWN_EVERY
        self._dash_timers[entity_id] = timer

    def _tick_sweat(self, entity: object, delta_time: float) -> None:
        """Emit sweat droplets on the ``Sweat.SPAWN_EVERY`` cadence."""
        timer = self._sweat_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_sweat_drops(self.groups.fx_sprites, entity)
            timer = Sweat.SPAWN_EVERY
        self._sweat_timers[id(entity)] = timer

    def _tick_dizzy_vortex(self, entity: object, delta_time: float) -> None:
        """Emit purple vortex swirls on the ``FxDizzy.VORTEX_SPAWN_EVERY`` cadence."""
        timer = self._dizzy_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_dizzy_vortex(self.groups.fx_sprites, entity)
            timer = FxDizzy.VORTEX_SPAWN_EVERY
        self._dizzy_timers[id(entity)] = timer

    def _tick_dizzy_stars(self, entity: object, delta_time: float) -> None:
        """Emit circling stars on the ``FxDizzy.STAR_SPAWN_EVERY`` cadence."""
        timer = self._dizzy_star_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_dizzy_stars(self.groups.fx_sprites, entity, FxDizzy.STAR_BATCH, FxDizzy.STAR_TTL)
            timer = FxDizzy.STAR_SPAWN_EVERY
        self._dizzy_star_timers[id(entity)] = timer
