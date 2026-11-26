"""Ports that let the simulation run without a window, a mixer or an art cache.

The simulation owns the rules; these ports are the only way it reaches drawing,
assets and camera framing. Every port has a null implementation, so a headless
level can be built and ticked without importing a single presentation module.
"""

from __future__ import annotations

from typing import Any, Protocol

import pygame

__all__ = [
    "AssetPort",
    "CameraPort",
    "FxPort",
    "NullAssetPort",
    "NullCamera",
    "NullOverlay",
    "NullWorldRenderer",
    "OverlayPort",
    "SnapshotPort",
    "WorldRendererPort",
]


class AssetPort(Protocol):
    """Surface source for animations and art-driven world objects."""

    def image(self, relative_path: str, *, alpha: bool = True) -> pygame.Surface: ...

    def frames(self, relative_path: str) -> list[pygame.Surface]: ...

    def clear(self) -> None: ...


class NullAssetPort:
    """Asset source with no art: surfaces exist but carry no pixels."""

    generation: int = 0

    def image(self, relative_path: str, *, alpha: bool = True) -> pygame.Surface:
        surface = pygame.Surface((1, 1))
        surface.set_alpha(0)
        return surface

    def frames(self, relative_path: str) -> list[pygame.Surface]:
        return [self.image(relative_path)]

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


class OverlayPort(Protocol):
    """What the level tells the debug overlay during a frame."""

    def note_clash(self, clash: Any) -> None: ...

    def draw_metrics_panel(self, player: Any, hit_stop: float) -> None: ...

    def stamp_clash_marker(self, camera: CameraPort) -> None: ...

    def update_metrics(self, metrics: Any) -> None: ...


class NullOverlay:
    """Overlay for a headless tick: every notification is a no-op."""

    def note_clash(self, clash: Any) -> None:
        return None

    def draw_metrics_panel(self, player: Any, hit_stop: float) -> None:
        return None

    def stamp_clash_marker(self, camera: CameraPort) -> None:
        return None

    def update_metrics(self, metrics: Any) -> None:
        return None


class WorldRendererPort(Protocol):
    """Everything the level asks of the renderer, including the debug panels."""

    camera: Any
    overlay: Any
    background_color: Any
    rescale: Any

    def draw(
        self,
        groups: Any,
        debug_enabled: bool,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None: ...

    def draw_health_bars(self, fighters: Any) -> None: ...

    def present(
        self,
        groups: Any,
        *,
        player: Any,
        fps: float,
        frame_time: float,
        alpha: float,
        scene_host: Any,
        spawn_cooldown: float,
        hit_stop: float,
        guard_events: Any,
        last_clash: Any,
        debug_enabled: bool,
    ) -> None: ...

    def set_surface(self, surface: pygame.Surface) -> None: ...

    def set_static_planes(self, static: Any, foreground: Any) -> None: ...

    def set_baked_planes(self, static: Any, foreground: Any) -> None: ...

    def bake_planes(
        self,
        statics: Any,
        foreground: Any,
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[Any, Any]: ...

    def chunk_index(self, sprites: Any) -> Any: ...

    def reconvert_tiles(self, static: Any, foreground: Any) -> None: ...

    def update_metrics(self, metrics: Any) -> None: ...


class NullWorldRenderer:
    """Renderer for headless simulation: no drawing, no display, no assets."""

    def __init__(self) -> None:
        self.camera: CameraPort = NullCamera()
        self.overlay: OverlayPort = NullOverlay()
        self.background_color: Any = None
        self.rescale: Any = 1.0

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

    def present(self, groups: Any, **_kwargs: Any) -> None:
        return None

    def set_surface(self, surface: pygame.Surface) -> None:
        return None

    def set_static_planes(self, static: Any, foreground: Any) -> None:
        return None

    def set_baked_planes(self, static: Any, foreground: Any) -> None:
        return None

    def bake_planes(
        self,
        statics: Any,
        foreground: Any,
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[Any, Any]:
        return None, None

    def chunk_index(self, sprites: Any) -> Any:
        return None

    def reconvert_tiles(self, static: Any, foreground: Any) -> None:
        return None

    def update_metrics(self, metrics: Any) -> None:
        return None


class SnapshotPort(Protocol):
    """A subsystem that can capture and restore its own simulation state."""

    def save_state(self) -> Any: ...

    def load_state(self, state: Any) -> None: ...


class FxPort(Protocol):
    """Render-only effects the fixed tick may ask for, never rules it obeys."""

    def spawn_corpse(self, group: Any, entity: Any) -> None: ...

    def spawn_dash_dust(self, group: Any, entity: Any, *, burst: bool) -> None: ...

    def spawn_dash_grains(self, group: Any, entity: Any, *, burst: bool) -> None: ...

    def spawn_dizzy_stars(self, group: Any, entity: Any, count: int, ttl: float) -> None: ...

    def spawn_dizzy_vortex(self, group: Any, entity: Any) -> None: ...

    def spawn_footstep_dust(self, group: Any, entity: Any, *, foot: Any, tier: Any) -> None: ...

    def spawn_footstep_grains(self, group: Any, entity: Any, *, foot: Any) -> None: ...

    def spawn_guard_arc(self, group: Any, target: Any, *, contact: Any) -> None: ...

    def spawn_impact_decal(self, group: Any, entity: Any, impact: Any) -> None: ...

    def spawn_landing_dust(self, group: Any, entity: Any, impact: Any) -> None: ...

    def spawn_landing_grains(self, group: Any, entity: Any, impact: Any) -> None: ...

    def spawn_sweat_drops(self, group: Any, entity: Any) -> None: ...


class NullFx:
    """Effects for a headless tick: nothing is spawned."""

    def spawn_corpse(self, group: Any, entity: Any) -> None:
        return None

    def spawn_dash_dust(self, group: Any, entity: Any, *, burst: bool) -> None:
        return None

    def spawn_dash_grains(self, group: Any, entity: Any, *, burst: bool) -> None:
        return None

    def spawn_dizzy_stars(self, group: Any, entity: Any, count: int, ttl: float) -> None:
        return None

    def spawn_dizzy_vortex(self, group: Any, entity: Any) -> None:
        return None

    def spawn_footstep_dust(self, group: Any, entity: Any, *, foot: Any, tier: Any) -> None:
        return None

    def spawn_footstep_grains(self, group: Any, entity: Any, *, foot: Any) -> None:
        return None

    def spawn_guard_arc(self, group: Any, target: Any, *, contact: Any) -> None:
        return None

    def spawn_impact_decal(self, group: Any, entity: Any, impact: Any) -> None:
        return None

    def spawn_landing_dust(self, group: Any, entity: Any, impact: Any) -> None:
        return None

    def spawn_landing_grains(self, group: Any, entity: Any, impact: Any) -> None:
        return None

    def spawn_sweat_drops(self, group: Any, entity: Any) -> None:
        return None
