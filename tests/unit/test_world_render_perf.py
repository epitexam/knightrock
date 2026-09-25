"""Regression guards for the per-frame world render cost.

The frame is ~97% static-sprite iteration, so these tests assert *what the
frame touches* rather than how long it takes: counting whole-group scans and
per-sprite rebuilds is deterministic, while a timing budget would flake on a
shared CI runner.
"""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups

pytestmark = pytest.mark.usefixtures("_world_render_display")


@pytest.fixture(scope="module", autouse=True)
def _world_render_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "audio")
    pygame.init()
    pygame.display.set_mode((320, 240))


def make_renderer(zoom: float = 1.0) -> tuple[Renderer, SpriteGroups]:
    surface = pygame.Surface((320, 240))
    camera = Camera(320, 240, zoom=zoom)
    camera.set_world_size(640, 480)
    return Renderer(surface, camera), SpriteGroups()


class FlashingEntity(pygame.sprite.Sprite):
    """A damageable entity: the only kind of thing that flashes."""

    def __init__(self, flash_timer: float = 0.05) -> None:
        super().__init__()
        self.faction = "enemy"
        self.image = pygame.Surface((8, 8), pygame.SRCALPHA)
        self.rect = pygame.FRect(4.0, 4.0, 8, 8)
        self.flash_timer = flash_timer


class Tile(pygame.sprite.Sprite):
    """A terrain tile: an image, a world rect, and no gameplay state."""

    def __init__(self, topleft: tuple[float, float] = (8.0, 8.0)) -> None:
        super().__init__()
        self.image = pygame.Surface((32, 32), pygame.SRCALPHA)
        self.rect = pygame.FRect(topleft, (32, 32))


class DashingPlayer(pygame.sprite.Sprite):
    """An entity that both flashes and dashes, i.e. the worst case."""

    def __init__(self, flash_timer: float = 0.05) -> None:
        super().__init__()
        self.faction = "player"
        self.state_machine = SimpleNamespace(current_state_name="dash")
        self.image = pygame.Surface((20, 30), pygame.SRCALPHA)
        self.rect = pygame.FRect(10.0, 10.0, 20, 30)
        self.flash_timer = flash_timer


def test_the_dashing_player_is_resolved_once_not_per_sprite(
    monkeypatch,
) -> None:
    """``is_player_dashing`` needs three lookups; the frame asked it ~1000 times.

    It used to run against every visible sprite to find at most one player.
    Resolving it once per frame turns the blit loop into an identity test.
    """
    renderer, groups = make_renderer()
    player = DashingPlayer()
    groups.all_sprites.add(player)
    groups.entity_sprites.add(player)
    for _ in range(200):
        groups.all_sprites.add(Tile((32.0, 32.0)))

    calls = 0
    import src.core.rendering.renderer as module

    original = module.is_player_dashing

    def counting(sprite):
        nonlocal calls
        calls += 1
        return original(sprite)

    monkeypatch.setattr(module, "is_player_dashing", counting)
    renderer.draw(groups)

    # Two per frame, both constant: one resolves the dashing player for the
    # blit loop, one by the ghost pass. Neither scales with the 200 tiles.
    assert calls == 2


def test_damage_flashes_only_scan_entities() -> None:
    """Only entities carry a ``flash_timer``, so only entities are scanned.

    Scanning ``all_sprites`` instead cost a ``getattr`` on every tile of the
    level, ~1000 of them, to find at most a handful of flashes.
    """
    renderer, groups = make_renderer()
    # The flashing entity is in entity_sprites only: a scan of all_sprites
    # would not find it, which is exactly what makes this a real assertion
    # about which group is walked.
    groups.entity_sprites.add(FlashingEntity())
    for _ in range(200):
        groups.all_sprites.add(Tile((32.0, 32.0)))

    flashes = renderer._collect_flashes(groups)

    assert len(flashes) == 1


def test_the_render_interpolates_between_ticks() -> None:
    """A sprite between two ticks is drawn partway between them.

    The simulation is fixed-step at 60Hz while a frame presents at whatever
    the display does, so the position a tick wrote is on average half a tick
    stale. Drawing it as-is showed that same image twice whenever two ticks
    ran per frame, which reads as judder.
    """
    renderer, groups = make_renderer()
    renderer.draw(groups)
    assert renderer.alpha == pytest.approx(0.0)

    renderer.draw(groups, alpha=0.5)
    assert renderer.alpha == pytest.approx(0.5)


def test_interpolation_moves_a_sprite_partway_toward_its_next_tick() -> None:
    """At half a tick, the sprite must be halfway between the two positions."""
    renderer, groups = make_renderer()
    tile = Tile((8.0, 8.0))
    groups.all_sprites.add(tile)
    renderer.draw(groups)
    tile.rect.x = 48.0

    renderer.alpha = 0.5
    blits = renderer._collect_visible_blits(groups)

    assert blits[0][1].x == pytest.approx(28.0)


def test_a_full_alpha_draws_the_current_position() -> None:
    renderer, groups = make_renderer()
    tile = Tile((8.0, 8.0))
    groups.all_sprites.add(tile)
    renderer.draw(groups)
    tile.rect.x = 48.0

    renderer.alpha = 1.0
    blits = renderer._collect_visible_blits(groups)

    assert blits[0][1].x == pytest.approx(48.0)


def test_a_sprite_is_never_interpolated_backwards() -> None:
    """Only a sprite that moved since the last tick has a previous position.

    A freshly spawned tile has none, and reading its position as "previous"
    would drag it from the origin on its first frame.
    """
    renderer, groups = make_renderer()
    tile = Tile((100.0, 8.0))
    groups.all_sprites.add(tile)

    renderer.alpha = 0.5
    blits = renderer._collect_visible_blits(groups)

    assert blits[0][1].x == pytest.approx(100.0)


def test_a_reversed_move_still_interpolates_forward() -> None:
    """Direction does not matter: the blend is between the two positions."""
    renderer, groups = make_renderer()
    tile = Tile((100.0, 8.0))
    groups.all_sprites.add(tile)
    renderer.draw(groups)
    tile.rect.x = 60.0

    renderer.alpha = 0.5
    blits = renderer._collect_visible_blits(groups)

    assert blits[0][1].x == pytest.approx(80.0)


def test_the_ghost_pass_only_scans_entities() -> None:
    """A dashing player in ``all_sprites`` alone must not produce a ghost.

    The pass walks ``entity_sprites``: the dashing player is an entity, so
    walking the whole level was a wasted scan of ~1000 tiles.
    """
    renderer, groups = make_renderer()
    groups.all_sprites.add(DashingPlayer())
    for _ in range(50):
        groups.all_sprites.add(Tile((32.0, 32.0)))

    renderer._spawn_afterimage(groups)

    assert renderer._ghosts == []


def test_the_ghost_pass_still_sees_a_dashing_entity() -> None:
    """The group swap must not silently disable the trail."""
    renderer, groups = make_renderer()
    player = DashingPlayer()
    groups.all_sprites.add(player)
    groups.entity_sprites.add(player)

    renderer._spawn_afterimage(groups)

    assert len(renderer._ghosts) == 1


def test_the_flash_silhouette_is_memoised() -> None:
    """A silhouette is 6.8us to build and a flash lasts 0.1s.

    Rebuilding it per frame was the most expensive operation on the hit
    feedback path. It only depends on the source image, so it is built once
    and copied to carry the per-frame alpha.
    """
    renderer, _ = make_renderer()
    image = pygame.Surface((16, 16), pygame.SRCALPHA)
    image.fill((255, 0, 0, 255))

    first = renderer._white_silhouette(image)
    second = renderer._white_silhouette(image)

    assert first is second
    assert first.get_size() == (16, 16)
    # White, and still carrying the source alpha as its mask.
    assert first.get_at((8, 8))[:3] == (255, 255, 255)


def test_the_flash_alpha_is_per_frame_not_shared() -> None:
    """The memoised silhouette must be copied, or one frame dims the next."""
    renderer, _ = make_renderer()
    image = pygame.Surface((16, 16), pygame.SRCALPHA)
    image.fill((255, 0, 0, 255))
    silhouette = renderer._white_silhouette(image)

    tinted = silhouette.copy()
    tinted.set_alpha(64)

    assert silhouette.get_alpha() != 64


def test_the_camera_reuses_its_frame_transform() -> None:
    """One transform per frame, not one per visible sprite.

    ``is_visible`` rebuilt the viewport ``FRect`` and ``apply`` rebuilt a
    ``Vector2`` plus two trig calls, ~1000 times each per frame.
    """
    camera = Camera(320, 240, zoom=1.25)
    camera.set_world_size(5000, 5000)
    camera.offset.update(100.0, 100.0)
    camera.begin_frame()
    before = (tuple(camera._shake), camera._shift, camera._shift_y)

    for _ in range(500):
        camera.is_visible(pygame.FRect(0, 0, 32, 32))
        camera.apply(pygame.FRect(0, 0, 32, 32))

    assert (tuple(camera._shake), camera._shift, camera._shift_y) == before


def test_moving_the_camera_invalidates_the_frame_transform() -> None:
    camera = Camera(320, 240, zoom=1.0)
    camera.set_world_size(5000, 5000)
    player = pygame.FRect(0, 0, 32, 32)
    camera.begin_frame()
    before = camera.apply(player)

    camera.follow(pygame.FRect(2000, 2000, 32, 32), 1.0)
    after = camera.apply(player)

    assert before != after


def test_a_zoom_change_invalidates_the_frame_transform() -> None:
    camera = Camera(320, 240, zoom=1.0)
    camera.set_world_size(5000, 5000)
    camera.begin_frame()
    before = camera.apply(pygame.FRect(100, 100, 32, 32))

    camera.set_zoom(2.0)
    after = camera.apply(pygame.FRect(100, 100, 32, 32))

    assert before != after


def test_a_viewport_change_invalidates_the_cull_rect() -> None:
    """A wider viewport must see sprites the old one culled away."""
    camera = Camera(320, 240, zoom=1.0)
    camera.set_world_size(5000, 5000)
    far_sprite = pygame.FRect(400, 100, 32, 32)
    camera.begin_frame()
    assert camera.is_visible(far_sprite) is False

    camera.set_viewport_size(800, 480)

    assert camera.is_visible(far_sprite) is True
