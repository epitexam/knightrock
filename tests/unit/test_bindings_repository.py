import json
from pathlib import Path

from src.core.input.bindings_repository import BindingsRepository, bindings_to_dict
from src.core.input.input_bindings import InputBindings


def test_bindings_roundtrip_through_versioned_repository(tmp_path: Path) -> None:
    repository = BindingsRepository(tmp_path / "settings.json")
    bindings = InputBindings()

    repository.save(bindings)
    loaded = repository.load()

    assert loaded == bindings
    assert json.loads(repository.path.read_text(encoding="utf-8")) == bindings_to_dict(bindings)


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
