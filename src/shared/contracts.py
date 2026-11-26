"""Ports that let the simulation run without a window, a mixer or an art cache.

The protocols are deliberately narrow: each one names only the calls the
current simulation actually makes. They grow when a tranche moves, never ahead
of a real consumer. Null implementations are the default so a headless test
can build a world without installing any adapter.
"""

from __future__ import annotations

from typing import Any, Protocol

import pygame

__all__ = [
    "AssetPort",
    "CameraPort",
    "NullAssetPort",
    "NullCamera",
    "NullWorldRenderer",
    "WorldRendererPort",
]


class AssetPort(Protocol):
    """Surface source for animations and art-driven world objects."""

    def image(self, relative_path: str, *, alpha: bool = True) -> pygame.Surface: ...

    def frames(self, relative_path: str) -> list[pygame.Surface]: ...

    def clear(self) -> None: ...


class NullAssetPort:
    """Asset source with no art: renders as a one-pixel transparent surface."""

    def image(self, relative_path: str, *, alpha: bool = True) -> pygame.Surface:
        surface = pygame.Surface((1, 1))
        surface.set_alpha(0)
        return surface

    def frames(self, relative_path: str) -> list[pygame.Surface]:
        return []

    def clear(self) -> None:
        return None


class CameraPort(Protocol):
    """Framing follower used by the simulation's camera system."""

    def follow(self, box: Any, delta_time: float) -> None: ...

    def hold(self, delta_time: float) -> None: ...

    def add_trauma(self, amount: float) -> None: ...


class NullCamera:
    """Camera for a headless tick: framing exists, but nothing is drawn."""

    def follow(self, box: Any, delta_time: float) -> None:
        return None

    def hold(self, delta_time: float) -> None:
        return None

    def add_trauma(self, amount: float) -> None:
        return None


class WorldRendererPort(Protocol):
    """The drawing surface behind ``Level.draw``."""

    def draw(
        self,
        groups: Any,
        debug_enabled: bool,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None: ...

    def draw_health_bars(self, fighters: Any) -> None: ...


class NullWorldRenderer:
    """Renderer for headless simulation tests: every draw call is a no-op."""

    def draw(
        self,
        groups: Any,
        debug_enabled: bool,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        return None

    def draw_health_bars(self, fighters: Any) -> None:
        return None
