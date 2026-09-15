"""Gameplay scene: one level, its deaths, its transitions (Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.level.level import Level
from src.core.settings import Gameplay

if TYPE_CHECKING:
    from src.core.game import Game


class GameplayScene(Scene):
    """Run a ``Level`` and trigger the end transitions.

    Transitions:
    - exit flag reached → next level (or menu if last level);
    - ``Gameplay.MAX_DEATHS`` deaths → Game Over scene;
    - ESC → pause (the scene is frozen on the stack).
    """

    def __init__(self, game: Game, level_id: int = 0, level: Level | None = None) -> None:
        """``level`` allows injecting a Level in tests (no TMX)."""
        super().__init__(game)
        self.level_id = level_id
        self.level: Level | None = level

    def enter(self) -> None:
        if self.level is None:
            self._load_level()

    def _load_level(self) -> None:
        if self.game.display_surface is None:
            raise RuntimeError("The game display is not initialized")
        level_data = self.game.level_manager.get(self.level_id)
        self.level = Level(
            self.game.display_surface,
            level_data,
            self.game.input_manager,
            level_id=self.level_id,
            events=self.game.events,
            gameplay_data=self.game.gameplay_data,
        )

    def update(self, delta_time: float) -> None:
        if self.level is None:
            raise RuntimeError("GameplayScene has no level loaded")
        self.game.input_manager.update()
        self.level.update(delta_time)

        if self.level.completed:
            self._advance_level()
        elif self.level.deaths >= Gameplay.MAX_DEATHS:
            # Local import: Menu/GameOver/Gameplay reference each other.
            from src.application.scenes.gameover_scene import GameOverScene

            self.game.scene_manager.push(GameOverScene(self.game, self.level_id))

    def _advance_level(self) -> None:
        from src.application.scenes.gameplay_scene import GameplayScene
        from src.application.scenes.menu_scene import MenuScene

        next_id = self.game.level_manager.next_id(self.level_id)
        if next_id is None:
            self.game.scene_manager.switch(MenuScene(self.game))
        else:
            self.game.scene_manager.switch(GameplayScene(self.game, next_id))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from src.application.scenes.pause_scene import PauseScene

            self.game.scene_manager.push(PauseScene(self.game, self.level_id))

    def draw(self) -> list[pygame.Rect] | None:
        if self.level is None:
            raise RuntimeError("GameplayScene has no level loaded")
        clock = self.game.clock
        fps = clock.get_fps() if clock else 0.0
        frame_time = clock.get_time() if clock else 0.0
        return self.level.draw(fps, game=self.game, frame_time=frame_time)
