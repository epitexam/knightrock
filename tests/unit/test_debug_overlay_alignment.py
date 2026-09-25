"""The debug overlay must annotate the pixels it describes.

The world pass interpolates sprites between simulation ticks; the overlay
annotates in world space and maps through ``camera.apply``, i.e. at the
simulation position. Letting both run at their own phase detaches every box,
label and line from the sprite it belongs to by up to half a tick, which
while moving reads as annotations stuck to the previous position.

Debug output exists to read exact positions, so the blend is pinned to the
current tick whenever the overlay draws.
"""

import os

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups

pytestmark = pytest.mark.usefixtures("_overlay_align_display")


@pytest.fixture(scope="module", autouse=True)
def _overlay_align_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


class Body(pygame.sprite.Sprite):
    """A sprite that moves, so interpolation has something to blend."""

    faction = "enemy"
    is_dead = False
    max_health = 0

    def __init__(self, x: float) -> None:
        super().__init__()
        self.image = pygame.Surface((16, 16), pygame.SRCALPHA)
        self.image.fill((255, 0, 0, 255))
        self.rect = pygame.FRect(x, 100, 16, 16)
        #: An entity carries a hitbox; terrain tiles carry only a rect, which
        #: is what makes them statics for the overlay.
        self.hitbox = pygame.FRect(x, 100, 16, 16)


def make() -> tuple[Renderer, SpriteGroups, Body]:
    surface = pygame.display.get_surface()
    assert surface is not None
    camera = Camera(320, 240, zoom=1.0)
    camera.set_world_size(5000, 5000)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    body = Body(40.0)
    groups.all_sprites.add(body)
    groups.entity_sprites.add(body)
    return renderer, groups, body


def test_debug_pins_the_blend_to_the_current_tick() -> None:
    """An interpolated sprite and its annotation would be half a tick apart."""
    renderer, groups, _body = make()
    renderer.draw(groups, debug_enabled=True, alpha=0.5)

    assert renderer.alpha == 1.0


def test_the_debug_sprite_is_drawn_where_the_overlay_reads_it() -> None:
    """The blitted rect must be the one ``camera.apply`` reports."""
    renderer, groups, body = make()
    renderer.draw(groups, debug_enabled=True, alpha=0.0)
    body.rect.x += 20.0

    renderer.draw(groups, debug_enabled=True, alpha=0.5)
    blitted = renderer._barrows[0][1]
    annotated = pygame.Rect(renderer.camera.apply(body.rect))

    assert blitted.topleft == annotated.topleft


def test_gameplay_still_interpolates() -> None:
    """The pin is a debug-mode decision, not a global one."""
    renderer, groups, body = make()
    renderer.draw(groups, alpha=0.0)
    body.rect.x += 20.0

    renderer.draw(groups, alpha=0.5)
    blitted = renderer._barrows[0][1]

    assert blitted.x == pytest.approx(50.0), "halfway between 40 and 60"


class Terrain(pygame.sprite.Sprite):
    """A terrain tile: a rect, no hitbox. What a level is mostly made of."""

    faction = None
    is_dead = False
    max_health = 0

    def __init__(self, x: float) -> None:
        super().__init__()
        self.image = pygame.Surface((16, 16), pygame.SRCALPHA)
        self.image.fill((80, 120, 80, 255))
        self.rect = pygame.FRect(x, 100, 16, 16)


def test_terrain_does_not_reach_the_reference_builder() -> None:
    """The overlay must not build hitboxes for the ~970 tiles of a level.

    ``_debug_reference`` allocates one to three FRects per call, and the gate
    that used to protect it tested ``type(sprite) is pygame.sprite.Sprite``,
    which never matches: the tiles are a *subclass*. So every tile paid for
    the allocation before the ``statics`` toggle could skip it, and the toggle
    defaulted to on. A level carried 972 sprites, 970 of them tiles.
    """
    renderer, groups, body = make()
    world_ui = renderer.ui_manager.world_ui
    calls: list[object] = []
    original = world_ui._debug_reference
    world_ui._debug_reference = lambda sprite: (  # type: ignore[method-assign]
        calls.append(sprite) or original(sprite)
    )
    sprites: list[pygame.sprite.Sprite] = [body]
    for index in range(5):
        sprites.append(Terrain(40.0 + index * 16))

    world_ui.draw_debug_overlays(sprites, renderer.camera, 0.0)

    assert calls == [body], "only the entity should reach the reference builder"


def test_the_statics_layer_can_still_bring_the_tiles_back() -> None:
    """F4 remains a way to see terrain, the default just stops paying for it."""
    renderer, groups, _body = make()
    world_ui = renderer.ui_manager.world_ui
    assert world_ui.layers["statics"] is False
    world_ui.toggle("statics")
    assert world_ui.layers["statics"] is True
