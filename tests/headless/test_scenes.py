"""Application scene machine tests (audit F8.1, Phase 2 #4)."""

import json
from pathlib import Path

import pygame
import pytest

from src.application.save_game import SaveGame
from src.application.scene import Scene
from src.application.scene_manager import SceneManager
from src.application.scenes.controls_category_scene import ControlsCategoryScene
from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.gameover_scene import GameOverScene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.level_select_scene import LevelSelectScene
from src.application.scenes.menu_scene import MenuScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.pause_scene import PauseScene
from src.application.scenes.victory_scene import VictoryScene
from src.core.input.input_actions import InputAction
from src.core.level.level import Level
from src.core.settings import Gameplay
from tests.headless.conftest import make_programmatic_level_data


class RecordingScene(Scene):
    """Fake scene tracing its lifecycle."""

    def __init__(self, game, name: str):
        super().__init__(game)
        self.name = name
        self.events: list[str] = []
        self.dirty_called = False

    def enter(self) -> None:
        self.events.append(f"enter:{self.name}")

    def exit(self) -> None:
        self.events.append(f"exit:{self.name}")

    def update(self, delta_time: float) -> None:
        self.events.append(f"update:{self.name}")

    def draw(self) -> list[pygame.Rect]:
        self.dirty_called = True
        return []


@pytest.fixture()
def manager(game_runtime) -> SceneManager:
    return game_runtime.scene_manager


def test_switch_replaces_the_whole_stack(manager: SceneManager):
    first = RecordingScene(manager.game, "first")
    second = RecordingScene(manager.game, "second")

    manager.switch(first)
    manager.switch(second)

    assert manager.current is second
    assert first.events == ["enter:first", "exit:first"]
    assert second.events == ["enter:second"]


def test_push_freezes_the_scene_below_and_pop_resumes_it(manager: SceneManager):
    gameplay = RecordingScene(manager.game, "gameplay")
    pause = RecordingScene(manager.game, "pause")
    manager.switch(gameplay)
    manager.push(pause)

    manager.update(1 / 60)
    assert gameplay.events == ["enter:gameplay"]  # frozen: no update
    assert pause.events[-1] == "update:pause"

    manager.pop()
    assert manager.current is gameplay
    manager.update(1 / 60)
    assert "update:gameplay" in gameplay.events


def test_draw_draws_all_scenes_when_stacked(manager: SceneManager):
    gameplay = RecordingScene(manager.game, "gameplay")
    pause = RecordingScene(manager.game, "pause")
    manager.switch(gameplay)
    manager.push(pause)

    assert manager.draw() is None  # overlay: full refresh
    assert gameplay.dirty_called and pause.dirty_called


def test_popping_the_last_scene_stops_the_game(manager: SceneManager):
    manager.switch(RecordingScene(manager.game, "only"))

    manager.pop()

    assert manager.current is None
    assert manager.game.running is False


def test_menu_switches_to_gameplay_on_confirm(manager: SceneManager):
    manager.switch(MenuScene(manager.game))

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
    manager.handle_event(event)

    assert isinstance(manager.current, GameplayScene)


def test_menu_escape_stops_the_game(manager: SceneManager):
    manager.switch(MenuScene(manager.game))

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert manager.game.running is True

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert manager.game.running is False


def test_menu_quit_confirmation_defaults_to_no(manager: SceneManager):
    """Un menu principal: ni Échap ni la ligne Quit ne coupent plus net."""
    menu = MenuScene(manager.game)
    manager.switch(menu)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert menu.confirming is True
    assert manager.game.running is True
    assert menu.confirm_model.current_item.action == "no"

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert menu.confirming is False
    assert manager.game.running is True


def test_menu_quit_confirmation_cancels_on_back(manager: SceneManager):
    menu = MenuScene(manager.game)
    manager.switch(menu)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert menu.confirming is False
    assert manager.game.running is True


def test_menu_quit_confirmation_is_armed_by_the_quit_row(manager: SceneManager):
    menu = MenuScene(manager.game)
    manager.switch(menu)
    menu.draw()
    target = menu.view.item_rects[-1].center

    manager.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target))

    assert menu.confirming is True
    assert manager.game.running is True


def test_menu_navigation_supports_keyboard_and_gamepad(manager: SceneManager):
    manager.switch(MenuScene(manager.game))

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0))

    assert manager.game.running is True


def test_menu_navigation_supports_pointer(manager: SceneManager):
    menu = MenuScene(manager.game)
    manager.switch(menu)
    menu.draw()
    target = menu.view.item_rects[3].center

    manager.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target))

    assert manager.game.running is True


def test_options_opens_from_menu_and_pause(manager: SceneManager):
    """§9 : les Options restent atteignables depuis le menu et depuis la pause."""
    menu = MenuScene(manager.game)
    manager.switch(menu)
    for _ in range(len(menu.model.items)):
        if menu.model.current_item is not None and menu.model.current_item.action == "options":
            break
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, OptionsScene)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert isinstance(manager.current, MenuScene)

    manager.switch(GameplayScene(manager.game, level=_make_level(manager.game)))
    manager.push(PauseScene(manager.game, level_id=0))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, OptionsScene)


def test_menu_navigation_supports_stick_and_hat(manager: SceneManager):
    """Lot 2 : le hat puis le stick déplacent la sélection, le bouton A valide."""
    menu = MenuScene(manager.game)
    manager.switch(menu)

    manager.handle_event(
        pygame.event.Event(pygame.JOYHATMOTION, instance_id=0, hat=0, value=(0, -1))
    )
    manager.handle_event(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.8))

    assert menu.model.current_item is not None
    assert menu.model.current_item.action == "options"

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0))

    assert isinstance(manager.current, OptionsScene)


def test_level_select_opens_from_menu_and_returns(manager: SceneManager):
    manager.switch(MenuScene(manager.game))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, LevelSelectScene)
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert isinstance(manager.current, MenuScene)


def test_menus_go_back_with_gamepad_b(manager: SceneManager):
    """Bouton B (manette) : retour des menus, comme ESC."""
    manager.switch(MenuScene(manager.game))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(manager.current, LevelSelectScene)

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    assert isinstance(manager.current, MenuScene)


def test_menus_go_back_with_secondary_mouse_click(manager: SceneManager):
    """Clic droit : retour des menus, comme ESC."""
    manager.switch(MenuScene(manager.game))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(manager.current, LevelSelectScene)

    manager.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(4, 4)))

    assert isinstance(manager.current, MenuScene)


def test_game_over_returns_to_menu_with_gamepad_b(manager: SceneManager):
    manager.switch(GameOverScene(manager.game, level_id=0))

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    assert isinstance(manager.current, MenuScene)


def test_pause_resumes_with_gamepad_b(manager: SceneManager):
    """Bouton B : ferme la pause et relance la partie, comme ESC."""
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)
    manager.push(PauseScene(manager.game, level_id=0))

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    assert manager.current is gameplay


def test_victory_returns_to_menu_with_secondary_mouse_click(manager: SceneManager):
    manager.switch(VictoryScene(manager.game, level_id=1))

    manager.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(4, 4)))

    assert isinstance(manager.current, MenuScene)


def test_victory_can_open_level_select(manager: SceneManager):
    manager.switch(VictoryScene(manager.game, level_id=0))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, LevelSelectScene)


def _make_level(game_runtime) -> Level:
    return Level(
        pygame.display.get_surface(),
        make_programmatic_level_data(),
        game_runtime.input_manager,
    )


def test_level_camera_viewport_matches_the_chosen_resolution(manager: SceneManager):
    """Le viewport caméra est la résolution choisie, pas les constantes Display.

    La fenêtre n'étant pas redimensionnable, la résolution du menu vidéo est
    le viewport stable du jeu. Si la caméra gardait 1440x900 dans une fenêtre
    1280x720, des sprites visibles seraient écartés par le culling.
    """
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    for width, height in ((1280, 720), (1920, 1080)):
        surface = pygame.Surface((width, height))
        gameplay.set_display_surface(surface)

        assert gameplay.level is not None
        assert (gameplay.level.camera.width, gameplay.level.camera.height) == (width, height)


def test_gameplay_escape_pushes_pause(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert isinstance(manager.current, PauseScene)
    manager.pop()
    assert manager.current is gameplay


def test_pause_confirm_resumes_gameplay(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)
    manager.push(PauseScene(manager.game, level_id=0))

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert manager.current is gameplay


def test_gameplay_death_limit_pushes_game_over(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    gameplay.level.deaths = Gameplay.MAX_DEATHS
    gameplay.update(1 / 60)

    assert isinstance(manager.current, GameOverScene)


def test_gameplay_completed_without_next_level_shows_victory(manager: SceneManager):
    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    gameplay.level.exit_reached = True
    gameplay.update(1 / 60)

    assert isinstance(manager.current, VictoryScene)


def test_game_over_retry_restarts_the_level(manager: SceneManager):
    game_over = GameOverScene(manager.game, level_id=0)
    manager.switch(game_over)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, GameplayScene)
    assert manager.current.level_id == 0


def test_level_completed_event_unlocks_and_persists_progression(game_runtime):
    """LevelCompleted → unlock level_unlock + JSON write (Phase 2 #6)."""
    from src.application.events import LevelCompleted

    game_runtime.events.emit(LevelCompleted(level_id=0, unlock_level_id=1))

    save = game_runtime.save_game
    assert save.is_unlocked(1)
    assert save.last_level_id == 0
    assert game_runtime._save_path.exists()  # noqa: SLF001 - internal store check
    assert SaveGame.load(game_runtime._save_path) == save  # noqa: SLF001


def test_completed_level_without_unlock_value_still_persists_last_level(game_runtime):
    from src.application.events import LevelCompleted

    game_runtime.events.emit(LevelCompleted(level_id=0))

    assert game_runtime.save_game.last_level_id == 0
    assert game_runtime.save_game.unlocked_levels == [0]


def test_menu_offers_continue_when_progress_exists(game_runtime):
    from src.application.events import LevelCompleted
    from src.application.scenes.gameplay_scene import GameplayScene

    game_runtime.events.emit(LevelCompleted(level_id=0, unlock_level_id=1))
    game_runtime.scene_manager.switch(MenuScene(game_runtime))
    menu = game_runtime.scene_manager.current

    assert "continue" in menu.options[0]
    assert len(menu.options) == 5

    routed = game_runtime.input_router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n))
    assert routed is not None
    menu.handle_routed(routed)

    assert isinstance(game_runtime.scene_manager.current, GameplayScene)
    assert game_runtime.scene_manager.current.level_id == 0


def test_menu_continue_starts_at_last_level(game_runtime, monkeypatch):
    from src.application.events import LevelCompleted
    from src.application.scenes.gameplay_scene import GameplayScene
    from tests.headless.conftest import make_programmatic_level_data

    # Level 1 has no TMX yet: stub the manager loading.
    monkeypatch.setattr(
        game_runtime.level_manager, "get", lambda _level_id: make_programmatic_level_data()
    )
    game_runtime.events.emit(LevelCompleted(level_id=0, unlock_level_id=1))
    game_runtime.save_game.last_level_id = 1
    game_runtime.scene_manager.switch(MenuScene(game_runtime))

    menu = game_runtime.scene_manager.current
    routed = game_runtime.input_router.route(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
    )
    assert routed is not None
    menu.handle_routed(routed)

    assert isinstance(game_runtime.scene_manager.current, GameplayScene)
    assert game_runtime.scene_manager.current.level_id == 1


def test_controls_screen_rebinds_and_persists(manager: SceneManager, tmp_path: Path) -> None:
    """UI-5 : Options → Contrôles capture une touche et écrit settings.json."""
    game = manager.game
    options = OptionsScene(game)
    manager.switch(options)
    for _ in range(len(options.model.items)):
        current = options.model.current_item
        if current is not None and current.action == "controls":
            break
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    controls = manager.current
    assert isinstance(controls, ControlsCategoryScene)
    assert [item.action for item in controls.model.items] == ["menu", "gameplay", "back"]

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    menu_controls = manager.current
    assert isinstance(menu_controls, ControlsScene)
    assert menu_controls.section == ControlsScene.MENU_SECTION

    manager.pop()
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    gameplay_controls = manager.current
    assert isinstance(gameplay_controls, ControlsScene)
    assert gameplay_controls.section == ControlsScene.GAMEPLAY_SECTION

    manager.pop()
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    menu_controls = manager.current
    assert isinstance(menu_controls, ControlsScene)
    assert menu_controls.section == ControlsScene.MENU_SECTION

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert menu_controls.capturing

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x))

    assert game.settings.bindings.menu.keyboard[InputAction.UI_DOWN] == pygame.K_x
    # L'appui qui termine la capture était routé (X = ui_down) : neutralisé.
    assert menu_controls.model.current_index == 1
    # Les écritures sont groupées par frame : la boucle les vide, ce test drive
    # le SceneManager sans boucle, il demande donc le flush explicitement.
    game.flush_settings()
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["bindings"]["menu"]["keyboard"]["ui_down"] == pygame.K_x

    # Le routeur applique le nouveau binding pour la suite du parcours.
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x))
    assert menu_controls.model.current_index == 2


def test_options_controls_is_a_category_with_two_submenus(manager: SceneManager) -> None:
    options = OptionsScene(manager.game)
    manager.switch(options)
    for _ in range(len(options.model.items)):
        current = options.model.current_item
        if current is not None and current.action == "controls":
            break
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    category = manager.current
    assert isinstance(category, ControlsCategoryScene)
    assert [item.action for item in category.model.items] == ["menu", "gameplay", "back"]

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(manager.current, ControlsScene)
    assert manager.current.section == ControlsScene.MENU_SECTION


def test_controls_capture_cancels_with_escape_before_leaving(manager: SceneManager) -> None:
    """ESC annule la capture ; un second ESC quitte l'écran."""
    game = manager.game
    menu = MenuScene(game)
    manager.switch(menu)
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    manager.push(controls)

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not controls.capturing
    assert manager.current is controls

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert manager.current is menu


def test_controls_rebinds_a_pad_button_and_can_reassign_b(manager: SceneManager) -> None:
    """Un bouton manette reste assignable, y compris B."""
    game = manager.game
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    manager.switch(controls)
    for _ in range(3):
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=7))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 7

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing
    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 1
    assert manager.current is controls


def test_all_menu_screens_draw_without_dedicated_display(manager: SceneManager) -> None:
    """§9 : chaque écran plein-écran se dessine (remplace les tests menu_panel)."""
    game = manager.game
    scenes: list[Scene] = [
        MenuScene(game),
        LevelSelectScene(game),
        OptionsScene(game),
        ControlsCategoryScene(manager.game),
        ControlsScene(game, ControlsScene.MENU_SECTION),
        ControlsScene(game, ControlsScene.GAMEPLAY_SECTION),
        PauseScene(game, level_id=0),
        GameOverScene(game, level_id=0),
        VictoryScene(game, level_id=0),
    ]

    for scene in scenes:
        manager.switch(scene)
        assert manager.draw() is None
