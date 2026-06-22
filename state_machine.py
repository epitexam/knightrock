from typing import Callable, Dict, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")


class State(Generic[T]):
    """
    Abstract base for all states.
    enter/exit receive context (previous/next state name) for conditional setup.
    """

    def __init__(self, entity: T) -> None:
        self.entity: T = entity

    def enter(self, previous: Optional[str] = None) -> None:
        pass

    def exit(self, next_state: Optional[str] = None) -> None:
        pass

    def update(self, delta_time: float) -> Optional[str]:
        return None


class StateMachine(Generic[T]):
    """
    Hierarchical finite state machine with a global interrupt system.

    Interrupts are high-priority conditions registered once at the machine level.
    They are evaluated before any state's own logic each tick, eliminating the need
    for each state to duplicate common transition checks (hurt, dash, block, etc.).

    Interrupt evaluation order is determined by priority (highest first).
    A given interrupt is skipped if the machine is already in the target state.
    """

    def __init__(self, entity: T) -> None:
        self.entity: T = entity
        self.states: Dict[str, State[T]] = {}
        self.current_state: Optional[State[T]] = None
        self.current_state_name: Optional[str] = None
        self.previous_state_name: Optional[str] = None
        self._interrupts: List[Tuple[int, str, Callable[[], bool]]] = []
        self.history: List[str] = []

    def add_state(self, name: str, state: State[T]) -> None:
        self.states[name] = state

    def add_interrupt(
        self,
        target: str,
        condition: Callable[[], bool],
        priority: int = 0,
    ) -> None:
        """
        Register a global interrupt.
        Higher priority interrupts are evaluated first.
        The condition is a zero-argument callable returning bool.
        """
        self._interrupts.append((priority, target, condition))
        self._interrupts.sort(key=lambda x: -x[0])

    def set_initial_state(self, name: str) -> None:
        self.current_state_name = name
        self.current_state = self.states[name]
        self.history.append(name)
        self.current_state.enter(None)

    def update(self, delta_time: float) -> None:
        for _, target, condition in self._interrupts:
            if target != self.current_state_name and condition():
                self.change_state(target)
                return

        if self.current_state:
            next_state = self.current_state.update(delta_time)
            if next_state and next_state in self.states:
                self.change_state(next_state)

    def change_state(self, new_name: str) -> None:
        if new_name == self.current_state_name:
            return

        prev = self.current_state_name

        if self.current_state:
            self.current_state.exit(new_name)

        self.previous_state_name = prev
        self.current_state_name = new_name
        self.current_state = self.states[new_name]

        self.history.append(new_name)
        if len(self.history) > 16:
            self.history = self.history[-16:]

        self.current_state.enter(prev)
