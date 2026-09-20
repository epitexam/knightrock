"""Hit detection, deterministic contact collection, and global hit-stop timing."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

import pygame

from src.combat.combatant_protocol import Combatant, CombatPort
from src.combat.frame_data import HitProperties, PhaseDefinition
from src.combat.hit_resolver import HitResolver
from src.core.settings import Combat as CombatSettings
from src.core.settings import Guard as GuardSettings
from src.entities.enemies.enemy import Enemy
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHashMember
from src.states.reaction_states import DIZZY_STATE


@dataclass(frozen=True)
class HitCandidate:
    """Immutable contact captured before any hit reaction mutates combat state."""

    attacker: Combatant
    target: Combatant
    hit: HitProperties
    charge_multiplier: float


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


def _attacker_ready(
    attacker: Combatant,
) -> tuple[CombatPort, tuple[pygame.FRect, ...], tuple[pygame.FRect, ...], PhaseDefinition] | None:
    """Attacker eligibility: alive, active phase, live and swept boxes."""
    if attacker.is_dead:
        return None
    combat = attacker.combat
    attack_boxes = combat.attack_boxes
    swept_boxes = combat.swept_attack_boxes
    phase = combat.current_phase
    if not combat.state.is_active or not attack_boxes or phase is None:
        return None
    # Per-index pairing preserved (D1): swept boxes follow the same order
    # as the live boxes; a missing origin (spawn/resize) degenerates to cur.
    if len(swept_boxes) != len(attack_boxes):
        swept_boxes = attack_boxes
    return combat, attack_boxes, swept_boxes, phase


def _nearby_targets(
    query_boxes: tuple[pygame.FRect, ...],
    combatants: tuple[Combatant, ...],
    order: dict[int, int],
    entity_grid: EntityGrid | None,
) -> list[Combatant]:
    """Geometric collection: local grid prune, then group order."""
    if entity_grid is None:
        return list(combatants)
    # Query around every swept box (D2: the whole tick's motion is what
    # matters, not just the final box), then restore group order so hit
    # resolution matches the exhaustive loop deterministically. Only
    # combatants have an entry in `order`, so the cast is safe.
    seen: set[int] = set()
    nearby: list[SpatialHashMember] = []
    for query_box in query_boxes:
        for member in entity_grid.near(query_box):
            if id(member) in order and id(member) not in seen:
                seen.add(id(member))
                nearby.append(member)
    return cast(
        list[Combatant],
        sorted(nearby, key=lambda m: order[id(m)]),
    )


def _is_valid_target(attacker: Combatant, target: Combatant, combat: CombatPort) -> bool:
    """Target eligibility: not self, alive, enemy faction, phase contact."""
    if attacker is target or target.is_dead:
        return False
    if attacker.faction == target.faction:
        return False
    return bool(combat.can_contact(target.id))


def _target_hurtbox(target: Combatant) -> pygame.FRect:
    """Hurt area of a target: swept when supported (P1), else raw hurtbox."""
    swept = getattr(target, "swept_hurtbox", None)
    return target.hurtbox if not callable(swept) else swept()


class CombatSystem:
    """Collect and resolve offensive contacts in two deterministic passes."""

    def __init__(self) -> None:
        self.hit_stop_timer: float = 0.0
        self.metrics: CombatMetrics = CombatMetrics()
        self.impact: float = 0.0
        self.guard_events: list[GuardEvent] = []

    def process_attacks(
        self,
        combat_sprites: Iterable[Combatant],
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Resolve contacts from a stable snapshot of active hitboxes.

        Detection is completed before damage reactions are applied. This allows
        simultaneous attacks to trade instead of depending on sprite insertion
        order. The iterable is materialized once, avoiding repeated Pygame group
        copies and supporting generators safely.

        When ``entity_grid`` is provided, target candidates are pruned through
        it (query around each active attack box, O(n · k) instead of the legacy
        exhaustive O(n²)); candidates are then sorted back into group order so
        hit resolution happens exactly like the exhaustive loop. Without a
        grid the pairs are tested exhaustively — still correct, just slower.
        """
        self.metrics = CombatMetrics()
        self.impact = 0.0
        self.guard_events = []
        if self.in_hit_stop:
            return

        combatants = tuple(combat_sprites)
        candidates = self._collect_candidates(combatants, entity_grid)
        self._resolve_candidates(candidates)

    def _collect_candidates(
        self,
        combatants: tuple[Combatant, ...],
        entity_grid: EntityGrid | None = None,
    ) -> tuple[HitCandidate, ...]:
        candidates: list[HitCandidate] = []
        order = {id(combatant): index for index, combatant in enumerate(combatants)}

        for attacker in combatants:
            ready = _attacker_ready(attacker)
            if ready is None:
                continue
            combat, _attack_boxes, swept_boxes, phase = ready
            # D2: grid prune around the swept boxes (whole tick motion).
            targets = _nearby_targets(swept_boxes, combatants, order, entity_grid)

            for target in targets:
                if not _is_valid_target(attacker, target, combat):
                    continue

                self.metrics.pairs_tested += 1
                # P1 sweep: attack-vs-hurt on swept geometry on BOTH sides
                # (bilateral generosity, documented in D3).
                hurt_box = _target_hurtbox(target)
                if not any(box.colliderect(hurt_box) for box in swept_boxes):
                    continue

                self.metrics.overlaps += 1
                candidates.append(
                    HitCandidate(
                        attacker=attacker,
                        target=target,
                        hit=phase.hit,
                        charge_multiplier=combat.charge_multiplier,
                    )
                )

        return tuple(candidates)

    def _resolve_candidates(self, candidates: tuple[HitCandidate, ...]) -> None:
        for candidate in candidates:
            result = HitResolver.resolve(
                attacker=candidate.attacker,
                target=candidate.target,
                hit=candidate.hit,
                charge_multiplier=candidate.charge_multiplier,
            )
            if not (result.applied or result.guarded):
                continue

            candidate.attacker.combat.record_contact(candidate.target.id)
            self.metrics.contacts += 1
            if result.guarded:
                kind = "guard"
                if result.parried:
                    kind = "parry"
                elif result.guard_broken:
                    kind = "break"
                self.guard_events.append(GuardEvent(kind, candidate.target))
                # Parry-stun: count consecutive perfect parries received by attacker
                if result.parried and isinstance(candidate.attacker, Enemy):
                    attacker = candidate.attacker
                    attacker.parries_taken += 1
                    if (
                        attacker.parry_stun_threshold is not None
                        and attacker.parries_taken >= attacker.parry_stun_threshold
                    ):
                        attacker.state_machine.change_state(
                            DIZZY_STATE, force=True, duration=attacker.parry_stun_duration
                        )
                        attacker.parries_taken = 0
                        self.guard_events.append(GuardEvent("stun", candidate.attacker))
            magnitude = (
                pygame.math.Vector2(candidate.hit.knockback.power).length()
                * candidate.charge_multiplier
            )
            self.impact = max(self.impact, magnitude)
            hitstop_duration = (
                CombatSettings.HITSTOP_BASE
                + candidate.hit.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR
                + magnitude * CombatSettings.HITSTOP_KNOCKBACK_FACTOR
            )
            if result.parried:
                hitstop_duration = max(hitstop_duration, GuardSettings.PARRY_HITSTOP)
            self.hit_stop_timer = max(self.hit_stop_timer, hitstop_duration)

            # Reset consecutive parry counter when attacker deals real HP damage
            if result.applied and hasattr(candidate.attacker, "parries_taken"):
                candidate.attacker.parries_taken = 0

    def update_timer(self, delta_time: float) -> None:
        """Advance the global hit-stop timer."""
        if self.hit_stop_timer > 0:
            self.hit_stop_timer = max(0.0, self.hit_stop_timer - delta_time)

    @property
    def in_hit_stop(self) -> bool:
        """Whether combat simulation is currently suspended."""
        return self.hit_stop_timer > 0
