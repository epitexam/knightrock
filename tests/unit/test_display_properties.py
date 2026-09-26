"""The display subsystem's invariants, checked across the whole setup space.

Every test here is a property over a grid, not a single case. That is the whole
point of the file, and it is a correction: the two regressions this branch
shipped -- the camera losing its scale, and the video menu's rows going dead to
the mouse -- both passed a suite that tested *points*. A point is a
configuration somebody thought of. A grid is the space the player is actually
in, and the two bugs sat in the gaps: one at a render scale no fixture used,
one on a code path no assertion followed all the way through to the settings.

The grids deliberately include the awkward shapes -- square, portrait,
ultrawide, and windows smaller than the framing -- because those are where
letterboxing arithmetic goes wrong, and a portrait window is a real thing a
player does by dragging a border.
"""

import pathlib
from types import SimpleNamespace

import pygame
import pytest

from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.presentation import Presentation
from src.core.display.viewport import RENDER_SCALES, Viewport, render_scale_for
from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.settings import Simulation

#: Window shapes worth surviving: the common ones, the awkward aspect ratios,
#: and sizes below the framing, which is where a "fit" calculation goes
#: negative.
WINDOWS = [
    (640, 360),
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1920, 1080),
    (2560, 1440),
    (3440, 1440),
    (3840, 2160),
    (1000, 1000),
    (900, 1600),
    (500, 400),
]


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


def _stage(size: tuple[int, int]) -> SimpleNamespace:
    """The two attributes ``Presentation`` reads off a window."""
    return SimpleNamespace(size=size, surface=pygame.Surface(size))


# --------------------------------------------------------------------------
# 1. The render target depends on the scale and on nothing else.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scale", RENDER_SCALES)
def test_the_target_is_the_framing_times_the_scale_at_every_window(
    scale: int, tmp_path: pathlib.Path
) -> None:
    seen = set()
    for window in WINDOWS:
        pygame.display.set_mode(window)
        seen.add(Viewport(DEFAULT_FRAMING, scale).size)
    assert seen == {DEFAULT_FRAMING.viewport_size(scale)}


@pytest.mark.parametrize("scale", RENDER_SCALES)
def test_the_camera_shows_the_framing_whatever_the_target(scale: int) -> None:
    """The framing is the invariant; the scale is a sharpness, not a zoom.

    A camera that divided by the window size made the visible world a function
    of a video setting, so this is the assertion that has to survive every
    future change to how the target is built.
    """
    viewport = Viewport(DEFAULT_FRAMING, scale)
    camera = Camera.for_target(viewport.surface)
    assert (camera.viewport_width, camera.viewport_height) == DEFAULT_FRAMING.size
    assert camera.scale == scale


# --------------------------------------------------------------------------
# 2. A scaled image and the rect it is blitted into are the same size.
# --------------------------------------------------------------------------


def _level_blit_mismatches(scale: int) -> set[tuple[int, int]]:
    """Every blit of a real level whose image and rect disagree, by how much.

    Returns the disagreements instead of asserting on them, so the size
    tolerance and the scale-invariance can be two separate claims about the
    same walk.
    """
    viewport = Viewport(DEFAULT_FRAMING, scale)
    level = Level(viewport.surface, LevelManager(LEVEL_PATHS).get(0), InputManager())
    for _ in range(10):
        level.update(Simulation.TIMESTEP)
    level.camera.begin_frame(1.0)

    blits = level.renderer._collect_visible_blits(level.groups)
    # The registered level, not a synthetic one: the regression this file
    # exists for resampled all seventy of its tiles, and a level with one
    # sprite in it cannot see that.
    assert len(blits) > 20, f"only {len(blits)} blits; this would prove nothing"

    mismatched: set[tuple[int, int]] = set()
    for image, rect, *_ in blits:
        delta = (abs(image.get_width() - rect.width), abs(image.get_height() - rect.height))
        if delta != (0, 0):
            mismatched.add(delta)
    return mismatched


def test_a_real_levels_sprites_are_never_resampled() -> None:
    """A sprite's image and its blit rect agree, to within a pixel of rounding.

    ``pygame.blit`` rescales a source that does not fit its destination without
    saying anything, so a real mismatch does not look like an error -- it looks
    like a level drawn at half size in the corner of the screen, which is
    exactly how the camera's missing scale announced itself.
    """
    for scale in RENDER_SCALES:
        worst = max((max(delta) for delta in _level_blit_mismatches(scale)), default=0)
        assert worst <= 1, f"at {scale}x a sprite is resampled by {worst}px"


def test_the_pixel_mismatch_does_not_grow_with_the_scale() -> None:
    """The assertion that tells rounding apart from that regression.

    One asset is a pixel short of its own rect at every scale, which is the
    rounding of a fractional world height. The bug scaled: a 64-unit sprite at
    2x was a 128px image in a 64px rect, and at 3x it was worse still. So the
    property is that the disagreement does not move when the scale does.
    """
    seen = {scale: frozenset(_level_blit_mismatches(scale)) for scale in RENDER_SCALES}

    assert len(set(seen.values())) == 1, f"the mismatch is scale-dependent: {seen}"


@pytest.mark.parametrize("scale", RENDER_SCALES)
def test_only_at_one_is_the_source_image_reused(scale: int) -> None:
    """At 1x nothing may be copied -- that is the whole point of the factor.

    The identity check was dropped from the suite when the camera was
    reworked. A regression here costs one rescale per sprite per frame and
    nothing else: no wrong pixels, just a frame that quietly got slower, which
    is why nothing else would have caught it.

    Above 1x a copy is required, so the identity holds at exactly one scale.
    Asserting it everywhere would be a test that could only ever pass at 1x.
    """
    viewport = Viewport(DEFAULT_FRAMING, scale)
    renderer = Renderer(viewport.surface, Camera.for_target(viewport.surface))
    image = pygame.Surface((64, 64), pygame.SRCALPHA)

    scaled = renderer._scaled_image(image)

    assert (scaled is image) is (scale == 1)
    assert scaled.get_size() == (64 * scale, 64 * scale)


# --------------------------------------------------------------------------
# 3. Presentation: no stretching, and the pointer comes back.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("window", WINDOWS)
def test_the_letterbox_preserves_the_framing_aspect(window: tuple[int, int]) -> None:
    viewport = Viewport(DEFAULT_FRAMING, 1)
    presentation = Presentation(_stage(window), viewport)

    rect = presentation.rect
    assert presentation.fit > 0.0
    assert rect.width <= window[0]
    assert rect.height <= window[1]
    # The fit is right to within a pixel of rounding, which is all an integer
    # rect can be: a 1366x768 window holds a 1365x768 image, and asking for
    # 1366 would mean stretching by one column. Expressed in pixels rather than
    # as a ratio, because "off by less than a pixel" is the claim; a bare
    # epsilon on the ratio is a number nobody can check against anything.
    assert abs(rect.width / rect.height - viewport.framing.aspect) * rect.height < 1.0


@pytest.mark.parametrize("window", [(1280, 720), (2560, 1440), (1000, 1000), (900, 1600)])
def test_the_pointer_survives_a_round_trip(window: tuple[int, int]) -> None:
    """Window to target and back, within a pixel.

    The inverse is not implemented, which is deliberate -- nothing needs it --
    but the forward map still has to be right, and the only way to show that is
    to invert it here and check the pair. A press that lands a few pixels off is
    a menu that is subtly wrong on a HiDPI screen and unclickable nowhere.
    """
    viewport = Viewport(DEFAULT_FRAMING, 2)
    presentation = Presentation(_stage(window), viewport)
    rect = presentation.rect

    samples = [
        (rect.x + 1, rect.y + 1),
        (rect.centerx, rect.centery),
        (rect.right - 1, rect.bottom - 1),
        (window[0] - 1, window[1] - 1),
    ]
    for point in samples:
        mapped = presentation.pointer_to_viewport(point)
        back = (rect.x + mapped[0] * presentation.fit, rect.y + mapped[1] * presentation.fit)
        assert max(abs(a - b) for a, b in zip(back, point, strict=True)) <= 1.0


@pytest.mark.parametrize(
    "window", [(800, 600), (1024, 768), (1000, 1000), (900, 1600), (3440, 1440)]
)
def test_the_pointer_is_inside_the_image_exactly_when_it_is_in_the_rect(
    window: tuple[int, int],
) -> None:
    """The whole contract, on a grid, assuming nothing about which axis has bars.

    A window narrower than the framing gets bars left and right; a wider one
    gets bars top and bottom; one with the framing's own aspect gets none. A
    test that hard-coded an axis would pass on two of those and be meaningless
    on the third, which is how a letterbox that ate the left edge of a 4:3
    screen would have looked fine here.

    Clamping instead of rejecting would fire whatever row is nearest the edge of
    the image, so a click on black would change a setting.
    """
    viewport = Viewport(DEFAULT_FRAMING, 1)
    presentation = Presentation(_stage(window), viewport)
    rect = presentation.rect
    assert rect.width <= window[0] and rect.height <= window[1]

    inside = outside = 0
    for x in range(0, window[0] + 1, max(1, window[0] // 40)):
        for y in range(0, window[1] + 1, max(1, window[1] // 30)):
            point = (x, y)
            assert presentation.pointer_in_viewport(point) == rect.collidepoint(point), point
            if rect.collidepoint(point):
                inside += 1
            else:
                outside += 1

    assert inside > 0, "the sample never landed on the image"


@pytest.mark.parametrize("window", [(1280, 720), (2560, 1440), (1920, 1080)])
def test_a_window_with_the_frames_own_aspect_has_no_bars(window: tuple[int, int]) -> None:
    """The 16:9-on-16:9 case, where a bar would be a bug.

    Easy to get wrong in the other direction: a fit calculation that rounds the
    letterbox up instead of down leaves a one-pixel bar that eats clicks along
    the whole left and right edge of the screen.
    """
    presentation = Presentation(_stage(window), Viewport(DEFAULT_FRAMING, 1))

    assert presentation.rect.size == window
    assert presentation.pointer_in_viewport((0, window[1] // 2))
    assert presentation.pointer_in_viewport((window[0] - 1, window[1] // 2))


# --------------------------------------------------------------------------
# 4. A bad scale is refused, by everything, identically.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0, -1, 0.5, 1.5, 2.25])
def test_no_two_things_disagree_about_a_bad_scale(scale: float) -> None:
    """One policy, or the two halves can build different worlds.

    The viewport used to refuse a fractional factor while the camera clamped it
    to 1. That combination is the bug this branch shipped: a target built at one
    density and rectangles drawn at another, with ``pygame.blit`` quietly
    resampling between them. Refusing everywhere is the only answer that cannot
    be half-applied.
    """
    with pytest.raises(ValueError):
        Viewport(DEFAULT_FRAMING, scale)
    with pytest.raises(ValueError):
        Camera(DEFAULT_FRAMING, scale)


@pytest.mark.parametrize("scale", RENDER_SCALES)
def test_the_camera_adopts_the_scale_of_a_new_target(scale: int) -> None:
    """``set_surface`` has to tell the camera, or the rectangles lag behind."""
    renderer = Renderer(
        Viewport(DEFAULT_FRAMING, 1).surface,
        Camera.for_target(Viewport(DEFAULT_FRAMING, 1).surface),
    )
    bigger = Viewport(DEFAULT_FRAMING, scale).surface

    renderer.set_surface(bigger)

    assert renderer.camera.scale == scale
    assert renderer._render_scale == scale


# --------------------------------------------------------------------------
# 5. The default sharpness follows the machine.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((911, 512), 1),
        ((1280, 720), 2),
        ((1440, 900), 2),
        ((1920, 1080), 2),
        ((2560, 1440), 3),
    ],
)
def test_the_default_sharpness_covers_the_window(window: tuple[int, int], expected: int) -> None:
    assert render_scale_for(window) == expected


def test_the_default_sharpness_is_always_one_of_the_choices() -> None:
    for width in range(320, 4001, 37):
        for height in (240, 480, 720, 900, 1080, 1440, 2160):
            assert render_scale_for((width, height)) in RENDER_SCALES


def test_an_unknown_desktop_keeps_the_old_default() -> None:
    """Headless runs have no desktop, and must not change behaviour."""
    assert render_scale_for((0, 0)) == 2


def test_a_smaller_target_is_never_chosen_for_a_window_it_can_hold() -> None:
    """The point of the whole exercise: never scale the frame *up* on the way out.

    4K is the exception the ladder cannot cover, and it is bounded rather than
    unbounded: ``RENDER_SCALES`` stops at 3x.
    """
    for window in WINDOWS:
        scale = render_scale_for(window)
        target = DEFAULT_FRAMING.viewport_size(scale)
        covers = target[0] >= window[0] and target[1] >= window[1]
        assert covers or scale == max(RENDER_SCALES), f"{window} at {scale}x is scaled up"
