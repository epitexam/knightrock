"""The strike layer: each family drawn its own way, the charge, the warning, the shots."""

from __future__ import annotations

import os

import pygame
import pytest

from src.presentation.rendering import strike_trails as st
from src.simulation.combat.shapes import ShapeKind, ShapePose
from tests.headless.arena import DT, PLAYER_X, SHOOT, SLASH, arena, foe, settle, tap


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


BLADE_SHAPE = ShapePose(ShapeKind.OBB, (28.0, 5.0), (10.0, 0.0), 0.0)
LIMB_SHAPE = ShapePose(ShapeKind.CAPSULE, (22.0, 8.0), (10.0, 0.0), 0.0)
RING_SHAPE = ShapePose(ShapeKind.CIRCLE, (30.0, 30.0), (10.0, 0.0), 0.0)


@pytest.mark.parametrize(
    ("enemy", "move", "shape", "unblockable", "look"),
    [
        (False, "slash_high_1", BLADE_SHAPE, False, st.BLADE),
        (False, "slash_high_4", BLADE_SHAPE, False, st.HEAVY_BLADE),
        (False, "charged_slash", BLADE_SHAPE, True, st.CHARGED),
        (False, "charged_slash_full", BLADE_SHAPE, True, st.CHARGED_FULL),
        (False, "death_blow", BLADE_SHAPE, True, st.DEATH),
        (False, "punch_1", LIMB_SHAPE, True, st.BODY),
        (False, "charged_kick", LIMB_SHAPE, True, st.CHARGED_BODY),
        (False, "throw", RING_SHAPE, True, st.THROW),
        (True, "claw_swipe", LIMB_SHAPE, False, st.ENEMY),
        (True, "shell_roll", RING_SHAPE, True, st.ENEMY_RING),
        (True, "bite", LIMB_SHAPE, True, st.ENEMY_UNBLOCKABLE),
    ],
)
def test_each_family_has_its_look(
    enemy: bool, move: str, shape: ShapePose, unblockable: bool, look: st.Look
) -> None:
    assert st.look_for(enemy, move, shape, unblockable) is look


def test_a_charged_cut_does_not_look_like_a_plain_one() -> None:
    plain, charged, full = st.BLADE, st.CHARGED, st.CHARGED_FULL
    assert plain.core != charged.core != full.core
    assert plain.ttl < charged.ttl < full.ttl
    assert plain.glow < charged.glow < full.glow


def test_a_held_button_shows_its_charge_and_lets_it_go() -> None:
    level, pad, player = arena()
    settle(level)
    trails = st.StrikeTrails()
    pad.held = frozenset({SLASH})
    for _ in range(40):
        level.update(DT)
    trails.update([player], DT)
    assert len(trails._charges) == 1

    pad.held = frozenset()
    level.update(DT)
    trails.update([player], DT)
    assert not trails._charges


def test_an_enemy_winding_up_is_warned_at_the_height_of_its_blow() -> None:
    from src.simulation.entities.enemies.schema import EnemyMove

    level, _pad, player = arena()
    tooth = foe(level, "tooth", PLAYER_X + 60.0)
    tooth.moves = (EnemyMove("snap", 400.0),)
    settle(level, 5)
    trails = st.StrikeTrails()
    warned = None
    for _ in range(240):
        level.update(DT)
        trails.update([tooth], DT)
        if trails._warnings:
            warned = trails._warnings[0]
            break
    assert warned is not None
    assert warned.point[1] > tooth.hitbox.centery, "a low blow is warned low"
    assert player is not None


def test_a_shot_in_flight_is_drawn_and_its_wake_fades_after_it() -> None:
    level, pad, _player = arena()
    settle(level)
    trails = st.StrikeTrails()
    tap(level, pad, SHOOT, ticks=6)
    shots = list(level.groups.projectile_sprites)
    trails.update([], DT, shots)
    assert len(trails._shots) == 1

    surface = pygame.Surface((400, 300), pygame.SRCALPHA)
    trails.draw(surface, level.camera)

    for _ in range(30):
        trails.update([], DT, ())
    assert not trails._shots
