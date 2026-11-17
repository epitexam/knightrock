"""Data-supplied resource paths must stay inside the application root.

``resource_path`` is the permissive resolver shared by the code, by
``AssetLibrary`` (which passes back absolute frame paths) and by tests that
build temporary trees. ``confined_resource_path`` is the companion used at
the *data* boundary: a tampered ``levels.json`` or ``enemies.json`` must not
be able to hand PyTMX or the image loader a file from elsewhere on disk.
"""

import json
import sys
from pathlib import Path

import pytest

from src.core.paths import PROJECT_ROOT, confined_resource_path, resource_path
from src.data.enemies import read_enemies_file


def test_relative_data_path_resolves_inside_the_project_root() -> None:
    resolved = confined_resource_path("assets/data/levels/1.tmx")

    assert Path(resolved).is_relative_to(PROJECT_ROOT.resolve())
    assert resolved == resource_path("assets/data/levels/1.tmx")


def test_absolute_data_path_inside_the_root_is_still_accepted() -> None:
    inside = PROJECT_ROOT / "assets" / "data" / "levels" / "1.tmx"

    assert confined_resource_path(str(inside)) == resource_path(str(inside))


def test_relative_traversal_is_refused() -> None:
    with pytest.raises(ValueError, match="escapes"):
        confined_resource_path("../../etc/passwd")


def test_absolute_path_outside_the_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        confined_resource_path(str(tmp_path / "secret.txt"))


def test_bundle_root_is_the_confinement_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert Path(confined_resource_path("assets/example.dat")).is_relative_to(tmp_path.resolve())
    with pytest.raises(ValueError, match="escapes"):
        confined_resource_path("../../outside.dat")


def test_enemy_animation_directory_cannot_traverse(tmp_path: Path) -> None:
    path = tmp_path / "enemies.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "enemies": {
                    "goblin": {
                        "size": [36.0, 48.0],
                        "color": [60, 130, 60],
                        "health": 60.0,
                        "attacks": {},
                        "attack_name": "claw_swipe",
                        "animations": {"idle": "../../etc/passwd"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="relative to the project root"):
        read_enemies_file(path, {})
