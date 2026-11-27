"""Always-on player HUD: health, battery and fury; dash and combo; slot machine; prompt.

Unlike the F1-F7 debug panels this overlay is **not** gated by
``Debug.is_enabled()``: it is what the player reads while fighting.

- Bottom left, three gauges: health, the blade's battery, and fury (bright
  once it can be spent, amber while the dark side spends it).
- Bottom right: the dash charges and the combo counter, which takes one ``!``
  and one step of colour per fury tier reached.
- Top centre: the slot machine's three reels while a spin turns and shows,
  and the power it granted while that lasts.
- Centre: the prompt -- the direction asked for and the time left to give it,
  or the slashes still to mash in a blade lock.

Everything is laid out apart from the drawing (:class:`HudLayout`), so the HUD
can be asserted on state and colours instead of on pixels. Wired from
``GameplayScene.draw`` after ``level.draw()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation.entities.player import Player

import pygame

from src.presentation.ui.metrics import Metrics
from src.presentation.ui.panel_renderer import PanelRenderer
from src.presentation.ui.styles import (
    PANEL_BG,
    PANEL_BORDER,
    TEXT_CRIT,
    TEXT_MUTED,
    TEXT_OK,
    TEXT_WARN,
)
from src.shared.colors import Color, Colors
from src.simulation.entities.player_kit import SYMBOLS, Direction, PromptKind
from src.simulation.settings import Clash, Combat

#: HUD geometry (px), at a scale of 1. The bar is a fixed width: the target is
#: a constant size, so a bar that grew with the display would be the same bar
#: drawn at three sizes depending on the video settings.
HUD_MARGIN = 20
HUD_BAR_HEIGHT = 14
HUD_BAR_GAP = 8
HUD_BAR_WIDTH = 220
HUD_LABEL_GAP = 8
HUD_PIP_SIZE = 14
HUD_PIP_GAP = 5
HUD_COMBO_BAR_HEIGHT = 6
HUD_COMBO_BAR_GAP = 4
HUD_REEL_SIZE = 40
HUD_REEL_GAP = 8
HUD_PROMPT_SIZE = 64
HUD_PROMPT_BAR_HEIGHT = 8

#: Track color of every gauge (same dark grey as the entity health bars).
HUD_TRACK = (35, 37, 40)
HUD_DASH_COLOR: Color = Colors.sky_blue
HUD_BATTERY_COLOR: Color = (110, 200, 255)
HUD_BATTERY_EMPTY_COLOR: Color = TEXT_CRIT
HUD_FURY_COLOR: Color = (170, 60, 200)
HUD_FURY_FULL_COLOR: Color = (230, 110, 255)
HUD_DARK_COLOR: Color = TEXT_WARN
HUD_PROMPT_COLOR: Color = (255, 245, 170)
#: The combo counter's colour at each fury tier, the plain amber first.
HUD_TIER_COLORS: tuple[Color, ...] = (TEXT_WARN, (255, 150, 60), (255, 105, 60), (255, 60, 90))

#: Labels of the bars, bottom first, right-aligned in a shared gutter.
HUD_BAR_LABELS = ("HP", "BAT", "FURY")

#: The direction of each prompt arrow, as a unit vector on screen.
_ARROWS: dict[Direction, tuple[float, float]] = {
    Direction.LEFT: (-1.0, 0.0),
    Direction.RIGHT: (1.0, 0.0),
    Direction.UP: (0.0, -1.0),
    Direction.DOWN: (0.0, 1.0),
}


def health_color(ratio: float) -> Color:
    """Green above 50%, amber above 25%, red below (debug panel thresholds)."""
    if ratio > 0.5:
        return TEXT_OK
    if ratio > 0.25:
        return TEXT_WARN
    return TEXT_CRIT


def battery_color(ratio: float) -> Color:
    """Blue while there is charge, red once the slashes are running on nothing."""
    return HUD_BATTERY_COLOR if ratio > 0.0 else HUD_BATTERY_EMPTY_COLOR


def fury_color(is_full: bool, in_dark: bool) -> Color:
    """Fury: amber while the dark side spends it, bright once full, dark while filling."""
    if in_dark:
        return HUD_DARK_COLOR
    if is_full:
        return HUD_FURY_FULL_COLOR
    return HUD_FURY_COLOR


def bar_width_for(target_width: int) -> int:
    """HUD bar width, shrunk only if the target is too narrow to hold it."""
    return max(1, min(HUD_BAR_WIDTH, target_width - 2 * HUD_MARGIN))


def tier_level(player: Player) -> int:
    """How many fury tiers the player has reached."""
    return int(player.fury.tier)


def _ratio(value: float, maximum: float) -> float:
    """Clamped ``value / maximum``; a missing maximum reads as empty."""
    if not maximum:
        return 0.0
    return max(0.0, min(1.0, value / maximum))


def _fill(bar: pygame.Rect, ratio: float) -> pygame.Rect:
    """Left-anchored portion of ``bar`` covered by ``ratio``."""
    return pygame.Rect(bar.x, bar.y, int(bar.width * ratio), bar.height)


@dataclass(frozen=True)
class Gauge:
    """One bar of the HUD: where it is, how full, in what colour, under what label."""

    label: str
    bar: pygame.Rect
    fill: pygame.Rect
    label_rect: pygame.Rect
    color: Color


@dataclass(frozen=True)
class PromptLayout:
    """The prompt on screen: the arrow or the mash count, and the time left."""

    kind: PromptKind
    direction: Direction | None
    box: pygame.Rect
    timer_bar: pygame.Rect
    timer_fill: pygame.Rect
    text: str


@dataclass(frozen=True)
class HudLayout:
    """Resolved geometry and colors of one HUD frame."""

    gauges: tuple[Gauge, ...]
    dash_pips: tuple[tuple[pygame.Rect, bool], ...]
    combo_text: str
    combo_color: Color
    combo_pos: tuple[int, int] | None
    combo_bar: pygame.Rect | None
    combo_fill: pygame.Rect | None
    reels: tuple[tuple[pygame.Rect, str], ...]
    power_text: str
    prompt: PromptLayout | None

    def gauge(self, label: str) -> Gauge:
        """The bar labelled ``label``."""
        return next(gauge for gauge in self.gauges if gauge.label == label)


class HUD:
    """Always-on player gauges, anchored to the display's corners and centre."""

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        self._scale = 1.0
        self._metrics = Metrics.for_scale(1.0)

    def set_scale(self, scale: float) -> None:
        self._metrics = Metrics.for_scale(scale)
        self._scale = self._metrics.scale

    def reserved_height(self) -> int:
        """How much of the screen's bottom the gauges take, margin included.

        The debug panels are laid out above it, so a tall panel never lands on
        a gauge.
        """
        bars = len(HUD_BAR_LABELS)
        return (
            self._px(HUD_MARGIN) * 2
            + self._px(HUD_BAR_HEIGHT) * bars
            + self._px(HUD_BAR_GAP) * (bars - 1)
        )

    def _px(self, value: int) -> int:
        """A design size in target pixels, never below one."""
        return self._metrics.px(value)

    def layout(self, player: Player) -> HudLayout | None:
        """Compute the frame's rects and colors without drawing anything."""
        if not player:
            return None
        screen = self.renderer.surface.get_size()
        pips = self._dash_pips(player, screen)
        combo_text, combo_pos, combo_bar, combo_fill = self._combo(player, screen, pips)
        reels, power_text = self._reels(player, screen)
        return HudLayout(
            gauges=self._gauges(player, screen),
            dash_pips=pips,
            combo_text=combo_text,
            combo_color=HUD_TIER_COLORS[min(tier_level(player), len(HUD_TIER_COLORS) - 1)],
            combo_pos=combo_pos,
            combo_bar=combo_bar,
            combo_fill=combo_fill,
            reels=reels,
            power_text=power_text,
            prompt=self._prompt(player, screen),
        )

    def _gauges(self, player: Player, screen: tuple[int, int]) -> tuple[Gauge, ...]:
        screen_w, screen_h = screen
        bar_w = int(bar_width_for(screen_w) * self._scale)
        health = _ratio(player.health, player.max_health)
        ratios = (health, player.battery.ratio, player.fury.ratio)
        colors = (
            health_color(health),
            battery_color(player.battery.ratio),
            fury_color(player.fury.is_full, player.fury.in_dark),
        )
        label_sizes = {
            label: self.renderer.render_text(label, self.renderer.label_font, TEXT_MUTED).get_size()
            for label in HUD_BAR_LABELS
        }
        label_w = max(width for width, _ in label_sizes.values())
        bar_x = self._px(HUD_MARGIN) + label_w + self._px(HUD_LABEL_GAP)
        height = self._px(HUD_BAR_HEIGHT)
        step = height + self._px(HUD_BAR_GAP)
        gauges: list[Gauge] = []
        for index, label in enumerate(HUD_BAR_LABELS):
            y = screen_h - self._px(HUD_MARGIN) - height - index * step
            bar = pygame.Rect(bar_x, y, bar_w, height)
            gauges.append(
                Gauge(
                    label=label,
                    bar=bar,
                    fill=_fill(bar, ratios[index]),
                    label_rect=self._label_rect(bar, label_sizes[label]),
                    color=colors[index],
                )
            )
        return tuple(gauges)

    def _dash_pips(
        self, player: Player, screen: tuple[int, int]
    ) -> tuple[tuple[pygame.Rect, bool], ...]:
        """Right-anchored pip row, read left-to-right, filled from the left."""
        screen_w, screen_h = screen
        total = max(0, int(player.dash.max_charges))
        filled = max(0, min(total, int(player.dash.charges)))
        size, gap = self._px(HUD_PIP_SIZE), self._px(HUD_PIP_GAP)
        y = screen_h - self._px(HUD_MARGIN) - size
        left = screen_w - self._px(HUD_MARGIN) - total * size - (total - 1) * gap
        return tuple(
            (pygame.Rect(left + index * (size + gap), y, size, size), index < filled)
            for index in range(total)
        )

    def _combo(
        self,
        player: Player,
        screen: tuple[int, int],
        pips: tuple[tuple[pygame.Rect, bool], ...],
    ) -> tuple[str, tuple[int, int] | None, pygame.Rect | None, pygame.Rect | None]:
        """``xN`` counter, a ``!`` per fury tier, and its decay bar; hidden at 0."""
        combat = player.combat
        count = int(combat.combo_count)
        if count <= 0:
            return "", None, None, None
        screen_w, screen_h = screen
        text = f"x{count}" + "!" * tier_level(player)
        text_surf = self.renderer.render_text(text, self.renderer.label_font, TEXT_WARN)
        top_of_pips = min((rect.top for rect, _ in pips), default=screen_h - self._px(HUD_MARGIN))
        bar = pygame.Rect(
            screen_w - self._px(HUD_MARGIN) - text_surf.get_width(),
            top_of_pips - self._px(HUD_COMBO_BAR_GAP) - self._px(HUD_COMBO_BAR_HEIGHT),
            text_surf.get_width(),
            self._px(HUD_COMBO_BAR_HEIGHT),
        )
        text_pos = (bar.x, bar.y - self._px(HUD_COMBO_BAR_GAP) - text_surf.get_height())
        ratio = _ratio(combat.combo_timer, Combat.COMBO_WINDOW)
        return text, text_pos, bar, _fill(bar, ratio)

    def _reels(
        self, player: Player, screen: tuple[int, int]
    ) -> tuple[tuple[tuple[pygame.Rect, str], ...], str]:
        """The three reels while a spin turns or shows, and the power while it lasts.

        While the spin turns each reel shows a symbol that changes with the
        time left; it lands on the drawn one when the spin stops.
        """
        slot = player.slot
        power_text = ""
        if slot.power is not None and slot.power_timer > 0.0:
            power_text = f"{slot.power.value.upper()} {slot.power_timer:.1f}s"
        if slot.reels is None or not (slot.spinning or slot.show_timer > 0.0):
            return (), power_text
        size, gap = self._px(HUD_REEL_SIZE), self._px(HUD_REEL_GAP)
        left = screen[0] // 2 - (3 * size + 2 * gap) // 2
        top = self._px(HUD_MARGIN)
        reels: list[tuple[pygame.Rect, str]] = []
        for index, symbol in enumerate(slot.reels):
            shown = symbol
            if slot.spinning:
                shown = (symbol + int(slot.spin_timer * 20) + index * 2) % len(SYMBOLS)
            rect = pygame.Rect(left + index * (size + gap), top, size, size)
            reels.append((rect, SYMBOLS[shown][0].upper()))
        return tuple(reels), power_text

    def _prompt(self, player: Player, screen: tuple[int, int]) -> PromptLayout | None:
        prompt = player.prompt
        if not prompt.active or prompt.kind is None:
            return None
        size = self._px(HUD_PROMPT_SIZE)
        box = pygame.Rect(0, 0, size, size)
        box.center = (screen[0] // 2, screen[1] // 3)
        timer_bar = pygame.Rect(
            box.x, box.bottom + self._px(HUD_BAR_GAP), size, self._px(HUD_PROMPT_BAR_HEIGHT)
        )
        text = ""
        if prompt.kind is PromptKind.CLASH:
            text = f"{max(0, Clash.PRESSES - prompt.presses)}"
        elif prompt.kind is PromptKind.THROW:
            text = f"{prompt.step + 1}/{len(prompt.steps)}"
        return PromptLayout(
            kind=prompt.kind,
            direction=prompt.expected,
            box=box,
            timer_bar=timer_bar,
            timer_fill=_fill(timer_bar, _ratio(prompt.timer, prompt.window)),
            text=text,
        )

    def draw(self, player: Player) -> None:
        """Paint the HUD for ``player``; a missing player draws nothing."""
        layout = self.layout(player)
        if layout is None:
            return
        self._paint(layout)

    def _paint(self, layout: HudLayout) -> None:
        """Draw one frame's HUD."""
        for gauge in layout.gauges:
            self._draw_gauge(gauge)
        self._draw_pips(layout.dash_pips)
        self._draw_combo(layout)
        self._draw_reels(layout)
        if layout.prompt is not None:
            self._draw_prompt(layout.prompt)

    def _draw_combo(self, layout: HudLayout) -> None:
        if layout.combo_pos is None or layout.combo_bar is None or layout.combo_fill is None:
            return
        surface = self.renderer.surface
        text = self.renderer.render_text(
            layout.combo_text, self.renderer.label_font, layout.combo_color
        )
        pygame.draw.rect(surface, HUD_TRACK, layout.combo_bar)
        if layout.combo_fill.width > 0:
            pygame.draw.rect(surface, layout.combo_color, layout.combo_fill)
        surface.blit(text, layout.combo_pos)

    def _draw_reels(self, layout: HudLayout) -> None:
        surface = self.renderer.surface
        for rect, letter in layout.reels:
            pygame.draw.rect(surface, PANEL_BG[:3], rect)
            pygame.draw.rect(surface, PANEL_BORDER, rect, width=1)
            glyph = self.renderer.render_text(letter, self.renderer.title_font, TEXT_WARN)
            surface.blit(glyph, glyph.get_rect(center=rect.center))
        if layout.power_text:
            glyph = self.renderer.render_text(layout.power_text, self.renderer.title_font, TEXT_OK)
            top = (layout.reels[0][0].bottom if layout.reels else 0) + self._px(HUD_MARGIN)
            surface.blit(glyph, glyph.get_rect(midtop=(surface.get_width() // 2, top)))

    def _draw_prompt(self, prompt: PromptLayout) -> None:
        surface = self.renderer.surface
        box = prompt.box
        pygame.draw.rect(surface, PANEL_BG[:3], box)
        pygame.draw.rect(surface, HUD_PROMPT_COLOR, box, width=2)
        if prompt.direction is not None:
            dx, dy = _ARROWS[prompt.direction]
            cx, cy = box.center
            reach = box.width * 0.35
            tip = (cx + dx * reach, cy + dy * reach)
            base = (cx - dx * reach * 0.6, cy - dy * reach * 0.6)
            side = (-dy * reach * 0.7, dx * reach * 0.7)
            corners = [
                tip,
                (base[0] + side[0], base[1] + side[1]),
                (base[0] - side[0], base[1] - side[1]),
            ]
            pygame.draw.polygon(surface, HUD_PROMPT_COLOR, corners)
        else:
            glyph = self.renderer.render_text("MASH", self.renderer.title_font, HUD_PROMPT_COLOR)
            surface.blit(glyph, glyph.get_rect(center=box.center))
        if prompt.text:
            glyph = self.renderer.render_text(prompt.text, self.renderer.label_font, TEXT_WARN)
            surface.blit(glyph, glyph.get_rect(midbottom=(box.centerx, box.top - 4)))
        pygame.draw.rect(surface, HUD_TRACK, prompt.timer_bar)
        if prompt.timer_fill.width > 0:
            pygame.draw.rect(surface, HUD_PROMPT_COLOR, prompt.timer_fill)

    def draw_notice(self, lines: tuple[str, ...]) -> None:
        """Paint a transient message, top-left, over everything.

        A dead key that says nothing is indistinguishable from a broken one, so
        a key that cannot act says so, once, in the corner the player is
        already looking at.
        """
        if not lines:
            return
        surface = self.renderer.surface
        font = self.renderer.label_font
        margin = self._px(HUD_MARGIN)
        rendered = [self.renderer.render_text(line, font, TEXT_WARN) for line in lines]
        width = max(drawn.get_width() for drawn in rendered) + margin * 2
        height = sum(drawn.get_height() for drawn in rendered) + margin * 2
        plate = pygame.Rect(margin, margin, width, height)
        backdrop = pygame.Surface(plate.size, pygame.SRCALPHA)
        backdrop.fill((*PANEL_BG[:3], 200))
        surface.blit(backdrop, plate.topleft)
        cursor_y = plate.top + margin
        for drawn in rendered:
            surface.blit(drawn, (plate.left + margin, cursor_y))
            cursor_y += drawn.get_height()

    def _label_rect(self, bar: pygame.Rect, label_size: tuple[int, int]) -> pygame.Rect:
        """Where a bar's label goes: right-aligned, one gap to the left of it."""
        return pygame.Rect(
            bar.x - self._px(HUD_LABEL_GAP) - label_size[0],
            bar.centery - label_size[1] // 2,
            label_size[0],
            label_size[1],
        )

    def _draw_gauge(self, gauge: Gauge) -> None:
        """Label + bordered gauge: the label sits right-aligned left of the bar."""
        surface = self.renderer.surface
        label_surf = self.renderer.render_text(gauge.label, self.renderer.label_font, TEXT_MUTED)
        surface.blit(label_surf, gauge.label_rect.topleft)
        pygame.draw.rect(surface, HUD_TRACK, gauge.bar)
        if gauge.fill.width > 0:
            pygame.draw.rect(surface, gauge.color, gauge.fill)
        pygame.draw.rect(surface, PANEL_BORDER, gauge.bar, width=1)

    def _draw_pips(self, pips: tuple[tuple[pygame.Rect, bool], ...]) -> None:
        """Dash slots: filled pips for the charges left, empty tracks otherwise."""
        surface = self.renderer.surface
        for rect, filled in pips:
            pygame.draw.rect(surface, HUD_DASH_COLOR if filled else HUD_TRACK, rect)
            pygame.draw.rect(surface, PANEL_BORDER, rect, width=1)
