"""The dash and the block, drawn: a spaced trail in colour with speed lines, and a shield.

The dash trail is spaced by the distance covered, so its stamps never pile up,
and each stamp nearer the fighter is bluer than the last; streaks run behind a
dashing fighter. The block is an animated shield: it opens outward on the side
the blow came from and throws sparks off its face.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core.display.framing import Framing
from src.core.fx.particles import ShieldArcParticle
from src.core.fx.spawners import spawn_guard_arc
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer, _ghost_tint
from src.core.rendering.strike_trails import StrikeTrails
from src.core.settings import Afterimage
from src.core.sprite_groups import SpriteGroups
from tests.unit.test_juice_effects import DashSprite


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def _renderer() -> tuple[Renderer, SpriteGroups, DashSprite]:
    camera = Camera(Framing(400.0, 200.0))
    camera.set_world_size(400, 200)
    renderer = Renderer(pygame.Surface((400, 200)), camera)
    groups = SpriteGroups()
    dasher = DashSprite(state="dash")
    groups.all_sprites.add(dasher)
    groups.entity_sprites.add(dasher)
    return renderer, groups, dasher


def test_a_dasher_standing_still_leaves_one_stamp_not_a_pile() -> None:
    renderer, groups, _dasher = _renderer()
    for _ in range(8):
        renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)

    assert len(renderer._ghosts) == 1


def test_a_dash_leaves_a_stamp_each_time_it_covers_the_spacing() -> None:
    renderer, groups, dasher = _renderer()
    for _ in range(5):
        renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)
        dasher.rect.x += Afterimage.SPACING + 1.0

    assert len(renderer._ghosts) == 5


def test_each_stamp_is_bluer_than_the_one_before() -> None:
    tints = [_ghost_tint(index) for index in range(Afterimage.TINT_STEPS + 1)]

    reds = [tint[0] for tint in tints]
    assert reds == sorted(reds, reverse=True), "the red drains out stamp by stamp"
    assert tints[-1] == Afterimage.DEEP_TINT


def test_a_dashing_fighter_trails_speed_lines_behind_it() -> None:
    trails = StrikeTrails()
    dasher = SimpleNamespace(
        faction="player",
        state_machine=SimpleNamespace(current_state_name="dash"),
        velocity=pygame.math.Vector2(900.0, 0.0),
        hitbox=pygame.FRect(100, 100, 40, 56),
        facing_right=True,
        is_dead=False,
        combat=None,
    )
    trails.update([dasher], 1 / 60)

    assert len(trails._dashes) == 1
    assert trails._dashes[0].back[0] < dasher.hitbox.centerx, "the lines run behind"

    dasher.state_machine.current_state_name = "run"
    trails.update([dasher], 1 / 60)
    assert not trails._dashes


def _entity(facing: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        hitbox=pygame.FRect(100, 100, 40, 48),
        velocity=pygame.math.Vector2(0.0, 0.0),
        facing_right=facing,
    )


def test_the_shield_opens_outward_as_it_lives() -> None:
    shield = spawn_guard_arc(Group(), _entity())
    assert isinstance(shield, ShieldArcParticle)
    first = pygame.mask.from_surface(shield.image).count()
    shield.update(shield.max_ttl * 0.5)

    assert shield.age > 0.0
    assert pygame.mask.from_surface(shield.image).count() != first, "it moves, it is not a stamp"


def test_the_shield_and_its_sparks_are_on_the_side_of_the_blow() -> None:
    shield = spawn_guard_arc(Group(), _entity(facing=True))
    assert shield is not None
    shield.update(shield.max_ttl * 0.4)
    image = shield.image
    width, height = image.get_size()
    left = sum(1 for x in range(width // 2) for y in range(height) if image.get_at((x, y))[3])
    right = sum(
        1 for x in range(width // 2, width) for y in range(height) if image.get_at((x, y))[3]
    )

    assert right > left * 2
