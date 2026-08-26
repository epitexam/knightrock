"""Hit detection, deterministic contact collection, and global hit-stop timing."""

from collections.abc import Iterable
from dataclasses import dataclass

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.core.settings import Combat as CombatSettings


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


class CombatSystem:
    """Collect and resolve offensive contacts in two deterministic passes."""

    def __init__(self) -> None:
        self.hit_stop_timer: float = 0.0
        self.metrics: CombatMetrics = CombatMetrics()

    def process_attacks(self, combat_sprites: Iterable[Combatant]) -> None:
        """Resolve contacts from a stable snapshot of active hitboxes.

        Detection is completed before damage reactions are applied. This allows
        simultaneous attacks to trade instead of depending on sprite insertion
        order. The iterable is materialized once, avoiding repeated Pygame group
        copies and supporting generators safely.
        """
        self.metrics = CombatMetrics()
        if self.in_hit_stop:
            return

        combatants = tuple(combat_sprites)
        candidates = self._collect_candidates(combatants)
        self._resolve_candidates(candidates)

    def _collect_candidates(
        self, combatants: tuple[Combatant, ...]
    ) -> tuple[HitCandidate, ...]:
        candidates: list[HitCandidate] = []

        for attacker in combatants:
            if attacker.is_dead:
                continue

            combat = attacker.combat
            attack_box = combat.attack_box
            phase = combat.current_phase
            if not combat.state.is_active or attack_box is None or phase is None:
                continue

            for target in combatants:
                if attacker is target or target.is_dead:
                    continue
                if attacker.faction == target.faction:
                    continue
                if not combat.can_contact(target.id):
                    continue

                self.metrics.pairs_tested += 1
                if not attack_box.colliderect(target.hurtbox):
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
            if not (result.applied or result.blocked):
                continue

            candidate.attacker.combat.record_contact(candidate.target.id)
            self.metrics.contacts += 1
            hitstop_duration = (
                CombatSettings.HITSTOP_BASE
                + candidate.hit.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR
            )
            self.hit_stop_timer = max(self.hit_stop_timer, hitstop_duration)

    def update_timer(self, delta_time: float) -> None:
        """Advance the global hit-stop timer."""
        if self.hit_stop_timer > 0:
            self.hit_stop_timer = max(0.0, self.hit_stop_timer - delta_time)

    @property
    def in_hit_stop(self) -> bool:
        """Whether combat simulation is currently suspended."""
        return self.hit_stop_timer > 0
