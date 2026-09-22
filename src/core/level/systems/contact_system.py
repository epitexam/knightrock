"""Unified offensive-contact pipeline (P4.1).

Every offensive producer (melee, projectiles, hazards, contact damage)
emits :class:`OffensiveBox` records; this system runs the shared pipeline:

1. broadphase: ``EntityGrid.near`` over the emitted geometry (exhaustive
   over the target sequence when no grid is given);
2. narrowphase: P1 swept boxes vs P2 swept hurt zones (melee) or the
   discrete hurt/hit box (projectile, hazard, contact damage);
3. resolve: ``HitResolver`` for melee and projectile boxes, direct
   ``receive_damage`` for hazard/contact boxes (legacy semantics: no
   attacker ``CombatPort``, configurable ``interrupt``, no global hit-stop).

Producers keep their own bookkeeping (contact memory, single-hit release,
guard-event drain) through ``record_contact`` and the returned
:class:`ContactOutcome`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, cast

import pygame

from src.combat.combatant_protocol import Combatant, DamageResult
from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.core.settings import Combat as CombatSettings
from src.core.settings import Guard as GuardSettings
from src.entities.enemies.enemy import Enemy
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHashMember
from src.states.reaction_states import DIZZY_STATE

__all__ = [
    "CombatMetrics",
    "ContactOutcome",
    "ContactSystem",
    "GuardEvent",
    "OffensiveBox",
]


@dataclass(frozen=True)
class OffensiveBox:
    """One offensive contact emitted by a producer.

    ``box`` is the discrete geometry (projectile/hazard/contact hitboxes,
    primary melee box); ``swept`` is the whole-tick geometry used by the
    melee narrowphase. ``record_contact`` is called with the *target* once a
    hit landed, so a producer can remember it (and release itself).
    """

    box: pygame.FRect
    swept: tuple[pygame.FRect, ...]
    hit: HitProperties
    faction: str | None
    owner_id: str
    can_contact: Callable[[str], bool]
    kind: str = "melee"
    attacker: Any = None
    charge_mult: float = 1.0
    interrupt: bool = True
    stop_after_first: bool = False
    accept: Callable[[Combatant], bool] | None = None
    record_contact: Callable[[Combatant], None] | None = None


@dataclass
class CombatMetrics:
    """Per-tick counters exposed to tests and debug tooling."""

    pairs_tested: int = 0
    overlaps: int = 0
    contacts: int = 0


@dataclass(frozen=True)
class GuardEvent:
    """Render-only guard outcome drained once per tick by the game loop."""

    kind: str
    target: Combatant


@dataclass
class ContactOutcome:
    """Aggregated result of one :meth:`ContactSystem.resolve` pass."""

    metrics: CombatMetrics = field(default_factory=CombatMetrics)
    guard_events: list[GuardEvent] = field(default_factory=list)
    impact: float = 0.0
    hit_stop: float = 0.0



def _zone_vulnerable(zone_tags: tuple[str, ...], hit_tags: tuple[str, ...]) -> bool:
    """Whether a zone is hittable by a hit carrying ``hit_tags``.

    No hit carries tags yet (P3t1), so every zone is vulnerable by
    construction; the matcher goes live when hit tags land.
    """
    if not zone_tags or not hit_tags:
        return True
    return not set(zone_tags).intersection(hit_tags)


def _target_swept_zones(target: Combatant) -> tuple[pygame.FRect, ...]:
    """Per-zone swept rectangles (P2), single legacy box as fallback.

    ``getattr`` only bridges minimal hazard/contact stubs that never
    implement the zone surface; full combatants expose
    ``Combatant.swept_hurtboxes`` from the protocol.
    """
    swept = getattr(target, "swept_hurtboxes", None)
    if callable(swept):
        zones = tuple(swept())
        if zones:
            return zones
    return (target.hurtbox,)


def _zone_mults(target: Combatant) -> tuple[float, ...]:
    """Per-zone damage multipliers (P2), neutral 1.0 for legacy targets.

    Declared on ``Combatant.hurtbox_mult``; ``getattr`` remains for stubs.
    """
    mults = getattr(target, "hurtbox_mult", ())
    if isinstance(mults, tuple):
        return mults
    if callable(mults):
        return tuple(mults())
    return (1.0,)


def _zone_tags(target: Combatant) -> tuple[tuple[str, ...], ...]:
    """Per-zone reserved invulnerability tags (empty when unknown, P2).

    Declared on ``Combatant.hurtbox_tags``; ``getattr`` remains for stubs.
    """
    tags = getattr(target, "hurtbox_tags", ())
    return tuple(tuple(zone) for zone in tags)


def _is_valid_target(box: OffensiveBox, target: Combatant) -> bool:
    """Target eligibility: not the owner, alive, enemy faction, contact.

    Duck-typed on purpose: hazard/contact producers are exercised with
    minimal stubs (no ``id``/``faction``), like the legacy systems were.
    """
    if getattr(target, "is_dead", False):
        return False
    target_id = getattr(target, "id", "") or ""
    if target_id and target_id == box.owner_id:
        return False
    if box.faction is not None and getattr(target, "faction", None) == box.faction:
        return False
    return bool(box.can_contact(target_id))


def _eligible(box: OffensiveBox, target: Combatant) -> bool:
    """Broadphase + producer filter (``accept``) applied before narrowphase."""
    if not _is_valid_target(box, target):
        return False
    return box.accept is None or bool(box.accept(target))


def _first_vulnerable_zone(
    target: Combatant, swept_boxes: tuple[pygame.FRect, ...]
) -> tuple[int, float] | None:
    """First vulnerable zone touched by any swept attack box (P2).

    Zones are tested in order; the first zone overlapping a swept box wins.
    The hit-vs-hurt tag matcher stays inert until hits carry tags (P3t1+).
    """
    zones = _target_swept_zones(target)
    mults = _zone_mults(target)
    tags = _zone_tags(target)
    for index, zone in enumerate(zones):
        if not any(box.colliderect(zone) for box in swept_boxes):
            continue
        zone_tags = tags[index] if index < len(tags) else ()
        if not _zone_vulnerable(zone_tags, ()):
            continue
        return index, mults[index] if index < len(mults) else 1.0
    return None


class ContactSystem:
    """Shared broadphase, narrowphase and resolve for offensive producers.

    ``metrics`` reflects the last :meth:`resolve` call (fed back to the
    producer via :class:`ContactOutcome`); ``tick_metrics`` accumulates
    across every producer of the current tick and is what the debug panel
    reads. Call :meth:`begin_tick` once per simulation tick to reset the
    accumulator when a single instance is shared by all four producers.
    """

    def __init__(self) -> None:
        self.metrics: CombatMetrics = CombatMetrics()
        self.tick_metrics: CombatMetrics = CombatMetrics()
        self.impact: float = 0.0
        self.hit_stop: float = 0.0
        self.guard_events: list[GuardEvent] = []

    def begin_tick(self) -> None:
        """Reset the per-tick metric accumulator (shared-instance wiring)."""
        self.tick_metrics = CombatMetrics()

    def resolve(
        self,
        boxes: Iterable[OffensiveBox],
        targets: Iterable[Combatant],
        entity_grid: EntityGrid | None = None,
    ) -> ContactOutcome:
        """Run broadphase, narrowphase and resolve for every box.

        Boxes are processed in producer order and targets keep the order of
        the passed sequence (broadphase results are re-sorted to match), so
        hit resolution stays deterministic with and without a grid.
        """
        self.metrics = CombatMetrics()
        self.impact = 0.0
        self.hit_stop = 0.0
        self.guard_events = []
        target_list = tuple(targets)
        order = {id(target): index for index, target in enumerate(target_list)}

        for box in boxes:
            for target in self._candidates(box, target_list, order, entity_grid):
                self.metrics.pairs_tested += 1
                if box.kind == "melee":
                    contact = _first_vulnerable_zone(target, box.swept)
                    if contact is None:
                        continue
                    self.metrics.overlaps += 1
                    self._resolve_melee(box, target, contact[1])
                else:
                    target_box = (
                        target.hurtbox if box.kind == "projectile" else target.hitbox
                    )
                    if not box.box.colliderect(target_box):
                        continue
                    self.metrics.overlaps += 1
                    self._resolve_generic(box, target)
                if box.stop_after_first:
                    break

        self.tick_metrics.pairs_tested += self.metrics.pairs_tested
        self.tick_metrics.overlaps += self.metrics.overlaps
        self.tick_metrics.contacts += self.metrics.contacts
        return ContactOutcome(
            metrics=self.metrics,
            guard_events=self.guard_events,
            impact=self.impact,
            hit_stop=self.hit_stop,
        )

    def _candidates(
        self,
        box: OffensiveBox,
        targets: tuple[Combatant, ...],
        order: dict[int, int],
        entity_grid: EntityGrid | None,
    ) -> list[Combatant]:
        """Broadphase: grid prune around the emitted geometry, group order kept."""
        if entity_grid is None:
            return [target for target in targets if _eligible(box, target)]
        seen: set[int] = set()
        nearby: list[SpatialHashMember] = []
        for swept in box.swept:
            for member in entity_grid.near(swept):
                key = id(member)
                if key in seen or key not in order:
                    continue
                seen.add(key)
                nearby.append(member)
        candidates = cast(
            list[Combatant], sorted(nearby, key=lambda member: order[id(member)])
        )
        return [target for target in candidates if _eligible(box, target)]


    def _resolve_melee(
        self, box: OffensiveBox, target: Combatant, zone_mult: float
    ) -> None:
        """Melee hit: shared resolver, per-zone damage, global hit-stop."""
        result = HitResolver.resolve(
            attacker=box.attacker,
            target=target,
            hit=box.hit,
            charge_multiplier=box.charge_mult,
            zone_mult=zone_mult,
        )
        if not (result.applied or result.guarded):
            return
        if box.record_contact is not None:
            box.record_contact(target)
        self.metrics.contacts += 1
        if result.guarded:
            self._record_guard_event(result, target)
            if result.parried:
                self._maybe_parry_stun(box.attacker)
        magnitude = (
            pygame.math.Vector2(box.hit.knockback.power).length() * box.charge_mult
        )
        self.impact = max(self.impact, magnitude)
        duration = (
            CombatSettings.HITSTOP_BASE
            + box.hit.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR
            + magnitude * CombatSettings.HITSTOP_KNOCKBACK_FACTOR
        )
        if result.parried:
            duration = max(duration, GuardSettings.PARRY_HITSTOP)
        self.hit_stop = max(self.hit_stop, duration)
        # Real HP damage resets the consecutive-parry counter.
        if result.applied and hasattr(box.attacker, "parries_taken"):
            box.attacker.parries_taken = 0

    def _resolve_generic(self, box: OffensiveBox, target: Combatant) -> None:
        """Projectile/hazard/contact hit, keeping their legacy semantics.

        A projectile box resolves through ``HitResolver`` (shared armor,
        stagger and finisher rules) but never drives global hit-stop or
        camera impact, exactly like the pre-P4 projectile path. Hazard and
        contact boxes carry no attacking ``CombatPort``: they apply their
        configured damage and knockback directly.
        """
        if box.attacker is not None:
            result = HitResolver.resolve(
                attacker=box.attacker, target=target, hit=box.hit
            )
            if not (result.applied or result.guarded):
                return
            self._record_guard_event(result, target)
        else:
            target.receive_damage(
                amount=box.hit.damage,
                source_center_x=box.box.centerx,
                knockback=box.hit.knockback,
                interrupt=box.interrupt,
            )
        self.metrics.contacts += 1
        if box.record_contact is not None:
            box.record_contact(target)

    def _record_guard_event(self, result: DamageResult, target: Combatant) -> None:
        """Record guard/parry/break outcomes for event-draining systems."""
        if not result.guarded:
            return
        kind = "guard"
        if result.parried:
            kind = "parry"
        elif result.guard_broken:
            kind = "break"
        self.guard_events.append(GuardEvent(kind, target))

    def _maybe_parry_stun(self, attacker: Any) -> None:
        """Parry-stun: count the consecutive perfect parries an enemy took."""
        if not isinstance(attacker, Enemy):
            return
        attacker.parries_taken += 1
        if (
            attacker.parry_stun_threshold is not None
            and attacker.parries_taken >= attacker.parry_stun_threshold
        ):
            attacker.state_machine.change_state(
                DIZZY_STATE, force=True, duration=attacker.parry_stun_duration
            )
            attacker.parries_taken = 0
            self.guard_events.append(GuardEvent("stun", attacker))
