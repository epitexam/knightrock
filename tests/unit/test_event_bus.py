"""EventBus tests (audit F8.1, Phase 2 #5)."""

import pytest

from src.application.events import (
    Event,
    EventBus,
    LevelCompleted,
    LevelStarted,
    PlayerDied,
)


def test_emit_dispatches_to_subscribers_of_that_type_only() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(PlayerDied, received.append)

    bus.emit(LevelCompleted(level_id=0))
    bus.emit(PlayerDied(entity_id="e1", deaths=0))

    assert len(received) == 1
    assert received[0] == PlayerDied(entity_id="e1", deaths=0)


def test_subscribers_run_in_subscription_order() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(LevelCompleted, lambda _: order.append("first"))
    bus.subscribe(LevelCompleted, lambda _: order.append("second"))

    bus.emit(LevelCompleted(level_id=1))

    assert order == ["first", "second"]


def test_unsubscribe_removes_the_handler() -> None:
    bus = EventBus()
    received: list[LevelStarted] = []
    handler = received.append
    bus.subscribe(LevelStarted, handler)

    bus.unsubscribe(LevelStarted, handler)
    bus.emit(LevelStarted(level_id=0))

    assert received == []


def test_subscribing_the_same_handler_twice_registers_it_once() -> None:
    """``subscribe``/``unsubscribe`` must be a symmetric pair.

    A second registration used to survive the unsubscribe that follows it (which
    removes a single occurrence), so a subscribe/unsubscribe cycle left a ghost
    subscriber that kept running its effect on every later emit.
    """
    bus = EventBus()
    received: list[LevelStarted] = []
    handler = received.append
    bus.subscribe(LevelStarted, handler)
    bus.subscribe(LevelStarted, handler)

    bus.emit(LevelStarted(level_id=0))

    assert received == [LevelStarted(level_id=0)]

    bus.unsubscribe(LevelStarted, handler)
    bus.emit(LevelStarted(level_id=1))

    assert received == [LevelStarted(level_id=0)]


def test_unsubscribe_unknown_handler_is_a_noop() -> None:
    bus = EventBus()
    bus.unsubscribe(PlayerDied, lambda _: None)  # does not raise


def test_emit_without_subscribers_is_a_noop() -> None:
    bus = EventBus()

    bus.emit(PlayerDied(entity_id="e9", deaths=3))  # does not raise


def test_clear_drops_every_subscription() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(PlayerDied, received.append)
    bus.clear()

    bus.emit(PlayerDied(entity_id="e1", deaths=0))

    assert received == []


def test_events_are_immutable_payloads() -> None:
    event = LevelCompleted(level_id=0)

    with pytest.raises(AttributeError):
        event.level_id = 2  # type: ignore[misc]


# -- subscriber isolation -----------------------------------------------------
#
# `emit` is called from inside the fixed tick and the subscribers are UI,
# audio, save and logging code the simulation cannot vouch for. Before the
# boundary, one of them raising killed the tick -- and the notification
# system marks a fact emitted *before* publishing it, so the fact was then
# never republished.


def exploding(event: Event) -> None:
    raise RuntimeError("subscriber is broken")


def test_a_failing_subscriber_does_not_stop_the_others() -> None:
    bus = EventBus()
    reached: list[str] = []
    bus.subscribe(LevelCompleted, exploding)
    bus.subscribe(LevelCompleted, lambda _: reached.append("after"))

    bus.emit(LevelCompleted(level_id=1))

    assert reached == ["after"]


def test_a_failing_subscriber_does_not_reach_the_emitter() -> None:
    """The emitter is the fixed tick; it must come back from this."""
    bus = EventBus()
    bus.subscribe(PlayerDied, exploding)

    bus.emit(PlayerDied(entity_id="e1", deaths=0))  # must not raise


def test_a_failure_is_recorded_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    bus.subscribe(LevelCompleted, exploding)

    with caplog.at_level("ERROR"):
        bus.emit(LevelCompleted(level_id=1))

    assert len(bus.failures) == 1
    failure = bus.failures[0]
    assert failure.handler is exploding
    assert isinstance(failure.error, RuntimeError)
    assert failure.event == LevelCompleted(level_id=1)
    assert "failed handling LevelCompleted" in caplog.text


def test_the_ordered_delivery_contract_survives_a_failure() -> None:
    """A failure is isolated, not reordered: the rest still run in order."""
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(LevelCompleted, lambda _: order.append("a"))
    bus.subscribe(LevelCompleted, exploding)
    bus.subscribe(LevelCompleted, lambda _: order.append("b"))

    bus.emit(LevelCompleted(level_id=1))

    assert order == ["a", "b"]


def test_a_subscriber_may_unsubscribe_during_delivery() -> None:
    """The walk is over a copy, so mutating the subscriber list is safe."""
    bus = EventBus()
    seen: list[str] = []

    def leaving(event: LevelStarted) -> None:
        seen.append("leaving")
        bus.unsubscribe(LevelStarted, staying)

    def staying(event: LevelStarted) -> None:
        seen.append("staying")

    bus.subscribe(LevelStarted, leaving)
    bus.subscribe(LevelStarted, staying)

    bus.emit(LevelStarted(level_id=0))
    bus.emit(LevelStarted(level_id=0))

    assert seen == ["leaving", "staying", "leaving"]


def test_clear_also_forgets_the_failures() -> None:
    bus = EventBus()
    bus.subscribe(LevelCompleted, exploding)
    bus.emit(LevelCompleted(level_id=1))

    bus.clear()

    assert bus.failures == ()


def test_a_broken_save_subscriber_cannot_cost_the_progression() -> None:
    """The scenario the boundary exists for, at the level it happens.

    A subscriber that does I/O -- here, persisting progression -- fails, and
    the other subscribers still run. The notification system marks a fact
    emitted *before* publishing it, so an exception escaping the publish would
    not delay that save, it would cancel it: permanently, and silently.
    """
    bus = EventBus()
    persisted: list[int] = []

    def failing_save(event: LevelCompleted) -> None:
        raise OSError("no space left on device")

    def working_save(event: LevelCompleted) -> None:
        persisted.append(event.unlock_level_id or 0)

    bus.subscribe(LevelCompleted, failing_save)
    bus.subscribe(LevelCompleted, working_save)

    bus.emit(LevelCompleted(level_id=1, unlock_level_id=2))

    assert persisted == [2]
    assert len(bus.failures) == 1
