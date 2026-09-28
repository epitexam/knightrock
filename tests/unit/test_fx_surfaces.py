"""FX particles: which ones may rebuild their surface, and which may not.

`src/core/fx.py` builds a particle's pixels once, at construction. A few of
them then pick a different surface per frame from a ladder they built
alongside, and these tests pin which, because the difference is invisible in
a screenshot and invisible in a frame time, and the mistake is easy to
reintroduce by "tidying" an update method.
"""

import os

import pygame
import pytest

from src.core.fx import (
    DashShockwaveParticle,
    DashTrailParticle,
    DizzyVortexParticle,
    DustParticle,
    OrbitParticle,
    clear_frame_cache,
    vortex_frames,
)
from src.core.settings import FxDash, FxDizzy


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_the_dash_trail_surface_is_built_once_and_only_faded() -> None:
    """The comet's shape is fixed, so rebuilding it would redraw identical pixels.

    16 `sin` evaluations and two polygon fills per particle per frame, to
    produce the same image, so that the alpha could be set on it.
    """
    particle = DashTrailParticle((0.0, 0.0), 1.0)
    original = particle.image

    for _ in range(8):
        particle.update(1 / 60)

    assert particle.image is original, "the trail must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_the_trail_fade_matches_the_ttl_curve() -> None:
    """Freezing the surface must not freeze the fade with it."""
    particle = DashTrailParticle((0.0, 0.0), 1.0)
    particle.max_ttl = FxDash.TRAIL_TTL

    particle.update(FxDash.TRAIL_TTL * 0.5)
    halfway = particle.image.get_alpha()
    particle.update(FxDash.TRAIL_TTL * 0.25)
    later = particle.image.get_alpha()

    assert 0 < later < halfway < 255


def test_the_trail_still_follows_its_position() -> None:
    """The rect is per-frame even though the surface is not."""
    particle = DashTrailParticle((0.0, 0.0), 1.0)
    particle.pos.update(120.0, 40.0)

    particle.update(1 / 60)

    assert particle.rect.centerx == 120.0
    assert particle.rect.centery == 40.0


def test_a_trail_still_reaps_at_the_end_of_its_life() -> None:
    particle = DashTrailParticle((0.0, 0.0), 1.0)

    particle.update(FxDash.TRAIL_TTL + 1.0)

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
