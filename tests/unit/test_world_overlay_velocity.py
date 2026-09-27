"""``world_overlay_velocity``: the vector, its minimum speed, and the two predicates that colour it.

Extracted from ``tests/unit/test_world_overlay_geo.py`` when the module it
tests was split out, so the tests moved with the code rather than reaching
across into a module that no longer owns it.
"""

import os

import pygame
import pytest
from pygame.math import Vector2

from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_velocity import VelocityLayer
from src.ui.world_ui import WorldUI
from tests.unit.helpers import lit_pixels, overlay_entity

SIZE = (1024, 768)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(SIZE)


@pytest.fixture()
def world_ui() -> WorldUI:
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill((0, 0, 0))
    return WorldUI(PanelRenderer(surface))


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(SIZE[0]), float(SIZE[1])))


@pytest.fixture()
def velocity(world_ui: WorldUI) -> VelocityLayer:
    return world_ui._geo.velocity


def test_a_velocity_that_is_not_a_vector_is_ignored(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """A tuple, a string, anything without ``.x``: drawn as nothing, not a crash.

    The debug pass reads attributes off whatever the scene hands it, and a
    sprite whose ``velocity`` is some other shape is exactly the case that
    turns a debug tool into the reason a frame is lost.
    """
    world_ui.surface.fill((0, 0, 0))
    for odd in ((3.0, 4.0), "fast", 12):
        entity = overlay_entity("Thing", velocity=odd)
        velocity.draw_velocity(entity, camera)
    assert lit_pixels(world_ui.surface) == 0


def test_a_sprite_with_no_box_draws_no_velocity(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """The arrow starts at the body, so a bodyless sprite has nowhere to start."""
    world_ui.surface.fill((0, 0, 0))
    entity = overlay_entity("Projectile", velocity=Vector2(300, 0))
    del entity.hitbox
    entity.rect = None
    velocity.draw_velocity(entity, camera)
    assert lit_pixels(world_ui.surface) == 0


def test_a_slow_sprite_draws_no_velocity(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """Below the minimum speed, nothing is drawn at all.

    The threshold is not about the arrow being too small to see -- a slow
    vector is stretched to the minimum length and would be perfectly visible.
    It is about a sprite that is barely moving not growing an arrow that claims
    it is. Nothing in the codebase slows a sprite to exactly zero, so this is
    the only place the cutoff itself is observable.
    """
    world_ui.surface.fill((0, 0, 0))
    velocity.draw_velocity(overlay_entity("Crawler", velocity=Vector2(59.0, 0.0)), camera)
    assert lit_pixels(world_ui.surface) == 0, "a sprite under the speed floor drew an arrow"


def test_a_sprite_over_the_speed_floor_does_draw(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """The positive side of the same threshold, so it is not vacuously green."""
    world_ui.surface.fill((0, 0, 0))
    velocity.draw_velocity(overlay_entity("Runner", velocity=Vector2(200.0, 0.0)), camera)
    assert lit_pixels(world_ui.surface) > 0


def test_a_zero_velocity_arrow_draws_nothing(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """The arrow method is called directly here, past the speed gate.

    ``draw_velocity`` already refuses a slow vector, so the only way to reach
    this branch is to call the painter with a zero vector -- and a head drawn
    on a tail of no length is a dot on the entity.
    """
    world_ui.surface.fill((0, 0, 0))
    velocity.draw_velocity_arrow(Vector2(300, 300), Vector2(0, 0), Colors.white)
    assert lit_pixels(world_ui.surface) == 0


def test_a_fast_sprite_gets_a_velocity_arrow(
    world_ui: WorldUI, velocity: VelocityLayer, camera: Camera
) -> None:
    """The positive case for the branch above, so it is not vacuously green."""
    world_ui.surface.fill((0, 0, 0))
    entity = overlay_entity("Runner", velocity=Vector2(400, 0))
    velocity.draw_velocity(entity, camera)
    assert lit_pixels(world_ui.surface) > 0, "a fast sprite drew no velocity arrow"
