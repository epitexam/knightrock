from collections.abc import Callable
from typing import Any


class NullStateMachine:
    """A dummy state machine used for entities that don't need state logic."""

    current_state_name: str | None = None

    def update(self, delta_time: float) -> None:
        """Update the state machine."""
        pass

    def change_state(self, name: str, force: bool = False, **kwargs: Any) -> None:
        """Change the current state."""
        pass

    def add_state(self, name: str, state: Any) -> None:
        """Register a state (no-op: keeps the StateMachine interface)."""
        pass

    def set_initial_state(self, name: str) -> None:
        """Set the initial state (no-op for the null state machine)."""
        self.current_state_name = name

    def add_interrupt(self, target: str, condition: Callable[[], bool], priority: int = 0) -> None:
        """Register an interrupt (no-op for the null state machine)."""
        pass

    def buffer_input(self, action: str, window: float = 0.15) -> None:
        """Buffer an input."""
        pass

    def consume_input(self, action: str) -> bool:
        """Consume a buffered input."""
        return False

    def save_state(self) -> Any:
        """Return a neutral snapshot (rollback, Phase 3 #3)."""
        from src.states.state_machine import StateMachineSnapshot

        return StateMachineSnapshot(
            current_state_name=None,
            previous_state_name=None,
            input_buffer={},
        )

    def load_state(self, snapshot: Any) -> None:
        """No-op: a null machine has no simulation state to restore."""
