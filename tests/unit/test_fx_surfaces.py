"""FX particles: which ones may rebuild their surface, and which may not.

`src/core/fx/particles.py` builds a particle's pixels once, at construction. A few of
them then pick a different surface per frame from a ladder they built
alongside, and these tests pin which, because the difference is invisible in
a screenshot and invisible in a frame time, and the mistake is easy to
reintroduce by "tidying" an update method.
"""

import os
from collections.abc import Iterator

import pygame
import pytest

from src.core.fx import (
    DizzyVortexParticle,
    DustParticle,
    clear_frame_cache,
    spawners,
    vortex_frames,
)
from src.core.settings import Dust, FxDizzy


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


def test_a_dust_puff_surface_is_built_once_and_only_faded() -> None:
    """A puff's shape is fixed, so rebuilding it would redraw the same pixels.

    This property has moved house twice now: it was pinned on the dash comet,
    then on the speed line, and both of those are gone. It stays on the dust
    because the claim is about the module and not about one particle -- every
    mark here builds its surface at construction and then only moves and
    fades, and a "tidying" of an update method is the mistake it catches.
    """
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    original = particle.image

    for _ in range(8):
        particle.update(1 / 60)

    assert particle.image is original, "the puff must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_the_puff_fade_matches_its_ttl_curve() -> None:
    """Freezing the surface must not freeze the fade with it."""
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    particle.max_ttl = Dust.TTL

    particle.update(Dust.TTL * 0.5)
    halfway = particle.image.get_alpha()
    particle.update(Dust.TTL * 0.25)
    later = particle.image.get_alpha()

    assert 0 < later < halfway < 255


def test_a_puff_still_follows_its_position() -> None:
    """The rect is per-frame even though the surface is not.

    A puff travels, so the claim is not that the position holds still but
    that the drawn rect is re-cut around wherever the particle now is.
    """
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    particle.pos.update(120.0, 40.0)

    particle.update(1 / 60)

    assert (particle.rect.centerx, particle.rect.centery) == pytest.approx(tuple(particle.pos))


def test_a_puff_still_reaps_at_the_end_of_its_life() -> None:
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))

    particle.update(Dust.TTL + 1.0)

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
