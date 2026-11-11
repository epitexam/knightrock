"""The game-over screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_page import MenuPage
from src.application.scenes.menu_scene import MenuScene
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem
from src.ui.styles import TEXT_CRIT
from src.ui.text import t

if TYPE_CHECKING:
    from src.application.game import Game


class GameOverScene(MenuPage):
    TITLE = t("title.game_over")
    TITLE_COLOR = TEXT_CRIT
    BACKGROUND = (16, 8, 10)
    opaque = True
    covers_panels_below = False
    #: The world stops; see ``Scene.halts_simulation`` for why saying so
    #: is not the same as simply not updating.
    halts_simulation = True

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(
            game, (MenuItem("retry", t("row.retry")), MenuItem("menu", t("row.to_menu")))
        )
        self.level_id = level_id

    def on_back_key(self, action: InputAction) -> str | None:
        self.game.scene_manager.switch(MenuScene(self.game))
        return MenuAction.BACK

    def act(self, action: str) -> None:
        if action == "retry":
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))
