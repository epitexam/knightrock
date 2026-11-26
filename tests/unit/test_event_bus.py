"""EventBus tests (audit F8.1, Phase 2 #5)."""

from dataclasses import dataclass

import pytest

from src.shared.events import (
    MAX_RECORDED_FAILURES,
    AppExitRequested,
    Event,
    EventBus,
    LevelCompleted,
    LevelStarted,
    PlayerDied,
    UiEffect,
    UiFeedback,
)


@dataclass(frozen=True)
class RogueEvent(Event):
    """A fact nobody declared in the closed union."""


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


def test_the_failure_log_is_bounded() -> None:
    """A permanently broken subscriber must not grow the log for a whole session."""
    bus = EventBus()
    bus.subscribe(LevelCompleted, exploding)

    for _ in range(MAX_RECORDED_FAILURES + 20):
        bus.emit(LevelCompleted(level_id=1))

    assert len(bus.failures) == MAX_RECORDED_FAILURES
    assert bus.failures[-1].event == LevelCompleted(level_id=1)


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


def test_subscribe_rejects_an_unregistered_event_type() -> None:
    bus = EventBus()
    with pytest.raises(TypeError, match="unregistered event type"):
        bus.subscribe(RogueEvent, lambda _: None)


def test_emit_rejects_an_unregistered_event() -> None:
    bus = EventBus()
    with pytest.raises(TypeError, match="unregistered event type"):
        bus.emit(RogueEvent())


def test_unsubscribing_an_unregistered_type_is_a_noop() -> None:
    bus = EventBus()
    bus.unsubscribe(RogueEvent, lambda _: None)


def test_every_declared_fact_can_be_emitted() -> None:
    bus = EventBus()
    seen: list[Event] = []
    for event_type in (
        LevelStarted,
        PlayerDied,
        LevelCompleted,
        AppExitRequested,
        UiFeedback,
    ):
        bus.subscribe(event_type, seen.append)
    facts = [
        LevelStarted(level_id=1),
        PlayerDied(entity_id="e0", deaths=0),
        LevelCompleted(level_id=1),
        AppExitRequested(),
        UiFeedback(effect=UiEffect.CONFIRMED),
    ]
    for fact in facts:
        bus.emit(fact)
    assert seen == facts


def test_rewind_rearms_a_notification_latch() -> None:
    """Facts are at least once: a rewind across a death re-publishes it.

    The latches are part of the level snapshot, so restoring an earlier tick
    makes the next replay emit the same fact again. Subscribers must tolerate
    that; the bus itself deliberately keeps no deduplication state.
    """
    from types import SimpleNamespace
    from typing import Any, cast

    from src.simulation.level.systems.notification_system import NotificationSystem

    bus = EventBus()
    seen: list[int] = []
    bus.subscribe(PlayerDied, lambda event: seen.append(event.deaths))
    notifications = NotificationSystem(bus, 0, cast(Any, None))
    dead = SimpleNamespace(id="e0", is_dead=True)

    notifications.process(dead, deaths=1, exit_reached=False)
    notifications.process(dead, deaths=1, exit_reached=False)
    assert seen == [1]

    # The rollback snapshot restores the latch to its pre-emission value.
    notifications.player_dead_emitted = False
    notifications.process(dead, deaths=1, exit_reached=False)
    assert seen == [1, 1]


def test_a_subscription_handle_detaches_once() -> None:
    bus = EventBus()
    seen: list[LevelStarted] = []
    handle = bus.subscribe_handle(LevelStarted, seen.append)

    bus.emit(LevelStarted(level_id=1))
    handle.unsubscribe()
    handle.unsubscribe()
    bus.emit(LevelStarted(level_id=2))

    assert seen == [LevelStarted(level_id=1)]


def test_a_subscription_handle_works_as_a_context_manager() -> None:
    bus = EventBus()
    seen: list[LevelStarted] = []
    with bus.subscribe_handle(LevelStarted, seen.append):
        bus.emit(LevelStarted(level_id=1))
    bus.emit(LevelStarted(level_id=2))

    assert seen == [LevelStarted(level_id=1)]


def test_a_handle_can_unsubscribe_another_listener_mid_delivery() -> None:
    bus = EventBus()
    order: list[str] = []

    def first(_: LevelStarted) -> None:
        order.append("first")
        second_handle.unsubscribe()

    def second(_: LevelStarted) -> None:
        order.append("second")

    bus.subscribe(LevelStarted, first)
    second_handle = bus.subscribe_handle(LevelStarted, second)
    bus.emit(LevelStarted(level_id=1))
    bus.emit(LevelStarted(level_id=2))

    # The delivery snapshot is a tuple: a listener removed mid-emit still runs
    # for that emit, and is gone from the next one.
    assert order == ["first", "second", "first"]
