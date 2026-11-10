"""Category menu for the two control-mapping screens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.menu_page import MenuPage
from src.ui.menu_model import MenuItem

if TYPE_CHECKING:
    from src.core.game import Game


class ControlsCategoryScene(MenuPage):
    TITLE = "CONTROLS"

    def __init__(self, game: Game) -> None:
        super().__init__(
            game,
            (
                MenuItem("menu", "Menu controls", kind="page"),
                MenuItem("gameplay", "Gameplay controls", kind="page"),
                MenuItem("back", "Back"),
            ),
        )

    def act(self, action: str) -> None:
        if action == "menu":
            self.game.scene_manager.push(ControlsScene(self.game, ControlsScene.MENU_SECTION))
        elif action == "gameplay":
            self.game.scene_manager.push(ControlsScene(self.game, ControlsScene.GAMEPLAY_SECTION))
