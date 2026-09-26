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
from src.core.display.viewport import Viewport
from src.core.input.input_actions import InputAction
from src.core.level.level import Level
from src.core.settings import Gameplay
from tests.headless.conftest import make_programmatic_level_data, make_viewport


class RecordingScene(Scene):
    """Fake scene tracing its lifecycle."""

    def __init__(self, game, name: str):
        super().__init__(game)
        self.name = name
        self.events: list[str] = []
        self.drawn = False

    def enter(self) -> None:
        self.events.append(f"enter:{self.name}")

    def exit(self) -> None:
        self.events.append(f"exit:{self.name}")

    def update(self, delta_time: float) -> None:
        self.events.append(f"update:{self.name}")

    def draw(self, surface: pygame.Surface) -> None:
        self.drawn = True


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

    manager.draw(pygame.display.get_surface())
    assert gameplay.drawn and pause.drawn


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
    menu.draw(pygame.display.get_surface())
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
    menu.draw(pygame.display.get_surface())
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


def test_the_hat_and_the_stick_agree_on_which_way_is_up(manager: SceneManager):
    """The D-pad and the stick must not disagree about up.

    They did. SDL reports a hat in screen coordinates, so ``y = +1`` is pushed
    down, and the router had it the wrong way round -- while the axis path was
    right. So one physical push moved the menu up and the other moved it down.

    Nothing caught it because the hat was only ever exercised horizontally, and
    the old test fired the hat and the stick one after the other and only looked
    where the selection ended up: both were wrong in the same direction, so the
    end matched the expectation and the bug was invisible. Each control gets its
    own assertion here, from a known starting row, because a shared endpoint
    cannot tell a correct pair from a consistently inverted one.
    """

    def selection_after(event: pygame.event.Event) -> str:
        menu = MenuScene(manager.game)
        manager.switch(menu)
        assert menu.model.current_item is not None
        start = menu.model.current_item.action
        manager.handle_event(event)
        assert menu.model.current_item is not None
        return f"{start}->{menu.model.current_item.action}"

    up = pygame.event.Event(pygame.JOYHATMOTION, instance_id=0, hat=0, value=(0, -1))
    stick_up = pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=-0.8)
    down = pygame.event.Event(pygame.JOYHATMOTION, instance_id=0, hat=0, value=(0, 1))
    stick_down = pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.8)

    assert selection_after(up) == selection_after(stick_up)
    assert selection_after(down) == selection_after(stick_down)
    assert selection_after(up) != selection_after(down), "up and down moved the same way"


def test_the_dpad_needs_only_a_partial_push(manager: SceneManager):
    """A stick does not have to be flat for the menu to move.

    The trigger threshold was 0.5, so anything short of half the stick's travel
    did nothing. That reads as lag rather than as a stiff stick: you push, the
    menu stays, you push harder, and then it moves.
    """
    menu = MenuScene(manager.game)
    manager.switch(menu)
    before = menu.model.current_index

    manager.handle_event(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.45)
    )

    assert menu.model.current_index != before


def test_menu_navigation_supports_stick_and_hat(manager: SceneManager):
    """Lot 2 : la croix puis le stick déplacent la sélection, le bouton A valide."""
    menu = MenuScene(manager.game)
    manager.switch(menu)
    start = menu.model.current_index

    # One D-pad press, one stick press: two rows down from where we were.
    manager.handle_event(
        pygame.event.Event(pygame.JOYHATMOTION, instance_id=0, hat=0, value=(0, 1))
    )
    manager.handle_event(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.8))

    assert menu.model.current_index == start + 2

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
        make_viewport().surface,
        make_programmatic_level_data(),
        game_runtime.input_manager,
    )


def test_the_camera_viewport_ignores_the_window(manager: SceneManager):
    """The bug this rework exists for, stated as a test.

    The camera used to be built from the window's pixel size, so the slice of
    world the player saw was decided by a video setting: at a large enough
    resolution a whole level fitted on screen. The viewport is now the framing,
    and the only thing that moves it is the window -- which changes how large the
    world is *drawn*, at whatever density the window implies, and never how much
    of it is shown.
    """
    from src.core.display.framing import DEFAULT_FRAMING
    from src.core.display.letterbox import letterbox

    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)

    for window in ((640, 360), (1280, 720), (1920, 1080), (2560, 1440), (1000, 1000)):
        size = letterbox(window, DEFAULT_FRAMING).size
        surface = Viewport(DEFAULT_FRAMING, size).surface
        gameplay.set_surface(surface)

        assert gameplay.level is not None
        camera = gameplay.level.camera
        assert (camera.viewport_width, camera.viewport_height) == DEFAULT_FRAMING.size
        assert camera.density == pytest.approx(size[0] / DEFAULT_FRAMING.width)
        # And the framing still covers the target, to within the pixel that
        # rounding a letterbox and rounding a sprite size cannot both avoid.
        # The rule rounds a sprite's size *up* so neighbours overlap rather than
        # gap, which can overshoot the target by one row -- clipped away.
        camera.begin_frame(1.0)
        covered = camera.apply_snapped(
            pygame.FRect(0.0, 0.0, DEFAULT_FRAMING.width, DEFAULT_FRAMING.height)
        )
        assert abs(covered.width - surface.get_width()) <= 1
        assert abs(covered.height - surface.get_height()) <= 1


def test_a_surface_that_is_not_the_framing_is_refused(manager: SceneManager) -> None:
    """The window is not a target, and a target is not an arbitrary surface.

    A target whose two axes imply different densities is not the framing drawn at
    some density, so it is refused rather than half-honoured -- and the camera
    is left exactly as it was, rather than moved to a density nobody asked for.
    The window itself is not refused because it *is* one: ``set_surface`` is
    handed the window's letterbox rectangle, which is the whole design.
    """
    from src.core.display.framing import DEFAULT_FRAMING

    gameplay = GameplayScene(manager.game, level=_make_level(manager.game))
    manager.switch(gameplay)
    assert gameplay.level is not None
    before = (gameplay.level.camera.viewport_width, gameplay.level.camera.viewport_height)

    with pytest.raises(ValueError):
        gameplay.set_surface(pygame.Surface((1280, 700)))

    assert (gameplay.level.camera.viewport_width, gameplay.level.camera.viewport_height) == (before)
    assert before == DEFAULT_FRAMING.size


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


def test_the_cancel_button_leaves_a_capture_instead_of_binding(manager: SceneManager) -> None:
    """A pad must be able to back out of a rebind.

    It could not: every button was treated as a binding, so pressing anything
    assigned it and the "press a key" prompt stayed up. No button got you out,
    which reads as a frozen screen rather than a wrong one, and the only escape
    was the keyboard.

    The cancel button is exempt while it *is* the cancel button -- the same
    trade ESC makes on the keyboard -- and becomes bindable again once cancel is
    moved elsewhere, which the second half checks. Nothing is lost for good.
    """
    game = manager.game
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    manager.switch(controls)
    for _ in range(3):
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing

    cancel = game.settings.bindings.menu.gamepad_buttons[InputAction.UI_BACK]
    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=cancel))

    assert not controls.capturing, "the cancel button bound a key instead of leaving"
    assert manager.current is controls, "cancelling must not also pop the screen"
    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] != cancel


def test_escape_leaves_a_capture_on_either_column(manager: SceneManager) -> None:
    """ESC used to work only while capturing a *key*.

    Armed on a pad cell it fell through and did nothing, so the keyboard had the
    same dead end the pad had, just from the other device.
    """
    game = manager.game
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    manager.switch(controls)
    for _ in range(3):
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    # Arm the *pad* cell, which is the column that used to have no way out.
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing, "the pad cell should be armed"

    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert not controls.capturing
    assert manager.current is controls


def test_controls_rebinds_a_pad_button(manager: SceneManager) -> None:
    """Un bouton manette reste assignable."""
    game = manager.game
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    manager.switch(controls)
    for _ in range(3):
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert controls.capturing

    manager.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=7))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 7


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
        assert manager.draw(pygame.display.get_surface()) is None


def _level_select(manager: SceneManager) -> LevelSelectScene:
    """The level select, reached the way the menu reaches it."""
    manager.switch(MenuScene(manager.game))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(manager.current, LevelSelectScene)
    return manager.current


def test_the_level_select_offers_a_back_row(manager: SceneManager):
    """A row, not only a key.

    ESC, the gamepad B button and the right mouse button all left this screen,
    and a pointer had nothing to click. Every other menu offers the row *and*
    the keys, and a screen that can only be left with a keyboard is a screen a
    controller or a mouse cannot leave.
    """
    scene = _level_select(manager)

    assert [item.action for item in scene.model.items][-1] == "back"
    assert scene.model.items[-1].label == "Back"
    assert scene.model.items[-1].enabled


def test_the_back_row_leaves_the_level_select_with_the_keyboard(manager: SceneManager):
    scene = _level_select(manager)

    for _ in scene.model.items:
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, MenuScene)


def test_the_back_row_leaves_the_level_select_with_the_pointer(manager: SceneManager):
    """The click lands on the rectangle the view drew, not on an assumed row.

    The point of a row is that it is somewhere you can see, so the test uses the
    rectangle the panel published -- the same one a player's cursor is over.
    """
    from src.core.input.event_router import InputDevice, RoutedInput

    scene = _level_select(manager)
    scene.draw(pygame.display.get_surface())
    rect = scene.view.item_rects[-1]

    action = scene.handle_routed(
        RoutedInput(
            InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=rect.center
        )
    )

    assert action is not None and action.value == "back"
    assert isinstance(manager.current, MenuScene)


def test_a_locked_level_still_leaves_the_back_row_reachable(manager: SceneManager):
    """The row is not swallowed by a disabled neighbour.

    A disabled level is skipped by the selection, which is right, and the row
    after the list has to survive that: otherwise the only way out is a key the
    screen does not advertise.
    """
    scene = _level_select(manager)
    locked = [
        index
        for index, item in enumerate(scene.model.items)
        if not item.enabled
    ]

    for _ in range(len(scene.model.items) + len(locked)):
        manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert isinstance(manager.current, MenuScene)
