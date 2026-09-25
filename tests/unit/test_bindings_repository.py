import json
from pathlib import Path
from types import MappingProxyType

import pygame

from src.core.input.bindings_repository import BindingsRepository, bindings_to_dict
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings, MenuBindings


def test_bindings_roundtrip_through_versioned_repository(tmp_path: Path) -> None:
    repository = BindingsRepository(tmp_path / "settings.json")
    bindings = InputBindings()

    repository.save(bindings)
    loaded = repository.load()

    assert loaded == bindings
    payload = json.loads(repository.path.read_text(encoding="utf-8"))
    assert payload["bindings"] == bindings_to_dict(bindings)


def test_custom_bindings_roundtrip_after_schema_validation(tmp_path: Path) -> None:
    repository = BindingsRepository(tmp_path / "settings.json")
    menu = MenuBindings(
        gamepad_axes=MappingProxyType(
            {
                InputAction.UI_LEFT: 7,
                InputAction.UI_RIGHT: 7,
                InputAction.UI_UP: 8,
                InputAction.UI_DOWN: 8,
            }
        )
    )
    bindings = InputBindings(menu=menu)

    repository.save(bindings)
    loaded = repository.load()

    assert loaded == bindings
    assert loaded.menu.gamepad_axes[InputAction.UI_RIGHT] == 7


def test_missing_bindings_file_uses_defaults(tmp_path: Path) -> None:
    repository = BindingsRepository(tmp_path / "settings.json")

    assert repository.load() == InputBindings()


def test_corrupted_or_unknown_bindings_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)

    path.write_text("not-json", encoding="utf-8")
    assert repository.load() == InputBindings()

    path.write_text(json.dumps({"version": 99, "gameplay": {}, "menu": {}}), encoding="utf-8")
    assert repository.load() == InputBindings()


def test_legacy_file_without_back_button_mirrors_cancel_binding(tmp_path: Path) -> None:
    """Fichier écrit avant le retour universel : le bouton B devient ui_back."""
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    buttons = payload["bindings"]["menu"]["gamepad_buttons"]
    del buttons["ui_back"]
    buttons["ui_cancel"] = 3  # bouton X : ancien binding utilisateur

    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load()

    assert loaded.menu.gamepad_buttons[InputAction.UI_BACK] == 3
    assert loaded.menu.gamepad_buttons[InputAction.UI_CANCEL] == 3


def test_back_button_can_be_bound_apart_from_cancel(tmp_path: Path) -> None:
    repository = BindingsRepository(tmp_path / "settings.json")
    buttons = MappingProxyType({**InputBindings().menu.gamepad_buttons, InputAction.UI_CANCEL: 8})

    repository.save(InputBindings(menu=MenuBindings(gamepad_buttons=buttons)))
    loaded = repository.load()

    assert loaded.menu.gamepad_buttons[InputAction.UI_BACK] == 1
    assert loaded.menu.gamepad_buttons[InputAction.UI_CANCEL] == 8


def test_legacy_conflicting_menu_arrows_are_repaired(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    menu = payload["bindings"]["menu"]
    menu["keyboard"]["ui_down"] = menu["keyboard"]["ui_right"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = repository.load()
    keyboard = loaded.menu.keyboard
    assert keyboard[InputAction.UI_DOWN] != keyboard[InputAction.UI_RIGHT]
    assert keyboard[InputAction.UI_DOWN] == pygame.K_DOWN
    assert keyboard[InputAction.UI_RIGHT] == pygame.K_RIGHT


def test_repository_keeps_ui_actions_out_of_gameplay_context(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "gameplay": {"keyboard": {"ui_up": 1}},
                "menu": {"keyboard": {}},
            }
        ),
        encoding="utf-8",
    )

    assert BindingsRepository(path).load() == InputBindings()
