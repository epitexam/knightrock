from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from src.simulation.settings import StateMachineConfig

__all__ = ["MachineState", "State", "StateMachine", "StateMachineSnapshot"]

if TYPE_CHECKING:
    from src.simulation.entities.entity import Entity

#: The fighter a state drives. Bound to ``Entity`` so a state shared by every
#: fighter reads the base class, and a player or enemy state reads its own.
EntityT = TypeVar("EntityT", bound="Entity")


class MachineState(Protocol):
    """The surface a state machine needs from a state, independent of its fighter."""

    tags: list[str]

    @property
    def snapshot_fields(self) -> tuple[str, ...]: ...

    def enter(self, previous: str | None = None, **kwargs: object) -> None: ...

    def exit(self, next_state: str | None = None) -> None: ...

    def update(self, delta_time: float) -> str | tuple[str, dict[str, object]] | None: ...


@dataclass(frozen=True)
class StateMachineSnapshot:
    """Serializable capture of the machine and its states' transient scalars.

    Restoring is a *teleport*: ``current_state`` is rebound directly and
    scalar attributes are written back without firing ``exit()``/``enter()``,
    so a rollback never re-runs state entry side-effects (which would reset
    the very timers the snapshot preserves).
    """

    current_state_name: str | None
    previous_state_name: str | None
    input_buffer: dict[str, float]
    state_attrs: dict[str, dict[str, object]] = field(default_factory=dict)


class State(Generic[EntityT]):
    """Abstract base for all states, typed by the fighter it drives.

    ``snapshot_fields`` is the declared rollback schema: the transient scalars
    a state needs restored by a teleport. A field added to a state must be
    declared here (or on its subclass) or it is silently absent from a rewind.
    """

    snapshot_fields: tuple[str, ...] = ()

    def __init__(self, entity: EntityT, tags: list[str] | None = None) -> None:
        """Initialize the State instance."""
        self.entity: EntityT = entity
        self.tags: list[str] = tags or []

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        """Enter the state. Accepts extra data (e.g., knockback direction)."""
        pass

    def exit(self, next_state: str | None = None) -> None:
        """Exit the state."""
        pass

    def update(self, delta_time: float) -> str | tuple[str, dict[str, object]] | None:
        """Update the current state. Can return a string or a tuple (state_name, kwargs)."""
        return None


def _capture_state_attrs(state: MachineState) -> dict[str, object]:
    """Copy the declared fields a state has already set.

    Several states create their transient fields in ``enter()`` rather than in
    ``__init__``, so a field may legitimately be absent before the first entry.
    """
    attrs = vars(state)
    return {name: attrs[name] for name in state.snapshot_fields if name in attrs}


class StateMachine:
    """Represent a StateMachine optimized for Hack 'n' Slash."""

    def __init__(self, entity: object) -> None:
        """Initialize the StateMachine instance."""
        self.entity: object = entity
        self.states: dict[str, MachineState] = {}

        self.current_state: MachineState | None = None
        self.current_state_name: str | None = None
        self.previous_state_name: str | None = None

        self._interrupts: list[tuple[int, str, Callable[[], bool]]] = []
        self.history: deque[str] = deque(maxlen=StateMachineConfig.HISTORY_MAXLEN)

        self._input_buffer: dict[str, float] = {}

        self.on_state_change: Callable[[str | None, str], None] | None = None

    def add_state(self, name: str, state: MachineState) -> None:
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

    def has_tag(self, tag: str) -> bool:
        """Check if current state has a specific tag (e.g., 'attack', 'invincible')."""
        return self.current_state is not None and tag in self.current_state.tags

    def buffer_input(self, action: str, window: float = 0.15) -> None:
        """Buffer an input (e.g., 'attack', 'jump') for a given duration in seconds."""
        self._input_buffer[action] = window

    def consume_input(self, action: str) -> bool:
        """Check if an input is buffered and consume it."""
        if action in self._input_buffer:
            del self._input_buffer[action]
            return True
        return False

    def _update_buffer(self, delta_time: float) -> None:
        """Decrement buffer timers and remove expired inputs."""
        expired = []
        for action, timer in self._input_buffer.items():
            self._input_buffer[action] = timer - delta_time
            if self._input_buffer[action] <= 0:
                expired.append(action)
        for action in expired:
            del self._input_buffer[action]

    def update(self, delta_time: float) -> None:
        """Update the current state."""
        self._update_buffer(delta_time)

        for _, target, condition in self._interrupts:
            if target != self.current_state_name and condition():
                self.change_state(target)
                return

        if self.current_state:
            next_state_info = self.current_state.update(delta_time)

            if next_state_info:
                if isinstance(next_state_info, tuple):
                    next_name, kwargs = next_state_info
                    if next_name in self.states:
                        self._change(next_name, False, kwargs)
                else:
                    if next_state_info in self.states:
                        self.change_state(next_state_info)

    def change_state(self, name: str, force: bool = False, **kwargs: object) -> None:
        """Perform change state. 'force' allows reloading an identical state."""
        self._change(name, force, kwargs)

    def _change(self, name: str, force: bool, kwargs: dict[str, object]) -> None:
        if name == self.current_state_name and not force:
            return

        prev = self.current_state_name
        if self.current_state:
            self.current_state.exit(name)

        self.previous_state_name = prev
        self.current_state_name = name
        self.current_state = self.states[name]
        self.history.append(name)

        self.current_state.enter(prev, **kwargs)

        if self.on_state_change:
            self.on_state_change(prev, name)

    def save_state(self) -> StateMachineSnapshot:
        """Capture the machine position and every state's transient scalars.

        Used by the rollback system.  ``history`` is
        deliberately not captured: it is debug/telemetry only and never
        read by simulation logic.
        """
        return StateMachineSnapshot(
            current_state_name=self.current_state_name,
            previous_state_name=self.previous_state_name,
            input_buffer=dict(self._input_buffer),
            state_attrs={name: _capture_state_attrs(state) for name, state in self.states.items()},
        )

    def load_state(self, snapshot: StateMachineSnapshot) -> None:
        """Teleport the machine back to a captured position.

        Binds ``current_state`` directly instead of calling
        ``change_state``: firing ``exit()``/``enter()`` on restore would
        re-run entry side-effects (timers reset to their initial value,
        velocities re-applied) and diverge from the captured simulation.
        """
        self.current_state_name = snapshot.current_state_name
        self.previous_state_name = snapshot.previous_state_name
        self._input_buffer = dict(snapshot.input_buffer)
        self.current_state = (
            self.states[snapshot.current_state_name]
            if snapshot.current_state_name is not None
            else None
        )
        for name, attrs in snapshot.state_attrs.items():
            state = self.states.get(name)
            if state is None:
                continue
            for attr_name, value in attrs.items():
                setattr(state, attr_name, value)
