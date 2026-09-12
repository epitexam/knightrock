"""Tests de la machine à scènes d'application (audit F8.1, Phase 2 #4)."""

import pygame
import pytest

from src.application.scene import Scene
from src.application.scene_manager import SceneManager
from src.application.scenes.gameover_scene import GameOverScene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_scene import MenuScene
from src.application.scenes.pause_scene import PauseScene
from src.core.level.level import Level
from src.core.settings import Gameplay
from tests.headless.conftest import make_programmatic_level_data


class RecordingScene(Scene):
    """Scène factice qui trace son cycle de vie."""

    def __init__(self, game, name: str):
        super().__init__(game)
        self.name = name
        self.events: list[str] = []
        self.dirty_called = False

    def enter(self) -> None:
        self.events.append(f"enter:{self.name}")

    def exit(self) -> None:
        self.events.append(f"exit:{self.name}")

    def update(self, delta_time: float) -> None:
        self.events.append(f"update:{self.name}")

    def draw(self) -> list[pygame.Rect]:
        self.dirty_called = True
        return []


@pytest.fixture()
def manager(game_runtime) -> SceneManager:
    return game_runtime.scene_manager


def test_switch_replaces_the_whole_stack(manager: SceneManager):
    first = RecordingScene(manager.game, "first")
    second = RecordingScene(manager.game, "second")

    manager.switch(first)
    manager.switch(second)

    assert manager.current is second
    assert first.events == ["enter:first", "exit:first"]
    assert second.events == ["enter:second"]


def test_push_freezes_the_scene_below_and_pop_resumes_it(manager: SceneManager):
    gameplay = RecordingScene(manager.game, "gameplay")
    pause = RecordingScene(manager.game, "pause")
    manager.switch(gameplay)
    manager.push(pause)

    manager.update(1 / 60)
    assert gameplay.events == ["enter:gameplay"]  # frozen: no update
    assert pause.events[-1] == "update:pause"

    manager.pop()
    assert manager.current is gameplay
    manager.update(1 / 60)
    assert "update:gameplay" in gameplay.events


def test_draw_draws_all_scenes_when_stacked(manager: SceneManager):
    gameplay = RecordingScene(manager.game, "gameplay")
    pause = RecordingScene(manager.game, "pause")
    manager.switch(gameplay)
    manager.push(pause)

    assert manager.draw() is None  # overlay: full refresh
    assert gameplay.dirty_called and pause.dirty_called


def test_popping_the_last_scene_stops_the_game(manager: SceneManager):
    manager.switch(RecordingScene(manager.game, "only"))

    manager.pop()

    assert manager.current is None
    assert manager.game.running is False


def test_menu_switches_to_gameplay_on_confirm(manager: SceneManager):
    manager.switch(MenuScene(manager.game))

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
    manager.handle_event(event)

    assert isinstance(manager.current, GameplayScene)


def test_menu_escape_stops_the_game(manager: SceneManager):
    manager.switch(MenuScene(manager.game))

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert manager.game.running is False


def _make_level(game_runtime) -> Level:
    return Level(
        pygame.display.get_surface(),
        make_programmatic_level_data(),
        game_runtime.input_manager,
    )


def test_gameplay_escape_pushes_pause(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert isinstance(manager.current, PauseScene)
    manager.pop()
    assert manager.current is gameplay


def test_gameplay_death_limit_pushes_game_over(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    gameplay.level.deaths = Gameplay.MAX_DEATHS
    gameplay.update(1 / 60)

    assert isinstance(manager.current, GameOverScene)


def test_gameplay_completed_without_next_level_returns_to_menu(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    gameplay.level.exit_reached = True
    gameplay.update(1 / 60)

    assert isinstance(manager.current, MenuScene)


def test_game_over_retry_restarts_the_level(manager: SceneManager):
    game_over = GameOverScene(manager.game, level_id=0)
    manager.switch(game_over)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, GameplayScene)
    assert manager.current.level_id == 0
