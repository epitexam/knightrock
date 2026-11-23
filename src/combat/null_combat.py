"""No-op combat stand-in, split from :mod:`src.combat.combat_component`.

``NullCombatComponent`` mirrors the public surface of ``CombatComponent`` for
entities without combat capabilities. It lives here so the null-object layer
can change without reopening the orchestrator; ``combat_component`` re-exports
it so every existing import path keeps working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.combat.attack_state import AttackStateSnapshot
from src.combat.charge_handler import ChargeSnapshot
from src.combat.determinism import geometry_checksum
from src.combat.frame_data import AttackDefinition, MoveId, PhaseDefinition, PhaseState
from src.combat.refusal import Refusal
from src.combat.shapes import ShapePose, SweptShape

if TYPE_CHECKING:
    from src.combat.combat_component import CombatSnapshot


class NullCombatComponent:
    """No-op stand-in for entities without combat capabilities.

    Implements the same public interface as ``CombatComponent`` so that
    systems can interact with any entity's ``combat`` attribute without
    null checks. Adapted for the deterministic, network-ready architecture.
    """

    def __init__(self) -> None:
        self.attacks_started: int = 0
        self.is_attacking: bool = False
        self.is_hurt: bool = False
        self.attack_box: pygame.FRect | None = None
        self.attack_boxes: tuple[pygame.FRect, ...] = ()
        self.swept_attack_boxes: tuple[pygame.FRect, ...] = ()
        self.attack_shapes: tuple[ShapePose, ...] = ()
        self.swept_attack_shapes: tuple[SweptShape, ...] = ()
        self.attack_anchors: tuple[tuple[float, float], ...] = ()
        self.charge_multiplier: float = 1.0
        self.hurt_timer: float = 0.0
        self.state: _NullAttackState = _NullAttackState()
        self.targets_hit: set[str] = self.state.targets_hit
        self.combo: _NullComboTracker = _NullComboTracker()
        self.hitbox: _NullHitboxManager = _NullHitboxManager()
        self.charging: _NullChargeHandler = _NullChargeHandler()

    @property
    def current_phase(self) -> PhaseDefinition | None:
        """Always returns ``None``."""
        return None

    @property
    def movement_multiplier(self) -> float:
        """Always returns ``1.0``."""
        return 1.0

    @property
    def cooldowns(self) -> dict[MoveId, float]:
        """Always returns an empty dict."""
        return {}

    @property
    def combo_count(self) -> int:
        """Always returns ``0``."""
        return 0

    @property
    def combo_timer(self) -> float:
        """Always returns ``0.0``."""
        return 0.0

    @property
    def air_combo_count(self) -> int:
        """Always returns ``0``."""
        return 0

    def record_hit_landed(self, airborne: bool) -> bool:
        """Never counts: there is no combo."""
        del airborne
        return False

    def add_attack(self, name: MoveId, definition: AttackDefinition) -> None:
        """No-op."""

    def has_attack(self, name: MoveId) -> bool:
        """Always ``False``: nothing is ever registered."""
        del name
        return False

    @property
    def current_attack_def(self) -> AttackDefinition | None:
        """Always ``None``: no move is ever running."""
        return None

    def start_attack(
        self,
        name: MoveId,
        charge_multiplier: float = 1.0,
    ) -> Refusal:
        """Always refuses: this entity has no attacks registered."""
        return Refusal.UNKNOWN

    def start_charge(self, name: MoveId) -> bool:
        """Always returns ``False``."""
        return False

    def release_charge(self, full: MoveId | None = None) -> Refusal:
        """Never starts an attack, with the same return contract as the real one."""
        del full
        return Refusal.UNKNOWN

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None:
        """No-op."""

    def cancel_attack(self) -> None:
        """No-op."""

    def update(self, delta_time: float) -> None:
        """No-op."""

    def sync_attack_box(self) -> None:
        """No-op."""

    def capture_attack_origin(self) -> None:
        """No-op."""

    def can_contact(self, target_id: str) -> bool:
        """A non-combatant never owns a valid offensive contact."""
        return False

    def record_contact(self, target_id: str) -> None:
        """No-op."""

    def reset_hurt_state(self) -> None:
        """Clear the neutral hurt state."""
        self.is_hurt = False
        self.hurt_timer = 0.0

    def reset(self) -> None:
        """No-op neutral reset, matching ``CombatComponent``."""
        self.reset_hurt_state()
        self.targets_hit.clear()

    def save_state(self) -> CombatSnapshot:
        """Return a dummy snapshot for rollback systems.

        Returns
        -------
        CombatSnapshot
            A default, serialized safe-state snapshot.
        """
        # Imported here, not at module scope: combat_component re-exports this
        # class, so a module-level import back would close an import cycle.
        from src.combat.combat_component import CombatSnapshot

        return CombatSnapshot(
            attack_state=AttackStateSnapshot(
                attack_name=None,
                phase_index=0,
                sub_state=PhaseState.IDLE.value,
                frame_counter=0,
                targets_hit=(),
                locked_facing=None,
                charge_multiplier=1.0,
                accumulator=0.0,
            ),
            is_hurt=False,
            hurt_timer=0.0,
            combo_count=0,
            combo_timer=0.0,
            cooldowns={},
            charge_state=ChargeSnapshot(),
            geometry_checksum=geometry_checksum(()),
        )

    def load_state(self, snapshot: CombatSnapshot) -> None:
        """No-op."""

    def verify_geometry_checksum(self, expected: str) -> None:
        """Validate the empty null combat geometry."""
        del expected


class _NullHitboxManager:
    rect = None
    rects: tuple = ()
    prev_rects: tuple = ()
    swept_rects: tuple = ()

    def clear(self) -> None:
        """No-op."""


class _NullChargeHandler:
    is_charging = False
    movement_multiplier = 1.0
    charge_timer = 0.0
    attack_name: MoveId | None = None

    def cancel(self) -> None:
        """No-op."""


class _NullAttackState:
    """Mock state for NullCombatComponent to avoid AttributeError in CombatSystem.

    Attributes
    ----------
    is_active : bool
        Always False.
    is_attacking : bool
        Always False.
    """

    is_active: bool = False
    is_attacking: bool = False
    sub_state: PhaseState = PhaseState.IDLE
    current_phase_def: PhaseDefinition | None = None

    def __init__(self) -> None:
        self.targets_hit: set[str] = set()

    def take_launches(self) -> list[tuple[str, float]]:
        """Never anything: nothing is ever thrown."""
        return []


class _NullComboTracker:
    """Mock combo tracker for NullCombatComponent.

    Attributes
    ----------
    count : int
        Always 0.
    """

    count = 0
    air_count = 0

    timer = 0.0
    is_armed = False

    def on_attack_started(self, resets_combo: bool) -> None:
        """No-op."""
        del resets_combo

    def on_hit_landed(self, airborne: bool) -> None:
        """No-op."""
        del airborne

    def disarm(self) -> None:
        """No-op."""

    def reset(self) -> None:
        """No-op."""

    def update(self, delta_time: float) -> None:
        """No-op."""
        del delta_time
