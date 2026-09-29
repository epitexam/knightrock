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
    SweatParticle,
    clear_frame_cache,
    puff_frames,
    spawn_landing_dust,
    spawners,
    vortex_frames,
)
from src.core.fx import particles as particles
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


def test_a_sweat_drop_surface_is_built_once_and_only_faded() -> None:
    """A drop's shape is fixed, so rebuilding it would redraw the same pixels.

    This property has moved house three times now: it was pinned on the dash
    comet, then on the speed line, then on the dust, all of which are gone or
    have become ladders. It stays on sweat because the claim is about the
    module and not about one particle -- every mark here either builds its
    surface at construction and then only moves and fades, or steps through a
    ladder it built alongside, and a "tidying" of an update method is the
    mistake it catches.
    """
    particle = SweatParticle((0.0, 0.0), (60.0, -20.0))
    original = particle.image

    for _ in range(8):
        particle.update(1 / 60)

    assert particle.image is original, "the drop must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_a_puff_picks_its_billow_from_a_shared_ladder() -> None:
    """The puff opens, and every step it opens to is one the session built once.

    The dust is the particle that was rebuilt per particle per frame: it used
    to scale its own copies of three PNGs at construction and then swap
    between them, and a landing put six of those on screen at once. It steps a
    shared ladder now, for the same reason the swirl does.
    """
    clear_frame_cache()
    ladder = puff_frames(Dust.PUFF_RADIUS)
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    seen = [particle.image]

    for _ in range(4):
        particle.update(1 / 60)
        seen.append(particle.image)

    assert len(ladder) == Dust.PUFF_STEPS
    assert len(set(seen)) > 1, "the puff has to billow"
    assert all(any(step is frame for frame in ladder) for step in seen), (
        "and every step it shows has to be one built once"
    )
    assert particle.ladder is ladder, "and the ladder is shared, not per puff"
    clear_frame_cache()


def test_a_hard_landing_does_not_paint_a_new_puff_surface() -> None:
    """A landing is twelve puffs and it must not be twelve sets of surfaces.

    The reason the ladder is keyed on a discrete radius and a discrete tone
    rather than on whatever the spawner asked for: this is the allocation
    ``notes/refacto.md`` flags as the FX plane's main remaining cost, and a
    landing is exactly when a dozen of them happen on the same tick.

    The bound is the grid, not the fan. The radius carries a jitter, so any
    one landing lands on several buckets and a later one may reach a bucket
    the first missed -- but the cache can never outgrow the grid, however
    many landings go through it. That ceiling is the whole reason for
    snapping: an unbounded cache keyed on a continuous radius is the same
    allocation as no cache at all.
    """
    clear_frame_cache()
    lander = _lander()
    for _ in range(12):
        spawn_landing_dust(pygame.sprite.Group(), lander, Dust.MIN_FALL_SPEED * 2.0)

    grid = len(Dust.PUFF_BUCKETS) * len(Dust.SIZE_PROFILE)
    assert 0 < len(particles._puff_cache) <= grid, (
        f"twelve landings painted {len(particles._puff_cache)} ladders, over a grid of {grid}"
    )
    clear_frame_cache()


def test_two_puffs_of_one_size_and_tone_share_their_ladder() -> None:
    """The share is by value, so two puffs of a size hold one set of surfaces."""
    clear_frame_cache()
    one = DustParticle((0.0, 0.0), (0.0, 0.0), radius=6.0, tint=0.0)
    two = DustParticle((0.0, 0.0), (0.0, 0.0), radius=6.4, tint=0.0)

    assert one.ladder is two.ladder, "6.0 and 6.4 are the same bucket"
    assert len(particles._puff_cache) == 1
    clear_frame_cache()


def _lander() -> object:
    """A stand-in with the one attribute the landing fan reads."""
    from types import SimpleNamespace

    return SimpleNamespace(hitbox=pygame.FRect(100.0, 100.0, 40, 48))


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
