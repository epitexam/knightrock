"""Tests d'intégration des événements Level → app (Phase 2 #5)."""

import pygame

from src.application.events import EventBus, LevelCompleted, LevelStarted, PlayerDied
from src.core.level.level import Level
from tests.headless.conftest import make_programmatic_level_data


class MockInputManager:
    """Stub d'input minimal (même contrat que la fixture conftest)."""

    def __init__(self) -> None:
        self.move_axis = 0.0
        self.left_held = False
        self.right_held = False
        self.block_held = False
        self.jump_just_pressed = False
        self.dash_just_pressed = False
        self.reset_just_pressed = False
        self.attack1_just_pressed = False
        self.attack2_just_pressed = False
        self.attack2_just_released = False
        self.attack3_just_pressed = False
        self.attack4_just_pressed = False
        self.special_attack_just_pressed = False

    def update(self) -> None:
        """No-op."""


def build_level_with_bus(events: EventBus | None) -> Level:
    """Construit un Level programmatique avec le bus fourni."""
    return Level(
        pygame.display.get_surface(),
        make_programmatic_level_data(),
        MockInputManager(),
        level_id=7,
        events=events,
    )


def test_level_emits_started_on_build() -> None:
    events = EventBus()
    received: list[LevelStarted] = []
    events.subscribe(LevelStarted, received.append)

    build_level_with_bus(events)

    assert [e.level_id for e in received] == [7]


def test_level_emits_player_died_once_per_death() -> None:
    level = build_level_with_bus(EventBus())
    received: list[PlayerDied] = []

    level.events.subscribe(PlayerDied, received.append)
    level.player.die()
    level.update(1 / 60)
    level.update(1 / 60)
    level.player.respawn()
    level.update(1 / 60)
    level.player.die()
    level.update(1 / 60)

    assert len(received) == 2
    assert received[0].entity_id == level.player.id


def test_level_emits_level_completed_once() -> None:
    level = build_level_with_bus(EventBus())
    received: list[LevelCompleted] = []

    level.events.subscribe(LevelCompleted, received.append)
    level.exit_reached = True
    level.update(1 / 60)
    level.update(1 / 60)

    assert len(received) == 1
    assert received[0].level_id == 7


def test_level_without_bus_does_not_fail() -> None:
    level = build_level_with_bus(None)
    level.player.die()
    level.update(1 / 60)

    assert level.player.is_dead
