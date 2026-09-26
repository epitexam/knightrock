"""Typed event bus for UI/combat decoupling (audit F8.1, Phase 2 #5).

The bus is **synchronous and strictly ordered**: ``emit`` invokes subscribers
immediately, in subscription order, on the simulation thread.  It therefore
introduces no non-determinism (no async queue, no threads) — subscribers are
observers (UI, save, audio, logs) and must **never mutate simulated state**.

Two families of facts travel on it, and a producer publishes in the form its
own layer allows:

* **simulation notifications** — ``LevelStarted``, ``PlayerDied``,
  ``LevelCompleted``. Emitted from inside the fixed tick by
  ``NotificationSystem`` and ``Level``, which hold no reference to the
  application: the bus is the *only* channel available to them, which is also
  what keeps a rewind from re-emitting a fact the player already saw.
* **interface feedback** — ``UiFeedback``, emitted by ``InputDispatcher`` from
  the report a scene returns. Here the producer *can* name its consumer, and it
  still does not, so that a second one (haptics, an on-screen tutorial) is
  added by subscribing rather than by reopening the screens.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

EventT = TypeVar("EventT", bound="Event")


@dataclass(frozen=True)
class Event:
    """Base of all bus events."""


@dataclass(frozen=True)
class LevelStarted(Event):
    """A level finished building and is ready to simulate."""

    level_id: int


@dataclass(frozen=True)
class PlayerDied(Event):
    """The player just entered the dead state (respawn comes later)."""

    entity_id: str
    deaths: int


@dataclass(frozen=True)
class LevelCompleted(Event):
    """The player reached the exit flag.

    ``unlock_level_id`` carries the ``level_unlock`` value declared in the
    level's TMX *Data* layer (0 = nothing new to unlock).
    """

    level_id: int
    unlock_level_id: int | None = None


class UiEffect(StrEnum):
    """What the interface just did, in the vocabulary producers share.

    Deliberately coarser than a menu action: the audio system must not have to
    know ``MenuItem`` actions to answer, and a consumer that needs the detail
    reads ``UiFeedback.action``. Dismissal is a third value and not a flavour
    of confirmation — it is what a screen that closes sounds like, and it is
    the only way the audio side can tell the two apart without a convention.
    """

    NAVIGATED = "navigated"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class UiFeedback(Event):
    """One interface interaction that reached a screen and was acted on.

    Published only when a screen actually performed the action, which is what
    makes the silence structural: a key the gameplay scene ignores, a press
    swallowed by a rebinding capture, a stick release, an unplugged pad — none
    of them is an interaction, so none of them is published.
    """

    effect: UiEffect
    action: str = ""


GameEvent = LevelStarted | PlayerDied | LevelCompleted | UiFeedback
"""Union of every concrete event payload."""

Handler = Callable[[GameEvent], None]


class EventBus:
    """Minimal pub/sub: ``subscribe(type, handler)`` then ``emit(event)``."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[Handler]] = {}

    def subscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> None:
        """Register ``handler`` for events of exactly ``event_type``.

        Idempotent for a given handler: subscribing the same one twice used to
        register it twice, and since ``unsubscribe`` removes a single
        occurrence the pair was not even symmetric — a subscribe/unsubscribe
        cycle left a ghost subscriber behind. A double-registered subscriber
        also runs its effect twice, which for a sound is a doubled click and
        for the save handler a second write of the progression file.
        """
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> None:
        """Remove a previously registered handler (no-op if absent)."""
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        with contextlib.suppress(ValueError):
            handlers.remove(handler)  # type: ignore[arg-type]

    def emit(self, event: GameEvent) -> None:
        """Dispatch ``event`` synchronously, in subscription order."""
        for handler in tuple(self._subscribers.get(type(event), ())):
            handler(event)

    def clear(self) -> None:
        """Drop every subscription (level teardown, tests)."""
        self._subscribers.clear()
