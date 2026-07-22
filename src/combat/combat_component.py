"""Combat component: the per-entity orchestrator for all combat mechanics.

``CombatComponent`` coordinates the attack state machine, hitbox manager,
combo tracker, charge handler, and hurt state. It provides a high-level
API for starting attacks, charging, and responding to damage.

``NullCombatComponent`` is a no-op stand-in for entities without combat
capabilities, implementing the same public interface.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.combat.attack_state import AttackStateMachine, AttackStateSnapshot
from src.combat.charge_handler import ChargeHandler
from src.combat.combo_tracker import ComboTracker
from src.combat.frame_data import AttackDefinition, PhaseDefinition, PhaseState
from src.combat.hitbox_manager import HitboxManager
from src.combat.knockback import KnockbackConfig
from src.combat.combatant_protocol import Combatant


@dataclass
class CombatSnapshot:
    """Lightweight, serializable snapshot of the combat component for rollback.

    Attributes
    ----------
    attack_state : AttackStateSnapshot
        Snapshot of the attack state machine.
    is_hurt : bool
        Whether the entity is currently in the hurt state.
    hurt_timer : float
        Remaining time for the hurt state.
    combo_count : int
        Current combo count.
    combo_timer : float
        Remaining time for the combo window.
    """
    attack_state: AttackStateSnapshot
    is_hurt: bool
    hurt_timer: float
    combo_count: int
    combo_timer: float


class CombatComponent:
    """Orchestrates all combat mechanics for a single entity.

    This component owns sub-modules for attack state, hitbox positioning,
    combo tracking, and charging, delegating work to each while enforcing
    high-level rules such as preventing attacks while hurt.

    Parameters
    ----------
    entity : Combatant
        The entity that owns this component.
    combo_window : float
        Duration in seconds of the combo window.
    hurt_duration : float
        Default duration in seconds of the hurt state when the entity is hit.

    Attributes
    ----------
    state : AttackStateMachine
        The frame-accurate attack state machine.
    hitbox : HitboxManager
        The manager responsible for positioning the attack hitbox.
    combo : ComboTracker
        The combo counter and window tracker.
    charging : ChargeHandler
        The handler for charge attack mechanics.
    is_hurt : bool
        Whether the entity is currently in the hurt state.
    """

    def __init__(
        self,
        entity: Combatant,
        combo_window: float,
        hurt_duration: float,
    ) -> None:
        self._entity: Combatant = entity
        self._attacks: dict[str, AttackDefinition] = {}
        self._cooldowns: dict[str, float] = {}

        self.state: AttackStateMachine = AttackStateMachine(self._attacks)
        self.hitbox: HitboxManager = HitboxManager(entity)
        self.combo: ComboTracker = ComboTracker(combo_window)
        self.charging: ChargeHandler = ChargeHandler(self._attacks)

        self.is_hurt: bool = False
        self._hurt_timer: float = 0.0
        self._hurt_duration: float = hurt_duration

    def add_attack(self, name: str, definition: AttackDefinition) -> None:
        """Register a new attack definition.

        Parameters
        ----------
        name : str
            Unique name identifying the attack (e.g. "light_attack").
        definition : AttackDefinition
            The immutable frame data and properties of the attack.
        """
        self._attacks[name] = definition
        self._cooldowns[name] = 0.0

    @property
    def is_attacking(self) -> bool:
        """Whether an attack sequence is currently in progress."""
        return self.state.is_attacking

    @property
    def attack_box(self) -> pygame.FRect | None:
        """The current active attack hitbox, or ``None`` if inactive."""
        return self.hitbox.rect

    @property
    def current_phase(self) -> PhaseDefinition | None:
        """The ``PhaseDefinition`` for the current active phase, or ``None``."""
        return self.state.current_phase_def

    @property
    def charge_multiplier(self) -> float:
        """Current damage multiplier from the attack state (1.0 if none)."""
        return self.state.charge_multiplier

    @property
    def targets_hit(self) -> set[int]:
        """Set of entity IDs already hit during the current attack sequence."""
        return self.state.targets_hit

    @property
    def movement_multiplier(self) -> float:
        """Movement speed multiplier to apply to the entity this frame."""
        if self.charging.is_charging:
            return self.charging.movement_multiplier

        # NOUVEAU : Si on attaque, on prend la vitesse de déplacement de l'attaque
        if self.state.is_attacking:
            attack = self.state.current_attack_def
            if attack is not None:
                return attack.attack_move_multiplier

        return 1.0

    def start_attack(
        self,
        name: str,
        charge_multiplier: float = 1.0,
    ) -> bool:
        """Attempt to start a new attack sequence.

        Facing direction is resolved deterministically inside the update loop
        via the state machine, so it is not passed as a parameter here.

        Parameters
        ----------
        name : str
            Name of the attack to start.
        charge_multiplier : float
            Damage multiplier from a released charge (default 1.0).

        Returns
        -------
        bool
            ``True`` if the attack started successfully.
        """
        if self.is_hurt or self.charging.is_charging:
            return False

        if name not in self._attacks:
            return False

        if self._cooldowns.get(name, 0.0) > 0:
            return False

        if self.state.is_attacking:
            if self.state.can_cancel_into(name):
                self.state.end()
            else:
                return False

        if not self.state.start(name, charge_multiplier):
            return False

        definition = self._attacks[name]
        self._cooldowns[name] = definition.cooldown
        self.combo.on_attack_started(definition.combo_reset)

        return True

    def start_charge(self, name: str) -> bool:
        """Begin charging an attack.

        Parameters
        ----------
        name : str
            Name of the attack to charge.

        Returns
        -------
        bool
            ``True`` if the charge started successfully.
        """
        if self.is_attacking or self.is_hurt:
            return False
        return self.charging.start_charge(name)

    def release_charge(self) -> bool:
        """Release the current charge and execute the attack.

        Returns
        -------
        bool
            ``True`` if the charge was released and the attack started.
        """
        result = self.charging.release_charge()
        if result is None:
            return False

        name, multiplier = result
        return self.start_attack(name, multiplier)

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None:
        """React to being hit.

        If ``interrupt`` is True, the current attack and charge are
        cancelled and the entity enters the hurt state for the specified
        duration.

        Parameters
        ----------
        duration : float | None
            Custom hurt duration in seconds. If ``None``, the default
            ``hurt_duration`` from the constructor is used. Ignored if
            ``interrupt`` is False.
        interrupt : bool
            Whether the hit interrupts the entity's current action.
            Set to False for hits absorbed by super armor.

        Notes
        -----
        If the entity is currently executing an attack whose definition
        has ``uninterruptible`` set to True, the interruption is ignored
        entirely: no hurt state is entered, the attack is not ended, and
        the charge is not cancelled. Damage itself is unaffected, since
        it is applied separately via ``take_damage``.
        """
        if not interrupt:
            return

        if self.state.is_attacking:
            attack = self.state.current_attack_def
            if attack is not None and attack.uninterruptible:
                return

        self.is_hurt = True
        self._hurt_timer = duration if duration is not None else self._hurt_duration

        self.state.end()
        self.hitbox.clear()
        self.charging.cancel()

    def take_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        """Forward damage to the entity's ``receive_damage`` method.

        Parameters
        ----------
        amount : int
            Hit points to subtract.
        source_center_x : float | None
            X centre of the damage source for knockback direction.
        knockback : KnockbackConfig | None
            Knockback impulse configuration.
        """
        self._entity.receive_damage(amount, source_center_x, knockback)

    def save_state(self) -> CombatSnapshot:
        """Capture the full combat state for a rollback frame.

        Returns
        -------
        CombatSnapshot
            A serializable snapshot of the combat component's current state.
        """
        return CombatSnapshot(
            attack_state=self.state.save_state(),
            is_hurt=self.is_hurt,
            hurt_timer=self._hurt_timer,
            combo_count=self.combo.count,
            combo_timer=self.combo._timer,
        )

    def load_state(self, snapshot: CombatSnapshot) -> None:
        """Restore combat state from a rollback frame.

        Parameters
        ----------
        snapshot : CombatSnapshot
            The snapshot to restore.
        """
        self.state.load_state(snapshot.attack_state)
        self.is_hurt = snapshot.is_hurt
        self._hurt_timer = snapshot.hurt_timer
        self.combo.count = snapshot.combo_count
        self.combo._timer = snapshot.combo_timer

    def update(self, delta_time: float) -> None:
        """Tick all combat sub-systems.

        Facing direction is read directly from the entity to ensure
        deterministic state resolution over the network.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        if self.is_hurt:
            self._hurt_timer -= delta_time
            if self._hurt_timer <= 0.0:
                self._hurt_timer = 0.0
                self.is_hurt = False

        for name in list(self._cooldowns):
            if self._cooldowns[name] > 0:
                self._cooldowns[name] -= delta_time

        self.combo.update(delta_time)
        self.charging.update(delta_time)
        self.state.resolve_facing(self._entity.facing_right)
        self.state.update(delta_time)
        self.hitbox.update(self.state)


class NullCombatComponent:
    """No-op stand-in for entities without combat capabilities.

    Implements the same public interface as ``CombatComponent`` so that
    systems can interact with any entity's ``combat`` attribute without
    null checks. Adapted for the deterministic, network-ready architecture.
    """

    def __init__(self) -> None:
        self.is_attacking: bool = False
        self.is_hurt: bool = False
        self.attack_box: pygame.FRect | None = None
        self.targets_hit: set[int] = set()
        self.charge_multiplier: float = 1.0
        self.state: _NullAttackState = _NullAttackState()
        self.combo: _NullComboTracker = _NullComboTracker()

    @property
    def current_phase(self) -> PhaseDefinition | None:
        """Always returns ``None``."""
        return None

    @property
    def movement_multiplier(self) -> float:
        """Always returns ``1.0``."""
        return 1.0

    def add_attack(self, name: str, definition: AttackDefinition) -> None:
        """No-op."""

    def start_attack(
        self,
        name: str,
        charge_multiplier: float = 1.0,
    ) -> bool:
        """Always returns ``False``."""
        return False

    def start_charge(self, name: str) -> bool:
        """Always returns ``False``."""
        return False

    def release_charge(self) -> bool:
        """Always returns ``False``."""
        return False

    def on_hit(
        self, duration: float | None = None, interrupt: bool = True
    ) -> None:
        """No-op."""

    def take_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        """No-op."""

    def update(self, delta_time: float) -> None:
        """No-op."""

    def save_state(self) -> CombatSnapshot:
        """Return a dummy snapshot for rollback systems.

        Returns
        -------
        CombatSnapshot
            A default, serialized safe-state snapshot.
        """
        return CombatSnapshot(
            attack_state=AttackStateSnapshot(
                attack_name=None,
                phase_index=0,
                sub_state=PhaseState.IDLE,
                frame_counter=0,
                targets_hit=set(),
                locked_facing=None,
                charge_multiplier=1.0,
                accumulator=0.0
            ),
            is_hurt=False,
            hurt_timer=0.0,
            combo_count=0,
            combo_timer=0.0
        )

    def load_state(self, snapshot: CombatSnapshot) -> None:
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
    is_active = False
    is_attacking = False


class _NullComboTracker:
    """Mock combo tracker for NullCombatComponent.

    Attributes
    ----------
    count : int
        Always 0.
    """
    count = 0

    def on_attack_started(self, resets_combo: bool) -> None:
        """No-op."""

    def update(self, delta_time: float) -> None:
        """No-op."""
