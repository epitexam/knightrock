"""The presentation implementation of the simulation's rendering ports.

``Level`` never imports this module: the composition root builds the adapter
and injects it. A headless caller injects ``NullWorldRenderer`` instead and no
presentation module is ever loaded.
"""

from __future__ import annotations

from typing import Any

import pygame

from src.presentation.rendering.camera import Camera
from src.presentation.rendering.renderer import Renderer
from src.presentation.rendering.static_layer import BakedStaticLayer, bake_static_layer
from src.presentation.rendering.tile_chunk_index import TileChunkIndex
from src.simulation.settings import Debug

__all__ = ["PresentationRenderer", "build_presentation_renderer"]


class PresentationRenderer:
    """Adapter around ``Renderer`` implementing ``WorldRendererPort``.

    Attribute access not declared by the port falls through to the wrapped
    renderer, so tools and tests that inspect renderer internals keep working
    without the simulation knowing those names exist.
    """

    def __init__(self, renderer: Renderer, camera: Camera) -> None:
        self._renderer = renderer
        self.camera = camera
        self.overlay = renderer.overlay
        self.background_color = renderer.background_color
        self.rescale = renderer.rescale

    def __getattr__(self, name: str) -> Any:
        return getattr(self._renderer, name)

    def draw(
        self,
        groups: Any,
        debug_enabled: bool = False,
        *,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        self._renderer.draw(groups, debug_enabled, dt=dt, alpha=alpha)

    def draw_health_bars(self, fighters: Any) -> Any:
        return self._renderer.draw_health_bars(fighters)

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
    ) -> None:
        self.draw(groups, debug_enabled, dt=frame_time / 1000.0, alpha=alpha)
        self.draw_health_bars(groups.entity_sprites)
        for event in guard_events:
            if event.kind == "clash":
                self.overlay.note_clash(last_clash)
        self.overlay.draw_metrics_panel(player=player, hit_stop=hit_stop)
        if not debug_enabled:
            return
        self.overlay.stamp_clash_marker(self.camera)
        self._renderer.draw_debug_panels(
            player=player,
            fps=fps,
            sprite_count=len(groups.static_sprites)
            + len(groups.all_sprites)
            + len(groups.fg_sprites),
            combat_count=len(groups.combat_sprites),
            entity_count=len(groups.entity_sprites),
            collision_count=len(groups.collision_sprites),
            hit_stop=hit_stop,
            spawn_cooldown=spawn_cooldown,
            scene_host=scene_host,
            frame_time=frame_time,
        )

    def set_surface(self, surface: pygame.Surface) -> None:
        self._renderer.set_surface(surface)

    def set_static_planes(self, static: Any, foreground: Any) -> None:
        self._renderer.set_static_planes(static, foreground)

    def set_baked_planes(self, static: Any, foreground: Any) -> None:
        self._renderer.set_baked_planes(static, foreground)

    def bake_planes(
        self,
        statics: Any,
        foreground: Any,
        size: tuple[float, float],
        enabled: bool | None,
    ) -> tuple[BakedStaticLayer | None, BakedStaticLayer | None]:
        def bake(sprites: Any) -> BakedStaticLayer | None:
            return bake_static_layer(
                sprites,
                size=size,
                density=self.camera.density,
                background=self.background_color,
                scale=self.rescale,
                enabled=enabled,
            )

        return bake(statics), bake(foreground)

    def chunk_index(self, sprites: Any) -> TileChunkIndex | None:
        return TileChunkIndex(sprites) if sprites else None

    def reconvert_tiles(self, static: Any, foreground: Any) -> None:
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

    def update_metrics(self, metrics: Any) -> None:
        self.overlay.update_metrics(metrics)


def build_presentation_renderer(
    surface: pygame.Surface,
    config: Any,
    overlay: Any = None,
    camera: Camera | None = None,
) -> PresentationRenderer:
    """Build the real adapter from a render target and level config."""
    selected = camera if camera is not None else Camera.for_target(surface)
    renderer = Renderer(surface, selected, config, overlay)
    return PresentationRenderer(renderer, selected)


def debug_enabled() -> bool:
    """Single read of the DEBUG setting for the composition root."""
    return Debug.is_enabled()
