from collections import deque
from typing import Callable, List, Optional, Tuple, Any


class State:
    """Abstract base for all states."""
    def __init__(self, entity: Any) -> None:
        """Initialize the State instance."""
        self.entity: Any = entity

    def enter(self, previous: Optional[str] = None) -> None:
        """Enter the state."""
        pass

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state."""
        pass

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        return None


class StateMachine:
    """Represent a StateMachine."""
    def __init__(self, entity: Any) -> None:
        """Initialize the StateMachine instance."""
        self.entity: Any = entity
        self.states: dict[str, State] = {}
        self.current_state: Optional[State] = None
        self.current_state_name: Optional[str] = None
        self.previous_state_name: Optional[str] = None
        self._interrupts: List[Tuple[int, str, Callable[[], bool]]] = []
        self.history: deque[str] = deque(maxlen=16)

    def add_state(self, name: str, state: State) -> None:
        """Add state."""
        self.states[name] = state

    def add_interrupt(self, target: str, condition: Callable[[], bool], priority: int = 0) -> None:
        """Add interrupt."""
        self._interrupts.append((priority, target, condition))
        self._interrupts.sort(key=lambda x: -x[0])

    def set_initial_state(self, name: str) -> None:
        """Set initial state."""
        self.current_state_name = name
        self.current_state = self.states[name]
        self.history.append(name)
        self.current_state.enter(None)

    def update(self, delta_time: float) -> None:
        """Update the current state."""
        for _, target, condition in self._interrupts:
            if target != self.current_state_name and condition():
                self.change_state(target)
                return
        if self.current_state:
            next_state = self.current_state.update(delta_time)
            if next_state and next_state in self.states:
                self.change_state(next_state)

    def change_state(self, new_name: str, force: bool = False) -> None:
        """Perform change state. 'force' allows reloading an identical state."""
        if new_name == self.current_state_name and not force:
            return
        prev = self.current_state_name
        if self.current_state:
            self.current_state.exit(new_name)
        self.previous_state_name = prev
        self.current_state_name = new_name
        self.current_state = self.states[new_name]
        self.history.append(new_name)
        self.current_state.enter(prev)