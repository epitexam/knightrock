"""Unified offensive-contact pipeline (P4.1).

Every offensive producer (melee, projectiles, hazards, contact damage)
emits :class:`OffensiveBox` records; this system runs the shared pipeline:

1. broadphase: ``EntityGrid.near`` over the emitted geometry (exhaustive
   over the target sequence when no grid is given);
2. narrowphase: swept attack/contact geometry vs swept target geometry
   for melee, projectiles and moving hazards, with the legacy discrete
   contact-damage path retained;
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
from src.combat.shapes import (
    ShapeKind,
    SweptShape,
    shape_aabb_intersects,
    swept_intersects_aabb,
)
from src.core.level.systems.combat_trace import CombatTrace, HitCandidate
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
    "ZoneContact",
]


@dataclass
class OffensiveBox:
    """One offensive contact emitted by a producer.

    ``box`` is the discrete current geometry; ``swept`` is the whole-tick
    geometry used for broadphase/narrowphase. Projectiles and moving hazards
    populate it from their previous/current rectangles. ``record_contact`` is
    called with the *target* once a hit landed, so a producer can remember it
    (and release itself).

    **Mutable, and split by lifetime.** The geometry is per-tick and is
    rewritten in place by a producer that keeps the box across ticks (the
    hazard and contact-damage systems, whose producers are static); ``hit`` and
    the per-producer fields are per-producer and are written once. It used to
    be frozen, which was never enforced by anything -- no caller hashes a box
    or puts one in a set -- and only made the construction expensive, since a
    frozen dataclass assigns each field through ``object.__setattr__``.
    Producers that build a fresh box every tick (melee, projectiles) are
    unaffected; they just do not get to skip the work.
    """

    box: pygame.FRect
    swept: tuple[pygame.FRect, ...]
    hit: HitProperties
    faction: str | None
    owner_id: str
    can_contact: Callable[[str], bool]
    swept_shapes: tuple[SweptShape, ...] = ()
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
    point: tuple[float, float] | None = None
    """Where the block landed, so the FX spawn at the contact and not at the
    middle of the defender. None when the outcome has no single contact
    point, as a clash between two attackers does not."""


def _contact_point(box: OffensiveBox, target: Combatant) -> tuple[float, float] | None:
    """The middle of the overlap between an attack box and its target.

    Falls back to the target's own centre when the two do not overlap in
    their stored rectangles, which a swept or moving attack can produce.
    """
    hitbox = getattr(target, "hitbox", None)
    if hitbox is None:
        return None
    overlap = box.box.clip(hitbox)
    if overlap.width <= 0.0 or overlap.height <= 0.0:
        return (hitbox.centerx, hitbox.centery)
    return (overlap.centerx, overlap.centery)


@dataclass
class ContactOutcome:
    """Aggregated result of one :meth:`ContactSystem.resolve` pass."""

    metrics: CombatMetrics = field(default_factory=CombatMetrics)
    guard_events: list[GuardEvent] = field(default_factory=list)
    impact: float = 0.0
    hit_stop: float = 0.0


@dataclass(frozen=True)
class ZoneContact:
    """One landed contact with the hurt zone that absorbed it (P2.4)."""

    owner_id: str
    target_id: str
    zone_index: int
    zone_mult: float
    kind: str = "melee"


def _zone_vulnerable(zone_tags: tuple[str, ...], hit_tags: tuple[str, ...]) -> bool:
    """Whether a zone is hittable by a hit carrying ``hit_tags``.

    Zone tags are invulnerability categories; matching hit categories make
    that zone invulnerable.
    """
    if not zone_tags or not hit_tags:
        return True
    return not set(zone_tags).intersection(hit_tags)


def _target_swept_zones(target: Combatant) -> tuple[pygame.FRect, ...]:
    """Per-zone swept rectangles (P2), single legacy box as fallback.

    The ``getattr`` looks redundant next to ``Combatant.swept_hurtboxes``,
    which the protocol does declare, and the audit read it that way. It is not
    redundant: the fallback is *behaviour*, not tolerance. A target that has
    no previous-tick capture -- one that has not been swept since it was
    placed, or a duck-typed producer's stand-in -- has no swept geometry to
    offer, and the discrete hurtbox is then the best available answer rather
    than a wrong one. The protocol says what a combatant *is*; this says what
    to do when it cannot answer.
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


def _swept_target_box(box: OffensiveBox, target: Combatant) -> pygame.FRect:
    """Return the target geometry swept only for swept offensive producers.

    Same reasoning as :func:`_target_swept_zones`: a target with no sweep
    falls back to its discrete geometry, which is a decision about what to
    draw rather than a duck-typing concession.
    """
    if box.kind == "projectile":
        swept = getattr(target, "swept_hurtbox", None)
        if callable(swept):
            return cast(pygame.FRect, swept())
        return target.hurtbox
    if box.kind == "hazard":
        swept = getattr(target, "swept_pushbox", None)
        if callable(swept):
            return cast(pygame.FRect, swept())
        return target.hitbox
    return target.hitbox


def _shape_swept_intersects(shape: SweptShape, target: pygame.FRect) -> bool:
    if shape.current.kind is ShapeKind.AABB:
        return False
    if shape.previous is None:
        return shape_aabb_intersects(shape.current, target)
    return swept_intersects_aabb(shape.previous, shape.current, target)


def _first_vulnerable_zone(
    target: Combatant,
    swept_boxes: tuple[pygame.FRect, ...],
    hit_tags: tuple[str, ...] = (),
    swept_shapes: tuple[SweptShape, ...] = (),
) -> tuple[int, float] | None:
    """First vulnerable zone touched by any swept attack box (P2).

    Zones are tested in order; the first vulnerable zone overlapping a swept
    box wins.
    """
    zones = _target_swept_zones(target)
    mults = _zone_mults(target)
    tags = _zone_tags(target)
    has_advanced = any(shape.current.kind is not ShapeKind.AABB for shape in swept_shapes)
    has_aabb = any(shape.current.kind is ShapeKind.AABB for shape in swept_shapes)
    for index, zone in enumerate(zones):
        advanced_hit = any(_shape_swept_intersects(shape, zone) for shape in swept_shapes)
        if not advanced_hit:
            if has_advanced and not has_aabb:
                continue
            if not any(box.colliderect(zone) for box in swept_boxes):
                continue
        zone_tags = tags[index] if index < len(tags) else ()
        if not _zone_vulnerable(zone_tags, hit_tags):
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
        #: Contacts landed this resolve, with their absorbing zone (P2.4).
        self.zone_contacts: list[ZoneContact] = []
        #: Optional Axe G dump; enabled only under DEBUG + DEBUG_COMBAT_DUMP.
        self.trace = CombatTrace(enabled=CombatTrace.is_enabled())
        self._nearby: list[SpatialHashMember] = []
        self._candidates_buffer: list[Combatant] = []
        self._seen: set[int] = set()

    def begin_tick(self) -> None:
        """Reset the per-tick metric accumulator (shared-instance wiring)."""
        self.tick_metrics = CombatMetrics()
        self.zone_contacts = []
        self.trace.begin_tick()

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
        # zone_contacts accumulates across producers of the same tick
        # (cleared only by begin_tick), mirroring tick_metrics.
        target_list = tuple(targets)
        order = {id(target): index for index, target in enumerate(target_list)}

        for box in boxes:
            for target in self._candidates(box, target_list, order, entity_grid):
                self.metrics.pairs_tested += 1
                if box.kind == "melee":
                    contact = _first_vulnerable_zone(
                        target,
                        box.swept,
                        box.hit.tags,
                        box.swept_shapes,
                    )
                    if contact is None:
                        continue
                    self.metrics.overlaps += 1
                    self._resolve_melee(box, target, contact[0], contact[1])
                else:
                    target_box = _swept_target_box(box, target)
                    shape_hit = any(
                        _shape_swept_intersects(shape, target_box) for shape in box.swept_shapes
                    )
                    swept_hit = any(swept.colliderect(target_box) for swept in box.swept)
                    if not shape_hit and not swept_hit:
                        continue
                    self.metrics.overlaps += 1
                    self._resolve_generic(box, target)
                if self.trace.enabled and self.zone_contacts:
                    last = self.zone_contacts[-1]
                    self.trace.record(
                        HitCandidate(
                            tick=self.trace.tick,
                            kind=last.kind,
                            owner_id=last.owner_id,
                            target_id=last.target_id,
                            box_count=len(box.swept),
                            zone_index=last.zone_index,
                            zone_mult=last.zone_mult,
                            pairs_tested=self.metrics.pairs_tested,
                            overlaps=self.metrics.overlaps,
                            contacts=self.metrics.contacts,
                            guarded=any(event.target is target for event in self.guard_events),
                            damage=box.hit.damage,
                            shape_kind=next(
                                (
                                    shape.current.kind.value
                                    for shape in box.swept_shapes
                                    if shape.current.kind is not ShapeKind.AABB
                                ),
                                "aabb",
                            ),
                        )
                    )
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
        """Broadphase with caller-owned buffers and stable target order.

        A grid that decided it was not worth indexing is treated as no grid at
        all, not as a grid that returns everything. The two are not the same
        cost: the unfiltered path skips the candidate sort, which at a small
        roster is the most expensive thing left in here.
        """
        if entity_grid is None or not entity_grid.indexed:
            self._candidates_buffer.clear()
            self._candidates_buffer.extend(target for target in targets if _eligible(box, target))
            return self._candidates_buffer
        self._nearby.clear()
        self._seen.clear()
        for swept in box.swept:
            if type(entity_grid) is EntityGrid:
                entity_grid.append_near(swept, self._nearby, self._seen)
            else:
                for member in entity_grid.near(swept):
                    key = id(member)
                    if key not in self._seen:
                        self._seen.add(key)
                        self._nearby.append(member)
        self._nearby.sort(key=lambda member: order.get(id(member), len(order)))
        self._candidates_buffer.clear()
        self._candidates_buffer.extend(
            target
            for member in self._nearby
            if id(member) in order and _eligible(box, target := cast(Combatant, member))
        )
        return self._candidates_buffer

    def _resolve_melee(
        self, box: OffensiveBox, target: Combatant, zone_index: int, zone_mult: float
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
        self.zone_contacts.append(
            ZoneContact(
                owner_id=box.owner_id,
                target_id=getattr(target, "id", "") or "",
                zone_index=zone_index,
                zone_mult=zone_mult,
                kind=box.kind,
            )
        )
        if result.guarded:
            self._record_guard_event(result, target, box)
            if result.parried:
                self._maybe_parry_stun(box.attacker)
        magnitude = pygame.math.Vector2(box.hit.knockback.power).length() * box.charge_mult
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
            result = HitResolver.resolve(attacker=box.attacker, target=target, hit=box.hit)
            if not (result.applied or result.guarded):
                return
            self._record_guard_event(result, target, box)
        else:
            target.receive_damage(
                amount=box.hit.damage,
                source_center_x=box.box.centerx,
                knockback=box.hit.knockback,
                interrupt=box.interrupt,
            )
        self.metrics.contacts += 1
        self.zone_contacts.append(
            ZoneContact(
                owner_id=box.owner_id,
                target_id=getattr(target, "id", "") or "",
                zone_index=0,
                zone_mult=1.0,
                kind=box.kind,
            )
        )
        if box.record_contact is not None:
            box.record_contact(target)

    def _record_guard_event(
        self, result: DamageResult, target: Combatant, box: OffensiveBox
    ) -> None:
        """Record guard/parry/break outcomes for event-draining systems."""
        if not result.guarded:
            return
        kind = "guard"
        if result.parried:
            kind = "parry"
        elif result.guard_broken:
            kind = "break"
        self.guard_events.append(GuardEvent(kind, target, _contact_point(box, target)))

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
