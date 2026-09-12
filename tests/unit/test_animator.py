"""Tests for the Animator (Phase 2 #1: AssetLibrary + Animator + sprite sheets)."""

import os
from pathlib import Path

import pygame
import pytest

from src.core.animation.animator import AnimationSpec, Animator
from src.core.asset_library import AssetLibrary


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    """Initialize a dummy SDL display: convert_alpha() requires a video mode."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


@pytest.fixture()
def library(tmp_path: Path) -> AssetLibrary:
    """AssetLibrary serving a 3-frame loop and a 2-frame one-shot."""
    anims = tmp_path / "anims"
    for name, count in (("loop", 3), ("once", 2)):
        directory = anims / name
        directory.mkdir(parents=True)
        for index in range(count):
            frame = pygame.Surface((4, 4), pygame.SRCALPHA)
            frame.fill((index * 40, 0, 0, 255))
            pygame.image.save(frame, directory / f"{index}.png")
    return AssetLibrary()


@pytest.fixture()
def specs(tmp_path: Path) -> dict[str, AnimationSpec]:
    base = str(tmp_path / "anims")
    return {
        "loop": AnimationSpec("loop", f"{base}/loop", frame_duration=0.1, loop=True),
        "once": AnimationSpec("once", f"{base}/once", frame_duration=0.1, loop=False),
    }


def test_play_switches_and_restarts(specs: dict[str, AnimationSpec], library: AssetLibrary) -> None:
    animator = Animator(library, specs, default="loop")
    animator.update(0.25)
    assert animator.frame_index == 2

    assert animator.play("once") is True
    assert animator.current == "once"
    assert animator.frame_index == 0


def test_play_is_noop_for_unknown_or_same_animation(
    specs: dict[str, AnimationSpec], library: AssetLibrary
) -> None:
    animator = Animator(library, specs, default="loop")

    assert animator.play("unknown") is False
    assert animator.play("loop") is False
    assert animator.current == "loop"


def test_looping_animation_wraps(specs: dict[str, AnimationSpec], library: AssetLibrary) -> None:
    animator = Animator(library, specs, default="loop")
    animator.update(0.1)
    animator.update(0.1)
    animator.update(0.1)

    assert animator.frame_index == 0
    assert not animator.finished


def test_non_looping_animation_holds_last_frame(
    specs: dict[str, AnimationSpec], library: AssetLibrary
) -> None:
    animator = Animator(library, specs, default="once")
    for _ in range(5):
        animator.update(0.1)

    assert animator.frame_index == 1
    assert animator.finished is True


def test_surface_is_scaled_and_cached(
    specs: dict[str, AnimationSpec], library: AssetLibrary
) -> None:
    animator = Animator(library, specs, default="loop")

    surface = animator.surface((8, 8), facing_right=True)

    assert surface is not None
    assert surface.get_size() == (8, 8)
    assert animator.surface((8, 8), facing_right=True) is surface


def test_surface_flips_for_left_facing(
    specs: dict[str, AnimationSpec], library: AssetLibrary
) -> None:
    animator = Animator(library, specs, default="loop")
    right = animator.surface((4, 4), facing_right=True)
    left = animator.surface((4, 4), facing_right=False)

    assert right is not None and left is not None
    assert pygame.transform.flip(left, True, False).get_at((0, 0)) == right.get_at((0, 0))


def test_surface_returns_none_for_empty_size(
    specs: dict[str, AnimationSpec], library: AssetLibrary
) -> None:
    animator = Animator(library, specs, default="loop")

    assert animator.surface((0, 8), facing_right=True) is None


def test_empty_specs_rejected(library: AssetLibrary) -> None:
    with pytest.raises(ValueError):
        Animator(library, {}, default="")
