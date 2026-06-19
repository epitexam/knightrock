from typing import Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class State(Generic[T]):
    """An abstract base class from which all specific states will inherit."""

    def __init__(self, entity: T) -> None:
        self.entity: T = entity

    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass

    def update(self, delta_time: float) -> Optional[str]:
        return None


class StateMachine(Generic[T]):
    """The universal component to attach to entities."""

    def __init__(self, entity: T) -> None:
        self.entity: T = entity
        self.states: Dict[str, State[T]] = {}
        self.current_state: Optional[State[T]] = None
        self.current_state_name: Optional[str] = None

    def add_state(self, name: str, state: State[T]) -> None:
        self.states[name] = state

    def set_initial_state(self, name: str) -> None:
        self.current_state_name = name
        self.current_state = self.states[name]
        self.current_state.enter()

    def update(self, delta_time: float) -> None:
        if self.current_state:
            next_state_name = self.current_state.update(delta_time)
            if next_state_name and next_state_name in self.states:
                self.change_state(next_state_name)

    def change_state(self, new_state_name: str) -> None:
        if new_state_name == self.current_state_name:
            return

        if self.current_state:
            self.current_state.exit()

        self.current_state_name = new_state_name
        self.current_state = self.states[new_state_name]
        self.current_state.enter()
