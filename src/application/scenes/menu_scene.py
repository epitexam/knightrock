from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.core.colors import Colors
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class MenuScene(Scene):
    TITLE = "KNIGHTROCK"
    CONFIRM_TITLE = "QUIT?"
    CONFIRM_ITEMS = (MenuItem("no", "No, go back"), MenuItem("yes", "Yes, quit"))

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        save = game.save_game
        has_progress = save.last_level_id != 0 or len(save.unlocked_levels) > 1
        items: tuple[MenuItem, ...]
        self.options: tuple[str, ...]
        if has_progress:
            items = (
                MenuItem("continue", f"Continue (level {save.last_level_id})"),
                MenuItem("new_game", "New game"),
                MenuItem("levels", "Level select"),
                MenuItem("options", "Options"),
                MenuItem("quit", "Quit"),
            )
            self.options = (
                f"ENTER: continue (level {save.last_level_id})",
                "N: new game",
                "LEVEL SELECT",
                "OPTIONS",
                "ESC: quit",
            )
        else:
            items = (
                MenuItem("play", "Play"),
                MenuItem("levels", "Level select"),
                MenuItem("options", "Options"),
                MenuItem("quit", "Quit"),
            )
            self.options = ("ENTER: play", "ESC: quit")
        self.model = MenuModel(items)
        self.view = MenuView()
        self.confirm_model = MenuModel(self.CONFIRM_ITEMS)
        self.confirm_view = MenuView()
        self._confirming = False

    @property
    def confirming(self) -> bool:
        """Whether the quit confirmation is currently armed."""
        return self._confirming

    def _arm_quit(self) -> None:
        """Ask for confirmation instead of quitting straight away.

        Quitting on a single stray Escape threw away the run without warning,
        so the prompt is drawn under the menu and defaults to "No".
        """
        self._confirming = True
        self.confirm_model.set_items(self.CONFIRM_ITEMS, 0)

    def _disarm_quit(self) -> None:
        self._confirming = False

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if self._confirming:
            return self._handle_confirm(routed_input)
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "quit" or routed_input.action is InputAction.UI_BACK:
            # Same outcome either way — arming the prompt — so both report the
            # dismissal, and the row does not sound different from the key.
            self._arm_quit()
            return MenuAction.BACK
        if action in ("play", "continue"):
            save = self.game.save_game
            start_id = save.last_level_id if save.is_unlocked(save.last_level_id) else 0
            self.game.scene_manager.switch(GameplayScene(self.game, start_id))
        elif action == "new_game":
            self.game.scene_manager.switch(GameplayScene(self.game, 0))
        elif action == "levels":
            from src.application.scenes.level_select_scene import LevelSelectScene

            self.game.scene_manager.push(LevelSelectScene(self.game))
        elif action == "options":
            from src.application.scenes.options_scene import OptionsScene

            self.game.scene_manager.push(OptionsScene(self.game))
        return action

    def _handle_confirm(self, routed_input: RoutedInput) -> str | None:
        """Route input to the confirmation panel, which owns it while armed."""
        if (
            routed_input.action is InputAction.UI_BACK
            or routed_input.action is InputAction.UI_CANCEL
        ):
            self._disarm_quit()
            return MenuAction.BACK
        action, _ = self.confirm_model.handle_routed(
            routed_input.action,
            routed_input.position,
            self.confirm_view.item_rects,
            routed_input.variant,
        )
        if action == "yes":
            self.game.running = False
        elif action == "no":
            self._disarm_quit()
            return MenuAction.BACK
        return action

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)
        self.confirm_view.set_scale(scale)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(Colors.dark_grey)
        panel = self.view.draw(surface, self.TITLE, self.model, top=180)
        if self._confirming:
            self.confirm_view.draw(
                surface, self.CONFIRM_TITLE, self.confirm_model, top=panel.bottom + 24
            )
