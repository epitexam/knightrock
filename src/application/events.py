"""Event bus typé pour le découplage UI/combat (audit F8.1, Phase 2 #5).

Le bus est **synchrone et strictement ordonné** : ``emit`` invoque les
abonnés immédiatement, dans l'ordre d'abonnement, sur le thread de la
simulation.  Il n'introduit donc aucune non-déterminisme (pas de file
asynchrone, pas de threads) — les abonnés sont des observateurs (UI,
sauvegarde, audio, logs) et ne doivent **jamais muter l'état simulé**.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
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


GameEvent = LevelStarted | PlayerDied | LevelCompleted
"""Union of every concrete event payload."""

Handler = Callable[[GameEvent], None]


class EventBus:
    """Pub/sub minimal : ``subscribe(type, handler)`` puis ``emit(event)``."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[Handler]] = {}

    def subscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> None:
        """Register ``handler`` for events of exactly ``event_type``."""
        self._subscribers.setdefault(event_type, []).append(handler)  # type: ignore[arg-type]

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
