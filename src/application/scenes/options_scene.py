"""Options hub: a category menu over the dedicated settings screens.

Every actual setting lives in the screen that owns it, so a value has a
single source of truth and a single place to change it:

- **Video settings** — the window's size, how the picture fits it, VSync, frame
  limit, UI scale;
- **Controls** — key/button rebinding and the menu stick Y inversion.

This screen is navigation only: it holds no toggle of its own, hence no
"reset" here either. Each sub-menu resets exactly what it owns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.scenes.menu_page import MenuPage
from src.ui.menu_model import MenuItem

if TYPE_CHECKING:
    from src.core.game import Game


class OptionsScene(MenuPage):
    TITLE = "OPTIONS"

    def __init__(self, game: Game) -> None:
        super().__init__(
            game,
            (
                MenuItem("video", "Video settings", kind="page"),
                MenuItem("controls", "Controls", kind="page"),
                MenuItem("back", "Back"),
            ),
        )

    def act(self, action: str) -> None:
        if action == "video":
            from src.application.scenes.video_scene import VideoScene

            self.game.scene_manager.push(VideoScene(self.game))
        elif action == "controls":
            from src.application.scenes.controls_category_scene import ControlsCategoryScene

            self.game.scene_manager.push(ControlsCategoryScene(self.game))
