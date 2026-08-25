"""Frame-accurate state machine for attack progression.

Manages the transition through startup, active, and recovery for each phase
of an attack, advancing one frame at a time using a fixed timestep derived
from ``frame_data.FRAME_RATE``. Supports deterministic network synchronization
and rollback via state snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.combat.frame_data import (
    FRAME_RATE,
    AttackDefinition,
    PhaseDefinition,
    PhaseState,
)


@dataclass
class AttackStateSnapshot:
    """Lightweight, serializable snapshot of the attack state machine.

    Used by rollback netcode to save and restore game state instantly without
    referencing complex objects or memory pointers.

    Attributes
    ----------
    attack_name : str | None
        Name of the currently executing attack.
    phase_index : int
        Index of the current phase within the attack definition.
    sub_state : PhaseState
        Current sub-state (IDLE, STARTUP, ACTIVE, RECOVERY).
    frame_counter : int
        Number of frames elapsed in the current sub-state.
    targets_hit : set[str]
        Set of entity IDs already hit during this attack sequence.
    locked_facing : bool | None
        Locked facing direction if the attack freezes direction, else None.
    charge_multiplier : float
        Damage multiplier applied from a charge release.
    accumulator : float
        Time accumulator for the fixed-timestep update loop.
    """
    attack_name: str | None
    phase_index: int
    sub_state: PhaseState
    frame_counter: int
    targets_hit: set[str]
    locked_facing: bool | None
    charge_multiplier: float
    accumulator: float


class AttackStateMachine:
    """Frame-accurate state machine driving attack progression.

    The machine tracks the current attack name, phase index, sub-state,
    and frame counter. It advances in fixed-step increments of
    ``1 / FRAME_RATE`` seconds to guarantee frame-accurate timing
    regardless of the game's variable delta time.

    Parameters
    ----------
    attacks : dict[str, AttackDefinition]
        Shared reference to the attack registry.
    """

    _FRAME_DURATION: float = 1.0 / FRAME_RATE

    def __init__(self, attacks: dict[str, AttackDefinition]) -> None:
        self._attacks: dict[str, AttackDefinition] = attacks
        self.attack_name: str | None = None
        self.phase_index: int = 0
        self.sub_state: PhaseState = PhaseState.IDLE
        self.frame_counter: int = 0
        self.targets_hit: set[str] = set()
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
    def effective_facing(self) -> bool | None:
        """The locked facing direction, or ``None`` if not locked."""
        return self._locked_facing

    @property
    def charge_multiplier(self) -> float:
        """Damage multiplier from charging (1.0 = no charge)."""
        return self._charge_multiplier

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
        if attack is None or self.phase_index >= len(attack.phases):
            return None
        return attack.phases[self.phase_index]

    def resolve_facing(self, entity_facing: bool) -> None:
        """Lock the facing direction on the first frame of the attack.

        In a deterministic network model, facing is resolved from the
        entity's state on the exact frame the attack begins, rather than
        being passed as an input parameter.

        Parameters
        ----------
        entity_facing : bool
            The entity's current facing direction this frame.
        """
        if self._locked_facing is None and self.attack_name is not None:
            attack = self.current_attack_def
            if attack and attack.lock_direction:
                self._locked_facing = entity_facing

    def can_cancel_into(self, attack_name: str) -> bool:
        """Check whether the current recovery allows cancelling into the given attack.

        Parameters
        ----------
        attack_name : str
            Name of the attack to cancel into.

        Returns
        -------
        bool
            ``True`` if the machine is in RECOVERY and the current phase's
            ``cancel_into`` tuple contains ``attack_name``.
        """
        if self.sub_state != PhaseState.RECOVERY:
            return False
        phase = self.current_phase_def
        if phase is None:
            return False
        return attack_name in phase.cancel_into

    def start(self, attack_name: str, charge_multiplier: float = 1.0) -> bool:
        """Begin a new attack sequence deterministically.

        The machine must be IDLE before calling this method.

        Parameters
        ----------
        attack_name : str
            Name of the attack to start.
        charge_multiplier : float
            Damage multiplier from a released charge (default 1.0).

        Returns
        -------
        bool
            ``True`` if the attack started successfully.
        """
        if not self.is_idle:
            return False
        if attack_name not in self._attacks:
            return False

        self.attack_name = attack_name
        self.phase_index = 0
        self.sub_state = PhaseState.STARTUP
        self.frame_counter = 0
        self._accumulator = 0.0
        self.targets_hit.clear()
        self._locked_facing = None
        self._charge_multiplier = charge_multiplier

        if self._attacks[attack_name].phases[0].reset_targets:
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

    def save_state(self) -> AttackStateSnapshot:
        """Capture the current state for rollback saving.

        Returns
        -------
        AttackStateSnapshot
            A serializable snapshot of the machine's current state.
        """
        return AttackStateSnapshot(
            attack_name=self.attack_name,
            phase_index=self.phase_index,
            sub_state=self.sub_state,
            frame_counter=self.frame_counter,
            targets_hit=set(self.targets_hit),
            locked_facing=self._locked_facing,
            charge_multiplier=self._charge_multiplier,
            accumulator=self._accumulator,
        )

    def load_state(self, snapshot: AttackStateSnapshot) -> None:
        """Restore a previously saved state during rollback.

        Parameters
        ----------
        snapshot : AttackStateSnapshot
            The snapshot to restore.
        """
        self.attack_name = snapshot.attack_name
        self.phase_index = snapshot.phase_index
        self.sub_state = snapshot.sub_state
        self.frame_counter = snapshot.frame_counter
        self.targets_hit = set(snapshot.targets_hit)
        self._locked_facing = snapshot.locked_facing
        self._charge_multiplier = snapshot.charge_multiplier
        self._accumulator = snapshot.accumulator

    def update(self, delta_time: float) -> None:
        """Advance the state machine by ``delta_time`` using a fixed timestep.

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
