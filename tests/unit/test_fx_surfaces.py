"""FX particles: which ones may rebuild their surface, and which may not.

`src/core/fx.py` redraws some particle surfaces every frame. That is
legitimate for a particle whose *look* changes -- a rotating vortex, an
expanding ring -- and waste for one whose look is fixed. These tests pin
which is which, because the difference is invisible in a screenshot and
invisible in a frame time, and the mistake is easy to reintroduce by
"tidying" an update method.
"""

import os

import pygame
import pytest

from src.core.fx import (
    DASH_TRAIL_TTL,
    DashShockwaveParticle,
    DashTrailParticle,
    DizzyVortexParticle,
    DustParticle,
)


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_the_dash_trail_surface_is_built_once_and_only_faded() -> None:
    """The streak's shape is fixed, so rebuilding it redrew identical pixels.

    28 `sin` evaluations and two polygon fills per particle per frame, to
    produce the same image, so that the alpha could be set on it.
    """
    particle = DashTrailParticle((0.0, 0.0), 1.0)
    original = particle.image

    for _ in range(10):
        particle.update(1 / 60)

    assert particle.image is original, "the trail must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_the_trail_fade_matches_the_ttl_curve() -> None:
    """Freezing the surface must not freeze the fade with it."""
    particle = DashTrailParticle((0.0, 0.0), 1.0)
    particle.max_ttl = DASH_TRAIL_TTL

    particle.update(DASH_TRAIL_TTL * 0.5)
    halfway = particle.image.get_alpha()
    particle.update(DASH_TRAIL_TTL * 0.25)
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

    particle.update(DASH_TRAIL_TTL + 1.0)

    assert particle.alive() is False


def test_a_rotating_vortex_may_rebuild_because_its_look_changes() -> None:
    """The counterpart to the trail: this one genuinely has new pixels."""
    particle = DizzyVortexParticle((0.0, 0.0))
    first = particle.image

    particle.update(1 / 60)

    assert particle.rotation > 0.0
    assert particle.image is not first, "a rotating vortex has to redraw"


def test_an_expanding_shockwave_may_rebuild_because_its_look_changes() -> None:
    particle = DashShockwaveParticle((0.0, 0.0))
    first = particle.image

    particle.update(1 / 60)

    assert particle.image is not first
    assert particle.current_radius > 0.0


def test_a_dust_puff_without_frames_keeps_one_surface() -> None:
    """The plain circle is fixed too, and must not churn."""
    particle = DustParticle((0.0, 0.0), (0.0, 0.0), ttl=1.0, radius=4.0)
    original = particle.image

    for _ in range(5):
        particle.update(1 / 60)

    assert particle.image is original
