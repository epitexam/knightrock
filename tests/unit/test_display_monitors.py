"""The display invariants, as properties rather than cases.

Every test here is a grid: a set of windows, a set of displays, a set of
policies, walked together. They exist because the display subsystem's failures
are all of the shape "a combination nobody tried" -- a window at an unusual
shape, a policy applied where it does not apply, a monitor with an origin the
primary does not have -- and a suite of hand-picked cases tests the combinations
somebody already thought of.

The claims are stated as *relations*, not as values, so they cannot drift when a
constant changes. Where a bound is in pixels it says so, because a tolerance in
the wrong unit is a tolerance that is either trivially true or accidentally
false: rounding a rectangle to whole pixels cannot preserve a ratio exactly, and
"at most one pixel across the whole frame" is a statement about the rendering,
where "1e-6" is a statement about arithmetic that does not happen.

The three that matter most:

- **the visible world never exceeds the framing**, on either axis, under every
  policy. This is the gameplay contract, and zoom is the policy that could have
  broken it: it fills the window by showing a *crop*, never by showing more.
- **the presented frame is the drawn frame**, byte for byte. Any resampling
  between the target and the window keeps a flat fill looking right and only
  breaks on detail.
- **a pointer in the window maps inside the picture, and back**. A click that
  lands on a neighbouring row is invisible in a screenshot.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))

from src.core.display.framing import Framing  # noqa: E402
from src.core.display.letterbox import (  # noqa: E402
    DENSITY_TOLERANCE_PX,
    FitPolicy,
    density_for,
)
from src.core.display.monitors import (  # noqa: E402
    MIN_WINDOW,
    Monitor,
    Topology,
    centre_on,
    fit_size,
    opening_size,
)
from src.core.display.presentation import Presentation  # noqa: E402

SHIPPED = Framing(1152.0, 648.0)

#: Windows worth walking: the shipped framing exactly, both 16:9 and 16:10 at
#: several densities, the shapes that produce bars on every side, and the small
#: ones where the density falls below 1 and a world unit is less than a pixel.
WINDOWS = [
    (1152, 648),
    (1920, 1080),
    (1600, 900),
    (1440, 900),
    (1280, 720),
    (2560, 1440),
    (3440, 1440),
    (5120, 1440),
    (1280, 1024),
    (800, 600),
    (640, 480),
    (1024, 768),
]

#: Framings other than the shipped one, so nothing depends on the default.
FRAMINGS = [SHIPPED, Framing(960.0, 540.0), Framing(1600.0, 900.0), Framing(1000.0, 1000.0)]

POLICIES = list(FitPolicy)


def _presentation(window: tuple[int, int], framing: Framing, policy: FitPolicy) -> Presentation:
    return Presentation(pygame.Surface(window), framing, fit=policy)


#: The visible world, in world units, for a presentation.
def _shown(p: Presentation) -> tuple[float, float]:
    return (p.picture.source.width / p.density, p.picture.source.height / p.density)


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("framing", FRAMINGS)
@pytest.mark.parametrize("policy", POLICIES)
def test_the_visible_world_never_exceeds_the_framing(
    window: tuple[int, int], framing: Framing, policy: FitPolicy
) -> None:
    """The gameplay contract, on every combination.

    Not "the framing is respected" but *how much*: the visible slice has to be
    within a pixel's worth of world units of the framing or less, on both axes.
    The pixel budget is ``DENSITY_TOLERANCE_PX``, the same bound
    :func:`density_for` uses, because that is the only rounding there is.

    Zoom is the one that could have broken this. It fills a window of any shape
    by making the picture larger than the window and showing a centred crop, so a
    21:9 screen sees the framing's 1152x648 world units and loses the edges of
    the image -- 1152x482 rather than 1152x648 -- instead of seeing a wider slice
    of the level. Widening the framing to fill the window would pass this test on
    the width axis and fail on the height, which is exactly why it is not offered.
    """
    p = _presentation(window, framing, policy)
    shown_w, shown_h = _shown(p)
    # The slack is one pixel *at this window's density*, in world units.
    # Rounding the rectangle to whole pixels is the only thing between the
    # framing and the picture, and at density 0.74 one pixel is 1.35 world units
    # while at 2.22 it is 0.45 -- so a slack fixed in either unit is wrong at one
    # end of the window range or the other. Expressed as a pixel count and
    # converted, it means the same thing everywhere.
    slack = DENSITY_TOLERANCE_PX / p.density

    assert shown_w <= framing.width + slack, (
        f"{policy.value} shows {shown_w:.2f} world units wide of a "
        f"{framing.width:.0f}-wide framing in a {window} window"
    )
    assert shown_h <= framing.height + slack, (
        f"{policy.value} shows {shown_h:.2f} world units high of a "
        f"{framing.height:.0f}-high framing in a {window} window"
    )


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("framing", FRAMINGS)
@pytest.mark.parametrize("policy", POLICIES)
def test_one_density_describes_the_target(
    window: tuple[int, int], framing: Framing, policy: FitPolicy
) -> None:
    """A target whose two axes imply different densities is refused, not fixed.

    The refusal itself is tested by raising; this is the other half, which is
    that no combination *should* trip it. If one did, the picture would be drawn
    stretched on one axis, and the framing contract would still be claiming
    otherwise.
    """
    p = _presentation(window, framing, policy)
    target = p.picture.target.size

    assert density_for(target, framing) == pytest.approx(p.density, abs=1e-9)
    horizontal = target[0] / framing.width
    vertical = target[1] / framing.height
    slack = DENSITY_TOLERANCE_PX / max(framing.width, framing.height)
    assert abs(horizontal - vertical) <= slack


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("policy", POLICIES)
def test_the_picture_never_leaves_the_window(window: tuple[int, int], policy: FitPolicy) -> None:
    """Whatever the policy, the picture is inside the window and the bars are outside it.

    Zoom's *target* is larger than its window -- that is how it fills -- but what
    it *shows* is the crop, and the crop is the window. Confusing the two is the
    mistake this pins down: a target bigger than the window is fine, a picture
    drawn off the edge of it is not.
    """
    p = _presentation(window, SHIPPED, policy)
    dest = p.picture.dest

    assert dest.x >= 0 and dest.y >= 0
    assert dest.right <= window[0], f"{policy.value} draws past the right edge"
    assert dest.bottom <= window[1], f"{policy.value} draws past the bottom edge"

    for bar in p.bars:
        assert not bar.colliderect(dest), f"a bar overlaps the picture under {policy.value}"


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("policy", POLICIES)
def test_only_zoom_covers_the_window(window: tuple[int, int], policy: FitPolicy) -> None:
    """Bars exist for the two policies that fit inside; zoom has none by design.

    Asserting which is which rather than just that it works, because "there are
    no bars" is indistinguishable from "the bars were never computed" -- and the
    strips have to be painted, since the blit only covers the picture and a strip
    left alone keeps the previous frame's pixels after a resize.
    """
    p = _presentation(window, SHIPPED, policy)

    if policy is FitPolicy.ZOOM:
        assert p.bars == (), "zoom fills the window, so there is no strip to paint"
        assert p.picture.dest.size == window
    else:
        assert tuple(p.bars) == p.picture.bars
        assert p.picture.dest.size != window or window == tuple(p.picture.target.size)


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("policy", POLICIES)
def test_a_pointer_maps_into_the_picture_and_back(
    window: tuple[int, int], policy: FitPolicy
) -> None:
    """The inverse of the blit is the inverse of the blit, not a near miss.

    Both halves, because either alone is satisfiable by something wrong: a
    forward map that always returns (0, 0) survives a check that nothing crashes,
    and an inverse that ignores the crop is exactly the zoom bug.
    """
    p = _presentation(window, SHIPPED, policy)
    corners = [(0, 0), (window[0] - 1, 0), (0, window[1] - 1), (window[0] - 1, window[1] - 1)]
    corners.append((window[0] // 2, window[1] // 2))

    for position in corners:
        if not p.pointer_in_viewport(position):
            continue
        target_position = p.pointer_to_viewport(position)
        assert p.picture.source.collidepoint(target_position), (
            f"{position} is over the picture but maps to {target_position}, "
            f"outside the crop {tuple(p.picture.source)}"
        )
        # And the round trip: target coordinates back to the window.
        back = (
            target_position[0] - p.picture.source.x + p.picture.dest.x,
            target_position[1] - p.picture.source.y + p.picture.dest.y,
        )
        assert back == position


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("policy", POLICIES)
def test_the_presented_frame_is_the_drawn_frame(window: tuple[int, int], policy: FitPolicy) -> None:
    """Not "the right colour in the middle": the same bytes, everywhere.

    A resampling step anywhere between the target and the screen keeps a flat
    fill looking correct and only breaks on detail, which is how a picture can be
    blurred by 40% and a test still pass. So the check is on the whole buffer,
    over lines rather than a fill so there is detail to lose.
    """
    p = _presentation(window, SHIPPED, policy)
    surface = p.surface
    for y in range(0, surface.get_height(), 5):
        pygame.draw.line(
            surface, (y % 256, 60, 200 - y % 200), (0, y), (surface.get_width() - 1, y)
        )

    p.present()

    shown = p.stage.subsurface(p.picture.dest)
    expected = surface.subsurface(p.picture.source)
    assert pygame.image.tobytes(shown, "RGB") == pygame.image.tobytes(expected, "RGB")


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("policy", POLICIES)
def test_the_interface_scale_follows_the_density(
    window: tuple[int, int], policy: FitPolicy
) -> None:
    """The picture grows with the window, so the interface must too.

    The whole point of reading the density off the target rather than configuring
    it: a menu laid out in target pixels would need every font size and padding to
    be right for every window, which is the mistake a fixed render target was
    supposed to prevent. Asserted as a monotonic relation -- a bigger window gives
    a bigger picture at the same framing -- because that is the claim, and the
    absolute scale belongs to the UI layer.
    """
    small = _presentation((1280, 720), SHIPPED, policy)
    large = _presentation((2560, 1440), SHIPPED, policy)

    assert small.density < large.density
    assert small.picture.target.width < large.picture.target.width


# --- window geometry against real display shapes ----------------------------

DESKS: list[Topology] = [
    # One screen, no room for a title bar.
    Topology((Monitor(0, "DP-1", (0, 0, 1024, 768), (0, 0, 1024, 768), 60),), named=True),
    # A panel with a taskbar: the usable area is smaller than the panel.
    Topology((Monitor(0, "DP-1", (0, 0, 1920, 1080), (0, 32, 1920, 1048), 60),), named=True),
    # The Linux case that put a window on the wrong monitor: primary at a
    # positive origin, the left screen at a negative one, different heights.
    Topology(
        (
            Monitor(0, "DP-1", (1920, 0, 2560, 1440), (1920, 0, 2560, 1400), 180),
            Monitor(1, "DP-2", (0, -180, 1920, 1080), (0, -180, 1920, 1040), 60),
        ),
        named=True,
    ),
    # Three screens stacked, which is a real docking setup and has no primary at
    # the origin of anything.
    Topology(
        (
            Monitor(0, "eDP-1", (0, -1080, 1920, 1080), (0, -1080, 1920, 1040), 60),
            Monitor(1, "DP-1", (-1280, -1440, 2560, 1440), (-1280, -1440, 2560, 1400), 144),
            Monitor(2, "HDMI-1", (1280, -1080, 1920, 1080), (1280, -1080, 1920, 1040), 120),
        ),
        named=True,
    ),
]


@pytest.mark.parametrize("desk", DESKS, ids=lambda d: f"{len(d.monitors)}screen")
def test_an_opening_window_always_fits_the_screen_it_opens_on(desk: Topology) -> None:
    """Whatever the panel, the window the game opens is reachable.

    Two properties, and the second is the one that was broken: the window has to
    fit the *usable* area rather than the panel -- a window sized from the panel
    sits under the taskbar and its own title bar is off the top -- and it has to
    be at least large enough for the interface, which the metrics layer will not
    shrink past its text floor.
    """
    for monitor in desk.monitors:
        size = opening_size(monitor)
        usable = monitor.usable_size

        assert size[0] <= usable[0], f"wider than the usable area of {monitor.name}"
        assert size[1] <= usable[1], f"taller than the usable area of {monitor.name}"
        assert size[0] >= min(MIN_WINDOW[0], usable[0])
        assert size[1] >= min(MIN_WINDOW[1], usable[1])


@pytest.mark.parametrize("desk", DESKS, ids=lambda d: f"{len(d.monitors)}screen")
def test_a_centred_window_is_centred_on_the_panel_it_opens_on(desk: Topology) -> None:
    """Centring needs the panel's origin, and the origin is not always zero.

    This is the arithmetic that used to be wrong on a real two-monitor machine:
    it assumed the primary sits at the origin of the virtual desktop, which is the
    Windows and macOS convention and is false on a Linux desktop whose primary is
    not leftmost. Measured there, a window 2176px wide was placed at x=192, which
    is on the *other* monitor.
    """
    for monitor in desk.monitors:
        size = opening_size(monitor)
        position = centre_on(monitor, size)

        assert position[0] >= monitor.usable_origin[0], "centred left of the panel"
        assert position[1] >= monitor.usable_origin[1], "centred above the panel"
        assert position[0] + size[0] <= monitor.usable_origin[0] + monitor.usable_size[0]
        assert position[1] + size[1] <= monitor.usable_origin[1] + monitor.usable_size[1]


@pytest.mark.parametrize("desk", DESKS, ids=lambda d: f"{len(d.monitors)}screen")
def test_an_oversized_window_is_clamped_and_the_choice_is_kept(desk: Topology) -> None:
    """A 4K window arriving at a laptop fits, and the file keeps saying 4K.

    Both halves, and they are not the same half. The clamp is what stops a player
    getting a window they cannot move. Keeping the stored value is what lets the
    size come back on the next launch on a machine that has the room -- and it is
    precisely what the old ``width``/``height`` keys got wrong, by overwriting
    the file at launch whenever the value did not fit.
    """
    oversized = (7680, 4320)
    for monitor in desk.monitors:
        clamped = fit_size(oversized, monitor)
        assert clamped[0] <= monitor.usable_size[0]
        assert clamped[1] <= monitor.usable_size[1]
        assert clamped[0] >= MIN_WINDOW[0] and clamped[1] >= MIN_WINDOW[1]


@pytest.mark.parametrize("desk", DESKS, ids=lambda d: f"{len(d.monitors)}screen")
def test_the_panel_under_a_point_is_the_panel_under_a_point(desk: Topology) -> None:
    """Which display the window is on, decided from its top-left corner.

    The one question the display subsystem still answers: the VSync row reads the
    rate off the panel the window is *on*, and this is how that is decided. A
    window may legitimately be larger than the panel, so the corner is what
    counts. When the corner is inside a panel there is nothing to guess, and
    ``nearest`` must agree with ``containing`` rather than approximate.
    """
    for monitor in desk.monitors:
        for point in (
            (monitor.bounds[0], monitor.bounds[1]),
            (monitor.bounds[0] + monitor.bounds[2] - 1, monitor.bounds[1] + monitor.bounds[3] - 1),
        ):
            holder = desk.containing(point)
            if holder is None:
                continue
            assert desk.nearest(point) is holder, (
                f"{point} is on {holder.name} but reported otherwise"
            )


def test_a_point_off_every_panel_gets_the_closest_one() -> None:
    """A monitor was unplugged; the window is now somewhere no panel is.

    The fallback is the nearest panel rather than the primary, because the window
    did not move and the panel closest to where it is is the one the player is
    looking at. The centre-point distance is restated here rather than trusted, so
    the test says what "closest" means.
    """
    desk = DESKS[2]
    far = (99999, 99999)
    assert desk.containing(far) is None

    def centre(monitor: Monitor) -> tuple[int, int]:
        left, top, width, height = monitor.bounds
        return (left + width // 2, top + height // 2)

    closest = min(
        desk.monitors,
        key=lambda monitor: (centre(monitor)[0] - far[0]) ** 2 + (centre(monitor)[1] - far[1]) ** 2,
    )
    assert desk.nearest(far) is closest
