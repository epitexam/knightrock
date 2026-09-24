from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.determinism import geometry_checksum
from src.combat.frame_data import HitProperties, PhaseDefinition
from src.combat.shapes import AnchorKind, EasingKind, ShapeKind, ShapePose
from src.core.level.systems.combat_system import CombatSystem
from src.data.attacks import (
    attack_definition_to_dict,
    read_attack_definition,
    read_attacks_file,
    write_attacks_file,
)
from tests.unit.helpers import activate, entity_at
from tests.unit.helpers import make_attack as attack


def _advanced_phase(
    shape: ShapeKind = ShapeKind.OBB,
    *,
    anchor: AnchorKind = AnchorKind.CENTER,
    anchor_offset: tuple[float, float] = (0.0, 0.0),
) -> PhaseDefinition:
    return PhaseDefinition(
        startup_frames=1,
        active_frames=2,
        recovery_frames=1,
        hitbox_size=(40.0, 20.0) if shape is not ShapeKind.CIRCLE else (20.0, 20.0),
        hitbox_offset=(0.0, 0.0),
        hitbox_shape=shape,
        hitbox_angle=30.0 if shape is ShapeKind.OBB else 0.0,
        hitbox_easing=EasingKind.EASE_IN_OUT,
        hitbox_anchor=anchor,
        hitbox_anchor_offset=anchor_offset,
        hit=HitProperties(damage=10.0),
    )


def test_advanced_shape_and_anchor_follow_attack_geometry_and_facing() -> None:
    owner = entity_at(
        100.0,
        definition=attack(
            _advanced_phase(
                anchor=AnchorKind.WEAPON,
                anchor_offset=(8.0, -6.0),
            ),
            lock_direction=False,
        ),
    )
    activate(owner)
    shape = owner.combat.attack_shapes[0]

    assert shape.kind is ShapeKind.OBB
    assert shape.position == (owner.hitbox.centerx + 8.0, owner.hitbox.centery - 6.0)
    assert shape.angle == pytest.approx(30.0)

    owner.facing_right = False
    owner.combat.sync_attack_box()
    shape = owner.combat.attack_shapes[0]

    assert shape.position == (owner.hitbox.centerx - 8.0, owner.hitbox.centery - 6.0)
    assert shape.angle == pytest.approx(-30.0)


def test_advanced_obb_can_trade_with_another_advanced_obb() -> None:
    definition = attack(_advanced_phase(ShapeKind.OBB))
    left = entity_at(0.0, faction="left", definition=definition)
    right = entity_at(10.0, faction="right", definition=definition)
    activate(left)
    activate(right)

    CombatSystem().process_attacks([left, right])

    assert left.health == 90.0
    assert right.health == 90.0


def test_v2_hitboxes_load_advanced_fields_without_legacy_phase_fields() -> None:
    raw = attack_definition_to_dict(PLAYER_ATTACKS["light_attack"])
    phase_data = raw["phases"][0]
    for key in ("hitbox_size", "hitbox_offset", "hitbox_keyframes", "extra_hitboxes"):
        phase_data.pop(key)
    phase_data["hitboxes"] = [
        {
            "shape": "capsule",
            "size": [30.0, 12.0],
            "offset": [18.0, -4.0],
            "angle": 15.0,
            "easing": "ease_in",
            "anchor": "hip",
            "anchor_offset": [2.0, -3.0],
            "keyframes": [
                {"frame": 0, "size": [20.0, 10.0], "offset": [10.0, 0.0], "angle": 0.0},
                {"frame": 3, "size": [40.0, 16.0], "offset": [30.0, -8.0], "angle": 45.0},
            ],
        }
    ]

    parsed = read_attack_definition(raw, "v2-test").phases[0]

    assert parsed.hitbox_shape is ShapeKind.CAPSULE
    assert parsed.hitbox_angle == 15.0
    assert parsed.hitbox_easing is EasingKind.EASE_IN
    assert parsed.hitbox_anchor is AnchorKind.HIP
    assert parsed.hitbox_anchor_offset == (2.0, -3.0)
    assert parsed.hitbox_keyframes[1].angle == 45.0


def test_v2_attack_file_roundtrips_through_read_and_write(tmp_path: Path) -> None:
    path = write_attacks_file(
        tmp_path / "attacks.json",
        {"player": {"light_attack": PLAYER_ATTACKS["light_attack"]}},
        version=2,
    )

    parsed = read_attacks_file(path)["player"]["light_attack"]

    assert parsed == PLAYER_ATTACKS["light_attack"]


def test_circle_shape_uses_narrowphase_instead_of_bounding_rect() -> None:
    definition = attack(_advanced_phase(ShapeKind.CIRCLE))
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    target = entity_at(14.0, faction="target", hurtbox_inflate=(-30.0, -30.0))
    target.hitbox.y = 12.0
    target.sync_rects()
    activate(attacker)

    shape = attacker.combat.attack_shapes[0]
    target_box = target.hurtbox

    assert shape.kind is ShapeKind.CIRCLE
    assert attacker.combat.attack_box.colliderect(target_box)

    CombatSystem().process_attacks([attacker, target])

    assert target.health == 100.0


def test_shape_checksum_changes_with_advanced_geometry() -> None:
    rect = pygame.FRect(0.0, 0.0, 40.0, 20.0)
    first = ShapePose(ShapeKind.OBB, (40.0, 20.0), (0.0, 0.0), 0.0)
    second = ShapePose(ShapeKind.OBB, (50.0, 30.0), (0.0, 0.0), 90.0)

    before = geometry_checksum((rect,), (first,))
    after = geometry_checksum((rect,), (second,))

    assert before != after


def test_advanced_sweep_detects_tunnelling_for_circles() -> None:
    attacker = entity_at(
        0.0, faction="attacker", definition=attack(_advanced_phase(ShapeKind.CIRCLE))
    )
    target = entity_at(20.0, faction="target", hurtbox_inflate=(-30.0, -30.0))
    attacker.combat.capture_attack_origin()
    activate(attacker)
    attacker.combat.update(1 / 60)
    attacker.hitbox.x += 40.0
    attacker.combat.sync_attack_box()

    assert not attacker.combat.attack_box.colliderect(target.hurtbox)
    CombatSystem().process_attacks([attacker, target])

    assert target.health == 90.0
