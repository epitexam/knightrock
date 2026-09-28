"""FX particles: which ones may rebuild their surface, and which may not.

`src/core/fx/particles.py` builds a particle's pixels once, at construction. A few of
them then pick a different surface per frame from a ladder they built
alongside, and these tests pin which, because the difference is invisible in
a screenshot and invisible in a frame time, and the mistake is easy to
reintroduce by "tidying" an update method.
"""

import math
import os
from collections.abc import Iterator

import pygame
import pytest

from src.core.fx import (
    DashShockwaveParticle,
    DizzyVortexParticle,
    DustParticle,
    OrbitParticle,
    StreakParticle,
    clear_frame_cache,
    spawners,
    vortex_frames,
)
from src.core.fx.particles import FxParticle, ShatterArcParticle
from src.core.settings import FxDash, FxDizzy


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


@pytest.fixture(autouse=True)
def _pinned_fx_rng() -> Iterator[None]:
    """Fix the draw, because these tests assert on the pixels it produces.

    Several spawners jitter from the FX module's own RNG, so which way a
    puff lands or how a fragment scatters is a function of how many draws
    the tests before them happened to make. Left alone that made a test here
    pass on its own and fail in the full suite -- a result that is evidence
    of the run's order rather than of the rule it claims to check.
    """
    spawners._fx_rng.seed(0xF00D)
    yield


def test_a_speed_line_surface_is_built_once_and_only_faded() -> None:
    """A moving mark's shape is fixed, so rebuilding it would redraw the same pixels.

    This property used to be pinned on the dash comet, which is gone: the
    ghosts now carry the path and a comet next to them said the same thing in
    a second colour. It moves onto the speed line, because the claim is about
    the module and not about one particle -- every mark here builds its
    surface at construction and then only moves and fades.
    """
    particle = StreakParticle((0.0, 0.0), (400.0, 0.0))
    original = particle.image

    for _ in range(8):
        particle.update(1 / 60)

    assert particle.image is original, "the mark must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_the_speed_line_fade_matches_its_ttl_curve() -> None:
    """Freezing the surface must not freeze the fade with it."""
    particle = StreakParticle((0.0, 0.0), (400.0, 0.0))
    particle.max_ttl = FxDash.STREAK_TTL

    particle.update(FxDash.STREAK_TTL * 0.5)
    halfway = particle.image.get_alpha()
    particle.update(FxDash.STREAK_TTL * 0.25)
    later = particle.image.get_alpha()

    assert 0 < later < halfway < 255


def test_a_speed_line_still_follows_its_position() -> None:
    """The rect is per-frame even though the surface is not.

    The mark travels, so the claim is not that the position holds still but
    that the drawn rect is re-cut around wherever the particle now is.
    """
    particle = StreakParticle((0.0, 0.0), (400.0, 0.0))
    particle.pos.update(120.0, 40.0)

    particle.update(1 / 60)

    assert (particle.rect.centerx, particle.rect.centery) == pytest.approx(tuple(particle.pos))
    assert particle.pos.x > 120.0, "and it really did travel"


def test_a_speed_line_still_reaps_at_the_end_of_its_life() -> None:
    particle = StreakParticle((0.0, 0.0), (400.0, 0.0))

    particle.update(FxDash.STREAK_TTL + 1.0)

    assert particle.alive() is False


def test_a_swirl_picks_its_rotation_step_from_a_shared_ladder() -> None:
    """The vortex animates by stepping a ladder, not by redrawing its arms.

    It used to draw three arms of three polygons per particle per frame, and
    a stun puts up to four of them on screen at once.
    """
    clear_frame_cache()
    particle = DizzyVortexParticle((0.0, 0.0))
    frames = vortex_frames()
    seen = [particle.image]

    for _ in range(4):
        particle.update(0.1)
        seen.append(particle.image)

    assert len(frames) == FxDizzy.VORTEX_FRAMES
    assert len(set(seen)) > 1, "the swirl has to animate"
    assert all(any(step is frame for frame in frames) for step in seen), (
        "and every step it shows has to be one it built once"
    )
    clear_frame_cache()


def test_the_shockwave_picks_a_prebuilt_step_and_thins_as_it_spreads() -> None:
    """The dash ring is drawn once per size, not scaled up from one image.

    Scaling a rim up makes a heavier rim, and a shockwave is defined by
    getting lighter as it spreads.
    """
    clear_frame_cache()
    particle = DashShockwaveParticle((0.0, 0.0), ttl=1.0)
    first = particle.image

    particle.update(0.2)
    grown = particle.image
    particle.update(0.6)
    widest = particle.image

    assert grown is not first
    assert grown.get_width() > first.get_width(), "the ring has to spread"
    assert widest.get_width() == particle.steps[-1].get_width(), "up to its last step"
    assert widest.get_width() > grown.get_width()
    clear_frame_cache()


def test_a_dust_puff_without_frames_keeps_one_surface() -> None:
    """The plain disc is fixed too, and must not churn."""
    particle = DustParticle((0.0, 0.0), (0.0, 0.0), ttl=1.0, radius=4.0)
    original = particle.image

    for _ in range(5):
        particle.update(1 / 60)

    assert particle.image is original


def test_an_orbit_star_keeps_one_surface_and_moves_on_its_position() -> None:
    """The dizzy stars are not sparks: they orbit, so they must not fall.

    Built once, the position is a function of the age, and the fade is the
    only thing that changes on the surface.
    """
    particle = OrbitParticle((100.0, 100.0), 20.0, 0.0, 2.4, (255, 220, 80), (255, 255, 255), 1.0)
    original = particle.image
    start_y = particle.pos.y

    particle.update(0.25)

    assert particle.image is original
    assert particle.pos.y != start_y, "the star has to move"
    assert particle.velocity == pygame.math.Vector2(0.0, 0.0), "and not by falling"


def test_the_base_particle_cannot_be_drawn_on_its_own() -> None:
    """`FxParticle` is a contract, not a shape.

    It carries the physics, the fade and the budget plumbing, and refuses to
    paint. A particle that forgot to override `_paint` would otherwise
    inherit a surface of `None` and take the first `set_alpha` on it as a
    crash somewhere further down, rather than here.
    """
    with pytest.raises(NotImplementedError):
        FxParticle((0.0, 0.0), 1.0)


def test_the_broken_ring_breaks_further_out_as_it_opens() -> None:
    """The shatter arc is the one particle that redraws from a prebuilt ladder.

    It has to open rather than fade: a guard that fails should look like the
    same shield coming apart, which means the fragments travel further as the
    ring opens. Indexing the fade instead would show the widest frame first
    and shrink from there -- the failure inflating instead of breaking.

    The ladder's surfaces are all the same size, by design: the span covers
    the furthest a fragment can ever travel, and each step differs in what
    is drawn inside it. So the claim is about the drawn extent, not the
    surface.
    """
    shatter = ShatterArcParticle((40.0, 40.0), 1.0, seed=7)

    def extent() -> int:
        """The furthest radius from the centre that anything is drawn at.

        Polarity matters: the fragments are spread over the whole ring, so
        probing one ray would find a gap and report the ring as closed.
        """
        image = shatter.image
        middle = image.get_width() / 2.0
        limit = image.get_width() // 2 - 1
        furthest = 0
        for degree in range(0, 360, 2):
            for radius in range(limit, 0, -1):
                if image.get_at(
                    (
                        round(middle + radius * math.cos(math.radians(degree))),
                        round(middle + radius * math.sin(math.radians(degree))),
                    )
                )[3]:
                    furthest = max(furthest, radius)
                    break
        return furthest

    reaches = []
    for _ in range(6):
        reaches.append(extent())
        shatter.update(1 / 30)

    assert reaches == sorted(reaches), "the fragments only ever travel further"
    assert reaches[-1] > reaches[0], "and they did travel"
