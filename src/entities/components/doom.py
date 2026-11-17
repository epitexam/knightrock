"""The doomed state and the death-blow recovery, extracted from ``Entity``.

The fighter's state machine still owns the *category in progress*; this
component owns the transition rules that lead into and out of it. Entity keeps
thin delegating members, so every existing caller and snapshot is unchanged.
"""

from __future__ import annotations

from typing import Protocol

from pygame.math import Vector2

from src.combat.combatant_protocol import Finish
from src.core.settings import Finisher
from src.states import state_names


class DoomCombatPort(Protocol):
    def cancel_attack(self) -> None: ...

    def reset_hurt_state(self) -> None: ...


class DoomStatePort(Protocol):
    @property
    def current_state_name(self) -> str | None: ...

    def change_state(self, name: str, force: bool = False, **kwargs: object) -> None: ...


class DoomOwner(Protocol):
    combat: DoomCombatPort
    state_machine: DoomStatePort
    velocity: Vector2
    health: float
    max_health: float
    stun: float
    stagger_timer: float
    is_dead: bool


class DoomTracker:
    """Rules for entering, leaving and recognising the doomed state."""

    def __init__(self, owner: DoomOwner) -> None:
        self.owner = owner

    @property
    def is_doomed(self) -> bool:
        """Whether the fighter waits, all but dead, for the death blow."""
        return bool(self.owner.state_machine.current_state_name == state_names.DOOMED)

    @property
    def is_helpless(self) -> bool:
        """Stunned, downed or doomed: an ``execute`` hit kills outright."""
        return self.owner.state_machine.current_state_name in (
            state_names.DIZZY,
            state_names.DOWNED,
            state_names.DOOMED,
        )

    @property
    def finish(self) -> Finish:
        """What this fighter's blow does to a target it would kill."""
        return Finish.NONE

    def doom(self) -> None:
        """Leave the fighter doomed: frozen, waiting for the death blow."""
        owner = self.owner
        owner.combat.cancel_attack()
        owner.combat.reset_hurt_state()
        owner.stun = 0.0
        owner.velocity.x = 0.0
        owner.health = min(owner.health, Finisher.DOOM_HEALTH)
        owner.state_machine.change_state(
            state_names.DOOMED, force=True, duration=Finisher.DOOM_TIME
        )

    def recover_from_doom(self) -> None:
        """A missed death blow: the fighter gets up with some health back."""
        owner = self.owner
        if not self.is_doomed or owner.is_dead:
            return
        owner.health = max(owner.health, owner.max_health * Finisher.RECOVER_RATIO)
        owner.stagger_timer = 0.0
        owner.state_machine.change_state("idle", force=True)
