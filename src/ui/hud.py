"""Always-on player HUD: health, guard posture, dash charges and combo.

Unlike the F1-F7 debug panels this overlay is **not** gated by
``Debug.is_enabled()`` (audit UI-7): it is what the player reads while
fighting. Everything is read-only and screen-anchored — health and guard
posture sit in the bottom-left corner, dash charges and the combo counter
in the bottom-right one — and the bar width follows the display width, so
the HUD stays readable from the windowed resolutions of the video settings
(audit UI-6).

Wired from ``GameplayScene.draw`` after ``level.draw()`` (decision D9):
neither ``src/core/level/level.py`` nor ``src/core/rendering/renderer.py``
is touched. ``HUD.draw`` hands back the rects it painted (plus last frame's)
so the dirty-rect presentation of a non-debug frame still shows the gauges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from src.core.colors import Color, Colors
from src.core.settings import Combat
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN

#: HUD geometry (px). The bar width is proportional to the display, within
#: these bounds, so the same HUD reads the same at 1280x720 and 1920x1080.
HUD_MARGIN = 20
HUD_BAR_HEIGHT = 14
HUD_BAR_GAP = 8
HUD_BAR_WIDTH_RATIO = 0.22
HUD_BAR_WIDTH_MIN = 140
HUD_BAR_WIDTH_MAX = 360
HUD_LABEL_GAP = 8
HUD_PIP_SIZE = 14
HUD_PIP_GAP = 5
HUD_COMBO_BAR_HEIGHT = 6
HUD_COMBO_BAR_GAP = 4

#: Track color of every gauge (same dark grey as the entity health bars).
HUD_TRACK = (35, 37, 40)
#: Dash charges read as an energy resource: the gameplay palette cyan-blue.
HUD_DASH_COLOR: Color = Colors.sky_blue
#: Combo counter: amber, the same accent as a warning-free "charged" gauge.
HUD_COMBO_COLOR: Color = TEXT_WARN

#: Labels drawn left of the two bars, right-aligned in a shared gutter.
HUD_BAR_LABELS = ("HP", "GRD")


def health_color(ratio: float) -> Color:
    """Green above 50%, amber above 25%, red below (debug panel thresholds)."""
    if ratio > 0.5:
        return TEXT_OK
    if ratio > 0.25:
        return TEXT_WARN
    return TEXT_CRIT


def posture_color(ratio: float, lockout_timer: float = 0.0) -> Color:
    """Guard gauge: red while the guard is locked out, amber at 30% or less."""
    if lockout_timer > 0:
        return TEXT_CRIT
    if ratio <= 0.3:
        return TEXT_WARN
    return TEXT_OK


def bar_width_for(display_width: int) -> int:
    """HUD bar width for a display: proportional, bounded and always fitting."""
    scaled = int(display_width * HUD_BAR_WIDTH_RATIO)
    width = max(HUD_BAR_WIDTH_MIN, min(HUD_BAR_WIDTH_MAX, scaled))
    return max(1, min(width, display_width - 2 * HUD_MARGIN))


def _ratio(value: float, maximum: float) -> float:
    """Clamped ``value / maximum``; a missing maximum reads as empty."""
    if not maximum:
        return 0.0
    return max(0.0, min(1.0, value / maximum))


def _fill(bar: pygame.Rect, ratio: float) -> pygame.Rect:
    """Left-anchored portion of ``bar`` covered by ``ratio``."""
    return pygame.Rect(bar.x, bar.y, int(bar.width * ratio), bar.height)


@dataclass(frozen=True)
class HudLayout:
    """Resolved geometry and colors of one HUD frame.

    Kept apart from the drawing so the HUD can be asserted on state and
    resolved colors (audit UI-7 acceptance) instead of on pixels.
    """

    health_bar: pygame.Rect
    health_fill: pygame.Rect
    health_color: Color
    posture_bar: pygame.Rect
    posture_fill: pygame.Rect
    posture_color: Color
    dash_pips: tuple[tuple[pygame.Rect, bool], ...]
    combo_text: str
    combo_pos: tuple[int, int] | None
    combo_bar: pygame.Rect | None
    combo_fill: pygame.Rect | None


class HUD:
    """Always-on player gauges, anchored to the display's bottom corners."""

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        #: HUD rects painted last frame: presented again so a gauge that
        #: shrinks (or a combo that expires) does not leave stale pixels.
        self._previous_dirty: list[pygame.Rect] = []

    def layout(self, player: Any) -> HudLayout | None:
        """Compute the frame's rects and colors without drawing anything."""
        if not player:
            return None

        screen_w, screen_h = self.renderer.display_surface.get_size()
        bar_w = bar_width_for(screen_w)
        health_ratio = _ratio(getattr(player, "health", 0.0), getattr(player, "max_health", 0.0))
        posture_ratio = _ratio(
            getattr(player, "guard_posture", 0.0), getattr(player, "guard_posture_max", 0.0)
        )

        # Both bars share a label gutter so they start on the same x.
        label_w = max(
            self.renderer.render_text(label, self.renderer.label_font, TEXT_MUTED).get_width()
            for label in HUD_BAR_LABELS
        )
        bar_x = HUD_MARGIN + label_w + HUD_LABEL_GAP
        health_y = screen_h - HUD_MARGIN - HUD_BAR_HEIGHT
        posture_y = health_y - HUD_BAR_GAP - HUD_BAR_HEIGHT

        health_bar = pygame.Rect(bar_x, health_y, bar_w, HUD_BAR_HEIGHT)
        posture_bar = pygame.Rect(bar_x, posture_y, bar_w, HUD_BAR_HEIGHT)

        pips = self._dash_pips(player, screen_w, screen_h)
        combo_text, combo_pos, combo_bar, combo_fill = self._combo(
            player, (screen_w, screen_h), pips
        )

        return HudLayout(
            health_bar=health_bar,
            health_fill=_fill(health_bar, health_ratio),
            health_color=health_color(health_ratio),
            posture_bar=posture_bar,
            posture_fill=_fill(posture_bar, posture_ratio),
            posture_color=posture_color(posture_ratio, getattr(player, "guard_lockout_timer", 0.0)),
            dash_pips=pips,
            combo_text=combo_text,
            combo_pos=combo_pos,
            combo_bar=combo_bar,
            combo_fill=combo_fill,
        )

    def _dash_pips(
        self, player: Any, screen_w: int, screen_h: int
    ) -> tuple[tuple[pygame.Rect, bool], ...]:
        """Right-anchored pip row, read left-to-right, filled from the left.

        The row is right-anchored (stable against the screen edge whatever
        the charge count) but fills like the health bars: the charges left
        are the leftmost, full slots.
        """
        total = max(0, int(getattr(player, "max_dash_charges", 0) or 0))
        filled = max(0, min(total, int(getattr(player, "dash_charges", 0) or 0)))
        y = screen_h - HUD_MARGIN - HUD_PIP_SIZE
        left = screen_w - HUD_MARGIN - total * HUD_PIP_SIZE - (total - 1) * HUD_PIP_GAP

        return tuple(
            (
                pygame.Rect(
                    left + index * (HUD_PIP_SIZE + HUD_PIP_GAP), y, HUD_PIP_SIZE, HUD_PIP_SIZE
                ),
                index < filled,
            )
            for index in range(total)
        )

    def _combo(
        self,
        player: Any,
        screen: tuple[int, int],
        pips: tuple[tuple[pygame.Rect, bool], ...],
    ) -> tuple[str, tuple[int, int] | None, pygame.Rect | None, pygame.Rect | None]:
        """``xN`` counter and its decay bar above the dash row; hidden at 0."""
        combat = getattr(player, "combat", None)
        count = int(getattr(combat, "combo_count", 0) or 0)
        if count <= 0:
            return "", None, None, None

        screen_w, screen_h = screen
        text = f"x{count}"
        text_surf = self.renderer.render_text(text, self.renderer.label_font, HUD_COMBO_COLOR)
        top_of_pips = min((rect.top for rect, _ in pips), default=screen_h - HUD_MARGIN)

        bar = pygame.Rect(
            screen_w - HUD_MARGIN - text_surf.get_width(),
            top_of_pips - HUD_COMBO_BAR_GAP - HUD_COMBO_BAR_HEIGHT,
            text_surf.get_width(),
            HUD_COMBO_BAR_HEIGHT,
        )
        text_pos = (bar.x, bar.y - HUD_COMBO_BAR_GAP - text_surf.get_height())
        ratio = _ratio(getattr(combat, "combo_timer", 0.0), Combat.COMBO_WINDOW)
        return text, text_pos, bar, _fill(bar, ratio)

    def draw(self, player: Any) -> list[pygame.Rect]:
        """Paint the gauges for ``player``; a missing player draws nothing.

        Returns the rects to present, like ``Renderer.draw`` does: the
        gameplay loop presents dirty rects only, so the HUD has to hand its
        own area over — plus last frame's, or a gauge that shrinks or a combo
        that expires would leave its old pixels on screen.
        """
        layout = self.layout(player)
        if layout is None:
            # No player: the gauges are gone, so hand last frame's area back
            # for one last refresh instead of freezing its stale pixels.
            stale, self._previous_dirty = self._previous_dirty, []
            return stale

        painted = self._paint(layout)
        rects = [*painted, *self._previous_dirty]
        self._previous_dirty = painted
        return rects

    def _paint(self, layout: HudLayout) -> list[pygame.Rect]:
        """Draw one frame's HUD and collect the rects it touched."""
        painted = [
            self._draw_bar(layout.health_bar, layout.health_fill, layout.health_color, "HP"),
            self._draw_bar(layout.posture_bar, layout.posture_fill, layout.posture_color, "GRD"),
            *self._draw_pips(layout.dash_pips),
        ]

        if layout.combo_pos is None or layout.combo_bar is None or layout.combo_fill is None:
            return painted

        surface = self.renderer.display_surface
        combo_text = self.renderer.render_text(
            layout.combo_text, self.renderer.label_font, HUD_COMBO_COLOR
        )
        pygame.draw.rect(surface, HUD_TRACK, layout.combo_bar)
        if layout.combo_fill.width > 0:
            pygame.draw.rect(surface, HUD_COMBO_COLOR, layout.combo_fill)
        surface.blit(combo_text, layout.combo_pos)
        painted.append(layout.combo_bar.union(pygame.Rect(layout.combo_pos, combo_text.get_size())))
        return painted

    def _draw_bar(
        self, bar: pygame.Rect, fill: pygame.Rect, color: Color, label: str
    ) -> pygame.Rect:
        """Label + bordered gauge: the label sits right-aligned left of ``bar``.

        Returns the bar united with its label, so the dirty rect covers the
        text too (it is painted outside the bar, in the margin gutter).
        """
        surface = self.renderer.display_surface
        label_surf = self.renderer.render_text(label, self.renderer.label_font, TEXT_MUTED)
        label_pos = (
            bar.x - HUD_LABEL_GAP - label_surf.get_width(),
            bar.centery - label_surf.get_height() // 2,
        )
        surface.blit(label_surf, label_pos)
        pygame.draw.rect(surface, HUD_TRACK, bar)
        if fill.width > 0:
            pygame.draw.rect(surface, color, fill)
        pygame.draw.rect(surface, PANEL_BORDER, bar, width=1)
        return bar.union(pygame.Rect(label_pos, label_surf.get_size()))

    def _draw_pips(self, pips: tuple[tuple[pygame.Rect, bool], ...]) -> list[pygame.Rect]:
        """Dash slots: filled pips for the charges left, empty tracks otherwise."""
        surface = self.renderer.display_surface
        for rect, filled in pips:
            pygame.draw.rect(surface, HUD_DASH_COLOR if filled else HUD_TRACK, rect)
            pygame.draw.rect(surface, PANEL_BORDER, rect, width=1)
        return [rect for rect, _ in pips]
