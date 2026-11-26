"""An empty scene stack reports a fact; it does not stop the application."""

from types import SimpleNamespace

import pygame

from src.application.scene import Scene
from src.application.scene_manager import SceneManager
from src.shared.events import AppExitRequested, EventBus


class _GameStub:
    def __init__(self) -> None:
        self.events = EventBus()
        self.input_router = SimpleNamespace(reset=lambda: None)
        self.running = True
        self.ui_scale = 1.0


class _Scene(Scene):
    def update(self, delta_time: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


def test_pop_emits_the_exit_request_without_touching_running() -> None:
    game = _GameStub()
    manager = SceneManager(game)  # type: ignore[arg-type]
    manager.switch(_Scene(game))  # type: ignore[arg-type]
    seen: list[AppExitRequested] = []
    game.events.subscribe(AppExitRequested, seen.append)

    manager.pop()

    assert manager.current is None
    assert game.running is True
    assert len(seen) == 1
