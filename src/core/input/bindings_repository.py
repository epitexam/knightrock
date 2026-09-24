import json
import logging
import os
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Any

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

logger = logging.getLogger(__name__)

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
    if not isinstance(data, str):
        raise ValueError("action must be a string")
    try:
        action = InputAction(data)
    except ValueError as error:
        raise ValueError(f"unknown action: {data}") from error
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
        },
    }


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
    gameplay = GameplayBindings(
        keyboard=_parse_action_map(gameplay_data["keyboard"], gameplay_actions, allow_pair=True),
        gamepad_buttons=_parse_int_map(gameplay_data["gamepad_buttons"], gameplay_actions),
        gamepad_axes=_parse_int_map(gameplay_data["gamepad_axes"], gameplay_actions),
        gamepad_hats=_parse_int_map(gameplay_data["gamepad_hats"], gameplay_actions),
        keyboard_combos=_parse_combo_map(gameplay_data["keyboard_combos"], gameplay_actions),
        gamepad_combos=_parse_combo_map(gameplay_data["gamepad_combos"], gameplay_actions),
    )
    menu = MenuBindings(
        keyboard=_parse_action_map(menu_data["keyboard"], menu_actions),
        gamepad_buttons=_parse_int_map(menu_data["gamepad_buttons"], menu_actions),
        gamepad_hats=_parse_int_map(menu_data["gamepad_hats"], menu_actions),
        gamepad_axes=_parse_int_map(menu_data["gamepad_axes"], menu_actions),
    )
    return InputBindings(gameplay=gameplay, menu=menu)


class BindingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_bindings_path()

    def load(self) -> InputBindings:
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
            return bindings_from_dict(data)
        except OSError, ValueError, TypeError, KeyError, json.JSONDecodeError:
            logger.warning("Unable to load input bindings, using defaults")
            return InputBindings()

    def save(self, bindings: InputBindings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bindings_to_dict(bindings), indent=2)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        temporary_path.replace(self.path)


def default_bindings_path() -> Path:
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
