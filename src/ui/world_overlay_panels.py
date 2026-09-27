"""Screen-space panels: the COMBAT readout and the world-space clash ring.

Extracted from ``world_ui.py`` as the last step of the split. Unlike the two
drawing passes, none of this is per-sprite work: it is the overlay's
screen-space furniture, and it is the only part that owns state between frames.

**A class, and this one earns it on state rather than on drawing.** Six
attributes live here -- the cached metrics lines, the whiff count, the tick
counter, the assembled panel lines, and the clash point with its remaining
lifetime. Threading those through signatures would be worse than holding them.

**A public attribute on the façade, not six delegating wrappers.** These six
methods are the overlay's API for ``level.py`` and ``ui_manager.py``, so
keeping them on ``WorldUI`` as one-line relays would have meant twelve lines of
pure boilerplate existing only to avoid renaming thirty call sites -- and
boilerplate is exactly what rots unnoticed. ``world_ui.panels.update_metrics``
says which concern it is; ``world_ui.update_metrics`` says nothing once the
concern has moved.
"""

from __future__ import annotations

import pygame

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_WARN
from src.ui.world_overlay_geo import GeoLayer
from src.ui.world_overlay_metrics import (
    CLASH_MARKER_LIFETIME,
    CLASH_TICK_S,
    COMBAT_PANEL_TITLE,
    METRICS_TICK_DIVISOR,
    MetricsCache,
    WorldOverlayMetrics,
)

__all__ = ["PanelLayer"]


class PanelLayer:
    """The COMBAT readout and the clash ring, with their state between frames.

    Constructed once by ``WorldUI`` and kept for the session. Reached as
    ``WorldUI.panels``.
    """

    def __init__(
        self,
        renderer: PanelRenderer,
        metrics: MetricsCache,
        geo: GeoLayer,
    ) -> None:
        self.renderer = renderer
        self._metrics = metrics
        #: Read only, and only for the live attack line. Panels -> geo is the
        #: one direction that edge runs in: a panel reports on a swing, it never
        #: asks the geometry pass to place anything.
        self._geo = geo
        self.metrics_text: tuple[str, ...] = ()
        self._metrics_whiffs = 0
        self._metrics_tick = 0
        #: Colored ``(text, color)`` lines of the unified COMBAT panel,
        #: refreshed by :meth:`draw_metrics_panel`, drawn by the debug flow.
        self.combat_panel_lines: list[tuple[str, Color]] = []
        self.clash_point: tuple[float, float] | None = None
        self._clash_ttl: float = 0.0

    @property
    def surface(self) -> pygame.Surface:
        """The live render target, read through so a resize needs no push."""
        return self.renderer.surface

    @property
    def metrics(self) -> WorldOverlayMetrics:
        """The overlay dimensions for the current density, asked for each time."""
        return self._metrics.current

    def draw_clash_marker(self, camera: Camera, delta_time: float | None = None) -> None:
        """Expanding ring at the last clash point; fades over its lifetime."""
        if self._clash_ttl <= 0.0 or self.clash_point is None:
            return
        self._clash_ttl -= CLASH_TICK_S if delta_time is None else max(0.0, delta_time)
        self.paint_clash_ring(camera)

    def paint_clash_ring(self, camera: Camera) -> None:
        point = self.clash_point
        if point is None:
            return
        anchor = camera.apply(pygame.FRect(point[0] - 1, point[1] - 1, 2, 2))
        center = (round(anchor.centerx), round(anchor.centery))
        progress = 1.0 - self._clash_ttl / CLASH_MARKER_LIFETIME
        radius = round(self.metrics.clash_radius * (0.5 + progress))
        pygame.draw.circle(self.surface, Colors.gold, center, radius, width=2)
        arm = 5
        pygame.draw.line(
            self.surface,
            Colors.white,
            (center[0] - arm, center[1] - arm),
            (center[0] + arm, center[1] + arm),
            width=1,
        )
        pygame.draw.line(
            self.surface,
            Colors.white,
            (center[0] - arm, center[1] + arm),
            (center[0] + arm, center[1] - arm),
            width=1,
        )

    def combat_panel(self) -> tuple[str, list[tuple[str, Color]]] | None:
        """``(title, lines)`` for the debug panel flow, or ``None`` when empty."""
        if not self.combat_panel_lines:
            return None
        return (COMBAT_PANEL_TITLE, self.combat_panel_lines)

    def draw_metrics_panel(
        self,
        metrics: object | None = None,
        player: object | None = None,
        hit_stop: float | None = None,
    ) -> None:
        """Refresh the cached COMBAT lines (drawn later by the debug flow).

        The counters are cached once per metrics tick into
        ``combat_panel_lines`` and blitted with the other screen panels by
        :meth:`UIManager.draw_combat_panel`, so side panels can never stack
        over them. Debug-only: nothing is collected when ``DEBUG`` is off.
        """
        if not Debug.is_enabled():
            return
        if metrics is not None:
            self.update_metrics(metrics)
        if not self.metrics_text:
            return
        lines: list[tuple[str, Color]] = [
            *((line, Colors.off_white) for line in self.metrics_text),
            (f"whiffs {self._metrics_whiffs}", TEXT_MUTED),
        ]
        attack = self._geo.live_attack_text(player)
        if attack is not None:
            lines.append((f"atk {attack}", Colors.gold))
        if hit_stop:
            lines.append((f"hit-stop {hit_stop:.2f}s", TEXT_WARN))
        if self._clash_ttl > 0.0:
            lines.append(("CLASH", TEXT_CRIT))
        self.combat_panel_lines = lines

    def note_clash(self, point: tuple[float, float] | None) -> None:
        """Record a fresh clash point (world px) to flash in the world."""
        if point is not None:
            self.clash_point = point
            self._clash_ttl = CLASH_MARKER_LIFETIME

    def stamp_clash_marker(self, camera: Camera) -> None:
        """Repaint the clash ring after the health bars, without decaying it.

        The health bars paint after the debug overlays; this second stamp
        lands on top of them so a clash ring is never hidden behind a bar.
        """
        if self._clash_ttl <= 0.0 or self.clash_point is None:
            return
        self.paint_clash_ring(camera)

    def update_metrics(self, metrics: object) -> None:
        self._metrics_tick += 1
        if self._metrics_tick % METRICS_TICK_DIVISOR:
            return
        pairs = int(getattr(metrics, "pairs_tested", 0) or 0)
        overlaps = int(getattr(metrics, "overlaps", 0) or 0)
        contacts = int(getattr(metrics, "contacts", 0) or 0)
        self._metrics_whiffs = max(0, pairs - overlaps)
        self.metrics_text = (
            f"pairs {pairs}",
            f"overlaps {overlaps}",
            f"contacts {contacts}",
        )
