"""An Xbox One pad: Start pauses, B attacks, and old files follow.

B was the menus' Back and the game's light attack, and the game paused on
Back -- so a light attack on the pad stopped the game. Start (the Menu button)
was the position reset.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pygame

from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.pause_scene import PauseScene
from src.application.settings_store import SettingsStore
from src.core.input.bindings_codec import bindings_to_dict
from src.core.input.event_router import EventRouter, InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import (
    XBOX_A,
    XBOX_B,
    XBOX_START,
    XBOX_VIEW,
    XBOX_X,
    XBOX_Y,
    InputBindings,
)


def test_the_default_layout_is_the_xbox_convention() -> None:
    pad = InputBindings().gameplay.gamepad_buttons
    assert pad[InputAction.JUMP] == XBOX_A
    assert pad[InputAction.ATTACK_1] == XBOX_X
    assert pad[InputAction.ATTACK_2] == XBOX_Y
    assert XBOX_B not in pad.values(), "two attack buttons: B is free"
    assert pad[InputAction.RESET] == XBOX_VIEW
    assert InputBindings().menu.gamepad_buttons[InputAction.UI_PAUSE] == XBOX_START
    assert XBOX_START not in pad.values(), "Start is the pause's alone"


def test_the_pad_buttons_route_as_the_menus_expect() -> None:
    router = EventRouter(InputBindings())

    def route(button: int) -> InputAction | None:
        routed = router.route(pygame.event.Event(pygame.JOYBUTTONDOWN, button=button, joy=0))
        return routed.action if routed is not None else None

    assert route(XBOX_A) is InputAction.UI_CONFIRM
    assert route(XBOX_B) is InputAction.UI_BACK
    assert route(XBOX_START) is InputAction.UI_PAUSE


def test_escape_stays_back_in_the_menus() -> None:
    router = EventRouter(InputBindings())
    routed = router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    assert routed is not None and routed.action is InputAction.UI_BACK


def test_the_game_pauses_on_start_and_escape_but_not_on_b() -> None:
    pauses = GameplayScene._pauses
    assert pauses(RoutedInput(InputAction.UI_PAUSE, InputDevice.GAMEPAD))
    assert pauses(RoutedInput(InputAction.UI_BACK, InputDevice.KEYBOARD))
    assert pauses(RoutedInput(InputAction.UI_BACK, InputDevice.MOUSE))
    assert not pauses(RoutedInput(InputAction.UI_BACK, InputDevice.GAMEPAD)), "B is an attack"


def test_start_resumes_from_the_pause_menu() -> None:
    popped: list[str] = []
    game = SimpleNamespace(
        ui_scale=1.0,
        scene_manager=SimpleNamespace(pop=lambda: popped.append("pop")),
    )
    PauseScene(game).handle_routed(RoutedInput(InputAction.UI_PAUSE, InputDevice.GAMEPAD))  # type: ignore[arg-type]
    assert popped == ["pop"]


def _old_default_file(path: Path) -> None:
    """A settings file as the game wrote it before the pause action existed."""
    data = bindings_to_dict(InputBindings())
    menu = data["menu"]
    gameplay = data["gameplay"]
    assert isinstance(menu, dict) and isinstance(gameplay, dict)
    del menu["gamepad_buttons"]["ui_pause"]
    del menu["keyboard"]["ui_pause"]
    gameplay["gamepad_buttons"] = {
        "jump": 0,
        "attack1": 1,
        "attack2": 2,
        "attack3": 3,
        "guard": 4,
        "attack4": 5,
        "reset": 7,
    }
    gameplay["gamepad_combos"] = {"special_attack": [1, 3]}
    path.write_text(json.dumps({"version": 4, "bindings": data}), encoding="utf-8")


def test_an_untouched_old_layout_moves_to_the_new_one(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _old_default_file(path)

    bindings = SettingsStore(path).load().bindings

    assert bindings.gameplay.gamepad_buttons == InputBindings().gameplay.gamepad_buttons
    assert bindings.gameplay.gamepad_combos == InputBindings().gameplay.gamepad_combos
    assert bindings.menu.gamepad_buttons[InputAction.UI_PAUSE] == XBOX_START
    assert bindings.menu.keyboard[InputAction.UI_PAUSE] == pygame.K_ESCAPE


def test_a_layout_the_player_built_is_kept_but_the_reset_leaves_start(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _old_default_file(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bindings"]["gameplay"]["gamepad_buttons"]["attack1"] = 9  # their own choice
    path.write_text(json.dumps(payload), encoding="utf-8")

    pad = SettingsStore(path).load().bindings.gameplay.gamepad_buttons

    assert pad[InputAction.ATTACK_1] == 9
    assert pad[InputAction.JUMP] == 0
    assert pad[InputAction.RESET] == XBOX_VIEW, "Start would pause and reset in one press"
