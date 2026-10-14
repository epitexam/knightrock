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
    """A file written before universal back: the B button becomes ui_back."""
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


def test_a_file_from_before_the_list_keys_gets_their_defaults(
    tmp_path: Path,
) -> None:
    """A page-down key that does not exist yet is not an unbound one.

    ``bindings_from_dict``'s contract is that a missing action is
    unbound -- right for a key the player detached, wrong for a
    key that did not exist when the file was written. Every player
    who never opened the controls screen has such a file, so every
    one of them would otherwise have a dead page-down key.
    """
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    keyboard = payload["bindings"]["menu"]["keyboard"]
    for action in (
        "ui_page_up",
        "ui_page_down",
        "ui_home",
        "ui_end",
    ):
        del keyboard[action]

    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load()

    assert loaded.menu.keyboard[InputAction.UI_PAGE_DOWN] == pygame.K_PAGEDOWN
    assert loaded.menu.keyboard[InputAction.UI_PAGE_UP] == pygame.K_PAGEUP
    assert loaded.menu.keyboard[InputAction.UI_HOME] == pygame.K_HOME
    assert loaded.menu.keyboard[InputAction.UI_END] == pygame.K_END


def test_a_file_with_one_list_key_is_left_alone(tmp_path: Path) -> None:
    """The four arrive as a set: a file that has any of them was
    written after they existed, so a player who rebound page down
    and left page up unbound meant exactly that.
    """
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    keyboard = payload["bindings"]["menu"]["keyboard"]
    del keyboard["ui_page_up"]
    del keyboard["ui_home"]
    del keyboard["ui_end"]
    keyboard["ui_page_down"] = pygame.K_SPACE

    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load()

    assert loaded.menu.keyboard[InputAction.UI_PAGE_DOWN] == pygame.K_SPACE
    assert InputAction.UI_PAGE_UP not in loaded.menu.keyboard
    assert InputAction.UI_HOME not in loaded.menu.keyboard
    assert InputAction.UI_END not in loaded.menu.keyboard


def test_the_shoulders_are_bound_to_paging_by_default() -> None:
    """A gamepad player walks a 28-row list one row at a time otherwise.

    4 and 5 are Guard and Attack 4 in *gameplay* -- a separate
    context, so borrowing the shoulders here costs nothing there.
    """
    bindings = InputBindings()

    assert bindings.menu.gamepad_buttons[InputAction.UI_PAGE_UP] == 4
    assert bindings.menu.gamepad_buttons[InputAction.UI_PAGE_DOWN] == 5


def test_a_file_from_before_the_shoulders_gets_them(tmp_path: Path) -> None:
    """The same migration as the keyboard side, on the button map.

    Home and end have no standard gamepad equivalent and stay on
    the keyboard, so the set that migrates is the two that do.
    """
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    buttons = payload["bindings"]["menu"]["gamepad_buttons"]
    del buttons["ui_page_up"]
    del buttons["ui_page_down"]

    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load()

    assert loaded.menu.gamepad_buttons[InputAction.UI_PAGE_UP] == 4
    assert loaded.menu.gamepad_buttons[InputAction.UI_PAGE_DOWN] == 5


def test_a_file_with_one_shoulder_is_left_alone(tmp_path: Path) -> None:
    """A file that has either of them was written after they existed,
    so a player who moved page down and unbound page up on purpose
    keeps exactly that.
    """
    path = tmp_path / "settings.json"
    repository = BindingsRepository(path)
    repository.save(InputBindings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    buttons = payload["bindings"]["menu"]["gamepad_buttons"]
    del buttons["ui_page_up"]
    del buttons["ui_page_down"]
    buttons["ui_page_down"] = 7

    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load()

    assert loaded.menu.gamepad_buttons[InputAction.UI_PAGE_DOWN] == 7
    assert InputAction.UI_PAGE_UP not in loaded.menu.gamepad_buttons
