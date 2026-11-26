"""The presentation implementation of the simulation's rendering ports.

``Level`` never imports this module: the composition root builds the adapter
and injects it. A headless caller injects ``NullWorldRenderer`` instead and no
presentation module is ever loaded.

The shared ports deliberately carry ``object`` where a value belongs to a
layer ``shared`` may not import. The casts here are the price of that boundary:
they are local, explicit and checked at the point where the concrete type is
known.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import cast

import pygame

from src.presentation.rendering.camera import Camera
from src.presentation.rendering.overlay import WorldOverlay
from src.presentation.rendering.renderer import Renderer
from src.presentation.rendering.static_layer import (
    BakedStaticLayer,
    _FrozenSprite,
    bake_static_layer,
)
from src.presentation.rendering.tile_chunk_index import TileChunkIndex
from src.shared.colors import Color
from src.shared.contracts import (
    CameraPort,
    FrameContext,
    OverlayPort,
    RenderGroups,
    SpriteLike,
)
from src.simulation.ecs.presentation import PresentationSprite
from src.simulation.level.level_data import LevelConfig
from src.simulation.level.scene_host import SceneHost
from src.simulation.level.systems.contact_system import GuardEvent
from src.simulation.settings import Debug
from src.simulation.sprite_groups import SpriteGroups

__all__ = ["PresentationRenderer", "build_presentation_renderer"]


class _OverlayAdapter:
    """Bind the overlay to the real camera; expose only the shared port."""

    def __init__(self, overlay: WorldOverlay, camera: Camera) -> None:
        self._overlay = overlay
        self._camera = camera

    @property
    def real(self) -> WorldOverlay:
        """The wrapped overlay, for tools and tests that inspect it."""
        return self._overlay

    def __getattr__(self, name: str) -> object:
        return getattr(self._overlay, name)

    def note_clash(self, clash: object | None) -> None:
        self._overlay.note_clash(clash)

    def draw_metrics_panel(self, player: object, hit_stop: float) -> None:
        self._overlay.draw_metrics_panel(player, hit_stop)

    def stamp_clash_marker(self, camera: CameraPort) -> None:
        self._overlay.stamp_clash_marker(self._camera)

    def update_metrics(self, metrics: object) -> None:
        self._overlay.update_metrics(metrics)


class PresentationRenderer:
    """Adapter around ``Renderer`` implementing ``WorldRendererPort``.

    Attribute access not declared by the port falls through to the wrapped
    renderer, so tools and tests that inspect renderer internals keep working
    without the simulation knowing those names exist.
    """

    def __init__(self, renderer: Renderer, camera: Camera) -> None:
        self._renderer = renderer
        self._camera = camera
        self.camera: CameraPort = camera
        self.overlay: OverlayPort = _OverlayAdapter(renderer.overlay, camera)
        self.background_color: Color = renderer.background_color
        self.rescale: Callable[[pygame.Surface], pygame.Surface] = renderer.rescale

    def __getattr__(self, name: str) -> object:
        return getattr(self._renderer, name)

    def draw(
        self,
        groups: RenderGroups,
        debug_enabled: bool = False,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        self._renderer.draw(cast("SpriteGroups", groups), debug_enabled, dt=dt, alpha=alpha)

    def draw_health_bars(self, fighters: Iterable[pygame.sprite.Sprite]) -> list[pygame.Rect]:
        return self._renderer.draw_health_bars(fighters)

    def present(self, groups: RenderGroups, context: FrameContext) -> None:
        real_groups = cast("SpriteGroups", groups)
        self.draw(
            real_groups, context.debug_enabled, dt=context.frame_time / 1000.0, alpha=context.alpha
        )
        self.draw_health_bars(real_groups.entity_sprites)
        for event in cast("Iterable[GuardEvent]", context.guard_events):
            if event.kind == "clash":
                self.overlay.note_clash(context.last_clash)
        self.overlay.draw_metrics_panel(context.player, context.hit_stop)
        if not context.debug_enabled:
            return
        self.overlay.stamp_clash_marker(self.camera)
        self._renderer.draw_debug_panels(
            player=context.player,
            fps=context.fps,
            sprite_count=len(real_groups.static_sprites)
            + len(real_groups.all_sprites)
            + len(real_groups.fg_sprites),
            combat_count=len(real_groups.combat_sprites),
            entity_count=len(real_groups.entity_sprites),
            collision_count=len(real_groups.collision_sprites),
            hit_stop=context.hit_stop,
            spawn_cooldown=context.spawn_cooldown,
            scene_host=cast("SceneHost | None", context.scene_host),
            frame_time=context.frame_time,
        )

    def set_surface(self, surface: pygame.Surface) -> None:
        self._renderer.set_surface(surface)

    def set_static_planes(self, static: object | None, foreground: object | None) -> None:
        self._renderer.set_static_planes(
            cast("TileChunkIndex | None", static), cast("TileChunkIndex | None", foreground)
        )

    def set_baked_planes(self, static: object | None, foreground: object | None) -> None:
        self._renderer.set_baked_planes(
            cast("BakedStaticLayer | None", static),
            cast("BakedStaticLayer | None", foreground),
        )

    def bake_planes(
        self,
        statics: Iterable[SpriteLike],
        foreground: Iterable[SpriteLike],
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[BakedStaticLayer | None, BakedStaticLayer | None]:
        def bake(sprites: Iterable[SpriteLike]) -> BakedStaticLayer | None:
            return bake_static_layer(
                cast("Iterable[_FrozenSprite]", sprites),
                size=size,
                density=self._camera.density,
                background=self.background_color,
                scale=self.rescale,
                enabled=enabled,
            )

        return bake(statics), bake(foreground)

    def chunk_index(self, sprites: Iterable[SpriteLike]) -> TileChunkIndex | None:
        if not sprites:
            return None
        return TileChunkIndex(cast("Iterable[PresentationSprite]", sprites))

    def reconvert_tiles(
        self, static: Iterable[SpriteLike], foreground: Iterable[SpriteLike]
    ) -> None:
        if pygame.display.get_surface() is None:
            return
        for sprite in (*static, *foreground):
            image = sprite.image
            if image is None:
                continue
            if image.get_flags() & pygame.SRCALPHA:
                sprite.image = image.convert_alpha()
            else:
                sprite.image = image.convert()

    def update_metrics(self, metrics: object) -> None:
        self.overlay.update_metrics(metrics)


def build_presentation_renderer(
    surface: pygame.Surface,
    config: LevelConfig | None,
    overlay: WorldOverlay | None = None,
    camera: Camera | None = None,
) -> PresentationRenderer:
    """Build the real adapter from a render target and level config."""
    selected = camera if camera is not None else Camera.for_target(surface)
    renderer = Renderer(surface, selected, config, overlay)
    return PresentationRenderer(renderer, selected)


def debug_enabled() -> bool:
    """Single read of the DEBUG setting for the composition root."""
    return Debug.is_enabled()
