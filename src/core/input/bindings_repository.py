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

# Actions dont la liaison se fait par paire (gauche, droite) : le clavier les
# stocke en tuple, et ``gamepad_buttons`` peut les recevoir en paire de boutons
# pour les pads qui exposent le d-pad en boutons.
_PAIR_ACTIONS = frozenset({InputAction.MOVE_X})


def _serialize_action_map(values: ActionMap) -> dict[str, object]:
    return {
        action.value: list(value) if isinstance(value, tuple) else value
        for action, value in values.items()
    }


def _serialize_int_map(values: ButtonMap | AxisMap) -> dict[str, object]:
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
            # move_x est une paire (gauche, droite) : un entier unique ferait
            # planter ``InputProvider._calculate_move_axis``.
            raise ValueError(f"{action.value} requires a pair of keys")
        return value
    if isinstance(value, list) and all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        if not value or (allow_pair and len(value) != 2):
            raise ValueError("invalid key binding")
        return tuple(value)
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


def _int_index(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _parse_int_map(data: object, allowed: set[InputAction], allow_pair: bool = False) -> ButtonMap:
    """Parse un index SDL unique, ou la paire (gauche, droite) de MOVE_X.

    ``allow_pair`` n'est ouvert que pour le contexte gameplay : les pads qui
    exposent le d-pad en boutons (Xbox/SDL2) peuvent ainsi binder le déplacement
    horizontal sur deux boutons, comme sur clavier.
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
            "mouse_buttons": _serialize_int_map(menu.mouse_buttons),
            "gamepad_buttons": _serialize_int_map(menu.gamepad_buttons),
            "gamepad_hats": _serialize_int_map(menu.gamepad_hats),
            "gamepad_axes": _serialize_int_map(menu.gamepad_axes),
            "new_game_key": menu.new_game_key,
            "invert_y": menu.invert_y,
        },
    }


def bindings_from_dict(data: object) -> InputBindings:
    """Valide un fichier de bindings (sous-ensembles libres, contexte respecté).

    Contrat depuis l'écran Contrôles à deux colonnes (audit UI-5) :

    * chaque clé d'une map doit appartenir au contexte (gameplay ou menu) ;
    * une map peut être partielle : l'absence d'une action signifie « non
      liée » (l'``InputProvider`` tolère les trous), ce qui permet de détacher
      une touche ou un bouton depuis l'UI ;
    * ``move_x`` reste une paire : de touches au clavier, et de boutons si la
      section ``gamepad_buttons`` du gameplay la déclare.
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
    menu_mouse = _parse_int_map(menu_data.get("mouse_buttons", {"ui_back": 3}), menu_actions)
    menu_buttons = _parse_int_map(menu_data["gamepad_buttons"], menu_actions)
    menu_hats = _parse_int_map(menu_data["gamepad_hats"], menu_actions)
    menu_axes = cast(AxisMap, _parse_int_map(menu_data["gamepad_axes"], menu_actions))
    if InputAction.UI_BACK not in menu_buttons and InputAction.UI_CANCEL in menu_buttons:
        # Fichier écrit avant le retour universel (bouton B / clic droit) : le
        # bouton B était alors lié à ui_cancel. On recopie la liaison vers
        # ui_back pour que le routeur émette l'action de retour attendue par
        # les scènes, sans perdre les autres réglages du fichier.
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
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
