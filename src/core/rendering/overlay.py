"""The world overlay: what the renderer needs from the interface layer.

Why this module exists
----------------------
``core/rendering/renderer.py`` used to ``import UIManager`` and construct one.
That is the wrong way round: ``core`` is the simulation and its drawing, and
``ui`` is the interface, so the arrow between them pointed from the layer that
should know least about presentation to the layer whose whole job is
presentation. The cost was not theoretical. The renderer could not be
instantiated without the interface, could not be drawn without a font cache
and a panel layout, and any test of a frame had to stand up the whole UI to
ask whether a tile was culled.

What replaced it is injection. ``Renderer`` takes a :class:`WorldOverlay` and
is handed one by the application layer, which is allowed to know about both.
:class:`NullOverlay` is the default, so a renderer built without one draws the
world and nothing else -- which is what most of them want, and what makes the
debug overlay a thing you install rather than a thing you cannot switch off.

The Protocol is deliberately narrow: it is the set of calls ``core`` actually
makes, not a mirror of ``UIManager``. The panel layout, the fonts, the compact
layout mode and the panel hit-testing are interface concerns and stayed in
``ui``; the debug panel *drawing* came across because ``core`` is what decides
when it happens, and a port that stops at "the caller knows" would have left
``PanelLayout`` imported in ``core`` -- the violation this is meant to remove.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

import pygame

from src.core.rendering.camera import Camera

__all__ = ["NullOverlay", "WorldOverlay"]


class WorldOverlay(Protocol):
    """The interface drawn over a frame of the world.

    Every method is a no-op obligation on an implementation that has nothing to
    say, so the port can be satisfied by :class:`NullOverlay` without
    pretending the work happened.
    """

    def set_surface(self, surface: pygame.Surface, density: float) -> None:
        """Adopt a new render target, at the density it implies."""

    def set_ui_scale(self, scale: float) -> None:
        """Adopt a new interface scale."""

    def draw_debug_overlays(
        self,
        sprites: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        delta_time: float,
    ) -> None:
        """Draw the world-space debug layer (hitboxes, velocities, labels)."""

    def draw_health_bars(
        self, entities: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> list[pygame.Rect]:
        """Draw the HP bars over the world pass; return the rects they occupy."""

    def draw_debug_panels(self, *, scene_host: Any = None, **counters: Any) -> None:
        """Draw the screen-side debug panels from a bag of counters.

        Keyword-only and untyped because the counters are the debug overlay's
        own vocabulary -- sprite and combat tallies, frame time, hit-stop -- and
        naming a dozen parameters in a port that ``core`` does not read any of
        would be a signature copied for the sake of the copy. The renderer
        measures how long this takes; the overlay decides what to draw.
        """

    def draw_metrics_panel(self, player: Any, hit_stop: float) -> None:
        """Draw the always-on combat metrics readout."""

    def note_clash(self, clash: Any) -> None:
        """Record a clash so the overlay can mark it where it happened."""

    def stamp_clash_marker(self, camera: Camera) -> None:
        """Draw the clash marker again, over the debug panels."""

    def update_metrics(self, metrics: Any) -> None:
        """Feed the contact pipeline's per-tick counters to the overlay."""


class NullOverlay:
    """A :class:`WorldOverlay` that draws nothing.

    The Null Object the codebase already uses elsewhere
    (:class:`~src.states.null_state_machine.NullStateMachine`,
    ``NullCombatComponent``): the alternative is an ``if overlay is not None``
    at every call site in the draw path, which is the thing a port is supposed
    to replace. It is also what makes the default honest -- a renderer with no
    overlay draws the world and no interface, rather than half of one.
    """

    def set_surface(self, surface: pygame.Surface, density: float) -> None:
        """Nothing to re-lay out."""

    def set_ui_scale(self, scale: float) -> None:
        """Nothing to rescale."""

    def draw_debug_overlays(
        self,
        sprites: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        delta_time: float,
    ) -> None:
        """No overlay layer."""

    def draw_health_bars(
        self, entities: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> list[pygame.Rect]:
        """No bars, and therefore no rects."""
        return []

    def draw_debug_panels(self, **counters: Any) -> None:
        """No panels."""

    def draw_metrics_panel(self, player: Any, hit_stop: float) -> None:
        """No metrics readout."""

    def note_clash(self, clash: Any) -> None:
        """No marker to place."""

    def stamp_clash_marker(self, camera: Camera) -> None:
        """No marker to stamp."""

    def update_metrics(self, metrics: Any) -> None:
        """Nothing reads them."""
