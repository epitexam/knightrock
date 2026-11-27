"""Ports that let the simulation run without a window, a mixer or an art cache.

The simulation owns the rules; these ports are the only way it reaches drawing,
assets and camera framing. Every port has a null implementation, so a headless
level can be built and ticked without importing a single presentation module.

The shared kernel may not import the other packages, so objects owned by the
simulation or the presentation layer are deliberately opaque here (``object``
or a narrow structural protocol). The real adapter casts them back to their
concrete types; the null adapter ignores them. This keeps the *shape* of each
call checked without creating a dependency from shared to a layer above it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

import pygame

from src.shared.colors import Color

__all__ = [
    "AssetPort",
    "CameraPort",
    "FrameContext",
    "FxPort",
    "NullAssetPort",
    "NullCamera",
    "NullFx",
    "NullOverlay",
    "NullWorldRenderer",
    "OverlayPort",
    "RenderGroups",
    "SnapshotPort",
    "SpriteLike",
    "WorldRendererPort",
]


class AssetPort(Protocol):
    """Surface source for animations and art-driven world objects."""

    generation: int

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

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None: ...

    def hold(self, delta_time: float) -> None: ...

    def add_trauma(self, amount: float) -> None: ...


class NullCamera:
    """Camera for a headless tick: framing exists, but nothing is drawn."""

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        return None

    def hold(self, delta_time: float) -> None:
        return None

    def add_trauma(self, amount: float) -> None:
        return None


class OverlayPort(Protocol):
    """What the level tells the debug overlay during a frame."""

    def note_clash(self, clash: object | None) -> None: ...

    def draw_metrics_panel(self, player: object, hit_stop: float) -> None: ...

    def stamp_clash_marker(self, camera: CameraPort) -> None: ...

    def update_metrics(self, metrics: object) -> None: ...


class NullOverlay:
    """Overlay for a headless tick: every notification is a no-op."""

    def note_clash(self, clash: object | None) -> None:
        return None

    def draw_metrics_panel(self, player: object, hit_stop: float) -> None:
        return None

    def stamp_clash_marker(self, camera: CameraPort) -> None:
        return None

    def update_metrics(self, metrics: object) -> None:
        return None


class SpriteLike(Protocol):
    """The only thing the renderer needs from a frozen plane's sprite."""

    image: pygame.Surface | None


class RenderGroups(Protocol):
    """The sprite planes a frame needs, read-only from the simulation's side."""

    @property
    def all_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def static_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def fg_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def fx_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def projectile_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def presentation_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def entity_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def combat_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...

    @property
    def collision_sprites(self) -> Iterable[pygame.sprite.Sprite]: ...


@dataclass(frozen=True)
class FrameContext:
    """One frame's presentation inputs, owned by the level and read by the adapter.

    Player, host, events and metrics are opaque here: their concrete types
    belong to layers that ``shared`` may not import. The adapter knows them.
    """

    player: object
    fps: float
    frame_time: float
    alpha: float
    scene_host: object | None
    spawn_cooldown: float
    hit_stop: float
    guard_events: Iterable[object]
    last_clash: object | None
    debug_enabled: bool


class WorldRendererPort(Protocol):
    """Everything the level asks of the renderer, including the debug panels."""

    camera: CameraPort
    overlay: OverlayPort
    background_color: Color
    rescale: Callable[[pygame.Surface], pygame.Surface]

    def draw(
        self,
        groups: RenderGroups,
        debug_enabled: bool,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None: ...

    def draw_health_bars(
        self, fighters: Iterable[pygame.sprite.Sprite]
    ) -> list[pygame.Rect] | None: ...

    def present(self, groups: RenderGroups, context: FrameContext) -> None: ...

    def set_surface(self, surface: pygame.Surface) -> None: ...

    def set_static_planes(self, static: object | None, foreground: object | None) -> None: ...

    def set_baked_planes(self, static: object | None, foreground: object | None) -> None: ...

    def bake_planes(
        self,
        statics: Iterable[SpriteLike],
        foreground: Iterable[SpriteLike],
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[object | None, object | None]: ...

    def chunk_index(self, sprites: Iterable[SpriteLike]) -> object | None: ...

    def reconvert_tiles(
        self, static: Iterable[SpriteLike], foreground: Iterable[SpriteLike]
    ) -> None: ...

    def update_metrics(self, metrics: object) -> None: ...


class NullWorldRenderer:
    """Renderer for headless simulation: no drawing, no display, no assets."""

    def __init__(self) -> None:
        self.camera: CameraPort = NullCamera()
        self.overlay: OverlayPort = NullOverlay()
        self.background_color: Color = (0, 0, 0)
        self.rescale: Callable[[pygame.Surface], pygame.Surface] = lambda image: image

    def draw(
        self,
        groups: RenderGroups,
        debug_enabled: bool,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        return None

    def draw_health_bars(
        self, fighters: Iterable[pygame.sprite.Sprite]
    ) -> list[pygame.Rect] | None:
        return None

    def present(self, groups: RenderGroups, context: FrameContext) -> None:
        return None

    def set_surface(self, surface: pygame.Surface) -> None:
        return None

    def set_static_planes(self, static: object | None, foreground: object | None) -> None:
        return None

    def set_baked_planes(self, static: object | None, foreground: object | None) -> None:
        return None

    def bake_planes(
        self,
        statics: Iterable[SpriteLike],
        foreground: Iterable[SpriteLike],
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[object | None, object | None]:
        return None, None

    def chunk_index(self, sprites: Iterable[SpriteLike]) -> object | None:
        return None

    def reconvert_tiles(
        self, static: Iterable[SpriteLike], foreground: Iterable[SpriteLike]
    ) -> None:
        return None

    def update_metrics(self, metrics: object) -> None:
        return None


class SnapshotPort(Protocol):
    """A subsystem that can capture and restore its own simulation state."""

    def save_state(self) -> object: ...

    def load_state(self, state: object) -> None: ...


class FxPort(Protocol):
    """Render-only effects the fixed tick may ask for, never rules it obeys."""

    def spawn_corpse(self, group: pygame.sprite.Group, entity: object) -> None: ...

    def spawn_dash_dust(
        self, group: pygame.sprite.Group, entity: object, *, burst: bool
    ) -> None: ...

    def spawn_dash_grains(
        self, group: pygame.sprite.Group, entity: object, *, burst: bool
    ) -> None: ...

    def spawn_dizzy_stars(
        self,
        group: pygame.sprite.Group,
        entity: object,
        count: int,
        ttl: float,
    ) -> None: ...

    def spawn_dizzy_vortex(self, group: pygame.sprite.Group, entity: object) -> None: ...

    def spawn_footstep_dust(
        self,
        group: pygame.sprite.Group,
        entity: object,
        *,
        foot: bool,
        tier: object,
    ) -> None: ...

    def spawn_footstep_grains(
        self, group: pygame.sprite.Group, entity: object, *, foot: bool
    ) -> None: ...

    def spawn_guard_arc(
        self, group: pygame.sprite.Group, target: object, *, contact: object
    ) -> None: ...

    def spawn_impact_decal(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None: ...

    def spawn_landing_dust(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None: ...

    def spawn_landing_grains(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None: ...

    def spawn_sweat_drops(self, group: pygame.sprite.Group, entity: object) -> None: ...


class NullFx:
    """Effects for a headless tick: nothing is spawned."""

    def spawn_corpse(self, group: pygame.sprite.Group, entity: object) -> None:
        return None

    def spawn_dash_dust(self, group: pygame.sprite.Group, entity: object, *, burst: bool) -> None:
        return None

    def spawn_dash_grains(self, group: pygame.sprite.Group, entity: object, *, burst: bool) -> None:
        return None

    def spawn_dizzy_stars(
        self,
        group: pygame.sprite.Group,
        entity: object,
        count: int,
        ttl: float,
    ) -> None:
        return None

    def spawn_dizzy_vortex(self, group: pygame.sprite.Group, entity: object) -> None:
        return None

    def spawn_footstep_dust(
        self,
        group: pygame.sprite.Group,
        entity: object,
        *,
        foot: bool,
        tier: object,
    ) -> None:
        return None

    def spawn_footstep_grains(
        self, group: pygame.sprite.Group, entity: object, *, foot: bool
    ) -> None:
        return None

    def spawn_guard_arc(
        self, group: pygame.sprite.Group, target: object, *, contact: object
    ) -> None:
        return None

    def spawn_impact_decal(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None:
        return None

    def spawn_landing_dust(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None:
        return None

    def spawn_landing_grains(
        self, group: pygame.sprite.Group, entity: object, impact: object
    ) -> None:
        return None

    def spawn_sweat_drops(self, group: pygame.sprite.Group, entity: object) -> None:
        return None
