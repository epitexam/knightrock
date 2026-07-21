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

    def buffer_input(self, action: str, window: float = 0.15) -> None:
        """Buffer an input."""
        pass

    def consume_input(self, action: str) -> bool:
        """Consume a buffered input."""
        return False