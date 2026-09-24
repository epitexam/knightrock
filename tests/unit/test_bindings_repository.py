import json
from pathlib import Path
from types import MappingProxyType

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
