"""
Combat component: the per-entity orchestrator for all combat mechanics.

``CombatComponent`` coordinates the attack state machine, hitbox manager,
combo tracker, charge handler, and hurt state.  It provides a high-level
API for starting attacks, charging, and responding to damage.

``NullCombatComponent`` is a no-op stand-in for entities without combat
capabilities, implementing the same public interface.
"""

from __future__ import annotations

import weakref
from typing import Any

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.charge_handler import ChargeHandler
from src.combat.combo_tracker import ComboTracker
from src.combat.frame_data import AttackDefinition, PhaseDefinition
from src.combat.hitbox_manager import HitboxManager
from src.combat.knockback import KnockbackConfig
from src.combat.combatant_protocol import Combatant


class CombatComponent:
    """Orchestrates all combat mechanics for a single entity.

    This component owns sub-modules for attack state, hitbox positioning,
    combo tracking, and charging, delegating work to each while enforcing
    high-level rules (e.g. cannot start an attack while hurt).

    Parameters
    ----------
    entity : Combatant
        The entity that owns this component.
    combo_window : float
        Duration in seconds of the combo window.  Subsequent attacks
        within this window increment the combo counter.
    hurt_duration : float
        Default duration in seconds of the hurt state when the entity
        is hit.

    Attributes
    ----------
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
    def targets_hit(self) -> weakref.WeakSet[Any]:
        """Set of entities already hit during the current attack sequence."""
        return self.state.targets_hit

    def start_attack(
        self,
        name: str,
        facing_right: bool,
        charge_multiplier: float = 1.0,
    ) -> bool:
        """Attempt to start a new attack sequence.

        The action is rejected if the entity is hurt, charging, or if the
        attack is on cooldown.  If the entity is currently in the RECOVERY
        sub-state and the new attack is in the current phase's
        ``cancel_into`` list, the current attack is ended first (cancel).

        Parameters
        ----------
        name : str
            Name of the attack to start.
        facing_right : bool
            Current facing direction of the entity.
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

        definition = self._attacks[name]

        if not self.state.start(name, facing_right, charge_multiplier):
            return False

        self._cooldowns[name] = definition.cooldown

        self.combo.on_attack_started(definition.combo_reset)

        return True

    def start_charge(self, name: str) -> bool:
        """Begin charging an attack.

        The action is rejected if the entity is already attacking, hurt,
        or already charging.

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

    def release_charge(self, facing_right: bool) -> bool:
        """Release the current charge and execute the attack.

        Parameters
        ----------
        facing_right : bool
            Current facing direction of the entity.

        Returns
        -------
        bool
            ``True`` if the charge was released and the attack started.
        """
        result = self.charging.release_charge()
        if result is None:
            return False

        name, multiplier = result
        return self.start_attack(name, facing_right, multiplier)

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None:
        """React to being hit.

        If ``interrupt`` is True, the current attack and charge are
        cancelled and the entity enters the hurt state for the specified
        duration.

        Parameters
        ----------
        duration : float | None
            Custom hurt duration in seconds.  If ``None``, the default
            ``hurt_duration`` from the constructor is used.  Ignored if
            ``interrupt`` is False.
        interrupt : bool
            Whether the hit interrupts the entity's current action.
            Set to False for hits absorbed by super armor.
        """
        if not interrupt:
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

        This method exists so that ``CombatSystem`` can interact solely
        with the ``combat`` component without needing a reference to the
        entity itself for damage application.

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

    def update(self, delta_time: float, facing_right: bool) -> None:
        """Tick all combat sub-systems.

        Must be called once per frame for each entity that has a combat
        component.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        facing_right : bool
            Current facing direction of the entity.
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

        self.state.update(delta_time)

        self.hitbox.update(self.state)


class NullCombatComponent:
    """No-op stand-in for entities without combat capabilities.

    Implements the same public interface as ``CombatComponent`` so that
    systems can interact with any entity's ``combat`` attribute without
    null checks.

    All mutation methods do nothing; all query methods return default
    falsy values.
    """

    def __init__(self) -> None:
        self.is_attacking: bool = False
        self.is_hurt: bool = False
        self.attack_box: pygame.FRect | None = None
        self.targets_hit: set[Any] = set()
        self.charge_multiplier: float = 1.0

    @property
    def current_phase(self) -> PhaseDefinition | None:
        """Always returns ``None``."""
        return None

    def add_attack(self, name: str, definition: AttackDefinition) -> None:
        """No-op."""

    def start_attack(
        self,
        name: str,
        facing_right: bool,
        charge_multiplier: float = 1.0,
    ) -> bool:
        """Always returns ``False``."""
        return False

    def start_charge(self, name: str) -> bool:
        """Always returns ``False``."""
        return False

    def release_charge(self, facing_right: bool) -> bool:
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

    def update(self, delta_time: float, facing_right: bool) -> None:
        """No-op."""
