"""A hazard hurts through its art, not through the empty part of its frame.

Floor spikes fill the bottom half of their 64px tile, a saw and a spiked ball
are discs in a square frame. Tested against the full frame, they hurt the
player from up to 32px above the spikes and from the empty corners of the
square -- which the contact cooldown's random delay used to hide, until audit
C2 made the first contact land on its tick.
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame
import pytest

from src.combat.frame_data import HitProperties
from src.combat.shapes import ShapeKind, ShapePose, SweptShape
from src.core.hazards import SpanHazard, art_bounds
from src.core.level.level_data import ObjectData, _gid_flips
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.world_builder import _build_static_hazard
from src.core.paths import PROJECT_ROOT
from src.core.sprite_groups import SpriteGroups
from tests.fakes import BodyStub

TILE = 64


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    pygame.display.set_mode((64, 64))


def _bottom_half_art() -> pygame.Surface:
    art = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    art.fill((0, 0, 0, 0))
    art.fill((200, 200, 220, 255), pygame.Rect(0, TILE // 2, TILE, TILE // 2))
    return art


def _spikes_at(x: float, y: float) -> SpanHazard:
    art = _bottom_half_art()
    spikes = SpanHazard((x, y), art, 0.0, False, damage=10.0)
    spikes.fit_contact(art_bounds([art], spikes.rect.size))
    return spikes


def _saw_at(x: float, y: float, side: float = 76.0) -> SpanHazard:
    saw = SpanHazard((x, y), pygame.Surface((side, side)), 0.0, False, damage=10.0)
    saw.fit_contact(pygame.FRect(0.0, 0.0, side, side), round_shape=True)
    return saw


def _hurt(body: BodyStub, hazard: SpanHazard) -> bool:
    hazard.capture_contact_origin()
    HazardDamageSystem().process([body], [hazard])
    return body.damage_taken > 0.0


# -- what the art covers -------------------------------------------------------


def test_the_art_bounds_are_the_opaque_part_of_the_frame() -> None:
    assert art_bounds([_bottom_half_art()], (TILE, TILE)) == pygame.FRect(0, 32, 64, 32)


def test_the_art_bounds_follow_the_frame_to_the_sprite_size() -> None:
    """The animator stretches each frame to the sprite: so do the bounds."""
    assert art_bounds([_bottom_half_art()], (128, 128)) == pygame.FRect(0, 64, 128, 64)


def test_art_with_nothing_opaque_keeps_the_whole_frame() -> None:
    blank = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    blank.fill((0, 0, 0, 0))

    assert art_bounds([blank], (TILE, TILE)) == pygame.FRect(0, 0, TILE, TILE)


# -- floor spikes ---------------------------------------------------------------


def test_the_air_above_floor_spikes_does_not_hurt() -> None:
    spikes = _spikes_at(0.0, 0.0)
    # Feet 10px inside the tile, 22px above the spikes.
    body = BodyStub(pygame.FRect(10.0, -30.0, 40.0, 40.0))

    assert not _hurt(body, spikes)


def test_touching_the_spikes_hurts() -> None:
    spikes = _spikes_at(0.0, 0.0)
    body = BodyStub(pygame.FRect(10.0, -6.0, 40.0, 40.0))  # feet 2px into the spikes

    assert _hurt(body, spikes)


def test_the_contact_moves_with_the_hazard() -> None:
    spikes = _spikes_at(0.0, 0.0)
    spikes.rect.topleft = (200.0, 100.0)
    spikes.sync_contact_shape()

    assert spikes.contact_rect() == pygame.FRect(200.0, 132.0, 64.0, 32.0)


# -- round hazards --------------------------------------------------------------


def test_the_empty_corner_of_a_saw_frame_does_not_hurt() -> None:
    saw = _saw_at(0.0, 0.0)
    # Bottom-right corner 6px into the frame's top-left corner: inside the
    # square, outside the disc (which meets the diagonal 11px in).
    body = BodyStub(pygame.FRect(-34.0, -34.0, 40.0, 40.0))

    assert not _hurt(body, saw)


def test_the_disc_of_a_saw_hurts() -> None:
    saw = _saw_at(0.0, 0.0)
    body = BodyStub(pygame.FRect(-24.0, -24.0, 40.0, 40.0))  # corner 16px in

    assert _hurt(body, saw)


def test_a_round_box_is_judged_on_its_shape_and_not_its_rectangle() -> None:
    """The rule in ContactSystem itself, for any producer with a round shape."""
    box = pygame.FRect(0.0, 0.0, 76.0, 76.0)
    disc = ShapePose(ShapeKind.CIRCLE, (76.0, 76.0), box.center)
    corner_only = BodyStub(pygame.FRect(-34.0, -34.0, 40.0, 40.0))
    offensive = OffensiveBox(
        box=box,
        swept=(box,),
        hit=HitProperties(damage=5.0),
        faction=None,
        owner_id="",
        can_contact=lambda _target_id: True,
        swept_shapes=(SweptShape(None, disc),),
        kind="hazard",
        interrupt=False,
    )

    ContactSystem().resolve((offensive,), (corner_only,))

    assert corner_only.damage_taken == 0.0


# -- the shipped art --------------------------------------------------------------


@pytest.mark.skipif(
    not (PROJECT_ROOT / "assets" / "graphics" / "enemies" / "floor_spikes").is_dir(),
    reason="needs the untracked assets/graphics tree",
)
def test_the_shipped_floor_spikes_hurt_through_their_bottom_half_only() -> None:
    from src.core.asset_library import shared_library
    from src.core.level.world_builder import FLOOR_SPIKES_ART

    frames = shared_library().frames(FLOOR_SPIKES_ART)

    area = art_bounds(frames, (TILE, TILE))

    assert area.top >= TILE / 2 - 1
    assert area.bottom == TILE


# -- a spike mirrored in Tiled ------------------------------------------------


def _spike_object(flip_y: bool) -> ObjectData:
    return ObjectData(
        name="floor_spike",
        x=0.0,
        y=0.0,
        width=64.0,
        height=64.0,
        gid=85,
        image=_bottom_half_art(),
        points=None,
        properties={},
        flip_y=flip_y,
    )


def _built(obj: ObjectData) -> SpanHazard:
    groups = SpriteGroups()
    _build_static_hazard(obj, groups)
    (hazard,) = groups.hazard_sprites
    hazard.update(1 / 60)  # the animator, when the art is there, takes over the image
    return hazard


def test_the_flip_flags_of_a_tiled_object_are_read_from_pytmx() -> None:
    """PyTMX gives a mirrored tile object its own gid, with the flags beside it."""
    flags = SimpleNamespace(flipped_horizontally=False, flipped_vertically=True)
    plain = SimpleNamespace(flipped_horizontally=0, flipped_vertically=0)
    tmx = SimpleNamespace(tiledgidmap={84: 231, 85: 231}, gidmap={231: [(84, plain), (85, flags)]})

    assert _gid_flips(tmx, 85) == (False, True)
    assert _gid_flips(tmx, 84) == (False, False)
    assert _gid_flips(tmx, None) == (False, False)


def test_a_spike_mirrored_in_tiled_hangs_and_hurts_from_the_top() -> None:
    """PyTMX hands the tile back unflipped; the builder turns it, art and contact."""
    hazard = _built(_spike_object(flip_y=True))

    assert hazard.image.get_bounding_rect(min_alpha=64).top == 0
    assert hazard.contact_rect().top == hazard.rect.top
    assert hazard.contact_rect().bottom <= hazard.rect.top + TILE / 2 + 1


def test_an_unmirrored_spike_is_unchanged() -> None:
    hazard = _built(_spike_object(flip_y=False))

    assert hazard.contact_rect().bottom == hazard.rect.bottom
    assert hazard.contact_rect().top >= hazard.rect.top + TILE / 2 - 1
