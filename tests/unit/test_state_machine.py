from src.states.state_machine import State, StateMachine


class MockState(State):
    def __init__(self, entity, tags=None):
        super().__init__(entity, tags)
        self.entered = False
        self.exited = False

    def enter(self, previous=None, **kwargs):
        self.entered = True

    def exit(self, next_state=None):
        self.exited = True


class MockEntity:
    pass


def test_state_machine_initial_state():
    entity = MockEntity()
    sm = StateMachine(entity)
    state = MockState(entity)
    sm.add_state("idle", state)
    sm.set_initial_state("idle")

    assert sm.current_state_name == "idle"
    assert sm.current_state == state
    assert state.entered


def test_state_machine_transition():
    entity = MockEntity()
    sm = StateMachine(entity)
    idle = MockState(entity)
    run = MockState(entity)

    sm.add_state("idle", idle)
    sm.add_state("run", run)
    sm.set_initial_state("idle")

    sm.change_state("run")

    assert idle.exited
    assert run.entered
    assert sm.current_state_name == "run"
    assert sm.previous_state_name == "idle"


def test_state_machine_input_buffer():
    entity = MockEntity()
    sm = StateMachine(entity)

    sm.buffer_input("attack", 0.5)
    assert sm.consume_input("attack")
    assert not sm.consume_input("attack")

    sm.buffer_input("jump", 0.1)
    sm.update(0.2)
    assert not sm.consume_input("jump")
