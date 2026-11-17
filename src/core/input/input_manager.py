from src.core.input.input_actions import InputAction
from src.core.input.input_provider import InputProvider, NullInputProvider
from src.core.input.input_state import InputState


class InputManager:
    def __init__(self, provider: InputProvider | None = None) -> None:
        self._provider: InputProvider = provider or NullInputProvider()
        self._current_state = InputState()
        self._prev_state = InputState()

    def apply_remote_state(self, state: InputState) -> None:
        """Install ``state`` as this tick's input, for driving one entity by hand.

        A whole ``Level`` reads its provider on every simulated tick, which
        would read over a state planted here; a network session feeds the
        level through an :class:`InputProvider` instead.
        """
        self._prev_state = self._current_state
        self._current_state = state

    def update(self) -> None:
        self._prev_state = self._current_state
        self._current_state = self._provider.poll()

    def snapshot(self) -> tuple[InputState, InputState]:
        return self._current_state, self._prev_state

    def restore_snapshot(self, current: InputState, previous: InputState) -> None:
        self._current_state = current
        self._prev_state = previous

    def axis(self, action: InputAction) -> float:
        if action is not InputAction.MOVE_X:
            raise ValueError(f"Action {action.value} is not an analog action")
        return self._current_state.move_axis

    def held(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action in self._current_state.held_actions

    def just_pressed(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action in self._current_state.held_actions and action not in (
            self._prev_state.held_actions
        )

    def just_released(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action not in self._current_state.held_actions and action in (
            self._prev_state.held_actions
        )

    @staticmethod
    def _require_discrete(action: InputAction) -> None:
        if action is InputAction.MOVE_X:
            raise ValueError("MOVE_X must be read through axis()")
        if action.value.startswith("ui_"):
            raise ValueError(f"UI action cannot enter simulation state: {action.value}")
