"""The level-complete screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.level_select_scene import LevelSelectScene
from src.application.scenes.menu_page import MenuPage
from src.application.scenes.menu_scene import MenuScene
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem
from src.ui.styles import TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class VictoryScene(MenuPage):
    TITLE = "VICTORY"
    TITLE_COLOR = TEXT_OK
    BACKGROUND = (12, 20, 14)
    opaque = True
    covers_panels_below = False
    #: The world stops; see ``Scene.halts_simulation`` for why saying so
    #: is not the same as simply not updating.
    halts_simulation = True

    def __init__(self, game: Game, level_id: int) -> None:
        super().__init__(
            game,
            (
                MenuItem("retry", "Retry"),
                MenuItem("levels", "Level select", kind="page"),
                MenuItem("menu", "Main menu"),
            ),
        )
        self.level_id = level_id

    def on_back_key(self, action: InputAction) -> str | None:
        self.game.scene_manager.switch(MenuScene(self.game))
        return MenuAction.BACK

    def on_device_removed(self) -> str | None:
        """A gamepad unplugged here also returns to the menu: the level is over."""
        return self.on_back_key(InputAction.UI_CANCEL)

    def act(self, action: str) -> None:
        if action == "retry":
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif action == "levels":
            self.game.scene_manager.push(LevelSelectScene(self.game))
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))
