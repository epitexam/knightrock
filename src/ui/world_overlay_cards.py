"""Label cards: what a sprite says, and where the card finds room for it.

The consumer half of the overlay's two passes. The box pass has drawn this
frame's geometry and registered the rectangles it took; this module reads that
back out of the `AnnotationSink` and places one card per sprite in the first
slot that fits.

A class because it owns the one piece of per-frame state in the drawing layers:
`previous_bar_obstacles`, the bar rects seen on the *previous* frame. Bars paint
after the cards but belong to the same stack, so a card placed against where its
bar is now has to keep clear of where the bar was — otherwise a bar sliding onto
its own card reads as a placement bug.

The sink is read, never written. A card claiming space the next sprite reads as
taken is exactly how a label ends up underneath a health bar."""

from __future__ import annotations

from typing import Any

import pygame
import pygame.sprite

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.entities.components.reaction import ReactionStatus
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER
from src.ui.world_overlay_bars import health_bar_rect, health_colour
from src.ui.world_overlay_metrics import (
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_LABEL_GAP,
    LABEL_MAX_NUDGES,
    LABEL_SEP,
    LABEL_TAG,
    MetricsCache,
    WorldOverlayMetrics,
)
from src.ui.world_overlay_shared import AnnotationSink, display_name, faction, label_color

Segments = list[list[tuple[str, Color]]]

LabelRequest = tuple[
    tuple[int, float, float], Segments, Color, pygame.FRect, int, int, pygame.sprite.Sprite
]


def join_flag_tokens(flags: list[tuple[str, Color]]) -> list[tuple[str, Color]]:
    """Interleave flag tokens with a bright ``|`` separator."""
    joined: list[tuple[str, Color]] = [flags[0]]
    for text, color in flags[1:]:
        joined.append((" | ", LABEL_SEP))
        joined.append((text, color))
    return joined


_Segments = list[list[tuple[str, Color]]]

_LabelRequest = tuple[
    tuple[int, float, float], _Segments, Color, pygame.FRect, int, int, pygame.sprite.Sprite
]


__all__ = ["CardLayer", "Segments", "LabelRequest", "join_flag_tokens"]


class CardLayer:
    """Places one label card per sprite, dodging everything already drawn.

    Constructed once by ``WorldUI`` and kept for the session.
    """

    def __init__(
        self,
        renderer: PanelRenderer,
        metrics: MetricsCache,
        sink: AnnotationSink,
        layers: dict[str, bool],
    ) -> None:
        self.renderer = renderer
        self._metrics = metrics
        self.sink = sink
        #: Read live, because a layer toggled mid-frame has to take effect on
        #: the next sprite rather than the next frame.
        self.layers = layers
        #: Health-bar rects seen on the previous frame. Bars paint after the
        #: cards but belong to the same tier stack, so a card dodges both where
        #: its bar is and where it was -- otherwise a bar sliding onto its own
        #: card reads as a placement bug.
        self.previous_bar_obstacles: list[pygame.Rect] = []

    @property
    def surface(self) -> pygame.Surface:
        """The live render target, read through so a resize needs no push."""
        return self.renderer.surface

    @property
    def metrics(self) -> WorldOverlayMetrics:
        """The overlay dimensions for the current density, asked for each time."""
        return self._metrics.current

    def attack_line(self, sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]] | None:
        """Attack row: gold name plus muted phase stats, ``None`` while idle."""
        combat = getattr(sprite, "combat", None)
        attack_state = getattr(combat, "state", None)
        attack_name = getattr(attack_state, "attack_name", None)
        if attack_name is None:
            return None
        sub_state = getattr(attack_state, "sub_state", None)
        sub_state_name = getattr(sub_state, "value", sub_state)
        phase_index = getattr(attack_state, "phase_index", 0)
        frame_counter = getattr(attack_state, "frame_counter", 0)
        target_count = len(getattr(combat, "targets_hit", ()))
        return [
            ("ATK ", LABEL_TAG),
            (f"{attack_name} ", Colors.gold),
            (
                f"p{phase_index} {sub_state_name}:{frame_counter} hits:{target_count}",
                Colors.light_grey,
            ),
        ]

    def blit_label(
        self,
        header: list[pygame.Surface],
        rows: list[list[pygame.Surface]],
        row_height: int,
        accent: Color,
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
        screen_width: int,
    ) -> None:
        """Blit the card: panel, top faction edge, bold header, divider, rows."""
        panel = pygame.Surface(background_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (18, 20, 24, 210), panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.surface.blit(panel, background_rect.topleft)
        # A 2px rule just inside the top border, spanning the card width. It
        # marks the faction at a glance without cutting through the card and
        # its divider the way a full-height side stripe did.
        accent_edge = pygame.Rect(
            background_rect.left + 1,
            background_rect.top + 1,
            background_rect.width - 2,
            2,
        )
        self.surface.fill(accent, accent_edge)
        cursor_x = label_rect.left
        cursor_y = label_rect.top
        for surface in header:
            self.surface.blit(surface, (cursor_x, cursor_y))
            cursor_x += surface.get_width()
        cursor_y += row_height + self.metrics.label_divider_top
        rule_left = max(background_rect.left + self.metrics.label_pad_x, 0)
        rule_right = min(background_rect.right - self.metrics.label_pad_x, screen_width)
        if rule_right > rule_left:
            pygame.draw.line(
                self.surface,
                PANEL_BORDER,
                (rule_left, cursor_y),
                (rule_right, cursor_y),
                1,
            )
        cursor_y += 1 + self.metrics.label_divider_bottom
        for line in rows:
            cursor_x = label_rect.left
            for surface in line:
                self.surface.blit(surface, (cursor_x, cursor_y))
                cursor_x += surface.get_width()
            cursor_y += row_height + self.metrics.label_line_gap

    def candidate_slots(
        self,
        base: pygame.Rect,
        anchor: pygame.Rect | pygame.FRect,
        screen_width: int,
        screen_height: int,
        below_drop: int = 0,
    ) -> list[pygame.Rect]:
        """Slots to try, best first: above the entity, then below it.

        A slot that would stick out of the display is shifted back inside
        (never clipped): the padded card must stay fully on-screen with its
        text, so shrinking a slot would just push the text out of its panel.
        """
        below = base.copy()
        below.midtop = (anchor.centerx, anchor.bottom + self.metrics.label_anchor_gap + below_drop)
        slots = [base]
        slots.extend(
            base.move(0, -self.metrics.label_nudge * step)
            for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        slots.append(below)
        slots.extend(
            below.move(0, self.metrics.label_nudge * step)
            for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        kept: list[pygame.Rect] = []
        for slot in slots:
            # The padded card sticks out LABEL_PAD_Y on every side: keep slots
            # whose *card* fits the display, shifted back inside when needed.
            if slot.height + self.metrics.label_pad_y * 2 > screen_height:
                continue  # taller than the display: no fully visible position
            if slot.top - self.metrics.label_pad_y < 0:
                slot.top = self.metrics.label_pad_y
            elif slot.bottom + self.metrics.label_pad_y > screen_height:
                slot.bottom = screen_height - self.metrics.label_pad_y
            slot.left = max(
                self.metrics.label_pad_x,
                min(slot.left, screen_width - slot.width - self.metrics.label_pad_x),
            )
            kept.append(slot)
        return kept

    def draw_labels(
        self,
        requests: list[LabelRequest],
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Draw collected labels, each dodging the ones already placed.

        The health bars drawn for the same sprites are registered as
        obstacles first, then this frame's attack annotation rects: a card
        keeps clear of both like of the other cards, so neither a bar nor
        a timeline can end up painted over a placed card.
        """
        bar_obstacles: list[pygame.Rect] = []
        for _priority, _segments, _color, anchor, _lifts, _drop, sprite in requests:
            bar = health_bar_rect(self.surface, sprite, anchor)
            if bar is not None:
                bar_obstacles.append(
                    bar.inflate(
                        self.metrics.label_bar_clearance * 2, self.metrics.label_bar_clearance * 2
                    )
                )
        placed: list[pygame.Rect] = [
            *bar_obstacles,
            *self.previous_bar_obstacles,
            *self.sink.obstacles,
        ]
        self.previous_bar_obstacles = bar_obstacles
        for _priority, segments, color, anchor, above_lift, below_drop, _sprite in requests:
            rect = self.place_label(
                segments,
                color,
                anchor,
                placed,
                screen_width,
                screen_height,
                above_lift=above_lift,
                below_drop=below_drop,
            )
            if rect is not None:
                placed.append(rect)

    @staticmethod
    def entity_lines(sprite: pygame.sprite.Sprite, state_machine: Any) -> list[str]:
        state_name = state_machine.current_state_name or "None"
        head = f"{type(sprite).__name__} {state_name}"
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            head += f" {health:.0f}/{max_health:.0f}"
        combat = getattr(sprite, "combat", None)
        attack_state = getattr(combat, "state", None)
        attack_name = getattr(attack_state, "attack_name", None)
        detail: list[str] = []
        if attack_name is not None:
            sub_state = getattr(attack_state, "sub_state", None)
            sub_state_name = getattr(sub_state, "value", sub_state)
            phase_index = getattr(attack_state, "phase_index", 0)
            frame_counter = getattr(attack_state, "frame_counter", 0)
            target_count = len(getattr(combat, "targets_hit", ()))
            detail.append(
                f"{attack_name} p{phase_index} {sub_state_name}:{frame_counter} hits:{target_count}"
            )
        flags = CardLayer.status_flag_strings(sprite)
        if flags:
            detail.append(" ".join(flags))
        return [head, *detail]

    def entity_segments(self, sprite: pygame.sprite.Sprite, state_machine: Any) -> Segments:
        """One row per datum, every token paired with its display color.

        - header: faction-colored name (the enemy registry type for foes,
          the class name otherwise) plus off-white state
        - ``HP`` row: value tinted by the health ratio
        - ``ZONE`` row (multi-zone sprites only): one ``name xmult`` token per
          zone in its zone color — the world boxes carry no text, the full
          roster lives here where rows never overlap
        - ``ATK`` row (while attacking): gold name, muted phase stats
        - flags row (active flags only, no tag — each flag reads on its
          own): last hit, stagger, OTG, gravity, air, ledge, ``|``-separated
        """
        faction_color = label_color(sprite)
        state_name = state_machine.current_state_name or "None"
        lines: Segments = [
            [(f"{display_name(sprite)} ", faction_color), (state_name, Colors.off_white)]
        ]
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            lines.append(
                [
                    ("HP ", LABEL_TAG),
                    (f"{health:.0f}/{max_health:.0f}", health_colour(health, max_health)),
                ]
            )

        zone_line = self.zone_line(sprite)
        if zone_line is not None:
            lines.append(zone_line)

        attack_line = self.attack_line(sprite)
        if attack_line is not None:
            lines.append(attack_line)

        flags = self.status_flag_tokens(sprite)
        if flags:
            lines.append(join_flag_tokens(flags))
        return lines

    def label_clearances(
        self, sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, int]:
        """Vertical room the label card must leave for the tiers below it.

        Returns ``(above_lift, below_drop)`` reserving — whichever applies —
        the health bar and this frame's attack annotations (timeline, zone
        tags, badges) for the sprite. The bar sits above the entity, or
        flips below it near the top of the screen with the annotations
        following it; annotations drawn without a bar (player, dead)
        reserve their own band relative to the sprite. ``(0, 0)`` when
        neither a bar nor annotations exist.
        """
        bar_lift = 0
        bar_drop = 0
        bar = health_bar_rect(self.surface, sprite, anchor)
        if bar is not None:
            # The padded card sticks out self.metrics.label_pad_y below its content box,
            # so the lift reserves bar + gap + padding: backgrounds touch
            # neither the bar nor each other.
            clearance = HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + self.metrics.label_pad_y
            if bar.bottom <= anchor.top:
                bar_lift = clearance
            else:
                bar_drop = clearance
        annotation_rects = self.sink.for_sprite(sprite)
        above_tops = [rect.top for rect in annotation_rects if rect.top < anchor.top]
        below_bottoms = [rect.bottom for rect in annotation_rects if rect.bottom > anchor.bottom]
        ann_lift = 0
        if above_tops:
            # Card background bottom sits ANNOTATION_TIER_GAP above the
            # highest annotation band drawn above the sprite.
            ann_lift = max(
                0,
                int(
                    float(anchor.top)
                    - self.metrics.label_anchor_gap
                    + self.metrics.label_pad_y
                    + self.metrics.tier_gap
                    - min(above_tops)
                ),
            )
        ann_drop = 0
        if below_bottoms:
            ann_drop = max(
                0,
                int(
                    max(below_bottoms)
                    + self.metrics.tier_gap
                    + self.metrics.label_pad_y
                    - float(anchor.bottom)
                    - self.metrics.label_anchor_gap
                ),
            )
        return (max(bar_lift, ann_lift), max(bar_drop, ann_drop))

    def label_lines(self, sprite: pygame.sprite.Sprite) -> list[str] | None:
        segments = self.label_segments(sprite)
        if segments is None:
            return None
        return [" ".join(text.strip() for text, _ in line) for line in segments]

    @staticmethod
    def label_priority(
        sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, float, float]:
        """Placement order: the player reads first, then top-to-bottom."""
        player_first = 0 if faction(sprite) == "player" else 1
        return (player_first, float(anchor.top), float(anchor.left))

    def label_request(
        self,
        sprite: pygame.sprite.Sprite,
        reference: pygame.FRect,
        is_static: bool,
        camera: Camera,
    ) -> LabelRequest | None:
        if not self.layers["labels"] or is_static:
            return None
        segments = self.label_segments(sprite)
        if segments is None:
            return None
        anchor = camera.apply(reference)
        priority = self.label_priority(sprite, anchor)
        above_lift, below_drop = self.label_clearances(sprite, anchor)
        return (
            priority,
            segments,
            label_color(sprite),
            anchor,
            above_lift,
            below_drop,
            sprite,
        )

    def label_segments(self, sprite: pygame.sprite.Sprite) -> Segments | None:
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            return self.entity_segments(sprite, state_machine)
        if getattr(sprite, "hitbox", None) is not None:
            return [[(self.projectile_line(sprite), Colors.yellow)]]
        return None

    def place_label(
        self,
        segments: Segments,
        color: Color,
        anchor: pygame.Rect | pygame.FRect,
        placed: list[pygame.Rect],
        screen_width: int,
        screen_height: int,
        above_lift: int = 0,
        below_drop: int = 0,
    ) -> pygame.Rect | None:
        """Render a label card in the first free slot near its entity.

        The header row uses the compact bold world font; detail rows use the
        compact regular world font. Slots run above the entity (nudging
        upward), then below it (nudging downward). ``above_lift`` reserves
        the health bar stacked between the entity and the card; ``below_drop``
        does the same when the bar flipped under the entity. ``placed``
        holds already-drawn cards *and* the bar/annotation obstacles. Returns the
        padded rect the card occupies, or ``None`` when every slot is taken
        or cannot fit on-screen — a dropped label beats an unreadable stack.
        """
        title_font = self.renderer.world_title_font
        body_font = self.renderer.world_label_font
        header = [self.renderer.render_text(text, title_font, tint) for text, tint in segments[0]]
        rows = [
            [self.renderer.render_text(text, body_font, tint) for text, tint in line]
            for line in segments[1:]
        ]
        row_height = max(
            [s.get_height() for s in header] + [s.get_height() for r in rows for s in r]
        )
        width = max(
            [sum(s.get_width() for s in header)] + [sum(s.get_width() for s in r) for r in rows]
        )
        divider_block = self.metrics.label_divider_top + 1 + self.metrics.label_divider_bottom
        height = (
            row_height * (len(rows) + 1) + self.metrics.label_line_gap * len(rows) + divider_block
            if rows
            else row_height
        )
        base = pygame.Rect(0, 0, width, height)
        base.midbottom = (anchor.centerx, anchor.top - self.metrics.label_anchor_gap - above_lift)
        for label_rect in self.candidate_slots(
            base, anchor, screen_width, screen_height, below_drop=below_drop
        ):
            background_rect = label_rect.inflate(
                self.metrics.label_pad_x * 2, self.metrics.label_pad_y * 2
            )
            if all(not background_rect.colliderect(other) for other in placed):
                self.blit_label(
                    header, rows, row_height, color, label_rect, background_rect, screen_width
                )
                return background_rect
        return None

    @staticmethod
    def projectile_line(sprite: pygame.sprite.Sprite) -> str:
        velocity = getattr(sprite, "velocity", None)
        vel = f"({velocity.x:.0f},{velocity.y:.0f})" if velocity is not None else "(?,?)"
        life = float(getattr(sprite, "life", 0.0) or 0.0)
        pierce = "pierce" if getattr(getattr(sprite, "config", None), "pierce", False) else "single"
        hits = len(getattr(sprite, "targets_hit", ()))
        faction = getattr(sprite, "faction", "?")
        return f"{type(sprite).__name__} {faction} {vel} {life:.1f}s {pierce} hits:{hits}"

    @staticmethod
    def reaction_flag(sprite: pygame.sprite.Sprite) -> str | None:
        """Label token for the last hit-reaction cause (kind + freshness).

        Reads the typed ``ReactionStatus`` — never a state-machine name.
        ``HIT`` marks a fresh reaction with its remaining freshness window
        in seconds; ``HIT ... (old)`` marks a stale cause whose freshness
        has expired.
        """
        reaction = getattr(sprite, "reaction_status", None)
        if not isinstance(reaction, ReactionStatus):
            return None
        age = float(getattr(sprite, "reaction_age", 0.0) or 0.0)
        if age > 0:
            return f"HIT {reaction.kind.value} {age:.2f}s"
        return f"HIT {reaction.kind.value} (old)"

    @staticmethod
    def status_flag_strings(sprite: pygame.sprite.Sprite) -> list[str]:
        """Plain-text status flags backing ``_entity_lines`` (ledge tests, docs)."""
        flags: list[str] = []
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            flags.append(f"STAG {stagger:.2f}s")
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            current = getattr(state_machine, "current_state_name", None)
            if current == "dizzy":
                flags.append(f"DIZZY {stagger:.2f}s")
        reaction_flag = CardLayer.reaction_flag(sprite)
        if reaction_flag is not None:
            flags.append(reaction_flag)
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            flags.append(f"OTG {otg:.2f}s")
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            flags.append(f"GRAV x{gravity_scale:.1f}")
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            flags.append("AIR")
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            flags.append("LEDGE")
        return flags

    @staticmethod
    def status_flag_tokens(sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]]:
        """Colored status flags for the untagged flags card row (same order as strings)."""
        names = CardLayer.status_flag_strings(sprite)
        colors: dict[str, Color] = {}
        reaction = CardLayer.reaction_flag(sprite)
        if reaction is not None:
            colors[reaction] = (
                Colors.red
                if float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0
                else Colors.dark_red
            )
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            colors[f"STAG {stagger:.2f}s"] = Colors.orange
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            current = getattr(state_machine, "current_state_name", None)
            if current == "dizzy":
                colors[f"DIZZY {stagger:.2f}s"] = Colors.gold
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            colors[f"OTG {otg:.2f}s"] = Colors.debug_otg
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            colors[f"GRAV x{gravity_scale:.1f}"] = Colors.debug_juggle
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            colors["AIR"] = Colors.light_grey
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            colors["LEDGE"] = Colors.yellow
        return [(name, colors.get(name, Colors.off_white)) for name in names]

    def zone_line(self, sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]] | None:
        """Zone roster row: ``name xmult`` per zone in its zone color.

        Only for sprites carrying more than one zone worth naming: single
        unnamed neutral zones (the legacy path) add no row. Tags ride the
        token text (``[tag]``) since the world seal is shape-only.
        """
        names = getattr(sprite, "hurtbox_zone_names", None)
        mults = getattr(sprite, "hurtbox_mult", None)
        tags = getattr(sprite, "hurtbox_tags", None)
        zones = getattr(sprite, "hurtboxes", None)
        count = len(tuple(zones)) if zones is not None else 0
        if count <= 1 and not names and not mults:
            return None
        tokens: list[tuple[str, Color]] = [("ZONE ", LABEL_TAG)]
        named = False
        for index in range(count):
            name = names[index] if isinstance(names, tuple) and index < len(names) else ""
            mult = mults[index] if isinstance(mults, tuple) and index < len(mults) else 1.0
            zone_tags = tags[index] if isinstance(tags, tuple) and index < len(tags) else ()
            label = f"{name} x{float(mult):g}" if name else f"x{float(mult):g}"
            if name or float(mult) != 1.0 or zone_tags:
                named = True
            if zone_tags:
                label += f" [{','.join(str(tag) for tag in zone_tags)}]"
            if index > 0:
                tokens.append(("| ", LABEL_SEP))
            tokens.append(
                (label + " ", Colors.debug_hurtbox_zones[index % len(Colors.debug_hurtbox_zones)])
            )
        return tokens if named else None
