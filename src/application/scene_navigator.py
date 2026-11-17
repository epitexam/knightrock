"""Scene transitions that used to be local imports scattered across screens.

Each method imports its target lazily in one place. Screens ask for a
transition by name instead of importing the screen they navigate to, which
breaks the Gameplay/Menu/Pause/GameOver import cycle without a factory registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.scene_context import SceneContext


class SceneNavigator:
    """Named transitions over the active scene stack."""

    def __init__(self, game: SceneContext) -> None:
        self.game = game

    def switch_to_gameplay(self, level_id: int) -> None:
        from src.application.scenes.gameplay_scene import GameplayScene

        self.game.scene_manager.switch(GameplayScene(self.game, level_id))

    def push_game_over(self, level_id: int) -> None:
        from src.application.scenes.gameover_scene import GameOverScene

        self.game.scene_manager.push(GameOverScene(self.game, level_id))

    def switch_to_victory(self, level_id: int) -> None:
        from src.application.scenes.victory_scene import VictoryScene

        self.game.scene_manager.switch(VictoryScene(self.game, level_id))

    def push_pause(self, level_id: int) -> None:
        from src.application.scenes.pause_scene import PauseScene

        self.game.scene_manager.push(PauseScene(self.game, level_id))

    def push_level_select(self) -> None:
        from src.application.scenes.level_select_scene import LevelSelectScene

        self.game.scene_manager.push(LevelSelectScene(self.game))

    def push_options(self) -> None:
        from src.application.scenes.options_scene import OptionsScene

        self.game.scene_manager.push(OptionsScene(self.game))

    def push_video(self) -> None:
        from src.application.scenes.video_scene import VideoScene

        self.game.scene_manager.push(VideoScene(self.game))

    def push_controls_category(self) -> None:
        from src.application.scenes.controls_category_scene import ControlsCategoryScene

        self.game.scene_manager.push(ControlsCategoryScene(self.game))

    def push_controls(self, section: str) -> None:
        from src.application.scenes.controls_scene import ControlsScene

        self.game.scene_manager.push(ControlsScene(self.game, section))
