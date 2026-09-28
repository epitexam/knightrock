import os
from pathlib import Path
from types import MappingProxyType
from typing import cast

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
    PadBinding,
)

BINDINGS_FORMAT_VERSION = 1

# Actions bound as a (left, right) pair: the keyboard stores them as a tuple,
# and ``gamepad_buttons`` can take a pair of buttons for pads that expose their
# d-pad as buttons.
_PAIR_ACTIONS = frozenset({InputAction.MOVE_X})


def _serialize_flat_map(values: ActionMap | ButtonMap | AxisMap) -> dict[str, object]:
    """Key an action map by its enum's value, widening any tuple to a list.

    One implementation for all three: a key map and a button/axis map are the
    same shape, and the two functions that used to be here differed only in
    their annotation.
    """
    return {
        action.value: list(value) if isinstance(value, tuple) else value
        for action, value in values.items()
    }


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
    pair_required = allow_pair and action in _PAIR_ACTIONS
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            raise ValueError("key code must be positive")
        if pair_required:
            # move_x is a (left, right) pair: a single int would break
            # ``InputProvider._calculate_move_axis``.
            raise ValueError(f"{action.value} requires a pair of keys")
        return value
    if isinstance(value, list) and all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        if not value or (allow_pair and len(value) != 2):
            raise ValueError("invalid key binding")
        return tuple(value)
    raise ValueError("invalid key binding")


def _repair_menu_direction_conflicts(bindings: ActionMap) -> ActionMap:
    """Restore defaults for every arrow involved in an old conflict."""
    defaults = {
        InputAction.UI_UP: pygame.K_UP,
        InputAction.UI_DOWN: pygame.K_DOWN,
        InputAction.UI_LEFT: pygame.K_LEFT,
        InputAction.UI_RIGHT: pygame.K_RIGHT,
    }
    result = dict(bindings)
    by_key: dict[int, list[InputAction]] = {}
    for action in defaults:
        value = result.get(action)
        if isinstance(value, int):
            by_key.setdefault(value, []).append(action)
    for actions in by_key.values():
        if len(actions) > 1:
            for action in actions:
                result[action] = defaults[action]
    return MappingProxyType(result)


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


def _int_index(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _parse_int_map(data: object, allowed: set[InputAction], allow_pair: bool = False) -> ButtonMap:
    """Parse a single SDL index, or MOVE_X's (left, right) pair.

    ``allow_pair`` is opened only for the gameplay context, so a pad that
    exposes its d-pad as buttons (Xbox/SDL2) can bind horizontal movement to two
    buttons the way the keyboard does.
    """
    if not isinstance(data, dict):
        raise ValueError("integer map must be an object")
    result: dict[InputAction, PadBinding] = {}
    for raw_action, raw_value in data.items():
        action = _parse_action(raw_action, allowed)
        single = _int_index(raw_value)
        if single is not None:
            if allow_pair and action in _PAIR_ACTIONS:
                raise ValueError(f"{action.value} requires a pair of indices")
            result[action] = single
            continue
        if (
            isinstance(raw_value, list)
            and allow_pair
            and action in _PAIR_ACTIONS
            and len(raw_value) == 2
        ):
            left, right = (_int_index(item) for item in raw_value)
            if left is None or right is None:
                raise ValueError("binding index must be a non-negative integer")
            result[action] = (left, right)
            continue
        raise ValueError("binding index must be a non-negative integer")
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
    """Serialise back to the on-disk schema, the exact inverse of `bindings_from_dict`."""
    gameplay = bindings.gameplay
    menu = bindings.menu
    return {
        "version": BINDINGS_FORMAT_VERSION,
        "gameplay": {
            "keyboard": _serialize_flat_map(gameplay.keyboard),
            "gamepad_buttons": _serialize_flat_map(gameplay.gamepad_buttons),
            "gamepad_axes": _serialize_flat_map(gameplay.gamepad_axes),
            "gamepad_hats": _serialize_flat_map(gameplay.gamepad_hats),
            "keyboard_combos": _serialize_combo_map(gameplay.keyboard_combos),
            "gamepad_combos": _serialize_combo_map(gameplay.gamepad_combos),
        },
        "menu": {
            "keyboard": _serialize_flat_map(menu.keyboard),
            "mouse_buttons": _serialize_flat_map(menu.mouse_buttons),
            "gamepad_buttons": _serialize_flat_map(menu.gamepad_buttons),
            "gamepad_hats": _serialize_flat_map(menu.gamepad_hats),
            "gamepad_axes": _serialize_flat_map(menu.gamepad_axes),
            "new_game_key": menu.new_game_key,
            "invert_y": menu.invert_y,
        },
    }


def bindings_from_dict(data: object) -> InputBindings:
    """Validate a bindings file: free-form subsets, context respected.

    The contract comes from the two-column controls screen (audit UI-5):

    * every key of a map must belong to its context (gameplay or menu);
    * a map may be partial -- a missing action means unbound, and
      ``InputProvider`` tolerates the gaps, which is what lets the UI detach a
      single key or button;
    * ``move_x`` stays a pair: two keys on the keyboard, two buttons if the
      gameplay ``gamepad_buttons`` section declares it.
    """
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
    gameplay_buttons = _parse_int_map(
        gameplay_data["gamepad_buttons"], gameplay_actions, allow_pair=True
    )
    gameplay_axes = cast(AxisMap, _parse_int_map(gameplay_data["gamepad_axes"], gameplay_actions))
    gameplay_hats = _parse_int_map(gameplay_data["gamepad_hats"], gameplay_actions)
    gameplay_keyboard_combos = _parse_combo_map(gameplay_data["keyboard_combos"], gameplay_actions)
    gameplay_gamepad_combos = _parse_combo_map(gameplay_data["gamepad_combos"], gameplay_actions)
    menu_keyboard = _parse_action_map(menu_data["keyboard"], menu_actions)
    # Older files: capturing an arrow sometimes left two menu directions on one
    # key. Repaired without disturbing the other custom remaps.
    menu_keyboard = _repair_menu_direction_conflicts(menu_keyboard)
    menu_mouse = _parse_int_map(menu_data.get("mouse_buttons", {"ui_back": 3}), menu_actions)
    menu_buttons = _parse_int_map(menu_data["gamepad_buttons"], menu_actions)
    menu_hats = _parse_int_map(menu_data["gamepad_hats"], menu_actions)
    menu_axes = cast(AxisMap, _parse_int_map(menu_data["gamepad_axes"], menu_actions))
    if InputAction.UI_BACK not in menu_buttons and InputAction.UI_CANCEL in menu_buttons:
        # A file written before universal back (B button / right click) bound
        # that button to ui_cancel. Copy the binding to ui_back so the router
        # emits the action the scenes expect, keeping the rest of the file.
        menu_buttons = MappingProxyType(
            {**menu_buttons, InputAction.UI_BACK: menu_buttons[InputAction.UI_CANCEL]}
        )
    new_game_key = menu_data.get("new_game_key", pygame.K_n)
    if new_game_key is not None and (
        not isinstance(new_game_key, int) or isinstance(new_game_key, bool) or new_game_key < 0
    ):
        raise ValueError("menu.new_game_key must be a non-negative integer or null")
    invert_y = menu_data.get("invert_y", False)
    if not isinstance(invert_y, bool):
        raise ValueError("menu.invert_y must be boolean")

    if InputAction.SPECIAL_ATTACK not in gameplay_keyboard_combos:
        raise ValueError("gameplay.keyboard_combos is missing special_attack")
    if InputAction.SPECIAL_ATTACK not in gameplay_gamepad_combos:
        raise ValueError("gameplay.gamepad_combos is missing special_attack")
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
        mouse_buttons=menu_mouse,
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
    """Where bindings live when nothing overrides it: beside the settings, not in the user config."""
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
