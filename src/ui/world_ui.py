"""The world overlay's facade: one frame of world-space drawing, in order.

Two passes over the same sprite list. The producer draws the geometry and
registers the screen space it took (`world_overlay_geo`); the consumer then
places one label card per sprite around it (`world_overlay_cards`). That order
is the contract -- a card that knew about a tier before the box pass drew it
would dodge nothing -- so it is expressed here and nowhere else.

What stays on the facade is what has to: the layer toggles, the frame loop, the
dimensions (`world_overlay_metrics`), the health bars (`world_overlay_bars`),
and the screen panels (`world_overlay_panels`).

The bars went first, and on their own argument rather than their size.
`Level.draw` calls them *before* it checks `DEBUG`, so they are painted on every
frame of a real game while everything else here sits behind `F1`. A production
path inside a debug module is the arrangement that decays quietly: it gets
reviewed with the debug layer's eye, and its tests get counted against the debug
layer's coverage.

Every dimension is in world units and multiplied by the pixel density exactly
once, in `WorldOverlayMetrics`. They used to be module constants here,
interleaved with the drawing, which is the worst of both: a constant that only
matters to the label placer is invisible while you are reading the box drawer.

This module re-exports no dimension. It used to: a 61-name `import (...)` from
`world_overlay_metrics` marked `# noqa: F401`, of which exactly two names had a
caller in `src` and the rest were read only by the test that asserted the
re-export existed. Every layer imports the dimensions it uses from
`world_overlay_metrics` directly, and so does `ui_manager`."""

from collections.abc import Iterable

import pygame

from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_bars import (
    draw_health_bars as _draw_health_bars,
)
from src.ui.world_overlay_bars import (
    health_bar_rect as _health_bar_rect,
)
from src.ui.world_overlay_cards import CardLayer, LabelRequest
from src.ui.world_overlay_geo import GeoLayer
from src.ui.world_overlay_metrics import OVERLAY_LAYERS, MetricsCache, WorldOverlayMetrics
from src.ui.world_overlay_panels import PanelLayer
from src.ui.world_overlay_shared import (
    AnnotationSink,
    debug_reference,
)


class WorldUI:
    """Render health bars and optional world-space diagnostics.

    Every dimension here is written in **world units** and multiplied by the
    target's pixel density at paint time, through :meth:`px` and :meth:`stroke`.
    That distinction is the whole reason this layer is legible: the rectangles
    come from ``camera.apply``, which scales, while the *widths*, *paddings* and
    *gaps* used to be handed to pygame raw -- so on a window where the world is
    drawn 1.9x larger, a 1px hitbox outline landed at 53% of its weight and the
    overlay read as "F1 does nothing". A tool that cannot be seen is a tool
    that is broken.
    """

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        # ``statics`` starts off: a level carries ~840 terrain tiles whose
        # outline tells you nothing, and drawing them is the single most
        # expensive thing the overlay does. Measured on level 0 at 1280x720
        # with DEBUG=1, the whole overlay pass goes from 1.98 ms to 0.09 ms
        # when the layer is off -- 1.9 ms of a 16.7 ms budget for a picture
        # of the tileset. F4 brings the layer back.
        self.layers: dict[str, bool] = {name: name != "statics" for name in OVERLAY_LAYERS}
        #: Attack annotation rects drawn this frame, keyed by sprite id. The
        #: box pass writes them, the card pass reads them, and the sink is what
        #: makes that one-way; see ``world_overlay_shared.AnnotationSink``.
        self._sink = AnnotationSink()
        self._metrics_cache = MetricsCache(self.renderer)
        #: Producer half of the frame: the sprite geometry and the tiers drawn
        #: above it. Built once, and reads the surface and the metrics live so a
        #: resize needs no push.
        self._geo = GeoLayer(self.renderer, self._metrics_cache, self._sink)
        #: Consumer half of the frame: one label card per sprite, placed around
        #: what the box pass just claimed. Built once, and reads the surface and
        #: the metrics live so a resize needs no push.
        self._cards = CardLayer(self.renderer, self._metrics_cache, self._sink, self.layers)
        #: Screen-space furniture: the COMBAT readout and the clash ring, with
        #: the state they keep between frames. Public, because ``level.py`` and
        #: ``ui_manager.py`` drive it directly.
        self.panels = PanelLayer(self.renderer, self._metrics_cache, self._geo)

    @property
    def annotation_rects(self) -> dict[int, list[pygame.Rect]]:
        """This frame's annotations, keyed by sprite id."""
        return self._sink.rects

    @property
    def annotation_obstacles(self) -> list[pygame.Rect]:
        """This frame's annotation rects, flattened, in draw order."""
        return self._sink.obstacles

    @property
    def metrics(self) -> WorldOverlayMetrics:
        """The overlay dimensions for the current density, rebuilt when it moves.

        Cached on the scale, so a static window costs one identity comparison per
        frame and a resize costs one table.
        """
        return self._metrics_cache.current

    def toggle(self, layer: str) -> bool:
        """Flip an overlay layer, returning its new state."""
        if layer not in self.layers:
            raise KeyError(f"Unknown overlay layer: {layer!r}")
        self.layers[layer] = not self.layers[layer]
        return self.layers[layer]

    def draw_debug_overlays(
        self,
        all_sprites: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        delta_time: float | None = None,
    ) -> None:
        # Fresh annotation bookkeeping: the rects drawn this frame feed both
        # the card obstacles and the card clearances.
        self._sink.clear()
        if not any(self.layers[name] for name in ("boxes", "labels", "velocities", "statics")):
            return
        screen_width = self.surface.get_width()

        # Labels are collected first and drawn after the loop so they can
        # dodge each other instead of stacking on shared screen space.
        requests: list[LabelRequest] = []
        for sprite in all_sprites:
            # Terrain tiles are ~840 of a level's sprites and have no hitbox,
            # no combat state and no velocity, so `is_static` below is the
            # gate that keeps the overlay cheap: `debug_reference` builds one
            # to three FRects per call, and the `statics` toggle skips all of
            # it for them.
            #
            # There used to be an exact-type test above this one, skipped on
            # the theory that it would catch the tiles for free. It never
            # matched anything: the tiles are `src.core.sprites.Sprite`, a
            # *subclass* of `pygame.sprite.Sprite`, so `type(sprite) is
            # pygame.sprite.Sprite` was false for every one of them and each
            # tile paid for a check that bought nothing. `is_static` is the
            # real test and it is the one below.
            is_static = getattr(sprite, "hitbox", None) is None
            if is_static and not self.layers["statics"]:
                continue
            reference = debug_reference(sprite)
            if reference is None or not camera.is_visible(reference):
                continue  # culled: off-screen, not worth a single pixel
            if self.layers["boxes"]:
                self._geo.draw_boxes(sprite, camera)
            if self.layers["velocities"]:
                self._geo.velocity.draw_velocity(sprite, camera)
            request = self._cards.label_request(sprite, reference, is_static, camera)
            if request is not None:
                requests.append(request)

        if requests:
            requests.sort(key=lambda request: request[0])
            self._cards.draw_labels(requests, screen_width, self.surface.get_height())

        self.panels.draw_clash_marker(camera, delta_time)

    @property
    def surface(self) -> pygame.Surface:
        """The surface this overlay draws into.

        Derived rather than copied at construction. It used to be assigned once,
        and every path that replaced the render target had to remember to
        reassign it -- one that forgot would have the overlay drawing into an
        orphaned surface while the rest of the frame went to the new one, with
        no symptom until the two sizes differ.
        """
        return self.renderer.surface

    # -- health bars ----------------------------------------------------------
    #
    # Delegated to `src/ui/world_overlay_bars.py`, which holds the real
    # implementation. `draw_health_bars` stays on the facade because the
    # renderer reaches the draw pass through the overlay port under that name,
    # and the bars are the one part of this file that is **not** debug-only:
    # `Level.draw` calls them before it checks `DEBUG`, so they are painted on
    # every frame of a real game. They were worth not sharing a module with
    # 1800 lines of F1-layer drawing.
    #
    # `_health_bar_rect` is the one exception to "callers use the bars module
    # directly": the card placer needs the bar of a sprite it already holds, and
    # routing that through the facade keeps `surface` in one place.

    def _health_bar_rect(
        self, sprite: pygame.sprite.Sprite, screen_rect: pygame.Rect | pygame.FRect
    ) -> pygame.Rect | None:
        """Where this sprite's bar sits, or None when it has none."""
        return _health_bar_rect(self.surface, sprite, screen_rect)

    def draw_health_bars(
        self,
        entities: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        screen_rects: dict[int, pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Draw the always-on HP bars; return the rects they occupy."""
        return _draw_health_bars(self.surface, entities, camera, screen_rects)
