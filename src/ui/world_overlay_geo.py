"""World-space geometry: what a sprite occupies, and the tiers drawn above it.

Extracted from ``world_ui.py`` as the second step of the split. This is the
producer half of the overlay's two passes: for each sprite it draws the
hitbox, the hurtbox zone seals, the swept attack boxes, the attack header chip
with its phase timeline, the anchor dots and the velocity arrow, and it
registers the screen space each of those took.

**A class, not functions, unlike the two modules before it.**
``world_overlay_bars`` and ``world_overlay_shared`` answer questions and are
handed what they need. This one draws, and drawing needs the surface, the
metrics for the current density and the per-frame annotation sink, thirty-odd
methods deep. Threading those through every signature would be thirty-odd
signatures all saying the same three things.

**The surface and the metrics are read, never cached.** ``surface`` is
``renderer.surface``, and the metrics table is rebuilt when the density moves.
Holding either would mean a resize path that has to remember to push new values
in here -- the bug ``WorldUI.surface`` was already fixed for once.

``health_bar_rect`` comes from the bars module directly rather than through the
facade: it is a fact about the world, and the facade is a seam for its own
callers, not a relay between its layers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from src.combat.shapes import ShapeKind, ShapePose, SweptShape
from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER
from src.ui.world_overlay_bars import health_bar_rect
from src.ui.world_overlay_metrics import (
    ANNOTATION_CHIP_FILL,
    BOX_DOT_CORE_RADIUS,
    BOX_DOT_INSET,
    BOX_DOT_RADIUS,
    BOX_DOT_RIM,
    BOX_DOT_RIM_WIDTH,
    HIT_HEIGHT_BADGES,
    PHASE_OUTLINE_COLORS,
    SWEEP_ARROW_HEAD,
    SWEEP_DISPLAY_MIN_PX,
    ZONE_FILL_ALPHA,
    MetricsCache,
    WorldOverlayMetrics,
    scaled_world_px,
)
from src.ui.world_overlay_shapes import ShapeLayer
from src.ui.world_overlay_shared import AnnotationSink, dodge_annotation, hitbox_color
from src.ui.world_overlay_velocity import VelocityLayer

if TYPE_CHECKING:
    from src.combat.frame_data import PhaseDefinition

__all__ = ["GeoLayer"]


class GeoLayer:
    """Draws one sprite's geometry and claims the screen space it used.

    Constructed once by ``WorldUI`` and kept for the session: it holds no
    per-frame state of its own, only the collaborators it draws with.
    """

    def __init__(
        self,
        renderer: PanelRenderer,
        metrics: MetricsCache,
        sink: AnnotationSink,
    ) -> None:
        self.renderer = renderer
        self._metrics = metrics
        self.sink = sink
        #: Collision poses and dashed outlines. A leaf that knows about shapes
        #: and nothing else; it never asks the box pass anything.
        self.shapes = ShapeLayer(renderer)
        #: Velocity previews, and the two predicates that decide their colour.
        self.velocity = VelocityLayer(renderer)

    @property
    def surface(self) -> pygame.Surface:
        """The live render target, read through so a resize needs no push.

        Derived rather than copied, and that is the whole contract: a resize
        that forgot to hand this layer a new surface would leave the overlay
        painting into an orphan with no symptom until the two sizes disagreed.
        """
        return self.renderer.surface

    @property
    def metrics(self) -> WorldOverlayMetrics:
        """The overlay dimensions for the current density.

        Never held: the table is rebuilt when the scale moves, so a copy kept
        here would go stale for exactly as long as nobody resized twice. The
        cache that decides that is ``MetricsCache``, shared with the other two
        layers so they cannot disagree about when the table went stale.
        """
        return self._metrics.current

    def stroke(self, world_px: int = 1) -> int:
        """An outline of ``world_px`` art pixels, in whole target pixels.

        Floored at 1, so a density below one thins the overlay rather than
        deleting it: *not drawing the outline* is the one outcome a debug tool
        must never produce.
        """
        return scaled_world_px(world_px, self.renderer.world_scale)

    @staticmethod
    def offensive_boxes(combat: object) -> tuple:
        boxes = getattr(combat, "attack_boxes", None)
        if boxes is None:
            legacy_box = getattr(combat, "attack_box", None)
            return (legacy_box,) if legacy_box is not None else ()
        return tuple(boxes)

    @staticmethod
    def offensive_shapes(combat: object) -> tuple[ShapePose, ...]:
        shapes = getattr(combat, "attack_shapes", ())
        return tuple(shapes) if isinstance(shapes, tuple) else ()

    def offensive_badges(self, combat: object) -> tuple[str, ...]:
        hit = self.offensive_hit(combat)
        if hit is None:
            return ()
        badges: list[str] = []
        shapes = self.offensive_shapes(combat)
        if shapes:
            badges.append(shapes[0].kind.value.upper())
        priority = int(getattr(hit, "priority", 0) or 0)
        if priority > 0:
            badges.append(f"P{priority}")
        if bool(getattr(hit, "unblockable", False)):
            badges.append("UBL")
        height = str(getattr(hit, "height", "mid") or "mid")
        if height != "mid":
            badges.append(HIT_HEIGHT_BADGES.get(height, height.upper()))
        return tuple(badges)

    @staticmethod
    def offensive_hit(combat: object) -> object | None:
        phase = getattr(combat, "current_phase", None)
        return getattr(phase, "hit", None)

    def offensive_outline(self, combat: object) -> Color:
        state = getattr(combat, "state", None)
        phase_name = getattr(getattr(state, "sub_state", None), "value", None)
        if isinstance(phase_name, str):
            return PHASE_OUTLINE_COLORS.get(phase_name, Colors.debug_attack_box)
        return Colors.debug_attack_box

    def attack_header_rect(
        self,
        sprite: pygame.sprite.Sprite,
        collider: pygame.FRect,
        camera: Camera,
        obstacles: list[pygame.Rect],
    ) -> pygame.Rect | None:
        """One chip naming the live attack: name, phase, badges.

        Merges the scattered ``ATK`` pill + ``b{i}`` ids + gold badges into a
        single header in the tier stack: glyphs on one row, the phase timeline
        tucked underneath on the same card, a 1 px leader line to the first
        attack box when boxes exist. ``None`` while idle (no name, no phase).
        """
        combat = getattr(sprite, "combat", None)
        state = getattr(combat, "state", None)
        attack_name = getattr(state, "attack_name", None)
        phase: PhaseDefinition | None = getattr(combat, "current_phase", None)
        attack_boxes = self.offensive_boxes(combat)
        if attack_name is None or phase is None:
            return None
        sub_state = getattr(state, "sub_state", None)
        frame_counter = int(getattr(state, "frame_counter", 0) or 0)
        phase_value = getattr(sub_state, "value", sub_state)
        phase_name = str(phase_value)
        badges = " ".join(self.offensive_badges(combat))
        tokens: list[tuple[str, Color]] = [
            (f"{attack_name} ", Colors.gold),
            (f"{phase_name}:{frame_counter}", Colors.off_white),
        ]
        if badges:
            tokens.append((f" {badges}", Colors.gold))
        glyphs = [
            self.renderer.render_text(text, self.renderer.world_title_font, color)
            for text, color in tokens
        ]
        text_w = sum(glyph.get_width() for glyph in glyphs)
        title_h = max(glyph.get_height() for glyph in glyphs)
        tl_widths, tl_rect_w = self.attack_timeline_widths(phase, state, phase_name)
        chip_text_w = text_w + self.metrics.chip_pad * 2
        chip_tl_w = tl_rect_w + self.metrics.chip_pad * 2
        chip_w = max(chip_text_w, chip_tl_w)
        chip_h = (
            self.metrics.chip_pad
            + title_h
            + self.metrics.header_text_gap
            + self.metrics.timeline_bar_height
            + self.metrics.chip_pad
        )
        screen = camera.apply(collider)
        bar = health_bar_rect(self.surface, sprite, screen)
        if bar is not None and bar.bottom <= screen.top:
            anchor_y = bar.top - self.metrics.tier_gap
        elif bar is not None:
            anchor_y = bar.bottom + self.metrics.tier_gap + chip_h
        else:
            anchor_y = int(screen.top) - self.metrics.tier_gap
        chip = pygame.Rect(int(screen.x), int(anchor_y - chip_h), chip_w, chip_h)
        chip = dodge_annotation(
            chip,
            obstacles,
            tier_gap=self.metrics.tier_gap,
            screen_width=self.surface.get_width(),
        )
        panel = pygame.Surface(chip.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, ANNOTATION_CHIP_FILL, panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.surface.blit(panel, chip.topleft)
        cursor = chip.x + (chip_w - text_w) // 2
        for glyph in glyphs:
            self.surface.blit(glyph, (cursor, chip.y + self.metrics.chip_pad))
            cursor += glyph.get_width()
        tl_x = chip.x + max(0, (chip_w - tl_rect_w) // 2)
        tl_y = chip.y + self.metrics.chip_pad + title_h + self.metrics.header_text_gap
        self.paint_attack_timeline(tl_x, tl_y, phase, tl_widths, state, phase_name)
        if attack_boxes:
            first = camera.apply(attack_boxes[0])
            pygame.draw.line(
                self.surface,
                PANEL_BORDER,
                (chip.centerx, chip.bottom + self.metrics.header_rule_gap),
                (int(first.centerx), int(first.top)),
                1,
            )
        return chip

    def attack_timeline_widths(
        self,
        phase: PhaseDefinition,
        state: object,
        sub_state: object,
    ) -> tuple[list[tuple[int, Color]], int]:
        """Phase segment widths, shrunk to ``TIMELINE_MAX_WIDTH``; total width."""
        startup = int(getattr(phase, "startup_frames", 0) or 0)
        active = int(getattr(phase, "active_frames", 0) or 0)
        recovery = int(getattr(phase, "recovery_frames", 0) or 0)
        raw = [
            max(1, startup * self.metrics.timeline_px_per_frame),
            max(1, active * self.metrics.timeline_px_per_frame),
            max(1, recovery * self.metrics.timeline_px_per_frame),
        ]
        total = sum(raw)
        if total > self.metrics.timeline_max_width:
            scaled = [
                max(1, round(width * self.metrics.timeline_max_width / total)) for width in raw
            ]
            widths = scaled
        else:
            widths = raw
        colors = (Colors.gold, Colors.debug_attack_box, Colors.light_grey)
        return [(width, color) for width, color in zip(widths, colors, strict=True)], sum(widths)

    def paint_attack_timeline(
        self,
        x: int,
        y: int,
        phase: PhaseDefinition,
        widths: list[tuple[int, Color]],
        state: object,
        sub_state: object,
    ) -> None:
        """Paint the phase segments at ``(x, y)`` with a progress outline."""
        cursor = x
        for width, color in widths:
            pygame.draw.rect(
                self.surface,
                color,
                pygame.Rect(cursor, y, width, self.metrics.timeline_bar_height),
            )
            cursor += width
        filled = self.timeline_progress(state, sub_state, phase)
        pygame.draw.rect(
            self.surface,
            Colors.off_white,
            pygame.Rect(x, y, min(filled, cursor - x), self.metrics.timeline_bar_height),
            width=self.stroke(),
        )

    @staticmethod
    def live_attack_text(player: object | None) -> str | None:
        """``name substate frame`` for the player's running attack, if any."""
        combat = getattr(player, "combat", None)
        state = getattr(combat, "state", None)
        name = getattr(state, "attack_name", None)
        if not name:
            return None
        sub_state = getattr(state, "sub_state", "")
        phase = getattr(sub_state, "value", sub_state)
        frame = getattr(state, "frame_counter", 0)
        return f"{name} {phase} f{frame}"

    def timeline_progress(self, state: object, sub_state: object, phase: PhaseDefinition) -> int:
        frame = int(getattr(state, "frame_counter", 0) or 0)
        startup = int(getattr(phase, "startup_frames", 0) or 0)
        active = int(getattr(phase, "active_frames", 0) or 0)
        recovery = int(getattr(phase, "recovery_frames", 0) or 0)
        if sub_state == "startup":
            return min(frame, startup) * self.metrics.timeline_px_per_frame
        if sub_state == "active":
            return (startup + min(frame, active)) * self.metrics.timeline_px_per_frame
        return (startup + active + min(frame, recovery)) * self.metrics.timeline_px_per_frame

    def draw_boxes(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        collider = getattr(sprite, "hitbox", None)
        combat = getattr(sprite, "combat", None)
        attack_boxes = self.offensive_boxes(combat)
        swept_boxes = self.swept_boxes(combat, len(attack_boxes))

        if collider is None:
            reference = getattr(sprite, "rect", None)
            if reference is not None:
                # Hazards, moving platforms, exits: rect-only sprites.
                pygame.draw.rect(
                    self.surface,
                    Colors.debug_static,
                    camera.apply(reference),
                    width=self.stroke(),
                )
            return
        screen = camera.apply(collider)
        # Tier stack for this entity: the health bar (painted after the
        # overlays) plus every annotation already placed this frame. Each
        # text annotation dodges the tiers below it, and is registered so
        # the label cards reserve its band.
        bar = health_bar_rect(self.surface, sprite, screen)
        tiers: list[pygame.Rect] = [bar] if bar is not None else []
        annotations: list[pygame.Rect] = []
        header_rect = self.attack_header_rect(sprite, collider, camera, [*tiers, *annotations])
        if header_rect is not None:
            annotations.append(header_rect)
        pygame.draw.rect(
            self.surface,
            hitbox_color(sprite),
            camera.apply(collider),
            width=self.stroke(),
        )
        # P2 multi-zone: shape tells the story, no text. Empty zones keep the
        # legacy thin outline; boosted zones (mult != 1.0) add a translucent
        # fill + a thicker outline; guarded zones (tags) draw a dashed seal.
        # Names and mults live on the label card's zone row, never in the
        # world — nothing to overlap, whatever the zone count.
        zones = self.hurtbox_zones(sprite, collider)
        mults = self.zone_mults(sprite, len(zones))
        tags = self.zone_tags(sprite, len(zones))
        for index, zone in enumerate(zones):
            color = Colors.debug_hurtbox_zones[index % len(Colors.debug_hurtbox_zones)]
            screen_zone = camera.apply(zone)
            mult = mults[index] if index < len(mults) else 1.0
            zone_tags = tags[index] if index < len(tags) else ()
            if mult != 1.0:
                fill = pygame.Surface(
                    (max(1, int(screen_zone.width)), max(1, int(screen_zone.height))),
                    pygame.SRCALPHA,
                )
                fill.fill((*color, ZONE_FILL_ALPHA))
                self.surface.blit(fill, (screen_zone.x, screen_zone.y))
                pygame.draw.rect(
                    self.surface,
                    color,
                    screen_zone,
                    width=self.metrics.zone_boost_outline,
                )
            else:
                pygame.draw.rect(
                    self.surface,
                    color,
                    screen_zone,
                    width=self.metrics.zone_outline,
                )
            if zone_tags:
                self.draw_zone_seal(screen_zone, color)
        annotations.extend(
            self.draw_offensive_boxes(
                sprite,
                collider,
                combat,
                attack_boxes,
                swept_boxes,
                camera,
                [*tiers, *annotations],
            )
        )
        # Phase 5 markers: OTG guard (cyan) and juggle gravity (purple).
        if float(getattr(sprite, "otg_timer", 0.0) or 0.0) > 0:
            pygame.draw.rect(
                self.surface,
                Colors.debug_otg,
                camera.apply(collider),
                width=3,
            )
        if float(getattr(sprite, "gravity_scale", 1.0) or 1.0) != 1.0:
            pygame.draw.rect(
                self.surface,
                Colors.debug_juggle,
                camera.apply(collider),
                width=2,
            )
        self.register_annotations(sprite, annotations)

    def draw_offensive_boxes(
        self,
        sprite: pygame.sprite.Sprite,
        collider: pygame.FRect | None,
        combat: object,
        attack_boxes: tuple,
        swept_boxes: tuple,
        camera: Camera,
        obstacles: list[pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Outline the attack boxes; dot in-situ indices; spray halo ghosts.

        Box indices ride their own box (a haloed ``●`` top-left corner of each
        box, ``○`` past the first) instead of floating in the tier stack: one
        header chip per attacker, no constellation of pills. Returns the
        in-situ dot rects so the caller can register them for label-card
        placement.
        """
        outline = self.offensive_outline(combat)
        shapes = self.offensive_shapes(combat)
        swept_shapes = self.swept_shapes(combat, len(attack_boxes))
        anchors = self.attack_anchors(combat)
        drawn: list[pygame.Rect] = []
        for index, attack_box in enumerate(attack_boxes):
            swept = swept_boxes[index] if index < len(swept_boxes) else None
            shape = shapes[index] if index < len(shapes) else None
            swept_shape = swept_shapes[index] if index < len(swept_shapes) else None
            anchor = anchors[index] if index < len(anchors) else None
            self.draw_attack_geometry(
                attack_box,
                swept,
                shape,
                swept_shape,
                anchor,
                outline,
                camera,
            )
            screen_box = camera.apply(attack_box)
            drawn.append(
                self.in_situ_dot(
                    (int(screen_box.x) + BOX_DOT_INSET, int(screen_box.y) + BOX_DOT_INSET),
                    outline,
                    filled=index == 0,
                )
            )
        return drawn

    def draw_attack_geometry(
        self,
        attack_box: pygame.FRect,
        swept: pygame.FRect | None,
        shape: ShapePose | None,
        swept_shape: SweptShape | None,
        anchor: tuple[float, float] | None,
        outline: Color,
        camera: Camera,
    ) -> None:
        advanced = shape is not None and shape.kind is not ShapeKind.AABB
        if advanced and shape is not None:
            self.shapes.draw_dashed_rect(camera.apply(attack_box), Colors.debug_broadphase)
        if swept is not None and swept != attack_box and self.box_moved(swept, attack_box):
            self.shapes.draw_dashed_rect(camera.apply(swept), Colors.debug_sweep)
            self.draw_motion_arrow(swept, attack_box, camera)
        if advanced and swept_shape is not None and swept_shape.previous is not None:
            previous = swept_shape.previous
            self.shapes.draw_shape_once(previous, Colors.debug_sweep, camera, 1)
            self.draw_motion_arrow(
                pygame.FRect(
                    previous.position[0] - previous.size[0] / 2.0,
                    previous.position[1] - previous.size[1] / 2.0,
                    previous.size[0],
                    previous.size[1],
                ),
                attack_box,
                camera,
            )
        if advanced and shape is not None:
            self.shapes.draw_shape(shape, outline, camera)
        else:
            pygame.draw.rect(self.surface, outline, camera.apply(attack_box), width=2)
        if anchor is not None:
            self.draw_anchor(anchor, camera)

    def draw_zone_seal(self, screen: pygame.FRect, color: Color) -> None:
        """Dashed inset seal for guarded/armored zones (tags present)."""
        x, y, w, h = screen.x, screen.y, screen.width, screen.height
        inset = self.metrics.zone_boost_outline + 1
        inner = pygame.FRect(x + inset, y + inset, max(0.0, w - inset * 2), max(0.0, h - inset * 2))
        if inner.width <= 0 or inner.height <= 0:
            return
        step = self.metrics.seal_dash + self.metrics.seal_gap
        cursor = inner.x
        while cursor < inner.x + inner.width:
            end = min(cursor + self.metrics.seal_dash, inner.x + inner.width)
            pygame.draw.line(
                self.surface, color, (cursor, inner.y), (end, inner.y), self.metrics.seal_width
            )
            pygame.draw.line(
                self.surface,
                color,
                (cursor, inner.y + inner.height),
                (end, inner.y + inner.height),
                self.metrics.seal_width,
            )
            cursor += step
        cursor = inner.y
        while cursor < inner.y + inner.height:
            end = min(cursor + self.metrics.seal_dash, inner.y + inner.height)
            pygame.draw.line(
                self.surface, color, (inner.x, cursor), (inner.x, end), self.metrics.seal_width
            )
            pygame.draw.line(
                self.surface,
                color,
                (inner.x + inner.width, cursor),
                (inner.x + inner.width, end),
                self.metrics.seal_width,
            )
            cursor += step

    def draw_motion_arrow(self, swept: pygame.FRect, current: pygame.FRect, camera: Camera) -> None:
        start = camera.apply(swept).center
        end = camera.apply(current).center
        delta = Vector2(end) - Vector2(start)
        if delta.length_squared() < 1.0:
            return
        pygame.draw.line(self.surface, Colors.debug_attack_box, start, end)
        direction = delta.normalize()
        normal = Vector2(-direction.y, direction.x)
        tip = Vector2(end)
        left = tip - direction * SWEEP_ARROW_HEAD + normal * SWEEP_ARROW_HEAD
        right = tip - direction * SWEEP_ARROW_HEAD - normal * SWEEP_ARROW_HEAD
        pygame.draw.polygon(
            self.surface, Colors.debug_attack_box, [tuple(tip), tuple(left), tuple(right)]
        )

    def draw_anchor(self, point: tuple[float, float], camera: Camera) -> None:
        center = camera.apply(pygame.FRect(point[0], point[1], 0.0, 0.0)).center
        radius = 5
        pygame.draw.line(
            self.surface,
            Colors.debug_anchor,
            (round(center[0] - radius), round(center[1])),
            (round(center[0] + radius), round(center[1])),
            1,
        )
        pygame.draw.line(
            self.surface,
            Colors.debug_anchor,
            (round(center[0]), round(center[1] - radius)),
            (round(center[0]), round(center[1] + radius)),
            1,
        )

    def register_annotations(self, sprite: pygame.sprite.Sprite, rects: list[pygame.Rect]) -> None:
        """Record an entity's annotation rects for this frame.

        The rects feed both the label-card obstacles and the card clearances,
        so a card reserves the annotation band drawn between the entity and the
        card slot. Registering is the only thing this layer does with them: the
        cards read them, and nothing in this pass reads them back.
        """
        self.sink.register(sprite, rects)

    @staticmethod
    def hurtbox_zones(
        sprite: pygame.sprite.Sprite, collider: pygame.FRect
    ) -> tuple[pygame.FRect, ...]:
        """Hurt outlines to draw: multi-zone list first, legacy single fallback.

        Zones identical to the collider are skipped (the collider outline
        already covers them); a zone equal to the collider would otherwise
        double-draw the same rectangle.
        """
        zones = getattr(sprite, "hurtboxes", None)
        rects = tuple(zones) if zones is not None else (getattr(sprite, "hurtbox", None),)
        return tuple(zone for zone in rects if zone is not None and zone is not collider)

    @staticmethod
    def zone_mults(sprite: pygame.sprite.Sprite, count: int) -> tuple[float, ...]:
        """Per-zone damage mults, neutral 1.0 past the known list."""
        mults = getattr(sprite, "hurtbox_mult", None)
        if not isinstance(mults, tuple):
            return (1.0,) * count
        values = tuple(float(mult) for mult in mults[:count])
        return values + (1.0,) * (count - len(values))

    @staticmethod
    def zone_tags(sprite: pygame.sprite.Sprite, count: int) -> tuple[tuple[str, ...], ...]:
        """Per-zone invulnerability tags, empty past the known list."""
        tags = getattr(sprite, "hurtbox_tags", None)
        if not isinstance(tags, tuple):
            return ((),) * count
        values = tuple(tuple(zone) for zone in tags[:count])
        return values + ((),) * (count - len(values))

    @staticmethod
    def swept_boxes(combat: object, count: int) -> tuple:
        swept = getattr(combat, "swept_attack_boxes", None)
        if callable(swept):
            boxes = tuple(swept())
            if len(boxes) == count:
                return boxes
        return (None,) * count

    @staticmethod
    def swept_shapes(combat: object, count: int) -> tuple[SweptShape | None, ...]:
        shapes = getattr(combat, "swept_attack_shapes", ())
        if not isinstance(shapes, tuple) or len(shapes) != count:
            return (None,) * count
        return shapes

    @staticmethod
    def attack_anchors(combat: object) -> tuple[tuple[float, float], ...]:
        anchors = getattr(combat, "attack_anchors", ())
        return tuple(anchors) if isinstance(anchors, tuple) else ()

    @staticmethod
    def box_moved(swept: pygame.FRect, current: pygame.FRect) -> bool:
        swept_center = Vector2(swept.centerx, swept.centery)
        current_center = Vector2(current.centerx, current.centery)
        if swept_center.distance_to(current_center) >= SWEEP_DISPLAY_MIN_PX:
            return True
        return (
            abs(swept.width - current.width) >= SWEEP_DISPLAY_MIN_PX
            or abs(swept.height - current.height) >= SWEEP_DISPLAY_MIN_PX
        )

    def in_situ_dot(
        self,
        position: tuple[int, int],
        color: Color,
        filled: bool,
    ) -> pygame.Rect:
        """Box-index dot: vector disc in the box corner, ``filled`` = first box.

        An attack may carry several boxes at once; the dot says which is
        which, in code order: the first box (index 0, the one the header's
        leader line points at) gets the solid disc, later boxes the ring.
        The disc is drawn with primitives — dark rim, phase-colored face,
        white core punched out for non-first boxes — never a ``●``/``○``
        font glyph, which rasterizes as a blurry blob at 14 px. The dot
        sits inside its own box corner (``BOX_DOT_INSET``), so it can never
        collide with the header, the card, or a sibling dot.
        """
        center = (
            position[0] + BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
            position[1] + BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
        )
        pygame.draw.circle(
            self.surface,
            BOX_DOT_RIM,
            center,
            BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
        )
        pygame.draw.circle(self.surface, color, center, BOX_DOT_RADIUS)
        if not filled:
            pygame.draw.circle(self.surface, Colors.off_white, center, BOX_DOT_CORE_RADIUS)
        side = (BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH) * 2 + 1
        return pygame.Rect(center[0] - side // 2, center[1] - side // 2, side, side)
