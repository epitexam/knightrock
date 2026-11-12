"""FeedbackSystem: what the player sees and feels of a tick, decided in one place.

Dust, sweat, dizzy swirls, guard rings and camera shake are render-only: they
never touch the simulation and are never snapshotted. They used to be decided
in three places -- ``PhysicsSystem`` (movement dust), ``GameplayLoop`` (guard
rings, impact and dash shake) and flags read by both -- and a fourth kind of
feedback, a combat sound, would have had no obvious home (audit §3.5). This
system owns all of it.

It has two entry points because the facts arrive at two moments of the tick,
and each is called exactly where its effects used to be produced, so nothing a
player sees moved: :meth:`after_movement` right after the entities moved,
:meth:`after_combat` once melee and projectiles are resolved.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from src.core.fx import (
    spawn_dash_dust,
    spawn_dash_grains,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_footstep_dust,
    spawn_footstep_grains,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_landing_grains,
    spawn_shatter_arc,
    spawn_sweat_drops,
)
from src.core.fx.tuning import DashDust, Dust, FootstepDust, FootstepTier, FxDizzy, Sweat
from src.core.level.systems.contact_system import GuardEvent
from src.core.settings import CameraShake
from src.core.settings import Combat as CombatSettings
from src.core.settings import Guard as GuardSettings
from src.core.sprite_groups import SpriteGroups
from src.entities.entity import Entity
from src.states import state_names

if TYPE_CHECKING:
    from src.core.level.systems.camera_system import CameraSystem
    from src.entities.player import Player

__all__ = ["FeedbackSystem"]


@dataclass
class _StepClock:
    """How far a fighter has walked since its last footstep, and which foot.

    Two fields and both of them are load-bearing. The distance is what paces
    the marks; the parity of the step count is which of the two feet laid this
    one, which is why the spawner is handed a bool rather than asked to keep
    its own alternation.

    Both live here rather than on the entity, for the reason the trail's timer
    does: FX state on a thing the simulation snapshots is the one coupling this
    module is supposed to not have.
    """

    walked: float = 0.0
    cooldown: float = 0.0
    foot: bool = False


def _in_dash_penalty(entity: Entity) -> bool:
    """Whether the entity drained every dash charge and sits out the penalty."""
    dash = entity.dash
    return dash is not None and dash.charges <= 0 and dash.penalty_timer > 0.0


def _is_dizzy(entity: Entity) -> bool:
    """Whether the entity is currently in a dizzy state."""
    current = entity.state_machine.current_state_name
    return current is not None and state_names.DIZZY in current


def _is_dashing(entity: Entity) -> bool:
    """Whether the entity is currently in a dash state."""
    return entity.state_machine.current_state_name == state_names.DASH


def _is_grounded(entity: Entity) -> bool:
    """Whether the entity is standing on a floor."""
    return bool(entity.on_surface.get("floor", False))


def _ground_speed(entity: Entity) -> float:
    """How fast the entity is rolling along the ground, in px/s."""
    return abs(float(entity.velocity.x))


def _footstep_tier(entity: Entity) -> FootstepTier | None:
    """The dust this entity's ground tier gets, or ``None`` if it gets none.

    Three outcomes and all three are real. A tier in ``FootstepDust.TIER`` gets
    its row. A tier in ``FootstepDust.SILENT`` -- ``walk_slow``, the one a
    fighter reaches under a raised guard -- gets ``None``, and that is the
    setting rather than a fallback: he is holding still as far as the ground is
    concerned. Anything else gets the default row, so an enemy patrolling marks
    the floor and the rule stays "a fighter rolling on a floor marks it" with the
    tiers as the refinement rather than the other way round.

    The three have to be told apart, because folding the second into the first
    is how an enemy chasing you ends up marking the floor at a walker's
    cadence: not in the table means two different things at once.

    Read from the state name rather than from the speed, and the state machine is
    the right thing to ask because it has already made this decision, with
    hysteresis so it does not flicker while acceleration crosses a boundary.
    Re-deriving it here from ``|velocity.x|`` would be a second classifier with
    none of that, and the flicker at this cadence is a scuff blinking under a
    fighter who is barely moving.
    """
    name = entity.state_machine.current_state_name
    if name is None:
        return FootstepDust.DEFAULT_TIER
    if name in FootstepDust.SILENT:
        return None
    return FootstepDust.TIER.get(name, FootstepDust.DEFAULT_TIER)


class FeedbackSystem:
    """Turn the facts of a tick into FX and camera shake."""

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
        # Per-entity walking cadence: distance since the last footstep, and
        # which foot threw it.
        self._step_clocks: dict[int, _StepClock] = {}

    def after_movement(self, delta_time: float) -> None:
        """Movement FX for this tick's moves, then advance every FX sprite."""
        self._spawn_movement_fx(delta_time)
        self.groups.fx_sprites.update(delta_time)

    def after_combat(
        self,
        impact: float,
        guard_events: list[GuardEvent],
        player: Player,
        camera: CameraSystem,
    ) -> None:
        """Shake for a heavy melee impact, ring and shake for guard outcomes, shake for a dash.

        ``impact`` is the strongest melee knockback this tick; ``guard_events``
        are this tick's guard, parry, break and stun outcomes, already drained
        from the systems that produced them.
        """
        if impact >= CombatSettings.HEAVY_KNOCKBACK_THRESHOLD:
            camera.add_trauma(impact / CameraShake.HEAVY_DIV)
        if guard_events:
            trauma = 0.0
            for event in guard_events:
                trauma = max(trauma, _trauma_for(event))
                _spawn_guard_fx(event, self.groups.fx_sprites)
            if trauma > 0.0:
                camera.add_trauma(trauma)
        if player.dash_started_this_frame:
            player.dash_started_this_frame = False
            camera.add_trauma(GuardSettings.PARRY_TRAUMA * 0.4)

    def _spawn_movement_fx(self, delta_time: float) -> None:
        """Turn movement and status into render-only FX.

        The puffs join ``fx_sprites`` (no collision, never snapshotted):
        landing fans use the fall speed ``Entity`` recorded on the landing
        tick, a dashing entity trails dust off its trailing edge while it has
        a floor under it, a fighter rolling on a floor throws a scuff every
        ``FootstepDust.TIER`` stride its ground tier asks for, a fully drained
        dasher sweats droplets every ``Sweat.SPAWN_EVERY`` seconds while its
        penalty runs, and a dizzy entity spawns purple vortex swirls every
        ``FxDizzy.VORTEX_SPAWN_EVERY`` seconds.

        The dash carries one mark, not five. It once had a backward fan of
        dust, a ground ring, a speed line every tick, wind lines on a cadence
        and a comet, all on the same 80ms event, and the frame they produced
        was a white cloud under a stretched rectangle with a hoop around it.
        Four of the five marked the path the renderer's afterimages already
        photograph. A trail is the one that was missing, and it is the only
        one that said the fighter had displaced anything.

        The footstep is the mark that keeps the dash the fast one. Its
        cadence is per locomotion tier and read by name -- a ``walk`` marks the
        floor every forty pixels and a ``run`` every fourteen, under a ceiling
        that stops the run becoming the trail -- and a tier that is absent from
        the table, which is what ``walk_slow`` is, marks nothing at all. All of
        that is in :data:`FootstepDust.TIER`; what belongs here is that this
        system is what asks, and that it asks once per tick for every entity
        rather than only for the one that happens to be the player.

        The landing hint is consumed here so a dead-or-frozen entity cannot
        re-emit it on later ticks; every spawner is its own particle-budget
        guard, so this system never has to know the cap.
        """
        sweating_ids: set[int] = set()
        dashing_ids: set[int] = set()
        dizzy_ids: set[int] = set()
        stepping_ids: set[int] = set()
        for entity in self.groups.entity_sprites:
            self._process_entity_fx(
                entity, delta_time, sweating_ids, dashing_ids, dizzy_ids, stepping_ids
            )
        self._cleanup_timers(sweating_ids, dashing_ids, dizzy_ids, stepping_ids)

    def _process_entity_fx(
        self,
        entity: Entity,
        delta_time: float,
        sweating_ids: set[int],
        dashing_ids: set[int],
        dizzy_ids: set[int],
        stepping_ids: set[int],
    ) -> None:
        impact = entity.render_hints.landed_impact
        landed = impact >= Dust.MIN_FALL_SPEED
        if landed:
            spawn_landing_dust(self.groups.fx_sprites, entity, impact)
            spawn_landing_grains(self.groups.fx_sprites, entity, impact)
            spawn_impact_decal(self.groups.fx_sprites, entity, impact)
        if _in_dash_penalty(entity):
            sweating_ids.add(id(entity))
            self._tick_sweat(entity, delta_time)
        dashing = _is_dashing(entity)
        if dashing:
            dashing_ids.add(id(entity))
            self._tick_dash_dust(entity, delta_time)
        if _is_dizzy(entity):
            dizzy_ids.add(id(entity))
            self._tick_dizzy_vortex(entity, delta_time)
            self._tick_dizzy_stars(entity, delta_time)
        # A tier of ``None`` is the silent one, not a missing one: the gate below
        # is what turns ``walk_slow`` into no dust at all.
        tier = _footstep_tier(entity)
        if (
            tier is not None
            and _is_grounded(entity)
            and _ground_speed(entity) >= (FootstepDust.MIN_SPEED)
        ):
            stepping_ids.add(id(entity))
            if not dashing and not landed:
                self._tick_footsteps(entity, delta_time, tier)
        entity.render_hints.landed_impact = 0.0

    def _cleanup_timers(
        self,
        sweating_ids: set[int],
        dashing_ids: set[int],
        dizzy_ids: set[int],
        stepping_ids: set[int],
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
        # The clock is dropped with the others, so an entity that stops walking
        # starts its next walk from a full stride rather than from whatever
        # fraction of one it had when it stopped -- a mark laid three pixels
        # into a step reads as a stutter when the fighter sets off again.
        self._step_clocks = {
            entity_id: clock
            for entity_id, clock in self._step_clocks.items()
            if entity_id in stepping_ids
        }

    def _tick_dash_dust(self, entity: Entity, delta_time: float) -> None:
        """Emit the dash trail: a burst on the first tick, puffs after that.

        Which tick is the first is not asked for and needs no flag. A timer
        that is absent means no dash has been seen for this entity, so the
        absence is the signal, and ``_cleanup_timers`` removes it again the
        moment the entity leaves the dash state. That is why the trail costs
        the simulation nothing: no new entity attribute, and no reader of
        ``Player.dash_started_this_frame``, which the gameplay
        loop already owns for the dash's camera shake.

        A dash is 0.08s long, which at 60Hz is five ticks and one burst -- so
        the cadence is what draws the ribbon and the burst is the shove at the
        front of it.

        Only on the floor. Dust needs something to come off, and a trail
        hanging in open air at the height of a mid-dash jump reads as the
        fighter smearing the screen rather than as ground he pushed away --
        and it is drawn over every one of those air dashes, which is where
        the eye finds it first.

        The burst belongs to the start of the dash, so a dash that began
        airborne spends it without spending the trail's only shove: the tick
        still arms the timer, and the landing that follows brings its own
        dust through the same fall speed the landing fan already reads.
        """
        entity_id = id(entity)
        timer = self._dash_timers.get(entity_id, DashDust.SPAWN_EVERY)
        first = entity_id not in self._dash_timers
        if not first:
            timer -= delta_time
        if (first or timer <= 0.0) and _is_grounded(entity):
            spawn_dash_dust(self.groups.fx_sprites, entity, burst=first)
            spawn_dash_grains(self.groups.fx_sprites, entity, burst=first)
        self._dash_timers[entity_id] = DashDust.SPAWN_EVERY if timer <= 0.0 else timer

    def _tick_footsteps(self, entity: Entity, delta_time: float, tier: FootstepTier) -> None:
        """Throw a scuff every ``tier.step_distance`` pixels of ground covered.

        The tier is resolved by the caller and arrives here already decided, so
        this method paces one comb and knows nothing about which gait it is
        pacing. That split is what makes the table in :data:`FootstepDust.TIER`
        the single place the cadences live: a walk and a run differ by the row
        they were handed, not by a branch in here.

        Paced by distance and not by time, so the marks come out evenly spaced
        along the ground. A time-paced comb would space them by the stride, which
        puts the slow tiers' marks closer together and reads as clustering rather
        than as walking.

        Two things bound it, and both are read rather than recomputed.
        ``MIN_SPEED`` is applied by the caller, so a fighter settling under
        friction leaves nothing at all rather than a puff per frame.
        ``MIN_STEP_EVERY`` is the cooldown here, and it is the reason a run
        asks for fourteen pixels and gets thirty: at a full run the run row
        alone would fire twenty-five times a second, which is the dash's ribbon
        drawn small. Under the ceiling the run is a shade under twelve steps a
        second against the walk's five, which is the difference the eye reads.

        The leftover distance is carried rather than cleared. Zeroing it on each
        emission loses whatever the fighter covered since the last tick, which
        at 350 px/s and a 60Hz tick is nearly six pixels a step; the comb is
        then paced by the frame rate instead of by the stride, and it is exactly
        the kind of drift that shows up as a change of feel when the frame time
        moves.

        The dash is excluded by the caller, and so is the tick a landing fired
        on: both already lay marks at the feet, and a footstep under either of
        them is the plane saying the same thing twice on one frame.
        """
        clock = self._step_clocks.get(id(entity))
        if clock is None:
            clock = _StepClock()
        clock.walked += _ground_speed(entity) * delta_time
        clock.cooldown -= delta_time
        if clock.walked >= tier.step_distance and clock.cooldown <= 0.0:
            clock.walked -= tier.step_distance
            clock.cooldown = FootstepDust.MIN_STEP_EVERY
            clock.foot = not clock.foot
            spawn_footstep_dust(self.groups.fx_sprites, entity, foot=clock.foot, tier=tier)
            spawn_footstep_grains(self.groups.fx_sprites, entity, foot=clock.foot)
        self._step_clocks[id(entity)] = clock

    def _tick_sweat(self, entity: Entity, delta_time: float) -> None:
        """Emit sweat droplets on the ``Sweat.SPAWN_EVERY`` cadence."""
        timer = self._sweat_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_sweat_drops(self.groups.fx_sprites, entity)
            timer = Sweat.SPAWN_EVERY
        self._sweat_timers[id(entity)] = timer

    def _tick_dizzy_vortex(self, entity: Entity, delta_time: float) -> None:
        """Emit purple vortex swirls on the ``FxDizzy.VORTEX_SPAWN_EVERY`` cadence."""
        timer = self._dizzy_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_dizzy_vortex(self.groups.fx_sprites, entity)
            timer = FxDizzy.VORTEX_SPAWN_EVERY
        self._dizzy_timers[id(entity)] = timer

    def _tick_dizzy_stars(self, entity: Entity, delta_time: float) -> None:
        """Emit circling stars on the ``FxDizzy.STAR_SPAWN_EVERY`` cadence."""
        timer = self._dizzy_star_timers.get(id(entity), 0.0) - delta_time
        if timer <= 0.0:
            spawn_dizzy_stars(self.groups.fx_sprites, entity, FxDizzy.STAR_BATCH, FxDizzy.STAR_TTL)
            timer = FxDizzy.STAR_SPAWN_EVERY
        self._dizzy_star_timers[id(entity)] = timer


def _trauma_for(event: GuardEvent) -> float:
    """How hard a guard outcome shakes the camera."""
    if event.kind == "parry":
        return GuardSettings.PARRY_TRAUMA
    if event.kind in ("break", "stun"):
        return GuardSettings.BREAK_TRAUMA
    return GuardSettings.GUARD_TRAUMA


def _spawn_guard_fx(event: GuardEvent, fx_group: pygame.sprite.Group) -> None:
    """The ring of a guard or parry, the shards of a break; a stun has its own swirl."""
    if event.kind == "parry":
        spawn_guard_arc(fx_group, event.target, parried=True, contact=event.point)
    elif event.kind == "break":
        spawn_shatter_arc(fx_group, event.target, contact=event.point)
    elif event.kind == "guard":
        spawn_guard_arc(fx_group, event.target, contact=event.point)
