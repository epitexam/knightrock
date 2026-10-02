"""Tests of the src/data package: typed JSON loaders + fallback (Phase 3 #4)."""

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from src.combat.attack_data import GOBLIN_ATTACKS, PLAYER_ATTACKS, SLIME_ATTACKS
from src.combat.frame_data import AttackDefinition, Stance
from src.core.input.input_manager import InputManager
from src.core.level.level_manager import LEVEL_PATHS
from src.core.paths import PROJECT_ROOT
from src.data.attacks import (
    ATTACKS_FILENAME,
    attack_definition_to_dict,
    read_attack_definition,
    read_attacks_file,
)
from src.data.enemies import ENEMIES_FILENAME, enemy_config_to_dict, read_enemies_file
from src.data.errors import GameplayDataError
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


def _grounded_player(input_manager: InputManager):
    """A fighter on the floor, for the posture-resolution test.

    Built directly rather than through a level: this asks what ``stance``
    returns for a given set of surface flags, so the only setup that matters is
    the flags.
    """
    import pygame

    from src.entities.player import Player

    player = Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=input_manager,
    )
    player.on_surface["floor"] = True
    return player


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
    assert phase.extra_hitboxes[0].keyframes == ()
    # Static box keeps its own (empty) keyframes curve in the dict shape.
    assert attack_definition_to_dict(sets["test_set"]["punch"])["phases"][0]["extra_hitboxes"] == [
        {"size": [20.0, 20.0], "offset": [-30.0, 0.0], "keyframes": []}
    ]


def test_read_attacks_file_extra_hitbox_keyframes_roundtrip(tmp_path: Path) -> None:
    """Each extra box follows its own curve (P2), parsed + interpolated + saved."""
    doc = _attacks_doc()
    doc["sets"]["test_set"]["punch"]["phases"][0]["extra_hitboxes"] = [
        {
            "size": [20.0, 20.0],
            "offset": [-30.0, 0.0],
            "keyframes": [
                {"frame": 0, "size": [20.0, 20.0], "offset": [-30.0, 0.0]},
                {"frame": 9, "size": [40.0, 20.0], "offset": [-10.0, 0.0]},
            ],
        }
    ]
    path = _write(tmp_path / "attacks.json", doc)

    sets = read_attacks_file(path)
    phase = sets["test_set"]["punch"].phases[0]

    assert len(phase.extra_hitboxes[0].keyframes) == 2
    # Third of the way along the 0->9 curve interpolates linearly.
    size, offset = phase.extra_box_at(0, 3)
    assert size[0] == pytest.approx(20.0 + 20.0 / 3)
    assert offset[0] == pytest.approx(-30.0 + 20.0 / 3)
    serialized = attack_definition_to_dict(sets["test_set"]["punch"])["phases"][0]["extra_hitboxes"]
    assert serialized[0]["keyframes"] == [
        {"frame": 0, "size": [20.0, 20.0], "offset": [-30.0, 0.0]},
        {"frame": 9, "size": [40.0, 20.0], "offset": [-10.0, 0.0]},
    ]


def test_read_attacks_file_extra_hitbox_keyframe_beyond_span_raises(
    tmp_path: Path,
) -> None:
    doc = _attacks_doc()
    # light_attack spans 3 startup + 6 active = 9 frames: frame 10 is out.
    doc["sets"]["test_set"]["punch"]["phases"][0]["extra_hitboxes"] = [
        {
            "size": [20.0, 20.0],
            "offset": [-30.0, 0.0],
            "keyframes": [{"frame": 10, "size": [20.0, 20.0], "offset": [-30.0, 0.0]}],
        }
    ]
    path = _write(tmp_path / "attacks.json", doc)

    with pytest.raises(ValueError, match="exceeds"):
        read_attacks_file(path)


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
    assert config.patrol_speed is None  # derived from chase_speed at runtime
    assert config.has_ai is True  # dataclass default


def test_read_enemies_file_explicit_patrol_speed(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "enemies": {
            "goblin": {
                "size": [36.0, 48.0],
                "color": [60, 130, 60],
                "health": 60.0,
                "attacks": "goblin",
                "chase_speed": 100.0,
                "patrol_speed": 40.0,
            }
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    enemies = read_enemies_file(path, {"goblin": dict(GOBLIN_ATTACKS)})

    assert enemies["goblin"].patrol_speed == 40.0
    assert enemy_config_to_dict(enemies["goblin"])["patrol_speed"] == 40.0


def test_enemy_config_to_dict_omits_default_patrol_speed() -> None:
    assert "patrol_speed" not in enemy_config_to_dict(GOBLIN_CONFIG)


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


def test_read_enemies_file_hurtbox_zones_roundtrip(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "enemies": {
            "goblin": {
                "size": [36.0, 48.0],
                "color": [60, 130, 60],
                "health": 60.0,
                "attacks": "goblin",
                "hurtbox_zones": [
                    {"name": "head", "inflate": [-10.0, -30.0], "mult": 1.2, "tags": ["head"]},
                    {"name": "torso", "inflate": [-4.0, -8.0]},
                    {"name": "legs", "inflate": [0.0, 4.0], "tags": ["legs", "low"]},
                ],
            }
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    enemies = read_enemies_file(path, {"goblin": dict(GOBLIN_ATTACKS)})
    config = enemies["goblin"]

    assert config.hurtbox_zones is not None
    assert [zone.name for zone in config.hurtbox_zones] == ["head", "torso", "legs"]
    assert config.hurtbox_zones[0].mult == pytest.approx(1.2)
    assert config.hurtbox_zones[0].inflate == (-10.0, -30.0)
    assert config.hurtbox_zones[2].tags == ("legs", "low")
    # Canonical serialized shape (defaults filled) -> reparse is stable.
    zones_dict = enemy_config_to_dict(config)["hurtbox_zones"]
    assert zones_dict == [
        {"name": "head", "inflate": [-10.0, -30.0], "mult": 1.2, "tags": ["head"]},
        {"name": "torso", "inflate": [-4.0, -8.0], "mult": 1.0, "tags": []},
        {"name": "legs", "inflate": [0.0, 4.0], "mult": 1.0, "tags": ["legs", "low"]},
    ]
    doc2 = {"version": 1, "enemies": {"goblin": enemy_config_to_dict(config)}}
    reparsed = read_enemies_file(_write(tmp_path / "enemies2.json", doc2), {"goblin": {}})
    assert reparsed["goblin"] == config


def test_read_enemies_file_without_zones_keeps_legacy_fallback(tmp_path: Path) -> None:
    """``hurtbox_inflate`` only: zones stay None (fallback on the old field)."""
    doc = {
        "version": 1,
        "enemies": {
            "goblin": {
                "size": [36.0, 48.0],
                "color": [60, 130, 60],
                "health": 60.0,
                "attacks": "goblin",
                "hurtbox_inflate": [-4.0, -6.0],
            }
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    config = read_enemies_file(path, {"goblin": dict(GOBLIN_ATTACKS)})["goblin"]

    assert config.hurtbox_zones is None
    assert config.hurtbox_inflate == (-4.0, -6.0)
    # Serializer omits the key for legacy payloads (JSON shape unchanged).
    assert "hurtbox_zones" not in enemy_config_to_dict(config)


def test_read_enemies_file_empty_zones_rejected(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "enemies": {
            "goblin": {
                "size": [36.0, 48.0],
                "color": [60, 130, 60],
                "health": 60.0,
                "attacks": "goblin",
                "hurtbox_zones": [],
            }
        },
    }
    path = _write(tmp_path / "enemies.json", doc)

    with pytest.raises(ValueError, match="at least one zone"):
        read_enemies_file(path, {"goblin": dict(GOBLIN_ATTACKS)})


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


# ── unknown keys, per file ────────────────────────────────────────────────
#
# `data/__init__.py` and `README.md` both promise that unknown keys raise across
# the whole package, not just in `attacks.json`. Each document therefore gets its
# own case, at its own level: a typo in the outermost object of a file is the one
# a hand-editor actually makes, and a check that only ran inside the inner
# reader would never see it.


def test_attacks_file_rejects_an_unknown_top_level_key(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "attacks.json",
        {"version": 1, "sets": {}, "evrey": {"goblin": {}}},
    )

    with pytest.raises(GameplayDataError, match=r"unknown field\(s\) 'evrey'"):
        read_attacks_file(path)


def test_enemies_file_rejects_an_unknown_top_level_key(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "enemies.json",
        {"version": 1, "enemies": {}, "enemys": {}},
    )

    with pytest.raises(GameplayDataError, match=r"unknown field\(s\) 'enemys'"):
        read_enemies_file(path, {})


def test_enemies_file_rejects_an_unknown_enemy_field(tmp_path: Path) -> None:
    """The inner level, keyed off ``EnemyConfig``'s own fields.

    ``EnemyConfig`` is the schema, so adding a field to it makes the file able
    to carry it with no edit here. The failure this prevents is a designer
    setting ``attack_ranges`` and watching the enemy keep its old reach.
    """
    path = _write(
        tmp_path / "enemies.json",
        {
            "version": 1,
            "enemies": {
                "goblin": {
                    "size": [36, 48],
                    "color": [200, 60, 60],
                    "health": 60.0,
                    "attacks": {"a": attack_definition_to_dict(PLAYER_ATTACKS["light_attack"])},
                    "attack_ranges": 90.0,
                }
            },
        },
    )

    with pytest.raises(GameplayDataError, match=r"unknown field\(s\) 'attack_ranges'"):
        read_enemies_file(path, {})


def test_player_file_rejects_an_unknown_override(tmp_path: Path) -> None:
    """Every key is a ``PlayerConfig`` field, so this was one ``set()`` call."""
    path = _write(
        tmp_path / "player.json",
        {"version": 1, "player": {"jump_hight": 700.0}},
    )

    with pytest.raises(GameplayDataError, match=r"unknown field\(s\) 'jump_hight'"):
        read_player_file(path, {})


def test_player_file_accepts_every_configurable_field(tmp_path: Path) -> None:
    """The flip side: nothing a dataclass field can express may be refused.

    ``_player_override_keys`` is derived from ``PlayerConfig``, so this walks the
    same list the guard does. Without it, a field added to the config would
    quietly stop being overridable -- the same silent failure this commit exists
    to remove, one level up.
    """
    from src.data.player import _player_override_keys

    everything = {key: _OVERRIDE_SAMPLES[key] for key in _player_override_keys()}
    path = _write(tmp_path / "player.json", {"version": 1, "player": everything})

    config = read_player_file(path, {"player": dict(PLAYER_ATTACKS)})

    assert config.faction == everything["faction"]
    assert config.dash_speed == everything["dash_speed"]
    assert config.max_wall_jumps == everything["max_wall_jumps"]


_OVERRIDE_SAMPLES: dict[str, object] = {
    "size": [48.0, 56.0],
    "color": [1, 2, 3],
    "health": 90.0,
    "max_health": 90.0,
    "hitbox_inflate": [-8.0, 0.0],
    "hurtbox_inflate": [0.0, 0.0],
    "hurtbox_zones": None,
    "attack_set": "player",
    "speed": 320.0,
    "floor_control": 25.0,
    "air_control": 12.0,
    "jump_height": 700.0,
    "wall_jump_height": 650.0,
    "wall_jump_push_multiplier": 320.0,
    "wall_jump_lock_duration": 0.1,
    "wall_jump_min_lock": 0.05,
    "wall_slide_speed": 100.0,
    "max_midair_jumps": 1,
    "max_wall_jumps": 3,
    "coyote_duration": 0.12,
    "jump_buffer_duration": 0.1,
    "guard_posture_max": 100.0,
    "guard_break_lockout": 1.2,
    "max_dash_charges": 5,
    "dash_speed": 1100.0,
    "dash_duration": 0.08,
    "dash_friction": 25.0,
    "dash_penalty_duration": 2.0,
    "dash_recharge_time": 0.35,
    "dash_gravity_mult": 0.0,
    "dash_coyote_time": 0.05,
    "hurt_duration": 0.12,
    "invincibility_duration": 0.18,
    "faction": "hero",
}


def test_levels_file_rejects_an_unknown_top_level_key(tmp_path: Path) -> None:
    path = _write(tmp_path / "levels.json", {"version": 1, "levels": {}, "levles": {}})

    with pytest.raises(GameplayDataError, match=r"unknown field\(s\) 'levles'"):
        read_levels_file(path)


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


def test_a_misspelled_stance_is_refused(tmp_path: Path) -> None:
    """The whitelist is a whitelist: an unknown posture is not a shrug.

    A typo here would silently drop the move from every posture, which reads as
    "this attack does nothing" rather than as a data error.
    """
    raw = {
        "phases": [
            {
                "startup_frames": 1,
                "active_frames": 2,
                "recovery_frames": 1,
                "hitbox_size": [30.0, 20.0],
                "hitbox_offset": [20.0, 0.0],
                "hit": {
                    "damage": 5.0,
                    "damage_type": "blunt",
                    "knockback": {"power": [100.0, 0.0]},
                },
            }
        ],
        "cooldown": 1.0,
        "stances": ["gound"],
    }

    with pytest.raises(GameplayDataError, match=r"unknown stance 'gound'"):
        read_attack_definition(raw, "t")


def test_a_single_stance_may_be_spelled_without_a_list(tmp_path: Path) -> None:
    """``"stances": "air"`` is what a designer writes for a one-entry move."""
    doc = {
        "version": 1,
        "sets": {
            "test_set": {
                "punch": attack_definition_to_dict(PLAYER_ATTACKS["air_attack"]),
            }
        },
    }
    doc["sets"]["test_set"]["punch"]["stances"] = "air"

    sets = read_attacks_file(_write(tmp_path / "attacks.json", doc))

    assert sets["test_set"]["punch"].stances == (Stance.AIR,)


def test_a_move_is_ground_only_unless_it_says_otherwise() -> None:
    """The default is the restriction, which is why the field is a whitelist.

    A posture added later has to be opted into; if the default were "anywhere",
    a new posture would silently make every existing move reachable from it.
    """
    definition = read_attack_definition(
        {
            "phases": [
                {
                    "startup_frames": 1,
                    "active_frames": 2,
                    "recovery_frames": 1,
                    "hitbox_size": [30.0, 20.0],
                    "hitbox_offset": [20.0, 0.0],
                    "hit": {
                        "damage": 5.0,
                        "damage_type": "blunt",
                        "knockback": {"power": [100.0, 0.0]},
                    },
                }
            ],
            "cooldown": 1.0,
        },
        "t",
    )

    assert definition.stances == (Stance.GROUND,)


def test_an_attack_reachable_from_nowhere_is_rejected() -> None:
    """An empty whitelist would make a move permanently unstartable."""
    with pytest.raises(ValueError, match="cannot be empty"):
        replace(
            PLAYER_ATTACKS["light_attack"],
            stances=(),
        )


def test_a_duplicated_stance_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        replace(
            PLAYER_ATTACKS["light_attack"],
            stances=(Stance.GROUND, Stance.AIR, Stance.GROUND),
        )


def test_the_posture_a_fighter_is_in_is_resolved_most_specific_first() -> None:
    """The postures overlap, so the order is the answer.

    Sliding a wall is also airborne, and the crouch needs a floor -- resolve in
    the other order and a wall-slide reads as AIR or a crouch reads as GROUND,
    each of which quietly changes which moves are live.
    """
    input_manager = InputManager()
    player = _grounded_player(input_manager)

    assert player.stance is Stance.GROUND

    player.on_surface["floor"] = False
    assert player.stance is Stance.AIR

    player.on_surface["left"] = True
    player.left_held = True
    player.velocity.y = 100.0
    assert player.stance is Stance.WALL

    player.on_surface["floor"] = True
    player.left_held = False
    player.crouch._wanted = True
    assert player.stance is Stance.CROUCH


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
