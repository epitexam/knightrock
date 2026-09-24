import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import (
    ActionMap,
    AxisMap,
    ButtonMap,
    ComboMap,
    GameplayBindings,
    InputBindings,
    KeyBinding,
    MenuBindings,
)

BINDINGS_FORMAT_VERSION = 1


def _serialize_action_map(values: ActionMap) -> dict[str, object]:
    return {
        action.value: list(value) if isinstance(value, tuple) else value
        for action, value in values.items()
    }


def _serialize_int_map(values: ButtonMap | AxisMap) -> dict[str, object]:
    return {action.value: value for action, value in values.items()}


def _serialize_combo_map(values: ComboMap) -> dict[str, object]:
    return {action.value: list(value) for action, value in values.items()}


def _parse_action(data: object, allowed: set[InputAction]) -> InputAction:
    if isinstance(data, InputAction):
        action = data
    elif isinstance(data, str):
        try:
            action = InputAction(data)
        except ValueError as error:
            raise ValueError(f"unknown action: {data}") from error
    else:
        raise ValueError("action must be a string")
    if action not in allowed:
        raise ValueError(f"action not allowed in context: {data}")
    return action


def _parse_key_value(value: object, action: InputAction, allow_pair: bool) -> KeyBinding:
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            raise ValueError("key code must be positive")
        return value
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        if not value or (allow_pair and len(value) != 2):
            raise ValueError("invalid key binding")
        return tuple(value)
    if action is InputAction.MOVE_X and allow_pair:
        raise ValueError("MOVE_X requires a pair of keys")
    raise ValueError("invalid key binding")


def _parse_action_map(
    data: object, allowed: set[InputAction], allow_pair: bool = False
) -> ActionMap:
    if not isinstance(data, dict):
        raise ValueError("action map must be an object")
    result: dict[InputAction, KeyBinding] = {}
    for raw_action, raw_value in data.items():
        action = _parse_action(raw_action, allowed)
        result[action] = _parse_key_value(raw_value, action, allow_pair)
    return MappingProxyType(result)


def _parse_int_map(data: object, allowed: set[InputAction]) -> ButtonMap:
    if not isinstance(data, dict):
        raise ValueError("integer map must be an object")
    result: dict[InputAction, int] = {}
    for raw_action, raw_value in data.items():
        action = _parse_action(raw_action, allowed)
        if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value < 0:
            raise ValueError("binding index must be a non-negative integer")
        result[action] = raw_value
    return MappingProxyType(result)


def _parse_combo_map(data: object, allowed: set[InputAction]) -> ComboMap:
    if not isinstance(data, dict):
        raise ValueError("combo map must be an object")
    result: dict[InputAction, tuple[int, ...]] = {}
    for raw_action, raw_value in data.items():
        action = _parse_action(raw_action, allowed)
        if not isinstance(raw_value, list) or not raw_value:
            raise ValueError("combo must be a non-empty list")
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in raw_value):
            raise ValueError("combo values must be integers")
        result[action] = tuple(raw_value)
    return MappingProxyType(result)


def bindings_to_dict(bindings: InputBindings) -> dict[str, object]:
    gameplay = bindings.gameplay
    menu = bindings.menu
    return {
        "version": BINDINGS_FORMAT_VERSION,
        "gameplay": {
            "keyboard": _serialize_action_map(gameplay.keyboard),
            "gamepad_buttons": _serialize_int_map(gameplay.gamepad_buttons),
            "gamepad_axes": _serialize_int_map(gameplay.gamepad_axes),
            "gamepad_hats": _serialize_int_map(gameplay.gamepad_hats),
            "keyboard_combos": _serialize_combo_map(gameplay.keyboard_combos),
            "gamepad_combos": _serialize_combo_map(gameplay.gamepad_combos),
        },
        "menu": {
            "keyboard": _serialize_action_map(menu.keyboard),
            "gamepad_buttons": _serialize_int_map(menu.gamepad_buttons),
            "gamepad_hats": _serialize_int_map(menu.gamepad_hats),
            "gamepad_axes": _serialize_int_map(menu.gamepad_axes),
            "new_game_key": menu.new_game_key,
            "invert_y": menu.invert_y,
        },
    }


def _require_actions(mapping: object, required: set[InputAction], context: str) -> None:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{context} must be an object")
    present = {_parse_action(action, required) for action in mapping}
    missing = required - present
    if missing:
        raise ValueError(
            f"{context} is missing actions: {sorted(action.value for action in missing)}"
        )


def _validate_context(
    keyboard: ActionMap,
    buttons: ButtonMap,
    axes: AxisMap,
    hats: ButtonMap,
    keyboard_required: set[InputAction],
    buttons_required: set[InputAction],
    axes_required: set[InputAction],
    hats_required: set[InputAction],
    context: str,
) -> None:
    _require_actions(keyboard, keyboard_required, f"{context}.keyboard")
    _require_actions(buttons, buttons_required, f"{context}.gamepad_buttons")
    _require_actions(axes, axes_required, f"{context}.gamepad_axes")
    _require_actions(hats, hats_required, f"{context}.gamepad_hats")


def bindings_from_dict(data: object) -> InputBindings:
    if not isinstance(data, dict) or data.get("version") != BINDINGS_FORMAT_VERSION:
        raise ValueError("unsupported bindings schema")
    gameplay_data = data["gameplay"]
    menu_data = data["menu"]
    if not isinstance(gameplay_data, dict) or not isinstance(menu_data, dict):
        raise ValueError("bindings contexts must be objects")
    gameplay_actions = {
        InputAction.MOVE_X,
        InputAction.MOVE_DOWN,
        InputAction.JUMP,
        InputAction.DASH,
        InputAction.GUARD,
        InputAction.RESET,
        InputAction.ATTACK_1,
        InputAction.ATTACK_2,
        InputAction.ATTACK_3,
        InputAction.ATTACK_4,
        InputAction.SPECIAL_ATTACK,
    }
    menu_actions = {
        InputAction.UI_UP,
        InputAction.UI_DOWN,
        InputAction.UI_LEFT,
        InputAction.UI_RIGHT,
        InputAction.UI_CONFIRM,
        InputAction.UI_BACK,
        InputAction.UI_CANCEL,
    }
    gameplay_keyboard = _parse_action_map(
        gameplay_data["keyboard"], gameplay_actions, allow_pair=True
    )
    gameplay_buttons = _parse_int_map(gameplay_data["gamepad_buttons"], gameplay_actions)
    gameplay_axes = _parse_int_map(gameplay_data["gamepad_axes"], gameplay_actions)
    gameplay_hats = _parse_int_map(gameplay_data["gamepad_hats"], gameplay_actions)
    gameplay_keyboard_combos = _parse_combo_map(gameplay_data["keyboard_combos"], gameplay_actions)
    gameplay_gamepad_combos = _parse_combo_map(gameplay_data["gamepad_combos"], gameplay_actions)
    menu_keyboard = _parse_action_map(menu_data["keyboard"], menu_actions)
    menu_buttons = _parse_int_map(menu_data["gamepad_buttons"], menu_actions)
    menu_hats = _parse_int_map(menu_data["gamepad_hats"], menu_actions)
    menu_axes = _parse_int_map(menu_data["gamepad_axes"], menu_actions)
    new_game_key = menu_data.get("new_game_key", pygame.K_n)
    if new_game_key is not None and (
        not isinstance(new_game_key, int) or isinstance(new_game_key, bool) or new_game_key < 0
    ):
        raise ValueError("menu.new_game_key must be a non-negative integer or null")
    invert_y = menu_data.get("invert_y", False)
    if not isinstance(invert_y, bool):
        raise ValueError("menu.invert_y must be boolean")

    _validate_context(
        gameplay_keyboard,
        gameplay_buttons,
        gameplay_axes,
        gameplay_hats,
        gameplay_actions - {InputAction.SPECIAL_ATTACK},
        {
            InputAction.JUMP,
            InputAction.ATTACK_1,
            InputAction.ATTACK_2,
            InputAction.ATTACK_3,
            InputAction.ATTACK_4,
            InputAction.GUARD,
            InputAction.RESET,
        },
        {InputAction.MOVE_X, InputAction.DASH, InputAction.MOVE_DOWN},
        {InputAction.MOVE_X, InputAction.MOVE_DOWN},
        "gameplay",
    )
    if InputAction.SPECIAL_ATTACK not in gameplay_keyboard_combos:
        raise ValueError("gameplay.keyboard_combos is missing special_attack")
    if InputAction.SPECIAL_ATTACK not in gameplay_gamepad_combos:
        raise ValueError("gameplay.gamepad_combos is missing special_attack")
    _validate_context(
        menu_keyboard,
        menu_buttons,
        menu_axes,
        menu_hats,
        menu_actions,
        {InputAction.UI_CONFIRM, InputAction.UI_CANCEL},
        {
            InputAction.UI_LEFT,
            InputAction.UI_RIGHT,
            InputAction.UI_UP,
            InputAction.UI_DOWN,
        },
        {
            InputAction.UI_LEFT,
            InputAction.UI_RIGHT,
            InputAction.UI_UP,
            InputAction.UI_DOWN,
        },
        "menu",
    )
    gameplay = GameplayBindings(
        keyboard=gameplay_keyboard,
        gamepad_buttons=gameplay_buttons,
        gamepad_axes=gameplay_axes,
        gamepad_hats=gameplay_hats,
        keyboard_combos=gameplay_keyboard_combos,
        gamepad_combos=gameplay_gamepad_combos,
    )
    menu = MenuBindings(
        keyboard=menu_keyboard,
        gamepad_buttons=menu_buttons,
        gamepad_hats=menu_hats,
        gamepad_axes=menu_axes,
        new_game_key=new_game_key,
        invert_y=invert_y,
    )
    return InputBindings(gameplay=gameplay, menu=menu)


class BindingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_bindings_path()

    def load(self) -> InputBindings:
        from src.application.settings_store import SettingsStore

        return SettingsStore(self.path).load().bindings

    def save(self, bindings: InputBindings) -> None:
        from src.application.settings_store import SettingsStore

        store = SettingsStore(self.path)
        store.save(store.load().with_bindings(bindings))


def default_bindings_path() -> Path:
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
