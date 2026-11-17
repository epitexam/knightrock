"""Scene transitions are named, and the imports live in one place."""

from src.application.scene_navigator import SceneNavigator
from src.application.scenes.controls_category_scene import ControlsCategoryScene
from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.gameover_scene import GameOverScene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.level_select_scene import LevelSelectScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.pause_scene import PauseScene
from src.application.scenes.victory_scene import VictoryScene


class _Manager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def switch(self, scene: object) -> None:
        self.calls.append(("switch", scene))

    def push(self, scene: object) -> None:
        self.calls.append(("push", scene))


class _Game:
    def __init__(self) -> None:
        self.scene_manager = _Manager()
        self.ui_scale = 1.0
        self.save_game = type("Save", (), {"unlocked_levels": [0]})()
        self.settings = type("Settings", (), {"bindings": object()})()
        self.level_manager = type("Levels", (), {"level_paths": {0: "level.tmx"}})()


def test_named_transitions_build_the_expected_scene() -> None:
    game = _Game()
    navigator = SceneNavigator(game)  # type: ignore[arg-type]

    navigator.switch_to_gameplay(2)
    navigator.push_game_over(2)
    navigator.switch_to_victory(2)
    navigator.push_pause(2)
    navigator.push_level_select()
    navigator.push_options()
    navigator.push_controls_category()
    navigator.push_controls("menu")

    assert [kind for kind, _ in game.scene_manager.calls] == [
        "switch",
        "push",
        "switch",
        "push",
        "push",
        "push",
        "push",
        "push",
    ]
    scenes = [scene for _, scene in game.scene_manager.calls]
    assert isinstance(scenes[0], GameplayScene)
    assert isinstance(scenes[1], GameOverScene)
    assert isinstance(scenes[2], VictoryScene)
    assert isinstance(scenes[3], PauseScene)
    assert isinstance(scenes[4], LevelSelectScene)
    assert isinstance(scenes[5], OptionsScene)
    assert isinstance(scenes[6], ControlsCategoryScene)
    assert isinstance(scenes[7], ControlsScene)
