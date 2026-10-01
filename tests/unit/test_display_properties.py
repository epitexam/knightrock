"""The display subsystem's invariants, checked across the whole setup space.

Every test here is a property over a grid, not a single case. That is the whole
point of the file, and it is a correction: the regressions this branch shipped --
the camera losing its scale, the video menu's rows going dead to the mouse, and
a fixed render target that could never be pixel-exact on a real display -- all
passed a suite that tested *points*. A point is a configuration somebody thought
of. A grid is the space the player is actually in, and those bugs sat in the
gaps.

The grids deliberately include the awkward shapes -- square, portrait,
ultrawide, and windows smaller than the framing -- because those are where
letterboxing arithmetic goes wrong, and a portrait window is a real thing a
player does by dragging a border.

The central property is the one the whole rework exists for:

    for every window, the frame that reaches the screen is the frame that was
    drawn, byte for byte, and the world it shows is the framing.

The first half is what makes the picture sharp at any size; the second is what
makes it fair.
"""

import math
import pathlib
from types import SimpleNamespace

import pygame
import pytest

from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import (
    already_a_whole_multiple,
    density_for,
    fits_whole_pixel,
    letterbox,
)
from src.core.display.presentation import Presentation
from src.core.display.viewport import Viewport
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

#: Windows whose letterbox has whole-pixel art available, and one that has none.
WHOLE_PIXEL_WINDOWS = [(1152, 648), (2304, 1296), (3456, 1944), (1280, 720), (2560, 1440)]


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


def _stage(size: tuple[int, int]) -> SimpleNamespace:
    """The two attributes ``Presentation`` reads off a window."""
    return SimpleNamespace(size=size, surface=pygame.Surface(size))


# --------------------------------------------------------------------------
# 1. The target is the window, and the density is read off it.
# --------------------------------------------------------------------------


def test_the_target_is_the_windows_own_letterbox_rect() -> None:
    """Every window draws into the rectangle that window asks for.

    The inverse of the property this branch used to assert -- that the target
    depends only on a scale -- and it is the whole design. A fixed target meant
    the finished frame had to be resampled onto the window, and a resampled
    frame is a soft one: measured at 2176x1224, a 1152x648 target cost 4.24 ms
    of ``smoothscale`` per frame and turned a 13-colour tileset into 128
    colours.

    Note that two windows *can* share a target -- a 3440x1440 ultrawide and a
    2560x1440 screen both letterbox to 2560x1440 -- and that is right rather than
    a collision: the picture depends on the window's shape, and two windows of
    the same shape want the same picture.
    """
    for window in WINDOWS:
        rect = letterbox(window, DEFAULT_FRAMING)
        target = Viewport(DEFAULT_FRAMING, rect.size)
        assert target.size == rect.size
        assert rect.size == letterbox(window, DEFAULT_FRAMING).size


@pytest.mark.parametrize("window", WINDOWS)
def test_a_bigger_window_never_shrinks_the_picture(window: tuple[int, int]) -> None:
    """The fit is monotone: more window never means less picture.

    A cheap property that catches a letterbox computed from the wrong axis, and
    the reason a window and a screen of the same shape agree above is not a
    coincidence of the list.
    """
    rect = letterbox(window, DEFAULT_FRAMING)
    for wider in (window[0] + 1, window[0] * 2, window[0] + 400):
        grown = letterbox((wider, window[1]), DEFAULT_FRAMING)
        assert grown.width >= rect.width
        assert grown.height >= rect.height
    for taller in (window[1] + 1, window[1] * 2, window[1] + 400):
        grown = letterbox((window[0], taller), DEFAULT_FRAMING)
        assert grown.width >= rect.width
        assert grown.height >= rect.height


@pytest.mark.parametrize("window", WINDOWS)
def test_the_camera_shows_the_framing_at_every_window(window: tuple[int, int]) -> None:
    """The framing is the invariant; the density is how sharply it is drawn.

    A camera that divided by the window size made the visible world a function
    of a video setting, so this is the assertion that has to survive every
    future change to how the target is built. What changed is everything around
    it: the density is now read off the target instead of chosen, and it is a
    fraction on most displays rather than a whole number.
    """
    target = Viewport(DEFAULT_FRAMING, letterbox(window, DEFAULT_FRAMING).size)
    camera = Camera.for_target(target.surface)
    assert (camera.viewport_width, camera.viewport_height) == DEFAULT_FRAMING.size
    assert camera.density == pytest.approx(target.density)


@pytest.mark.parametrize("window", WINDOWS)
def test_the_density_agrees_with_both_axes_of_the_target(window: tuple[int, int]) -> None:
    """One density for the width and the height, or the framing does not hold.

    Rounding a letterbox to whole pixels cannot preserve a ratio exactly, so the
    two axes always differ a little. A little is the claim; a pixel and a half
    is the tolerance, expressed in pixels because that is a thing you can check.
    """
    size = letterbox(window, DEFAULT_FRAMING).size
    horizontal = size[0] / DEFAULT_FRAMING.width
    vertical = size[1] / DEFAULT_FRAMING.height
    assert abs(horizontal - vertical) * max(DEFAULT_FRAMING.size) < 1.5
    assert density_for(size) == pytest.approx(horizontal)


# --------------------------------------------------------------------------
# 2. A magnified image and the rect it is blitted into are the same size.
# --------------------------------------------------------------------------


def _level_blit_mismatches(window: tuple[int, int]) -> set[tuple[int, int]]:
    """Every blit of a real level whose image and rect disagree, by how much.

    Returns the disagreements instead of asserting on them, so "never" and "does
    not depend on the window" can be two separate claims about the same walk.
    """
    size = letterbox(window, DEFAULT_FRAMING).size
    level = Level(
        Viewport(DEFAULT_FRAMING, size).surface, LevelManager(LEVEL_PATHS).get(0), InputManager()
    )
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


@pytest.mark.parametrize("window", [(500, 400), (1366, 768), (2176, 1224), (2560, 1440)])
def test_a_real_levels_sprites_are_never_resampled(window: tuple[int, int]) -> None:
    """A sprite's image and its blit rect agree **exactly**, at any window.

    ``pygame.blit`` rescales a source that does not fit its destination without
    saying anything, so a real mismatch does not look like an error -- it looks
    like a level drawn at half size in the corner of the screen, which is
    exactly how the camera's missing scale announced itself.

    There is no tolerance here any more, and that is the point of the rounding
    rule: the image is magnified with ``Camera.scaled_size`` and the rectangle
    is built from the same number, so "off by one pixel of rounding" is not an
    acceptable state to be in, it is a second rounding somewhere.
    """
    assert _level_blit_mismatches(window) == set(), (
        f"at {window} a sprite is resampled: {sorted(_level_blit_mismatches(window))}"
    )


def test_the_blit_agreement_does_not_depend_on_the_window() -> None:
    """The property that tells rounding apart from the regression.

    The bug scaled: a 64-unit sprite at 2x was a 128px image in a 64px rect, and
    at 3x it was worse still. So the property is that the disagreement does not
    move when the window does -- and here it is not merely small, it is absent.
    """
    seen = {window: frozenset(_level_blit_mismatches(window)) for window in WINDOWS}
    assert set(map(frozenset, seen.values())) == {frozenset()}, seen


def test_neighbouring_tiles_leave_no_gap_at_a_fractional_density() -> None:
    """The other half of the rounding rule: rounding down must not open a seam.

    ``apply_snapped`` rounds the position down and the size to ``scaled_size``.
    Rounding both the same way would make a run of tiles drift apart by a pixel
    every few tiles, which shows as a line of background through the terrain.
    Rounding the position down cannot: the difference between two rounded
    positions is at least ``floor(size)`` and the size is ``round(size)``, so
    neighbours always touch.
    """
    camera = Camera(DEFAULT_FRAMING, density=2176 / 1152)
    camera.begin_frame(1.0)
    tile = 64.0
    previous_right = None
    for index in range(64):
        rect = camera.apply_snapped(pygame.FRect(index * tile, 0.0, tile, tile))
        if previous_right is not None:
            assert rect.left <= previous_right, f"a gap opened at tile {index}"
        previous_right = rect.right


@pytest.mark.parametrize("density", [1.0, 1.25, 1.8889, 2.0, 3.5])
def test_only_at_one_is_the_source_image_reused(density: float) -> None:
    """At a density of exactly 1 nothing may be copied.

    A regression here costs one rescale per sprite per frame and nothing else:
    no wrong pixels, just a frame that quietly got slower, which is why nothing
    else would have caught it. Above 1 a magnified copy is required, so the
    identity holds at exactly one density -- asserting it everywhere would be a
    test that could only ever pass at 1.
    """
    size = (
        round(DEFAULT_FRAMING.width * density),
        round(DEFAULT_FRAMING.height * density),
    )
    viewport = Viewport(DEFAULT_FRAMING, size)
    renderer = Renderer(viewport.surface, Camera.for_target(viewport.surface))
    image = pygame.Surface((64, 64), pygame.SRCALPHA)

    scaled = renderer._scaled_image(image)

    assert (scaled is image) is (density == 1.0)
    assert scaled.get_size() == renderer.camera.scaled_size((64, 64))


# --------------------------------------------------------------------------
# 3. Presentation: the frame is the picture, and the pointer comes back.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("window", WINDOWS)
def test_the_presented_frame_is_the_drawn_frame(window: tuple[int, int]) -> None:
    """No resampling anywhere between the target and the screen.

    The property the whole rework exists for, and the one that cannot be
    asserted by inspecting a ratio: whatever is drawn into the target has to come
    out of the other side of :meth:`Presentation.present` unchanged, at every
    window. A ``smoothscale`` left anywhere in this path shows up here as a
    difference, not as a subtlety.
    """
    stage = _stage(window)
    presentation = Presentation(stage.surface, DEFAULT_FRAMING)

    # Something with structure in it: a flat fill would survive a resample of any
    # ratio and prove nothing.
    target = presentation.surface
    for y in range(0, target.get_height(), 7):
        pygame.draw.line(
            target, ((y * 7) % 256, 40, 200 - y % 200), (0, y), (target.get_width() - 1, y)
        )

    presentation.present()

    shown = stage.surface.subsurface(presentation.rect)
    assert pygame.image.tobytes(shown, "RGB") == pygame.image.tobytes(target, "RGB")


@pytest.mark.parametrize("window", WINDOWS)
def test_the_letterbox_preserves_the_framing_aspect(window: tuple[int, int]) -> None:
    presentation = Presentation(_stage(window).surface, DEFAULT_FRAMING)

    rect = presentation.rect
    assert rect.width <= window[0]
    assert rect.height <= window[1]
    # The fit is right to within a pixel of rounding, which is all an integer
    # rect can be: a 1366x768 window holds a 1365x768 image, and asking for
    # 1366 would mean stretching by one column. Expressed in pixels rather than
    # as a ratio, because "off by less than a pixel" is the claim; a bare
    # epsilon on the ratio is a number nobody can check against anything.
    assert abs(rect.width / rect.height - DEFAULT_FRAMING.aspect) * rect.height < 1.5


@pytest.mark.parametrize("window", [(1280, 720), (2560, 1440), (1000, 1000), (900, 1600)])
def test_the_pointer_survives_a_round_trip(window: tuple[int, int]) -> None:
    """Window to target and back, exactly.

    The inverse is not implemented, which is deliberate -- nothing needs it --
    but the forward map still has to be right, and the only way to show that is
    to invert it here and check the pair. A press that lands a few pixels off is
    a menu that is subtly wrong on a HiDPI screen and unclickable nowhere.

    There is no ratio left in the pair, so there is no tolerance either: the
    mapping is a subtraction now and a subtraction that is off is a bug.
    """
    presentation = Presentation(_stage(window).surface, DEFAULT_FRAMING)
    rect = presentation.rect

    samples = [
        (rect.x + 1, rect.y + 1),
        (rect.centerx, rect.centery),
        (rect.right - 1, rect.bottom - 1),
        (window[0] - 1, window[1] - 1),
    ]
    for point in samples:
        mapped = presentation.pointer_to_viewport(point)
        assert (rect.x + mapped[0], rect.y + mapped[1]) == point


@pytest.mark.parametrize(
    "window", [(800, 600), (1024, 768), (1000, 1000), (900, 1600), (3440, 1440)]
)
def test_the_pointer_is_inside_the_image_exactly_when_it_is_in_the_rect(
    window: tuple[int, int],
) -> None:
    """The whole contract, on a grid, assuming nothing about which axis has bars.

    A window narrower than the framing gets bars left and right; a wider one
    gets bars top and bottom; one with the framing's own aspect gets none. A test
    that hard-coded an axis would pass on two of those and be meaningless on the
    third, which is how a letterbox that ate the left edge of a 4:3 screen would
    have looked fine here.

    Clamping instead of rejecting would fire whatever row is nearest the edge of
    the image, so a click on black would change a setting.
    """
    presentation = Presentation(_stage(window).surface, DEFAULT_FRAMING)
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
    presentation = Presentation(_stage(window).surface, DEFAULT_FRAMING)

    assert presentation.rect.size == window
    assert presentation.pointer_in_viewport((0, window[1] // 2))
    assert presentation.pointer_in_viewport((window[0] - 1, window[1] // 2))


# --------------------------------------------------------------------------
# 4. Whole-pixel art is opt-in, and it is a whole number when it is on.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("window", WINDOWS)
def test_whole_pixel_art_is_a_whole_density_inside_the_window(window: tuple[int, int]) -> None:
    rect = letterbox(window, DEFAULT_FRAMING, pixel_perfect=True)
    assert rect.width <= window[0] and rect.height <= window[1]
    if not fits_whole_pixel(window, DEFAULT_FRAMING):
        # Nothing to snap to, so the fitted rectangle is offered unchanged and
        # the row says so rather than pretending.
        assert rect.size == letterbox(window, DEFAULT_FRAMING).size
        return
    density = density_for(rect.size)
    assert density == int(density)
    assert rect.size == (
        round(DEFAULT_FRAMING.width * density),
        round(DEFAULT_FRAMING.height * density),
    )


@pytest.mark.parametrize("window", WHOLE_PIXEL_WINDOWS)
def test_whole_pixel_art_keeps_the_framing_exactly(window: tuple[int, int]) -> None:
    """At a whole density the visible world is still the framing, bars and all."""
    rect = letterbox(window, DEFAULT_FRAMING, pixel_perfect=True)
    assert rect.width / rect.height == pytest.approx(DEFAULT_FRAMING.aspect, abs=1e-3)
    assert rect.width % round(DEFAULT_FRAMING.width) == 0


#: Windows that are already a whole multiple of the framing, so snapping to one
#: would change nothing. The first three are exact multiples of 1152x648 at this
#: framing; the rest are the ordinary sizes a player ends up with.
ALREADY_WHOLE_WINDOWS = [(1152, 648), (2304, 1296), (3456, 1944)]


@pytest.mark.parametrize("window", ALREADY_WHOLE_WINDOWS)
def test_a_window_that_is_already_whole_says_so(window: tuple[int, int]) -> None:
    """The one class of window where whole-pixel art is honoured by doing nothing.

    ``fits_whole_pixel`` asks whether a whole multiple fits and answers yes here;
    this asks whether taking it would *do* anything and answers no. Both are true
    at once, and only the second one tells the player why the picture does not
    move when they press the row.
    """
    assert fits_whole_pixel(window, DEFAULT_FRAMING), "a whole multiple does fit"
    assert already_a_whole_multiple(window, DEFAULT_FRAMING), "and taking it changes nothing"


@pytest.mark.parametrize("window", [(1920, 1080), (2560, 1440), (1440, 810), (1280, 720)])
def test_a_window_that_is_not_whole_has_work_to_do(window: tuple[int, int]) -> None:
    """The complement, and the direction that matters: snapping must *change* it.

    Asserted against ``letterbox`` directly rather than against a table of
    expected sizes, because the claim is the one the row depends on -- if this
    ever said "already whole" for a window that is not, the row would tell the
    player there is nothing to do when there plainly was.
    """
    assert not already_a_whole_multiple(window, DEFAULT_FRAMING), (
        f"{window} is not a whole multiple of the framing"
    )
    assert (
        letterbox(window, DEFAULT_FRAMING).size
        != letterbox(window, DEFAULT_FRAMING, pixel_perfect=True).size
    )


def test_a_window_too_small_for_one_is_not_reported_as_already_whole() -> None:
    """The two refusals are different and must not collapse into one.

    Below the framing there is no whole multiple to take, so ``letterbox`` hands
    back the fitted rectangle unchanged -- the same rectangle
    ``already_a_whole_multiple`` compares against. Without the check below, a
    window too small for the art would be indistinguishable from a window that is
    already exactly sized, and the row would say "already whole" on a window
    where the right answer is "too small".
    """
    assert not fits_whole_pixel((800, 600), DEFAULT_FRAMING)
    assert not already_a_whole_multiple((800, 600), DEFAULT_FRAMING), (
        "it is a refusal, not a job already done"
    )


# --------------------------------------------------------------------------
# 5. A bad density is refused, by everything, identically.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("density", [0, -1, -0.5, float("nan")])
def test_no_two_things_disagree_about_a_bad_density(density: float) -> None:
    """One policy, or the two halves can build different worlds.

    The viewport used to refuse a fractional factor while the camera clamped it
    to 1. That combination is a bug this branch shipped: a target built at one
    density and rectangles drawn at another, with ``pygame.blit`` quietly
    resampling between them. Refusing everywhere is the only answer that cannot
    be half-applied.

    A density of 0.5 is legal now -- a window smaller than the framing really
    does magnify by less than one -- and both halves have to agree about *that*
    too, which is why the positive case is asserted next to the refusals.
    """
    with pytest.raises(ValueError):
        Camera(DEFAULT_FRAMING, density)
    assert Camera(DEFAULT_FRAMING, 0.5).density == 0.5
    assert Viewport(DEFAULT_FRAMING, (576, 324)).density == pytest.approx(0.5)


@pytest.mark.parametrize("size", [(1152, 700), (1152, 600), (2000, 648), (3, 3)])
def test_a_target_that_is_not_the_framing_at_one_density_is_refused(
    size: tuple[int, int],
) -> None:
    """The target and the camera refuse the same targets, for the same reason.

    A rectangle whose two axes imply different pixel densities is not the
    framing drawn at some density, it is a mistake upstream -- and at 0.5x
    against 0.9x the frame would be drawn stretched, which is the one thing this
    whole arrangement exists to make impossible.
    """
    with pytest.raises(ValueError):
        Viewport(DEFAULT_FRAMING, size)
    with pytest.raises(ValueError):
        Camera.for_target(pygame.Surface(size))


@pytest.mark.parametrize("window", [(640, 360), (2176, 1224), (2560, 1440)])
def test_the_camera_adopts_the_density_of_a_new_target(window: tuple[int, int]) -> None:
    """``set_surface`` has to tell the camera, or the rectangles lag behind."""
    first = Viewport(DEFAULT_FRAMING, letterbox((1152, 648), DEFAULT_FRAMING).size)
    renderer = Renderer(first.surface, Camera.for_target(first.surface))
    bigger = Viewport(DEFAULT_FRAMING, letterbox(window, DEFAULT_FRAMING).size).surface

    renderer.set_surface(bigger)

    expected = density_for(bigger.get_size())
    assert renderer.camera.density == pytest.approx(expected)
    assert renderer._density == pytest.approx(expected)
    # The size rule asks the camera, so a sprite and its rect cannot disagree.
    assert renderer.camera.scaled_size((64, 64)) == tuple(
        math.ceil(64 * expected) for _ in range(2)
    )


# --------------------------------------------------------------------------
# 6. One target, one camera, one interface scale: they cannot drift apart.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("window", WINDOWS)
def test_the_target_the_camera_and_the_interface_all_read_the_same_density(
    window: tuple[int, int], tmp_path: pathlib.Path
) -> None:
    """The cascade, end to end, on the real runtime.

    A window resize has three consequences -- a new surface, a new density, a new
    interface scale -- and they used to live in three places, so a resize could
    move two of them and leave the third describing a target that no longer
    existed. Here the same window is driven through ``Game`` and all three are
    read back off the one object that owns them.
    """
    from src.core.game import Game

    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game.initialize_display()
    game.presentation.retarget(_stage(window).surface)
    game._retarget()

    target = Viewport(DEFAULT_FRAMING, game.presentation.rect.size)
    assert target.size == game.presentation.surface.get_size()
    assert game.presentation.density == pytest.approx(target.density)
    assert game.ui_scale == pytest.approx(game.settings.ui_scale * target.density)

    camera = Camera.for_target(game.presentation.surface)
    assert camera.density == pytest.approx(target.density)
    assert (camera.viewport_width, camera.viewport_height) == DEFAULT_FRAMING.size
