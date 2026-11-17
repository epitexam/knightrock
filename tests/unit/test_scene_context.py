"""Scenes depend on a declared context, not on the concrete runtime."""

from src.application.game import Game
from src.application.scene_context import SceneContext
from src.application.scenes.menu_scene import MenuScene


def test_game_satisfies_the_scene_context() -> None:
    game = Game()
    context: SceneContext = game

    context.quit()

    assert game.running is False


def test_a_scene_accepts_the_context_type() -> None:
    game = Game()

    scene = MenuScene(game)

    assert scene.game is game
