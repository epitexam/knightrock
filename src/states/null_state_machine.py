class NullStateMachine:
    current_state_name = None

    def update(self, delta_time: float) -> None:
        pass

    def change_state(self, name: str, force: bool = False) -> None:
        pass