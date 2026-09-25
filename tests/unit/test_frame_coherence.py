"""The frame must be coherent: everything moves by the same amount.

Interpolation used to be applied per sprite, from the rect that sprite was
last drawn at. A sprite that had just entered the view had no such rect, so
it was drawn at its current position while its visible neighbours were drawn
partway towards theirs -- leaving a seam of background along the leading edge
of the newly revealed geometry, sweeping across the screen as the camera
moved. The blend now lives in the camera, so there is a single transform for
the whole frame and a sprite cannot lag behind another.

The same transform is what the HP bars and the debug overlay read, which is
why they stay on their sprites without any special case.
"""

import os

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups

pytestmark = pytest.mark.usefixtures("_coherent_display")

BACKGROUND = (24, 28, 36)
WIDTH, HEIGHT = 480, 320
TILE = 32


@pytest.fixture(scope="module", autouse=True)
def _coherent_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT))


class Tile(pygame.sprite.Sprite):
    """Terrain: a rect, no hitbox."""

    faction = None
    is_dead = False
    max_health = 0

    def __init__(self, x: float, y: float) -> None:
        super().__init__()
        self.image = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        self.image.fill((80, 120, 80, 255))
        self.rect = pygame.FRect(x, y, TILE, TILE)


class Body(pygame.sprite.Sprite):
    """An entity: carries a hitbox, and the bars attach to it."""

    faction = "enemy"
    is_dead = False
    max_health = 100
    health = 50

    def __init__(self, x: float) -> None:
        super().__init__()
        self.image = pygame.Surface((16, 16), pygame.SRCALPHA)
        self.image.fill((255, 0, 0, 255))
        self.rect = pygame.FRect(x, 100, 16, 16)
        self.hitbox = pygame.FRect(x, 100, 16, 16)


def make() -> tuple[Renderer, SpriteGroups, Body]:
    surface = pygame.display.get_surface()
    assert surface is not None
    camera = Camera(WIDTH, HEIGHT, zoom=1.0)
    camera.set_world_size(5000, 5000)
    renderer = Renderer(surface, camera)
    renderer.background_color = BACKGROUND
    groups = SpriteGroups()
    for i in range(40):
        for j in range(40):
            groups.all_sprites.add(Tile(i * TILE, j * TILE))
    body = Body(200.0)
    groups.all_sprites.add(body)
    groups.entity_sprites.add(body)
    return renderer, groups, body


def scroll(renderer: Renderer, groups: SpriteGroups, alpha: float) -> None:
    """One tick of camera motion, then one frame at ``alpha``.

    The camera is moved by setting the offset directly rather than through
    ``follow``: the follow smoothing would land on a fraction of a pixel, and
    the point of the test is a displacement big enough to survive rounding.
    """
    offset = renderer.camera.offset
    renderer.camera._previous_offset.update(offset.x, offset.y)
    offset.update(offset.x + 16, offset.y + 9)
    renderer.draw(groups, alpha=alpha)


def test_scrolling_never_exposes_the_background() -> None:
    """No seam along the leading edge of newly revealed terrain.

    Per-sprite interpolation left a strip of background wherever a tile that
    had just entered the view was drawn ahead of its interpolated neighbours.
    """
    renderer, groups, _body = make()
    renderer.draw(groups, alpha=1.0)
    worst = 0
    for _step in range(30):
        scroll(renderer, groups, 0.5)
        renderer.camera.begin_frame(0.5)
        surface = pygame.display.get_surface()
        assert surface is not None
        surface.fill(BACKGROUND)
        for image, rect in renderer._collect_visible_blits(groups):
            surface.blit(image, rect)
        worst = max(
            worst,
            sum(
                1
                for y in range(HEIGHT)
                for x in range(WIDTH)
                if surface.get_at((x, y))[:3] == BACKGROUND
            ),
        )
    assert worst == 0, f"{worst} px of background visible mid-scroll"


def test_every_sprite_moves_by_the_same_amount() -> None:
    """One transform for the frame: no sprite can lag behind another.

    The spread is allowed one pixel, and only because blits are integral: a
    shared sub-pixel camera offset lands on a different rounding for each
    sprite. That is a rounding artefact, not a phase difference. Per-sprite
    interpolation produced the opposite -- a gap of a full camera step, several
    pixels wide, which is what the seam was.
    """
    renderer, groups, body = make()
    renderer.draw(groups, alpha=1.0)
    before = {id(row): rect for row, rect, _ in renderer._barrows}
    camera_before = renderer.camera.offset.copy()

    scroll(renderer, groups, 0.5)
    after = {id(row): rect for row, rect, _ in renderer._barrows}

    shared = set(before) & set(after)
    assert len(shared) > 5, "the fixture must share a camera across many sprites"
    xs = {after[key].x - before[key].x for key in shared}
    ys = {after[key].y - before[key].y for key in shared}
    assert max(xs) - min(xs) <= 1, f"x spread too wide: {xs}"
    assert max(ys) - min(ys) <= 1, f"y spread too wide: {ys}"
    assert min(abs(x) for x in xs) > 0, "the frame must actually have moved"
    assert camera_before != renderer.camera.offset


def test_the_bar_and_the_overlay_read_the_same_transform() -> None:
    """Both map through the camera, so neither can sit behind the sprite."""
    renderer, groups, body = make()
    renderer.draw(groups, alpha=0.0)
    body.rect.x += 40.0
    renderer.draw(groups, alpha=0.5)

    blitted = next(rect for _, rect, _ in renderer._barrows if rect.width == 16)
    annotated = pygame.Rect(renderer.camera.apply(body.rect))

    assert blitted.topleft == annotated.topleft


def test_a_full_tick_draws_the_current_position() -> None:
    renderer, groups, body = make()
    renderer.draw(groups, alpha=1.0)
    body.rect.x += 40.0

    renderer.draw(groups, alpha=1.0)
    blitted = next(rect for _, rect, _ in renderer._barrows if rect.width == 16)

    assert blitted.topleft == pygame.Rect(renderer.camera.apply(body.rect)).topleft


def test_a_frame_carrying_the_hud_never_presents_partially() -> None:
    """The HUD is painted after the render decides what to present.

    Its rects can therefore only join the set on the *next* frame, so a
    partial present would show the gauges one frame stale: a band along the
    bottom of the window alternating between the old and the new fill. The
    HUD is on screen throughout gameplay, so a frame carrying overlay rects
    is not allowed to take the partial path at all.
    """
    renderer, groups, body = make()
    renderer.add_overlay_rects([pygame.Rect(0, HEIGHT - 40, WIDTH, 40)])

    rects = renderer.draw(groups)

    assert rects is None, "a frame with overlay rects must repaint everything"


def test_a_frame_without_overlays_still_uses_the_partial_path() -> None:
    """The guard is about overlays, not a blanket full refresh.

    A sparse scene whose previous frame was equally sparse still takes the
    partial path, so the refresh stays available to whatever does not paint
    on top of the world pass.
    """
    renderer, _groups, _body = make()
    groups = SpriteGroups()
    groups.all_sprites.add(Tile(0.0, 0.0))
    groups.all_sprites.add(Body(40.0))

    first = renderer.draw(groups)
    second = renderer.draw(groups)

    assert first is not None
    assert second is not None
