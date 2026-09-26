"""Nothing may survive its frame.

The renderer used to erase the union of the sprite rects and present only the
listed ones, so anything painted outside that union -- the HUD gauges, the world
HP bars -- was written to the surface but never erased on the following frame.
A gauge that shrank or a bar that trailed its sprite left a stripe of stale
pixels, which read as banding while running. Keeping the erase region, the
declared overlay rects and the previous frame's rects in exact agreement was
the whole difficulty, and they did not always agree.

There is no incremental path any more, so there is nothing left to keep in step:
every frame erases the whole target and repaints every layer. The test below is
the property that used to be worth a fuzz and is now worth a straight
comparison -- the rendered target must equal a from-scratch repaint of the same
frame, pixel for pixel. A divergence would mean some layer is drawing outside
the erase again.
"""

import os

import pygame
import pytest

from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups
from src.ui.hud import HUD

pytestmark = pytest.mark.usefixtures("_staleness_display")

BACKGROUND = (24, 28, 36)
WIDTH, HEIGHT = 320, 240


@pytest.fixture(scope="module", autouse=True)
def _staleness_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT))


class Enemy(pygame.sprite.Sprite):
    """A damageable enemy: the only kind of sprite that carries a world bar."""

    faction = "enemy"
    is_dead = False
    max_health = 100
    health = 50

    def __init__(self, x: float = 40.0, size: int = 20) -> None:
        super().__init__()
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.image.fill((255, 0, 0, 255))
        self.rect = pygame.FRect(x, 100, size, size)


class Player:
    """The minimal surface ``HUD.layout`` reads."""

    health = 100
    max_health = 100
    guard_posture = 50
    guard_posture_max = 100
    guard_posture_lockout_timer = 0.0
    guard_lockout_timer = 0.0
    dash_charges = 2
    max_dash_charges = 2
    dash_recharge_timer = 0.0
    combo_count = 0
    combo_timer = 0.0


def make_world() -> tuple[Renderer, SpriteGroups, Enemy, HUD, Player]:
    surface = pygame.display.get_surface()
    assert surface is not None
    camera = Camera(Framing(float(WIDTH), float(HEIGHT)))
    camera.set_world_size(5000, 5000)
    renderer = Renderer(surface, camera)
    renderer.background_color = BACKGROUND
    groups = SpriteGroups()
    enemy = Enemy()
    groups.all_sprites.add(enemy)
    groups.entity_sprites.add(enemy)
    return renderer, groups, enemy, HUD(renderer.ui_manager.renderer), Player()


def run_live(alpha: float, steps: int = 30) -> pygame.Surface:
    """The real path: ``Renderer.draw`` then the bars and the HUD on top."""
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill(BACKGROUND)
    renderer, groups, enemy, hud, player = make_world()
    for step in range(steps):
        enemy.rect.x = 20.0 + step * 4
        player.health = max(30, 100 - step * 2)
        renderer.draw(groups, alpha=alpha)
        renderer.draw_health_bars(groups.entity_sprites)
        hud.draw(player)
    return surface.copy()


def run_from_scratch(alpha: float, steps: int = 30) -> pygame.Surface:
    """The reference: the same frame painted onto a surface nothing survives on."""
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill(BACKGROUND)
    renderer, groups, enemy, hud, player = make_world()
    for step in range(steps):
        enemy.rect.x = 20.0 + step * 4
        player.health = max(30, 100 - step * 2)
        surface.fill(BACKGROUND)
        renderer.camera.begin_frame(alpha)
        for image, rect in renderer._collect_visible_blits(groups):
            surface.blit(image, rect)
        renderer.draw_health_bars(groups.entity_sprites)
        hud.draw(player)
    return surface.copy()


def divergence(left: pygame.Surface, right: pygame.Surface) -> int:
    return sum(
        1
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if left.get_at((x, y))[:3] != right.get_at((x, y))[:3]
    )


@pytest.mark.parametrize("alpha", [0.0, 0.5])
def test_a_moving_frame_leaves_no_stale_pixel(alpha: float) -> None:
    """A shrinking gauge and a moving bar must not outlive their frame."""
    assert divergence(run_live(alpha), run_from_scratch(alpha)) == 0


def test_a_frame_reports_nothing_because_there_is_nothing_to_report() -> None:
    """The partial set, its budget, and the escape hatch are all gone."""
    renderer, groups, _enemy, _hud, _player = make_world()

    assert renderer.draw(groups, alpha=0.0) is None
    assert not hasattr(renderer, "add_overlay_rects")
    assert not hasattr(renderer, "clear_overlay_rects")


def test_the_hp_bar_stays_on_its_sprite() -> None:
    """The bar is drawn on the sprite it belongs to, not half a tick behind.

    The world pass interpolates between simulation ticks, so a bar anchored to
    the simulation position while its sprite is blitted partway towards the
    next one leaves a stripe of bar-coloured pixels behind it.
    """
    renderer, groups, enemy, _hud, _player = make_world()

    enemy.rect.x = 40.0
    renderer.draw(groups, alpha=0.0)
    enemy.rect.x = 48.0
    renderer.draw(groups, alpha=0.5)
    blitted = renderer._collect_visible_blits(groups)[0][1]
    bar = renderer.draw_health_bars(groups.entity_sprites)[0]

    assert bar.centerx == blitted.centerx
