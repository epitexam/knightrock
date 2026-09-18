"""Tests of the src/data package: typed JSON loaders + fallback (Phase 3 #4)."""

import json
import logging
from pathlib import Path

import pytest

from src.combat.attack_data import GOBLIN_ATTACKS, PLAYER_ATTACKS, SLIME_ATTACKS
from src.combat.frame_data import AttackDefinition
from src.core.level.level_manager import LEVEL_PATHS
from src.core.paths import PROJECT_ROOT
from src.data.attacks import ATTACKS_FILENAME, attack_definition_to_dict, read_attacks_file
from src.data.enemies import ENEMIES_FILENAME, read_enemies_file
from src.data.levels import LEVELS_FILENAME, levels_to_dict, read_levels_file
from src.data.player import PLAYER_FILENAME, read_player_file
from src.data.provider import GameplayData, gameplay_data_root, load_gameplay_data
from src.entities.enemies.schema import EnemyConfig
from src.entities.enemies.types.dummy import DUMMY_CONFIG
from src.entities.enemies.types.goblin import GOBLIN_CONFIG
from src.entities.enemies.types.slime import SLIME_CONFIG
from src.entities.player_config import DEFAULT_PLAYER_CONFIG, PlayerConfig


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _attacks_doc() -> dict:
    return {
        "version": 1,
        "sets": {"test_set": {"punch": attack_definition_to_dict(PLAYER_ATTACKS["light_attack"])}},
    }


# ── attacks.json ──────────────────────────────────────────────────────────


def test_read_attacks_file_roundtrips(tmp_path: Path) -> None:
    path = _write(tmp_path / "attacks.json", _attacks_doc())

    sets = read_attacks_file(path)

    assert isinstance(sets["test_set"]["punch"], AttackDefinition)
    assert attack_definition_to_dict(sets["test_set"]["punch"]) == attack_definition_to_dict(
        PLAYER_ATTACKS["light_attack"]
    )


def test_read_attacks_file_extra_hitboxes_roundtrip(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"][0]["extra_hitboxes"] = [
        {"size": [20.0, 20.0], "offset": [-30.0, 0.0]}
    ]
    path = _write(tmp_path / "attacks.json", doc)

    sets = read_attacks_file(path)
    phase = sets["test_set"]["punch"].phases[0]

    assert len(phase.extra_hitboxes) == 1
    assert phase.extra_hitboxes[0].size == (20.0, 20.0)
    assert phase.extra_hitboxes[0].offset == (-30.0, 0.0)
    # Serializer keeps the JSON shape stable for JSON-driven tooling.
    assert attack_definition_to_dict(sets["test_set"]["punch"])["phases"][0]["extra_hitboxes"] == [
        {"size": [20.0, 20.0], "offset": [-30.0, 0.0]}
    ]


def test_read_attacks_file_hitbox_keyframes_roundtrip(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"][0]["hitbox_keyframes"] = [
        {"frame": 0, "size": [20.0, 20.0], "offset": [10.0, 0.0]},
        {"frame": 9, "size": [40.0, 20.0], "offset": [30.0, 0.0]},
    ]
    path = _write(tmp_path / "attacks.json", doc)

    sets = read_attacks_file(path)
    phase = sets["test_set"]["punch"].phases[0]

    assert len(phase.hitbox_keyframes) == 2
    assert phase.hitbox_keyframes[1].frame == 9
    # A third of the way along the 0->9 curve interpolates linearly.
    size, offset = phase.hitbox_at(3)
    assert size[0] == pytest.approx(20.0 + 20.0 / 3)
    assert size[1] == 20.0
    assert offset[0] == pytest.approx(10.0 + 20.0 / 3)
    assert offset[1] == 0.0
    assert attack_definition_to_dict(sets["test_set"]["punch"])["phases"][0][
        "hitbox_keyframes"
    ] == [
        {"frame": 0, "size": [20.0, 20.0], "offset": [10.0, 0.0]},
        {"frame": 9, "size": [40.0, 20.0], "offset": [30.0, 0.0]},
    ]


def test_read_attacks_file_keyframe_beyond_active_span_raises(
    tmp_path: Path,
) -> None:
    doc = _attacks_doc()
    # light_attack spans 3 startup + 6 active = 9 frames: frame 10 is out.
    doc["sets"]["test_set"]["punch"]["phases"][0]["hitbox_keyframes"] = [
        {"frame": 10, "size": [20.0, 20.0], "offset": [10.0, 0.0]}
    ]
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="exceeds"):
        read_attacks_file(path)


def test_read_attacks_file_bad_extra_hitbox_raises(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"][0]["extra_hitboxes"] = [{"size": [20.0, 20.0]}]
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="offset"):
        read_attacks_file(path)


def test_read_attacks_file_missing_required_field_raises(tmp_path: Path) -> None:
    doc = _attacks_doc()
    del doc["sets"]["test_set"]["punch"]["cooldown"]
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="cooldown"):
        read_attacks_file(path)


def test_read_attacks_file_unknown_damage_type_raises(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"][0]["hit"]["damage_type"] = "psychic"
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="damage_type"):
        read_attacks_file(path)


def test_read_attacks_file_wrong_version_raises(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["version"] = 99
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="version"):
        read_attacks_file(path)


def test_read_attacks_file_bad_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "attacks.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        read_attacks_file(path)


def test_read_attacks_file_phases_must_be_non_empty(tmp_path: Path) -> None:
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"] = []
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="non-empty"):
        read_attacks_file(path)


# ── enemies.json ──────────────────────────────────────────────────────────


def test_read_enemies_file_with_attack_set_reference(tmp_path: Path) -> None:
    attack_sets = {"goblin": dict(GOBLIN_ATTACKS)}
    doc = {
        "version": 1,
        "enemies": {
            "goblin": {
                "size": [36.0, 48.0],
                "color": [60, 130, 60],
                "health": 60.0,
                "attacks": "goblin",
                "attack_name": "claw_swipe",
            }
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    enemies = read_enemies_file(path, attack_sets)

    config = enemies["goblin"]
    assert isinstance(config, EnemyConfig)
    assert config.health == 60.0
    assert dict(config.attacks) == attack_sets["goblin"]
    assert config.attack_name == "claw_swipe"
    assert config.chase_speed == 120.0  # dataclass default
    assert config.has_ai is True  # dataclass default


def test_read_enemies_file_unknown_attack_set_raises(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "enemies": {
            "orc": {"size": [36, 48], "color": [0, 0, 0], "health": 1.0, "attacks": "nope"}
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    with pytest.raises(ValueError, match="unknown attack set"):
        read_enemies_file(path, {"goblin": {}})


# ── player.json ───────────────────────────────────────────────────────────


def test_read_player_file_overrides_defaults(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "player": {"health": 80.0, "color": [255, 120, 200], "faction": "hero"},
    }
    path = _write(tmp_path / "player.json", doc)

    config = read_player_file(path, {"player": dict(PLAYER_ATTACKS)})

    assert isinstance(config, PlayerConfig)
    assert config.health == 80.0
    assert config.faction == "hero"
    assert config.color == (255, 120, 200)
    assert config.speed == PlayerConfig().speed  # untouched default
    assert config.max_wall_jumps == float("inf")  # untouched default


def test_read_player_file_inf_wall_jumps(tmp_path: Path) -> None:
    doc = {"version": 1, "player": {"max_wall_jumps": "inf"}}
    path = _write(tmp_path / "player.json", doc)

    config = read_player_file(path, {})

    assert config.max_wall_jumps == float("inf")


def test_read_player_file_attack_set_reference(tmp_path: Path) -> None:
    doc = {"version": 1, "player": {"attack_set": "player"}}
    path = _write(tmp_path / "player.json", doc)

    config = read_player_file(path, {"player": dict(PLAYER_ATTACKS)})

    assert dict(config.attacks) == PLAYER_ATTACKS


# ── levels.json ───────────────────────────────────────────────────────────


def test_read_levels_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "levels.json",
        levels_to_dict({0: "assets/data/levels/1.tmx", 1: "assets/data/levels/2.tmx"}),
    )

    levels = read_levels_file(path)

    assert levels == {0: "assets/data/levels/1.tmx", 1: "assets/data/levels/2.tmx"}


def test_read_levels_file_rejects_non_integer_id(tmp_path: Path) -> None:
    path = _write(tmp_path / "levels.json", {"version": 1, "levels": {"zero": "a.tmx"}})

    with pytest.raises(ValueError, match="not an integer"):
        read_levels_file(path)


# ── provider: fallback, parity, errors ─────────────────────────────────


def test_load_gameplay_data_falls_back_when_dir_is_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    empty = tmp_path / "gameplay"
    empty.mkdir()

    with caplog.at_level(logging.WARNING):
        data = load_gameplay_data(empty)

    assert set(data.attack_sets) == {"player", "goblin", "slime"}
    assert data.attack_sets["player"] == PLAYER_ATTACKS
    assert data.player is None
    assert dict(data.levels) == LEVEL_PATHS
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 4  # one per missing JSON file


def test_load_gameplay_data_uses_json_when_present(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _write(root / "attacks.json", _attacks_doc())
    _write(
        root / "enemies.json",
        {
            "version": 1,
            "enemies": {
                "orc": {
                    "size": [40, 50],
                    "color": [10, 200, 10],
                    "health": 25.0,
                    "attacks": {"bite": attack_definition_to_dict(PLAYER_ATTACKS["light_attack"])},
                }
            },
        },
    )
    _write(root / "player.json", {"version": 1, "player": {"health": 70.0}})
    _write(
        root / "levels.json",
        levels_to_dict({0: "assets/data/levels/1.tmx"}),
    )

    data = load_gameplay_data(root)

    assert isinstance(data, GameplayData)
    assert set(data.attack_sets) == {"test_set"}
    assert data.enemies["orc"].health == 25.0
    assert data.player is not None and data.player.health == 70.0
    assert dict(data.levels) == {0: "assets/data/levels/1.tmx"}


def test_load_gameplay_data_fails_loudly_on_corrupt_json(tmp_path: Path) -> None:
    root = tmp_path / "data"
    bad = root
    bad.mkdir(parents=True)
    (bad / "attacks.json").write_text('{"version": 1, "sets": }', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_gameplay_data(root)


def test_shipped_gameplay_json_files_are_present() -> None:
    """The tracked JSON must exist, else every other test only sees fallback."""
    root = gameplay_data_root()

    # Locked-in layout decision: gameplay data lives in the tracked top-level
    # ``data/gameplay/`` (``assets/`` is git-ignored, so it cannot carry it).
    assert root == PROJECT_ROOT / "data" / "gameplay"
    for name in (ATTACKS_FILENAME, ENEMIES_FILENAME, PLAYER_FILENAME, LEVELS_FILENAME):
        assert (root / name).is_file(), f"missing tracked gameplay file: {name}"


def test_load_gameplay_data_json_parity_with_builtin_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tracked JSON must reproduce the historical Python values exactly.

    Asserted on the end state of the *default* root, so a transcription error
    in the tracked files fails CI instead of silently shifting the balance.
    """
    monkeypatch.delenv("KNIGHTROCK_DATA_DIR", raising=False)
    data = load_gameplay_data()

    assert data.player is not None, "shipped player.json was not loaded"

    for name, builtin in (
        ("player", PLAYER_ATTACKS),
        ("goblin", GOBLIN_ATTACKS),
        ("slime", SLIME_ATTACKS),
    ):
        assert data.attack_sets[name] == builtin

    # Enemy configs are frozen dataclasses: full equality, field by field.
    assert data.enemies["goblin"] == GOBLIN_CONFIG
    assert data.enemies["dummy"] == DUMMY_CONFIG
    assert data.enemies["slime"] == SLIME_CONFIG

    # The JSON encodes DEFAULT_PLAYER_CONFIG (pink sprite), not the bare
    # PlayerConfig() defaults; Player uses the former when config is None.
    assert data.player == DEFAULT_PLAYER_CONFIG

    assert dict(data.levels) == LEVEL_PATHS
