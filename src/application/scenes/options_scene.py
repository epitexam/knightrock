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
from src.presentation.ui.menu_model import MenuItem
from src.presentation.ui.text import t

if TYPE_CHECKING:
    from src.application.scene_context import SceneContext


class OptionsScene(MenuPage):
    TITLE = t("title.options")

    def __init__(self, game: SceneContext) -> None:
        super().__init__(
            game,
            (
                MenuItem("video", t("row.video"), kind="page"),
                MenuItem("controls", t("row.controls"), kind="page"),
                MenuItem("back", t("row.back")),
            ),
        )

    def act(self, action: str) -> None:
        if action == "video":
            self.game.scene_manager.navigator.push_video()
        elif action == "controls":
            self.game.scene_manager.navigator.push_controls_category()
