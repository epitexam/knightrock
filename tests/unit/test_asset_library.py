"""Tests for the nascent AssetLibrary (audit F4.1 / Phase 1 #3)."""

import os
from pathlib import Path

import pygame
import pytest

from src.core.asset_library import AssetLibrary


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    """Initialize a dummy SDL display: convert_alpha() requires a video mode."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


@pytest.fixture()
def png_paths(tmp_path: Path) -> dict[str, Path]:
    """Create one opaque and one alpha PNG in a temp dir."""
    opaque = tmp_path / "opaque.png"
    raw = pygame.Surface((8, 8))
    raw.fill((200, 30, 30))
    pygame.image.save(raw, opaque)

    alpha = tmp_path / "alpha.png"
    raw_alpha = pygame.Surface((8, 8), pygame.SRCALPHA)
    raw_alpha.fill((20, 120, 220, 128))
    pygame.image.save(raw_alpha, alpha)
    return {"opaque": opaque, "alpha": alpha}


def test_image_loads_and_returns_same_object_for_repeated_calls(
    png_paths: dict[str, Path],
) -> None:
    library = AssetLibrary()
    first = library.image(png_paths["alpha"])
    second = library.image(png_paths["alpha"])

    assert first is second
    assert first.get_width() == 8
    assert first.get_height() == 8
    # convert_alpha() produces a per-pixel-alpha surface.
    assert first.get_flags() & pygame.SRCALPHA


def test_opaque_images_use_plain_convert(png_paths: dict[str, Path]) -> None:
    library = AssetLibrary()
    surface = library.image(png_paths["opaque"], alpha=False)

    assert not surface.get_flags() & pygame.SRCALPHA


def test_alpha_and_opaque_are_cached_separately(png_paths: dict[str, Path]) -> None:
    library = AssetLibrary()
    alpha_surf = library.image(png_paths["alpha"])
    opaque_surf = library.image(png_paths["alpha"], alpha=False)

    assert alpha_surf is not opaque_surf


def test_clear_drops_cache(png_paths: dict[str, Path]) -> None:
    library = AssetLibrary()
    first = library.image(png_paths["alpha"])
    library.clear()
    second = library.image(png_paths["alpha"])

    assert first is not second


def test_preload_warms_cache(png_paths: dict[str, Path]) -> None:
    library = AssetLibrary()
    library.preload([png_paths["alpha"], png_paths["opaque"]])

    assert library.image(png_paths["alpha"]) is library.image(png_paths["alpha"])


def test_missing_file_raises_error(tmp_path: Path) -> None:
    library = AssetLibrary()

    with pytest.raises(OSError):
        library.image(tmp_path / "missing.png")
