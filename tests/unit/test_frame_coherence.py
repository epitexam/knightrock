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
from types import SimpleNamespace

import pygame
import pytest

from src.core.display.framing import Framing
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
    camera = Camera(Framing(float(WIDTH), float(HEIGHT)))
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
    before = {id(surface): rect for surface, rect in renderer._collect_visible_blits(groups)}
    camera_before = renderer.camera.offset.copy()

    scroll(renderer, groups, 0.5)
    after = {id(surface): rect for surface, rect in renderer._collect_visible_blits(groups)}

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

    blitted = next(rect for _, rect in renderer._collect_visible_blits(groups) if rect.width == 16)
    annotated = pygame.Rect(renderer.camera.apply(body.rect))

    assert blitted.topleft == annotated.topleft


def test_a_full_tick_draws_the_current_position() -> None:
    renderer, groups, body = make()
    renderer.draw(groups, alpha=1.0)
    body.rect.x += 40.0

    renderer.draw(groups, alpha=1.0)
    blitted = next(rect for _, rect in renderer._collect_visible_blits(groups) if rect.width == 16)

    assert blitted.topleft == pygame.Rect(renderer.camera.apply(body.rect)).topleft


def test_no_frame_reports_rects_any_more() -> None:
    """There is no partial presentation left to opt out of.

    The HUD used to be painted after the render decided what to present, so its
    rects could only enter the set on the *next* frame and a partial present
    showed the gauges one frame stale. The HUD is on screen throughout
    gameplay, so the escape hatch was "never present partially when an overlay
    is on screen" -- which in practice meant never, since the HUD is always
    there. Removing the partial path removes the problem rather than guarding
    against it.
    """
    renderer, groups, _body = make()
    renderer.draw(groups, alpha=0.5)

    assert renderer.draw(groups, alpha=0.5) is None
    assert not hasattr(renderer, "add_overlay_rects")


def test_every_frame_repaints_the_whole_target() -> None:
    """A full erase each frame is what makes a stale pixel impossible.

    The incremental path had to keep the erase region, the declared overlay
    rects and the previous frame's rects in exact agreement; when they slipped,
    something survived. A single full erase has nothing to keep in step.
    """
    renderer, groups, body = make()
    renderer.draw(groups, alpha=1.0)
    old_x, old_y = int(body.rect.x), int(body.rect.y)
    body.rect.x += 40.0

    renderer.draw(groups, alpha=1.0)

    # Where the body used to be, the tile underneath is back: nothing survived.
    assert renderer.surface.get_at((old_x + 4, old_y + 4))[:3] == (80, 120, 80)
    assert renderer.surface.get_at((old_x + 44, old_y + 4))[:3] == (255, 0, 0)


def test_a_dash_ghost_stays_anchored_to_the_world_while_the_camera_moves() -> None:
    """A ghost remembers where it was in the world, not where it was on screen.

    The trail used to store the screen rect computed once, at spawn, so it
    stayed nailed to the window while the world scrolled underneath: during a
    dash the ghost slid backwards across the screen instead of hanging in the
    world, and one spawned near an edge sat against that edge for its whole
    life. Mapping the world anchor through the camera every frame keeps the
    trail attached to the ground the player actually ran over.
    """
    renderer, _groups, _body = make()
    groups = SpriteGroups()
    dasher = DashingPlayer(100.0, 100.0)
    groups.entity_sprites.add(dasher)
    groups.all_sprites.add(dasher)

    renderer.draw(groups, dt=1.0)
    spawn = renderer._ghosts[0]
    assert spawn[2] > 0.0, "the dash should have spawned a ghost"

    # the world stays put, the camera pans right underneath the trail
    before = renderer._update_afterimages(groups, 1 / 60)[0][1]
    renderer.camera.follow(pygame.FRect(400.0, 100.0, 32, 32), 1 / 60)
    renderer.camera.begin_frame(1.0)
    after = renderer._update_afterimages(groups, 1 / 60)[0][1]

    assert after.x < before.x, "the ghost must travel with the world, not the window"


class DashingPlayer(pygame.sprite.Sprite):
    """A player in the dash state, which is what spawns the ghost trail."""

    faction = "player"
    is_dead = False
    max_health = 100
    health = 100

    def __init__(self, x: float, y: float) -> None:
        super().__init__()
        self.image = pygame.Surface((32, 32), pygame.SRCALPHA)
        self.image.fill((200, 200, 255, 255))
        self.rect = pygame.FRect(x, y, 32, 32)
        self.hitbox = pygame.FRect(x, y, 32, 32)
        self.state_machine = SimpleNamespace(current_state_name="dash")
