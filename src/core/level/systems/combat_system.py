"""Hit detection, hit-vs-hit priority/clash, and global hit-stop timing.

Detection itself is delegated to the unified
:class:`~src.core.level.systems.contact_system.ContactSystem` (P4.1): this
class owns the melee *producer* half (attacker eligibility, hit-vs-hit
priority/clash) and the global hit-stop timer.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import pygame

from src.combat.combatant_protocol import Combatant, CombatPort
from src.combat.frame_data import PhaseDefinition
from src.core.level.systems.contact_system import (
    CombatMetrics,
    ContactOutcome,
    ContactSystem,
    GuardEvent,
    OffensiveBox,
)
from src.core.settings import Combat as CombatSettings
from src.physics.entity_grid import EntityGrid

__all__ = ["CombatMetrics", "CombatSystem", "ContactSystem", "GuardEvent"]


@dataclass(frozen=True)
class _ReadyAttacker:
    attacker: Combatant
    combat: CombatPort
    attack_boxes: tuple[pygame.FRect, ...]
    swept_boxes: tuple[pygame.FRect, ...]
    phase: PhaseDefinition


def _attacker_ready(
    attacker: Combatant,
) -> _ReadyAttacker | None:
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
    return _ReadyAttacker(attacker, combat, attack_boxes, swept_boxes, phase)


def _record_for(combat: CombatPort) -> Callable[[Combatant], None]:
    """Adapter: the unified pipeline records targets, ports record ids."""

    def record(target: Combatant) -> None:
        combat.record_contact(target.id)

    return record


class CombatSystem:
    """Collect and resolve offensive contacts in two deterministic passes."""

    def __init__(self, contact_system: ContactSystem | None = None) -> None:
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        self.hit_stop_timer: float = 0.0
        self.metrics: CombatMetrics = CombatMetrics()
        self.impact: float = 0.0
        self.guard_events: list[GuardEvent] = []

    def process_attacks(
        self,
        combat_sprites: Iterable[Combatant],
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Resolve melee contacts from a stable snapshot of active hitboxes.

        Detection is completed before damage reactions are applied. This allows
        simultaneous attacks to trade instead of depending on sprite insertion
        order. The iterable is materialized once, avoiding repeated Pygame group
        copies and supporting generators safely.

        Hit-vs-hit priority/clash runs first (P3t1), then every surviving
        attacker feeds the unified :class:`ContactSystem` (P4.1), which owns
        broadphase, narrowphase and hit resolution; its counters and hit-stop
        are merged back here so existing consumers keep reading the same
        attributes.
        """
        self.metrics = CombatMetrics()
        self.impact = 0.0
        self.guard_events = []
        if self.in_hit_stop:
            return

        combatants = tuple(combat_sprites)
        ready = self._collect_ready(combatants)
        losers, clashed = self._resolve_hit_vs_hit(ready)
        boxes = self._produce_boxes(ready, losers, clashed)
        outcome = self.contact_system.resolve(boxes, combatants, entity_grid)
        self._merge(outcome)

    def _merge(self, outcome: ContactOutcome) -> None:
        """Fold the unified pass's outcome into this system's public state."""
        self.metrics.pairs_tested += outcome.metrics.pairs_tested
        self.metrics.overlaps += outcome.metrics.overlaps
        self.metrics.contacts += outcome.metrics.contacts
        self.guard_events.extend(outcome.guard_events)
        self.impact = max(self.impact, outcome.impact)
        self.hit_stop_timer = max(self.hit_stop_timer, outcome.hit_stop)

    def _produce_boxes(
        self,
        ready: list[_ReadyAttacker],
        losers: set[int],
        clashed: set[int],
    ) -> tuple[OffensiveBox, ...]:
        """Melee producer: one box per surviving ready attacker.

        The whole swept geometry travels in ``swept`` (P1); the first live
        box is the discrete ``box`` so the record stays uniform across
        producers.
        """
        boxes: list[OffensiveBox] = []
        for entry in ready:
            if id(entry.attacker) in losers or id(entry.attacker) in clashed:
                continue
            combat = entry.combat
            boxes.append(
                OffensiveBox(
                    box=entry.attack_boxes[0],
                    swept=entry.swept_boxes,
                    hit=entry.phase.hit,
                    faction=entry.attacker.faction,
                    owner_id=entry.attacker.id,
                    can_contact=combat.can_contact,
                    record_contact=_record_for(combat),
                    attacker=entry.attacker,
                    charge_mult=combat.charge_multiplier,
                )
            )
        return tuple(boxes)

    def _collect_ready(self, combatants: tuple[Combatant, ...]) -> list[_ReadyAttacker]:
        return [
            entry
            for attacker in combatants
            if (entry := _attacker_ready(attacker)) is not None
        ]

    def _resolve_hit_vs_hit(
        self, ready: list[_ReadyAttacker]
    ) -> tuple[set[int], set[int]]:
        losers: set[int] = set()
        clashed: set[int] = set()
        for index_a in range(len(ready)):
            for index_b in range(index_a + 1, len(ready)):
                entry_a = ready[index_a]
                entry_b = ready[index_b]
                if entry_a.attacker.faction == entry_b.attacker.faction:
                    continue
                if id(entry_a.attacker) in clashed or id(entry_b.attacker) in clashed:
                    continue
                if not any(
                    box_a.colliderect(box_b)
                    for box_a in entry_a.swept_boxes
                    for box_b in entry_b.swept_boxes
                ):
                    continue
                self.metrics.overlaps += 1
                pa = entry_a.phase.hit.priority
                pb = entry_b.phase.hit.priority
                if pa == pb:
                    if entry_a.phase.hit.clash != 'clash':
                        continue
                    entry_a.attacker.combat.cancel_attack()
                    entry_b.attacker.combat.cancel_attack()
                    clashed.add(id(entry_a.attacker))
                    clashed.add(id(entry_b.attacker))
                    self.guard_events.append(GuardEvent('clash', entry_a.attacker))
                    self.guard_events.append(GuardEvent('clash', entry_b.attacker))
                    self.hit_stop_timer = max(
                        self.hit_stop_timer, CombatSettings.HITSTOP_BASE
                    )
                elif pa > pb:
                    entry_b.attacker.combat.cancel_attack()
                    losers.add(id(entry_b.attacker))
                else:
                    entry_a.attacker.combat.cancel_attack()
                    losers.add(id(entry_a.attacker))
        return losers, clashed

    def update_timer(self, delta_time: float) -> None:
        """Advance the global hit-stop timer."""
        if self.hit_stop_timer > 0:
            self.hit_stop_timer = max(0.0, self.hit_stop_timer - delta_time)

    @property
    def in_hit_stop(self) -> bool:
        """Whether combat simulation is currently suspended."""
        return self.hit_stop_timer > 0
