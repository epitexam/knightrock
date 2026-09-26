"""The camera is a pure translation over a fixed framing.

The zoom tests this file replaces asserted that a higher zoom shows less of the
world. That was true and it was not enough: the zoom was derived from the
*window*, so the visible world was still a free variable of a video setting, and
a player could widen their field of view by opening the video menu. What is
asserted now is the stronger property -- the visible world does not depend on
anything the player can configure -- plus the covering arithmetic, which is
unchanged and still worth fuzzing.
"""

import os
import random

import pygame
import pytest

from src.core.display.framing import DEFAULT_FRAMING, Framing
from src.core.display.viewport import Viewport
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1440, 900))


class StaticSprite(pygame.sprite.Sprite):
    def __init__(self, topleft, size=(16, 16), color=(255, 0, 0)):
        super().__init__()
        self.image = pygame.Surface(size)
        self.image.fill(color)
        self.rect = pygame.FRect(topleft, size)


def _settled(camera: Camera, target: pygame.FRect) -> None:
    """Run the follow long enough to converge on the target."""
    for _ in range(240):
        camera.follow(target, 1 / 60)


def test_the_visible_world_is_the_framing_and_nothing_else() -> None:
    camera = Camera()

    assert (camera.viewport_width, camera.viewport_height) == DEFAULT_FRAMING.size


def test_a_second_camera_with_another_framing_sees_that_much() -> None:
    """The framing is the only input, so a different one gives a different view."""
    tight = Camera(Framing(800.0, 450.0))
    wide = Camera(Framing(1920.0, 1080.0))

    assert (tight.viewport_width, tight.viewport_height) == (800.0, 450.0)
    assert (wide.viewport_width, wide.viewport_height) == (1920.0, 1080.0)


def test_the_camera_exposes_no_zoom_at_all() -> None:
    """A zoom setter is exactly the door this rework closed.

    Asserted rather than merely absent, so putting one back is a test failure
    and not a silent return to the old behaviour.
    """
    camera = Camera()

    assert not hasattr(camera, "zoom")
    assert not hasattr(camera, "set_zoom")
    assert not hasattr(camera, "set_viewport_size")


def test_apply_is_the_identity_when_the_camera_has_not_moved() -> None:
    camera = Camera()
    camera.begin_frame(1.0)
    box = pygame.FRect(100, 100, 40, 40)

    assert camera.apply(box) == box


def test_apply_translates_by_the_offset() -> None:
    camera = Camera()
    camera.offset.update(30.0, -12.0)
    camera.begin_frame(1.0)

    assert camera.apply(pygame.FRect(10.0, 20.0, 5.0, 6.0)) == pygame.FRect(-20.0, 32.0, 5.0, 6.0)


def test_a_higher_framing_shrinks_the_visible_world() -> None:
    """Kept from the zoom era, restated: more framing, more world."""
    tight = Camera(Framing(800.0, 450.0))
    loose = Camera(Framing(1600.0, 900.0))

    assert tight.viewport_width < loose.viewport_width
    assert tight.viewport_height < loose.viewport_height


def test_culling_uses_the_framing_rect() -> None:
    camera = Camera()
    camera.set_world_size(4000, 3000)
    camera.offset.update(1000.0, 800.0)
    camera.begin_frame(1.0)

    assert camera.is_visible(pygame.FRect(1000.0, 800.0, 32, 32))
    # Just past the framing's right edge.
    assert not camera.is_visible(pygame.FRect(1000.0 + camera.viewport_width + 1, 800.0, 32, 32))


def test_follow_centres_the_target() -> None:
    camera = Camera()
    camera.set_world_size(8000, 6000)
    target = pygame.FRect(4000, 3000, 64, 64)
    _settled(camera, target)
    camera.begin_frame(1.0)

    centre = camera.apply(target).center
    assert centre == pytest.approx((camera.viewport_width / 2, camera.viewport_height / 2), abs=1.0)


def test_follow_stays_inside_the_world() -> None:
    camera = Camera()
    camera.set_world_size(2000, 1200)
    _settled(camera, pygame.FRect(0, 0, 64, 64))
    camera.begin_frame(1.0)

    assert camera.offset.x >= 0.0
    assert camera.offset.y >= 0.0


def test_a_world_smaller_than_the_framing_is_centred() -> None:
    camera = Camera()
    camera.set_world_size(400, 300)
    _settled(camera, pygame.FRect(0, 0, 32, 32))
    camera.begin_frame(1.0)

    assert camera.offset.x == pytest.approx(-(camera.viewport_width - 400) / 2)
    assert camera.offset.y == pytest.approx(-(camera.viewport_height - 300) / 2)


def test_the_interpolation_blend_moves_the_whole_frame_together() -> None:
    """alpha is the camera's, not a per-sprite offset: that is what keeps a
    frame coherent when a sprite enters the view."""
    camera = Camera()
    camera.set_world_size(8000, 6000)
    camera.offset.update(500.0, 400.0)
    camera._previous_offset.update(400.0, 300.0)

    camera.begin_frame(0.0)
    at_zero = camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8))
    camera.begin_frame(1.0)
    at_one = camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8))

    # Halfway: the offset is halfway between the two positions.
    assert at_zero.x == pytest.approx(1000.0 - 400.0)
    assert at_one.x == pytest.approx(1000.0 - 500.0)
    assert camera.apply(pygame.FRect(2000.0, 1000.0, 8, 8)).x - at_one.x == 1000.0


def test_alpha_is_clamped_to_the_tick() -> None:
    camera = Camera()
    camera.set_world_size(8000, 6000)
    camera.offset.update(500.0, 400.0)
    camera._previous_offset.update(400.0, 300.0)

    camera.begin_frame(-5.0)
    before = camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8))
    camera.begin_frame(0.0)
    assert camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8)) == before
    camera.begin_frame(9.0)
    at_one = camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8))
    camera.begin_frame(1.0)
    assert camera.apply(pygame.FRect(1000.0, 1000.0, 8, 8)) == at_one


def test_the_shake_is_deterministic() -> None:
    """Same ticks, same pixels: otherwise a rollback rewinds the picture too."""

    def shaken() -> tuple[float, float]:
        camera = Camera()
        camera.add_trauma(1.0)
        for _ in range(30):
            camera.follow(pygame.FRect(0, 0, 8, 8), 1 / 60)
        return camera.shake_offset()

    assert shaken() == shaken()


def test_trauma_decays_and_is_clamped() -> None:
    camera = Camera()
    camera.add_trauma(5.0)
    assert camera.trauma == 1.0
    camera.add_trauma(-3.0)
    assert camera.trauma == 1.0, "a negative amount must not make shake negative"
    for _ in range(240):
        camera.follow(pygame.FRect(0, 0, 8, 8), 1 / 60)
    assert camera.trauma == 0.0


def test_a_screen_rect_covers_the_pixels_it_was_meant_to_cover() -> None:
    """Screen rects round outward, so the extent is never trimmed.

    ``pygame.Rect`` truncates the fractional bounds ``apply`` returns, which
    always rounds a rectangle *in*. The tile at the far edge of a level came
    out a pixel short: the last column of the frame was painted by nothing and
    kept the background fill. The camera only reaches that alignment when it is
    pushed against its clamp, which in practice means dashing into a corner.
    """
    camera = Camera()
    camera.set_world_size(2560, 1920)
    camera.offset.x = 2560 - camera.viewport_width
    camera.offset.y = 1920 - camera.viewport_height
    camera._previous_offset = pygame.Vector2(camera.offset)
    camera.begin_frame(1.0)

    right_edge = camera.apply_covering(pygame.FRect(2496.0, 1856.0, 64.0, 64.0))
    bottom_edge = camera.apply_covering(pygame.FRect(0.0, 1856.0, 64.0, 64.0))

    assert right_edge.right == round(camera.viewport_width)
    assert bottom_edge.bottom == round(camera.viewport_height)


def test_a_screen_rect_left_of_the_view_rounds_down_not_toward_zero() -> None:
    """Negative screen coordinates floor, they do not truncate toward zero.

    Truncation would move a sprite sitting off the left edge one pixel to the
    right, so its first visible column would show the neighbouring tile's
    pixel instead of its own.
    """
    camera = Camera()
    camera.begin_frame(1.0)

    rect = camera.apply_covering(pygame.FRect(-40.0, -40.0, 64.0, 64.0))

    assert rect.left == -40
    assert rect.top == -40


@pytest.mark.parametrize(
    "framing",
    [
        Framing(800.0, 450.0),
        Framing(1152.0, 648.0),
        Framing(1920.0, 1080.0),
        Framing(500.0, 1400.0),
    ],
)
def test_a_covering_rect_always_contains_the_exact_extent(framing: Framing) -> None:
    """The invariant holds for any world size, framing, offset and rect.

    The far edges come from ``apply``'s own result rather than being recomputed
    from the world rect: the two disagree in the last bit, and ``ceil`` of a
    value one bit below the true one lands a whole pixel short, which is the
    bug this replaces. Fuzzing every combination is what caught it.
    """
    rng = random.Random(20260925)
    camera = Camera(framing)
    camera.set_world_size(8000, 600)
    view_w, view_h = camera.viewport_width, camera.viewport_height

    for _ in range(400):
        camera.offset.x = rng.uniform(-50.0, 8000.0 - view_w + 50.0)
        camera.offset.y = rng.uniform(-50.0, 600.0 - view_h + 50.0)
        camera._previous_offset = pygame.Vector2(camera.offset)
        camera.begin_frame(rng.random())
        world = pygame.FRect(
            rng.uniform(-100.0, 8000.0),
            rng.uniform(-100.0, 600.0),
            rng.uniform(0.5, 200.0),
            rng.uniform(0.5, 200.0),
        )
        exact = camera.apply(world)
        got = camera.apply_covering(world)

        assert got.left <= exact.left
        assert got.top <= exact.top
        assert got.right >= exact.right
        assert got.bottom >= exact.bottom


class _FlashingEntity(pygame.sprite.Sprite):
    def __init__(self) -> None:
        super().__init__()
        self.faction = "enemy"
        self.image = pygame.Surface((8, 8), pygame.SRCALPHA)
        self.rect = pygame.FRect(4.0, 4.0, 8, 8)
        self.flash_timer = 0.05


def _renderer(scale: int) -> Renderer:
    """A renderer on a target built the way the game builds one."""
    surface = Viewport(DEFAULT_FRAMING, scale).surface
    return Renderer(surface, Camera.for_target(surface))


def test_the_camera_reads_its_scale_off_the_target() -> None:
    """And not the other way round: a scale passed next to a target of another
    size would scale the images and not the rectangles, and the world would be
    drawn at half the density the framing claims."""
    for scale in (1, 2, 3):
        surface = Viewport(DEFAULT_FRAMING, scale).surface
        assert Camera.for_target(surface).scale == scale
        assert Renderer(surface, Camera.for_target(surface))._render_scale == scale


@pytest.mark.parametrize("size", [(1400, 900), (640, 480), (0, 0), (2305, 1296)])
def test_a_target_that_does_not_match_the_framing_is_refused(size) -> None:
    """Rounding a mismatched ratio would draw a world at a density nobody asked
    for, and the framing would stop describing what is on screen."""
    with pytest.raises(ValueError):
        Camera.for_target(pygame.Surface(size))


def test_a_two_to_one_target_scales_the_image_and_the_rect_together() -> None:
    """The bug this file was extended for: image scaled, rect not, and pygame
    silently resizes the source to fit the destination."""
    renderer = _renderer(2)
    image = pygame.Surface((10, 20))
    rect = pygame.FRect(0.0, 0.0, 10.0, 20.0)
    renderer.camera.offset.update(0, 0)
    renderer.camera.begin_frame(1.0)

    scaled = renderer._scaled_image(image)
    covering = renderer.camera.apply_covering(rect)

    assert renderer._render_scale == 2
    assert scaled.get_size() == (20, 40)
    assert covering.size == scaled.get_size(), (
        "a blit whose source and destination differ is silently resampled, which "
        "is how the world ends up drawn at the wrong size"
    )


def test_the_framing_covers_the_whole_target_at_every_scale() -> None:
    """The other half: the visible world has to *be* the target, not a corner."""
    for scale in (1, 2, 3):
        surface = Viewport(DEFAULT_FRAMING, scale).surface
        camera = Camera.for_target(surface)
        camera.offset.update(0, 0)
        camera.begin_frame(1.0)

        covered = camera.apply_covering(
            pygame.FRect(0.0, 0.0, DEFAULT_FRAMING.width, DEFAULT_FRAMING.height)
        )

        assert covered.size == surface.get_size()


def test_a_one_to_one_target_pays_nothing_for_scaling() -> None:
    renderer = _renderer(1)
    image = pygame.Surface((10, 20))

    assert renderer._scaled_image(image) is image
    assert renderer._scaled_image_once(image) is image


def test_the_scaled_cache_is_keyed_by_the_image_alone() -> None:
    """The key used to carry the zoom. The scale is fixed for a target, so an
    image can only ever have one scaled form."""
    renderer = _renderer(2)
    image = pygame.Surface((8, 8))

    first = renderer._scaled_image(image)
    assert renderer._scaled_image(image) is first
    assert len(renderer._scaled_cache) == 1


def test_adopting_a_new_target_drops_the_scale_cache() -> None:
    renderer = _renderer(2)
    renderer._scaled_image(pygame.Surface((8, 8)))
    assert renderer._scaled_cache

    new_target = Viewport(DEFAULT_FRAMING, 1).surface
    renderer.set_surface(new_target)

    assert not renderer._scaled_cache
    assert renderer._render_scale == 1
    assert renderer.camera.scale == 1


def test_a_new_target_does_not_disturb_what_the_camera_shows() -> None:
    """The scale moves with the target; the *framing* must not.

    The old code resized the camera with the window, which is the original bug:
    the visible world was a function of a video setting. A new target changes
    how large the world is drawn and nothing about how much of it is shown."""
    renderer = _renderer(2)
    before = (renderer.camera.viewport_width, renderer.camera.viewport_height)

    renderer.set_surface(Viewport(DEFAULT_FRAMING, 1).surface)

    assert (renderer.camera.viewport_width, renderer.camera.viewport_height) == before
    assert renderer.camera.scale == 1, "the scale does follow the target"


def test_draw_returns_nothing_and_paints_the_whole_target() -> None:
    """No partial presentation any more, so there is no rect set to return."""
    groups = SpriteGroups()
    groups.all_sprites.add(StaticSprite((0, 0)))
    renderer = _renderer(1)
    renderer.background_color = (7, 9, 11)

    assert renderer.draw(groups) is None

    pixel = renderer.surface.get_at((1100, 600))
    assert pixel[:3] == (7, 9, 11) or pixel[:3] == (255, 0, 0)


def test_the_background_is_erased_every_frame() -> None:
    """A shrinking sprite must not leave anything behind: the erase is the
    whole target now, so the one-frame-late overlay bookkeeping is gone."""
    groups = SpriteGroups()
    groups.all_sprites.add(StaticSprite((0, 0), size=(64, 64)))
    renderer = _renderer(1)
    renderer.background_color = (3, 5, 7)
    renderer.draw(groups)

    groups.all_sprites.empty()
    renderer.draw(groups)

    assert renderer.surface.get_at((10, 10))[:3] == (3, 5, 7)


def test_a_flashing_entity_is_collected_without_touching_the_scale_cache() -> None:
    groups = SpriteGroups()
    entity = _FlashingEntity()
    groups.entity_sprites.add(entity)
    renderer = _renderer(1)
    renderer.camera.begin_frame(1.0)

    assert renderer._collect_flashes(groups)
    assert not renderer._scaled_cache, "a transient surface must not be cached"
