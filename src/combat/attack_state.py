"""
Frame-accurate state machine for attack progression.

Manages the transition through startup → active → recovery for each phase
of an attack, advancing one frame at a time using a fixed timestep derived
from ``frame_data.FRAME_RATE``.
"""

from __future__ import annotations

import weakref
from typing import Any

from src.combat.frame_data import (
    FRAME_RATE,
    AttackDefinition,
    PhaseDefinition,
    PhaseState,
)


class AttackStateMachine:
    """Frame-accurate state machine driving attack progression.

    The machine tracks the current attack name, phase index, sub-state
    (startup / active / recovery / idle), and the frame counter within
    the current sub-state.  It advances in fixed-step increments of
    ``1 / FRAME_RATE`` seconds to guarantee frame-accurate timing
    regardless of the game's variable delta time.

    Parameters
    ----------
    attacks : dict[str, AttackDefinition]
        Shared reference to the attack registry.  The same dictionary
        instance is owned by ``CombatComponent``, so attacks added after
        construction are automatically visible.

    Attributes
    ----------
    attack_name : str | None
        Name of the currently executing attack, or ``None`` if idle.
    phase_index : int
        Index into the current attack's ``phases`` tuple.
    sub_state : PhaseState
        Current sub-state within the active phase.
    frame_counter : int
        Number of frames elapsed in the current sub-state.
    targets_hit : weakref.WeakSet[Any]
        Set of entities already hit during the current attack.  Uses weak
        references so dead entities are not kept alive.
    """

    _FRAME_DURATION: float = 1.0 / FRAME_RATE

    def __init__(self, attacks: dict[str, AttackDefinition]) -> None:
        self._attacks: dict[str, AttackDefinition] = attacks
        self.attack_name: str | None = None
        self.phase_index: int = 0
        self.sub_state: PhaseState = PhaseState.IDLE
        self.frame_counter: int = 0
        self.targets_hit: weakref.WeakSet[Any] = weakref.WeakSet()
        self._accumulator: float = 0.0
        self._locked_facing: bool | None = None
        self._charge_multiplier: float = 1.0

    @property
    def is_idle(self) -> bool:
        """Whether the machine is in the IDLE state."""
        return self.sub_state == PhaseState.IDLE

    @property
    def is_active(self) -> bool:
        """Whether the machine is in the ACTIVE sub-state (hitbox live)."""
        return self.sub_state == PhaseState.ACTIVE

    @property
    def is_attacking(self) -> bool:
        """Whether any attack phase is in progress (non-IDLE)."""
        return self.sub_state != PhaseState.IDLE

    @property
    def current_attack_def(self) -> AttackDefinition | None:
        """The ``AttackDefinition`` for the current attack, or ``None``."""
        if self.attack_name is None:
            return None
        return self._attacks.get(self.attack_name)

    @property
    def current_phase_def(self) -> PhaseDefinition | None:
        """The ``PhaseDefinition`` for the current phase, or ``None``."""
        attack = self.current_attack_def
        if attack is None:
            return None
        if self.phase_index >= len(attack.phases):
            return None
        return attack.phases[self.phase_index]

    @property
    def effective_facing(self) -> bool | None:
        """The locked facing direction, or ``None`` if not locked."""
        return self._locked_facing

    @property
    def charge_multiplier(self) -> float:
        """Damage multiplier from charging (1.0 = no charge)."""
        return self._charge_multiplier

    def can_cancel_into(self, attack_name: str) -> bool:
        """Check whether the current recovery allows cancelling into *attack_name*.

        Parameters
        ----------
        attack_name : str
            Name of the attack to cancel into.

        Returns
        -------
        bool
            ``True`` if the machine is in RECOVERY and the current phase's
            ``cancel_into`` tuple contains *attack_name*.
        """
        if self.sub_state != PhaseState.RECOVERY:
            return False
        phase = self.current_phase_def
        if phase is None:
            return False
        return attack_name in phase.cancel_into

    def start(
        self,
        attack_name: str,
        facing_right: bool,
        charge_multiplier: float = 1.0,
    ) -> bool:
        """Begin a new attack sequence.

        The machine **must** be IDLE before calling this method.  Use
        ``end()`` first if a cancel is required.

        Parameters
        ----------
        attack_name : str
            Name of the attack to start.
        facing_right : bool
            Current facing direction of the attacker.
        charge_multiplier : float
            Damage multiplier from charging (default 1.0).

        Returns
        -------
        bool
            ``True`` if the attack started successfully.
        """
        if not self.is_idle:
            return False
        if attack_name not in self._attacks:
            return False

        attack = self._attacks[attack_name]
        self.attack_name = attack_name
        self.phase_index = 0
        self.sub_state = PhaseState.STARTUP
        self.frame_counter = 0
        self._accumulator = 0.0
        self.targets_hit.clear()
        self._locked_facing = facing_right if attack.lock_direction else None
        self._charge_multiplier = charge_multiplier

        if attack.phases[0].reset_targets:
            self.targets_hit.clear()

        return True

    def end(self) -> None:
        """Immediately return to IDLE, clearing all attack state."""
        self.attack_name = None
        self.phase_index = 0
        self.sub_state = PhaseState.IDLE
        self.frame_counter = 0
        self._accumulator = 0.0
        self.targets_hit.clear()
        self._locked_facing = None
        self._charge_multiplier = 1.0

    def update(self, delta_time: float) -> None:
        """Advance the state machine by *delta_time* using a fixed timestep.

        Each call accumulates elapsed time and advances one frame per
        ``1 / FRAME_RATE`` seconds, ensuring frame-accurate progression
        even under variable frame rates.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last update.
        """
        if self.is_idle:
            return

        self._accumulator += delta_time
        while self._accumulator >= self._FRAME_DURATION:
            self._accumulator -= self._FRAME_DURATION
            self._advance_one_frame()

    def _advance_one_frame(self) -> None:
        """Advance one frame and handle sub-state transitions."""
        self.frame_counter += 1
        phase = self.current_phase_def
        if phase is None:
            self.end()
            return

        if self.sub_state == PhaseState.STARTUP:
            if self.frame_counter >= phase.startup_frames:
                self._enter_sub_state(PhaseState.ACTIVE)

        elif self.sub_state == PhaseState.ACTIVE:
            if self.frame_counter >= phase.active_frames:
                self._enter_sub_state(PhaseState.RECOVERY)

        elif self.sub_state == PhaseState.RECOVERY:
            if self.frame_counter >= phase.recovery_frames:
                self._advance_phase()

    def _enter_sub_state(self, new_state: PhaseState) -> None:
        """Transition to a new sub-state within the current phase.

        Parameters
        ----------
        new_state : PhaseState
            The sub-state to enter.
        """
        self.sub_state = new_state
        self.frame_counter = 0

    def _advance_phase(self) -> None:
        """Move to the next phase of the current attack, or end if none remains."""
        if self.attack_name is None:
            return

        attack = self._attacks[self.attack_name]
        next_index = self.phase_index + 1

        if next_index >= len(attack.phases):
            self.end()
            return

        self.phase_index = next_index
        phase = attack.phases[next_index]

        if phase.reset_targets:
            self.targets_hit.clear()

        self.sub_state = PhaseState.STARTUP
        self.frame_counter = 0
