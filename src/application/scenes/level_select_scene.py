"""The level list: every registered level, the locked ones greyed out."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_page import MenuPage
from src.presentation.ui.menu_model import MenuItem
from src.presentation.ui.text import t
from src.shared.colors import Colors

if TYPE_CHECKING:
    from src.application.scene_context import SceneContext


class LevelSelectScene(MenuPage):
    TITLE = t("title.levels")
    BACKGROUND = Colors.dark_grey
    opaque = True
    covers_panels_below = False
    scrollable = True

    def __init__(self, game: SceneContext) -> None:
        unlocked = set(game.save_game.unlocked_levels)
        levels = tuple(
            MenuItem(
                f"level:{level_id}", t("row.level", level=level_id), enabled=level_id in unlocked
            )
            for level_id in sorted(game.level_manager.level_paths)
        )
        super().__init__(game, (*levels, MenuItem("back", t("row.back"))))

    def act(self, action: str) -> None:
        if action.startswith("level:"):
            level_id = int(action.partition(":")[2])
            self.game.scene_manager.switch(GameplayScene(self.game, level_id))
