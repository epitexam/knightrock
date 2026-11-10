"""The pause menu, drawn over the frozen world."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.menu_page import MenuPage
from src.application.scenes.menu_scene import MenuScene
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem
from src.ui.styles import TEXT_WARN

if TYPE_CHECKING:
    from src.core.game import Game


class PauseScene(MenuPage):
    TITLE = "PAUSE"
    TITLE_COLOR = TEXT_WARN
    #: The world stops; see ``Scene.halts_simulation`` for why saying so
    #: is not the same as simply not updating. The world stays visible under
    #: the stack's veil, because the page covers the panels below it.
    halts_simulation = True

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(
            game,
            (
                MenuItem("resume", "Resume"),
                MenuItem("options", "Options", kind="page"),
                MenuItem("menu", "Back to menu"),
            ),
        )
        self.level_id = level_id

    def on_back_key(self, action: InputAction) -> str | None:
        """Back resumes; Cancel goes to the main menu."""
        if action is InputAction.UI_BACK:
            self.game.scene_manager.pop()
        else:
            self.game.scene_manager.switch(MenuScene(self.game))
        return MenuAction.BACK

    def act(self, action: str) -> None:
        if action == "resume":
            self.game.scene_manager.pop()
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))
        elif action == "options":
            from src.application.scenes.options_scene import OptionsScene

            self.game.scene_manager.push(OptionsScene(self.game))
