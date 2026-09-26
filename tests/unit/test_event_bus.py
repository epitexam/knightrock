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
