"""World-space UI overlays for entities and combat debugging.

UX rules (debug readability pass):
- Viewport culling: off-screen sprites draw nothing, not even labels.
- Color by faction: blue hitbox = player, red = foe, grey = neutral. Hurtboxes
  stay green, offensive boxes orange, projectiles draw their flight vector.
- Label cards: each datum gets its own row (header, HP, attack, flags), each
  token its own color — name by faction, HP by ratio, attack name in gold,
  every flag in its semantic color. Rows never collapse into one running
  sentence; static geometry (hazards, platforms, exits) gets an outline
  only — no text.
- Vertical stack (debug): entity, then its health bar, then its label card —
  the card floats above the bar and never covers it. Near the top of the
  screen the bar flips below the entity and the card takes the freed space.
- Labels never stack: each label dodges upward (then below its entity) to a
  free slot, and is dropped rather than overdrawn when no slot is left.
- Layers are toggleable at runtime (F1 boxes, F2 labels, F3 velocities,
  F4 statics) via :meth:`WorldUI.toggle`, wired in ``GameplayScene``.
"""

from collections.abc import Iterable

import pygame

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.entities.components.reaction import VELOCITY_KINDS, ReactionStatus
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN

#: Separator between tokens inside one label row (``HP``/``ATK``/``FX``).
#: ``Colors.grey`` (80,85,95) is unreadable on the dark card fill, so labels
#: use a slightly brighter grey that still reads as secondary.
LABEL_SEP: Color = Colors.light_grey

#: Tag introducing a detail row (``HP`` / ``ATK`` / ``FX``): muted grey so the
#: *value* carries the color, never the tag.
LABEL_TAG: Color = TEXT_MUTED

#: Velocity vectors show where the sprite heads in this many seconds.
VELOCITY_PREVIEW_S = 0.15

#: Hide near-stationary drift vectors below this speed (px/s).
VELOCITY_MIN_SPEED = 60.0

#: World margin around the viewport: sprites grazing the edge still draw.
CULL_MARGIN_PX = 64.0

#: Horizontal / vertical padding inside a label card (px per side).
LABEL_PAD_X = 8
LABEL_PAD_Y = 5

#: Gap between the stacked rows of a label card. Rows carry a muted
#: ``HP``/``ATK``/``FX`` tag so the row rhythm stays scannable.
LABEL_LINE_GAP = 5

#: Divider block between the bold header and the detail rows: breathing room
#: above the rule, the 1 px rule itself, then room below it.
LABEL_DIVIDER_TOP = 4
LABEL_DIVIDER_BOTTOM = 5

#: Vertical step a label takes when dodging another label (px). Cards are
#: taller than the legacy one-liners (a two-row card is ~45 px tall with
#: padding), so a dodge may take two steps to clear — the placer tries up to
#: LABEL_MAX_NUDGES steps above, then below, before dropping the label.
LABEL_NUDGE_PX = 28

#: How many dodge steps a label may take above (then below) its entity
#: before being dropped: ~2 label heights of travel is plenty readable.
LABEL_MAX_NUDGES = 6

#: Toggleable overlay layers (F1-F5).
OVERLAY_LAYERS = ("boxes", "labels", "velocities", "statics", "panels")

#: Health bar geometry: bar height, gap entity->bar, gap bar->label card.
#: The bar width stays responsive (80% of the on-screen sprite width,
#: clamped to [30, 60] px and to the viewport); only the vertical rhythm
#: is fixed so the stack entity -> bar -> card never overlaps.
HEALTH_BAR_HEIGHT = 6
HEALTH_BAR_ANCHOR_GAP = 8
HEALTH_BAR_LABEL_GAP = 4

#: Gap between an entity edge and its label card when no health bar sits
#: between them (statics, projectiles, or labels layer with bars hidden).
LABEL_ANCHOR_GAP = 8

#: One label row: ``(text, color)`` tokens laid out left to right.
_Segments = list[list[tuple[str, Color]]]

#: A collected label: sort key, colored rows, faction accent, screen
#: anchor, clearance above (bar above the entity) and below (bar flipped
#: under the entity near the top of the screen).
_LabelRequest = tuple[tuple[int, float, float], _Segments, Color, pygame.FRect, int, int]


def join_flag_tokens(flags: list[tuple[str, Color]]) -> list[tuple[str, Color]]:
    """Interleave flag tokens with a bright ``|`` separator."""
    joined: list[tuple[str, Color]] = [flags[0]]
    for text, color in flags[1:]:
        joined.append((" | ", LABEL_SEP))
        joined.append((text, color))
    return joined


class WorldUI:
    """Render health bars and optional world-space diagnostics."""

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        self.display_surface = renderer.display_surface
        self.layers: dict[str, bool] = dict.fromkeys(OVERLAY_LAYERS, True)

    def toggle(self, layer: str) -> bool:
        """Flip an overlay layer, returning its new state."""
        if layer not in self.layers:
            raise KeyError(f"Unknown overlay layer: {layer!r}")
        self.layers[layer] = not self.layers[layer]
        return self.layers[layer]

    def draw_debug_overlays(
        self, all_sprites: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> None:
        viewport = self._viewport(camera)
        screen_width = self.display_surface.get_width()

        # Labels are collected first and drawn after the loop so they can
        # dodge each other instead of stacking on shared screen space.
        requests: list[_LabelRequest] = []
        for sprite in all_sprites:
            if type(sprite) is pygame.sprite.Sprite:
                continue  # static tiles: ~900/level, nothing useful to show
            reference = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
            if reference is None or not viewport.colliderect(reference):
                continue  # culled: off-screen, not worth a single pixel
            is_static = getattr(sprite, "hitbox", None) is None
            if is_static and not self.layers["statics"]:
                continue
            if self.layers["boxes"]:
                self._draw_boxes(sprite, camera)
            if self.layers["velocities"]:
                self._draw_velocity(sprite, camera)
            if not self.layers["labels"] or is_static:
                continue
            segments = self._label_segments(sprite)
            if segments is None:
                continue
            anchor = camera.apply(reference)
            priority = self._label_priority(sprite, anchor)
            above_lift, below_drop = self._label_clearances(sprite, anchor)
            requests.append(
                (priority, segments, self._label_color(sprite), anchor, above_lift, below_drop)
            )

        if requests:
            requests.sort(key=lambda request: request[0])
            self._draw_labels(requests, screen_width)

    @staticmethod
    def _viewport(camera: Camera) -> pygame.Rect:
        offset = getattr(camera, "offset", pygame.math.Vector2(0, 0))
        width = float(getattr(camera, "width", 0) or 0)
        height = float(getattr(camera, "height", 0) or 0)
        if width <= 0 or height <= 0:
            surface = pygame.display.get_surface()
            width, height = (surface.get_width(), surface.get_height()) if surface else (0, 0)
        return pygame.Rect(
            offset.x - CULL_MARGIN_PX,
            offset.y - CULL_MARGIN_PX,
            width + 2 * CULL_MARGIN_PX,
            height + 2 * CULL_MARGIN_PX,
        )

    @staticmethod
    def _display_name(sprite: pygame.sprite.Sprite) -> str:
        """Header name: the enemy registry type for foes, the class otherwise.

        Every foe shares the ``Enemy`` class, so the class name says nothing —
        the stored ``enemy_type`` (``"goblin"``, ``"slime"``, ...) does. Other
        factions keep their class name, and typeless enemies fall back to it.
        """
        if WorldUI._faction(sprite) == "enemy":
            return getattr(sprite, "enemy_type", None) or type(sprite).__name__
        return type(sprite).__name__

    @staticmethod
    def _faction(sprite: pygame.sprite.Sprite) -> str | None:
        return getattr(sprite, "faction", None)

    def _hitbox_color(self, sprite: pygame.sprite.Sprite) -> Color:
        faction = self._faction(sprite)
        if faction == "enemy":
            return Colors.red
        if faction == "player":
            return Colors.debug_hitbox
        return Colors.light_grey

    def _label_color(self, sprite: pygame.sprite.Sprite) -> Color:
        if getattr(sprite, "state_machine", None) is None:
            return Colors.yellow  # projectiles
        faction = self._faction(sprite)
        if faction == "enemy":
            return Colors.light_red
        if faction == "player":
            return Colors.light_green
        return Colors.text_muted

    @staticmethod
    def _health_color(health: float, max_health: float) -> Color:
        """HP tint by remaining ratio: green, then warn orange, then crit red."""
        ratio = health / max_health if max_health else 0.0
        if ratio <= 0.25:
            return TEXT_CRIT
        if ratio <= 0.5:
            return TEXT_WARN
        return TEXT_OK

    def _draw_boxes(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        collider = getattr(sprite, "hitbox", None)
        hurtbox = getattr(sprite, "hurtbox", None)
        combat = getattr(sprite, "combat", None)
        attack_boxes = getattr(combat, "attack_boxes", None)
        if attack_boxes is None:
            legacy_box = getattr(combat, "attack_box", None)
            attack_boxes = (legacy_box,) if legacy_box is not None else ()

        if collider is None:
            reference = getattr(sprite, "rect", None)
            if reference is not None:
                # Hazards, moving platforms, exits: rect-only sprites.
                pygame.draw.rect(
                    self.display_surface,
                    Colors.debug_static,
                    camera.apply(reference),
                    width=1,
                )
            return
        pygame.draw.rect(
            self.display_surface,
            self._hitbox_color(sprite),
            camera.apply(collider),
            width=1,
        )
        if hurtbox is not None and hurtbox is not collider:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_hurtbox,
                camera.apply(hurtbox),
                width=1,
            )
        for attack_box in attack_boxes:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_attack_box,
                camera.apply(attack_box),
                width=2,
            )
        # Phase 5 markers: OTG guard (cyan) and juggle gravity (purple).
        if float(getattr(sprite, "otg_timer", 0.0) or 0.0) > 0:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_otg,
                camera.apply(collider),
                width=3,
            )
        if float(getattr(sprite, "gravity_scale", 1.0) or 1.0) != 1.0:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_juggle,
                camera.apply(collider),
                width=2,
            )

    def _draw_velocity(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        velocity = getattr(sprite, "velocity", None)
        if velocity is None:
            return
        try:
            vx, vy = float(velocity.x), float(velocity.y)
        except AttributeError, TypeError:
            return
        if vx * vx + vy * vy < VELOCITY_MIN_SPEED * VELOCITY_MIN_SPEED:
            return
        origin = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
        if origin is None:
            return
        start = camera.apply(origin).center
        end = (start[0] + vx * VELOCITY_PREVIEW_S, start[1] + vy * VELOCITY_PREVIEW_S)
        color = Colors.debug_velocity
        if self._is_reaction_push(sprite):
            color = Colors.red  # reaction push vector, not locomotion
        pygame.draw.line(self.display_surface, color, start, end, width=2)
        pygame.draw.circle(self.display_surface, color, end, 2)

    @staticmethod
    def _is_reaction_push(sprite: pygame.sprite.Sprite) -> bool:
        """Whether the vector shows a fresh hit-reaction push (red), not locomotion.

        Reads the typed ``ReactionStatus`` cause — never a state-machine name
        — so the overlay cannot diverge from the reaction that applied the
        velocity.
        """
        status = getattr(sprite, "reaction_status", None)
        if not isinstance(status, ReactionStatus):
            return False
        return (
            float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0.0
            and status.kind in VELOCITY_KINDS
        )

    def _label_lines(self, sprite: pygame.sprite.Sprite) -> list[str] | None:
        segments = self._label_segments(sprite)
        if segments is None:
            return None
        return [" ".join(text.strip() for text, _ in line) for line in segments]

    def _label_segments(self, sprite: pygame.sprite.Sprite) -> _Segments | None:
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            return self._entity_segments(sprite, state_machine)
        if getattr(sprite, "hitbox", None) is not None:
            return [[(self._projectile_line(sprite), Colors.yellow)]]
        return None

    def _entity_segments(self, sprite: pygame.sprite.Sprite, state_machine) -> _Segments:
        """One row per datum, every token paired with its display color.

        - header: faction-colored name (the enemy registry type for foes,
          the class name otherwise) plus off-white state
        - ``HP`` row: value tinted by the health ratio
        - ``ATK`` row (while attacking): gold name, muted phase stats
        - ``FX`` row (active flags only): each flag in its semantic color,
          ``|``-separated
        """
        faction_color = self._label_color(sprite)
        state_name = state_machine.current_state_name or "None"
        lines: _Segments = [
            [(f"{self._display_name(sprite)} ", faction_color), (state_name, Colors.off_white)]
        ]
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            lines.append(
                [
                    ("HP ", LABEL_TAG),
                    (f"{health:.0f}/{max_health:.0f}", self._health_color(health, max_health)),
                ]
            )

        attack_line = self._attack_line(sprite)
        if attack_line is not None:
            lines.append(attack_line)

        flags = self._status_flag_tokens(sprite)
        if flags:
            lines.append([("FX ", LABEL_TAG), *join_flag_tokens(flags)])
        return lines

    def _attack_line(self, sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]] | None:
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

    @staticmethod
    def _status_flag_tokens(sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]]:
        """Colored status flags for the ``FX`` card row (same order as strings)."""
        names = WorldUI._status_flag_strings(sprite)
        colors: dict[str, Color] = {}
        reaction = WorldUI._reaction_flag(sprite)
        if reaction is not None:
            colors[reaction] = (
                Colors.red
                if float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0
                else Colors.dark_red
            )
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            colors[f"STAG {stagger:.2f}"] = Colors.orange
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            colors[f"OTG {otg:.2f}"] = Colors.debug_otg
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            colors[f"JGx{gravity_scale:.2f}"] = Colors.debug_juggle
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            colors["AIR"] = Colors.light_grey
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            colors["LEDGE"] = Colors.yellow
        return [(name, colors.get(name, Colors.off_white)) for name in names]

    @staticmethod
    def _reaction_flag(sprite: pygame.sprite.Sprite) -> str | None:
        """Label token for the last hit-reaction cause (kind + freshness).

        Reads the typed ``ReactionStatus`` — never a state-machine name.
        ``RX`` marks a fresh reaction with its remaining freshness window;
        ``RX~`` marks a stale cause whose freshness has expired.
        """
        reaction = getattr(sprite, "reaction_status", None)
        if not isinstance(reaction, ReactionStatus):
            return None
        age = float(getattr(sprite, "reaction_age", 0.0) or 0.0)
        if age > 0:
            return f"RX {reaction.kind.value} {age:.2f}"
        return f"RX~ {reaction.kind.value}"

    @staticmethod
    def _status_flag_strings(sprite: pygame.sprite.Sprite) -> list[str]:
        """Plain-text status flags backing ``_entity_lines`` (ledge tests, docs)."""
        flags: list[str] = []
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            flags.append(f"STAG {stagger:.2f}")
        reaction_flag = WorldUI._reaction_flag(sprite)
        if reaction_flag is not None:
            flags.append(reaction_flag)
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            flags.append(f"OTG {otg:.2f}")
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            flags.append(f"JGx{gravity_scale:.2f}")
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            flags.append("AIR")
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            flags.append("LEDGE")
        return flags

    @staticmethod
    def _entity_lines(sprite: pygame.sprite.Sprite, state_machine) -> list[str]:
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
        flags = WorldUI._status_flag_strings(sprite)
        if flags:
            detail.append(" ".join(flags))
        return [head, *detail]

    @staticmethod
    def _projectile_line(sprite: pygame.sprite.Sprite) -> str:
        velocity = getattr(sprite, "velocity", None)
        vel = f"({velocity.x:.0f},{velocity.y:.0f})" if velocity is not None else "(?,?)"
        life = float(getattr(sprite, "life", 0.0) or 0.0)
        pierce = "pierce" if getattr(getattr(sprite, "config", None), "pierce", False) else "single"
        hits = len(getattr(sprite, "targets_hit", ()))
        faction = getattr(sprite, "faction", "?")
        return f"{type(sprite).__name__} {faction} {vel} {life:.1f}s {pierce} hits:{hits}"

    @staticmethod
    def _label_priority(
        sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, float, float]:
        """Placement order: the player reads first, then top-to-bottom."""
        player_first = 0 if WorldUI._faction(sprite) == "player" else 1
        return (player_first, float(anchor.top), float(anchor.left))

    @staticmethod
    def _has_health_bar(sprite: pygame.sprite.Sprite) -> bool:
        """Whether ``draw_health_bars`` will draw a bar for this sprite."""
        if getattr(sprite, "is_dead", False):
            return False
        if not getattr(sprite, "max_health", 0):
            return False
        return (
            getattr(sprite, "hitbox", None) is not None or getattr(sprite, "rect", None) is not None
        )

    def _health_bar_rect(
        self, sprite: pygame.sprite.Sprite, screen_rect: pygame.Rect | pygame.FRect
    ) -> pygame.Rect | None:
        """Responsive health bar rect: width follows the sprite, clamped.

        The bar sits ``HEALTH_BAR_ANCHOR_GAP`` above the entity; near the
        top of the screen (no room above) it flips below the entity so it
        stays visible instead of clipping. Returns ``None`` for sprites
        without a bar (dead, no ``max_health``, statics).
        """
        if not self._has_health_bar(sprite):
            return None
        screen_width = self.display_surface.get_width()
        screen_height = self.display_surface.get_height()
        bar_width = max(30, min(float(screen_rect.width) * 0.8, 60))
        bar_x = screen_rect.centerx - bar_width / 2
        bar_x = min(max(bar_x, 0), max(0, screen_width - bar_width))
        bar_y = float(screen_rect.top) - HEALTH_BAR_ANCHOR_GAP - HEALTH_BAR_HEIGHT
        if bar_y < 0:
            bar_y = float(screen_rect.bottom) + HEALTH_BAR_ANCHOR_GAP
            if bar_y + HEALTH_BAR_HEIGHT > screen_height:
                return None
        return pygame.Rect(int(bar_x), int(bar_y), int(bar_width), HEALTH_BAR_HEIGHT)

    def _label_clearances(
        self, sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, int]:
        """Vertical room the label card must leave for the health bar.

        Returns ``(above_lift, below_drop)``: when the bar sits above the
        entity the card's default slot moves up by bar + gap; when the bar
        flipped below (top of screen) the below-slots move down instead.
        ``(0, 0)`` when no bar is drawn.
        """
        bar = self._health_bar_rect(sprite, anchor)
        if bar is None:
            return (0, 0)
        # The padded card sticks out LABEL_PAD_Y below its content box, so
        # the lift reserves bar + gap + padding: backgrounds touch neither
        # the bar nor each other.
        clearance = HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + LABEL_PAD_Y
        if bar.bottom <= anchor.top:
            return (clearance, 0)
        return (0, clearance)

    def _draw_labels(
        self,
        requests: list[_LabelRequest],
        screen_width: int,
    ) -> None:
        """Draw collected labels, each dodging the ones already placed."""
        screen_height = self.display_surface.get_height()
        placed: list[pygame.Rect] = []
        for _priority, segments, color, anchor, above_lift, below_drop in requests:
            rect = self._place_label(
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

    def _place_label(
        self,
        segments: _Segments,
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
        does the same when the bar flipped under the entity. Returns the
        padded rect the card occupies, or ``None`` when every slot is taken
        or off-screen — a dropped label beats an unreadable stack.
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
        divider_block = LABEL_DIVIDER_TOP + 1 + LABEL_DIVIDER_BOTTOM
        height = (
            row_height * (len(rows) + 1) + LABEL_LINE_GAP * len(rows) + divider_block
            if rows
            else row_height
        )
        base = pygame.Rect(0, 0, width, height)
        base.midbottom = (anchor.centerx, anchor.top - LABEL_ANCHOR_GAP - above_lift)
        for label_rect in self._candidate_slots(
            base, anchor, screen_width, screen_height, below_drop=below_drop
        ):
            background_rect = label_rect.inflate(LABEL_PAD_X * 2, LABEL_PAD_Y * 2)
            if all(not background_rect.colliderect(other) for other in placed):
                self._blit_label(
                    header, rows, row_height, color, label_rect, background_rect, screen_width
                )
                return background_rect
        return None

    @staticmethod
    def _candidate_slots(
        base: pygame.Rect,
        anchor: pygame.Rect | pygame.FRect,
        screen_width: int,
        screen_height: int,
        below_drop: int = 0,
    ) -> list[pygame.Rect]:
        """Slots to try, best first: above the entity, then below it."""
        below = base.copy()
        below.midtop = (anchor.centerx, anchor.bottom + LABEL_ANCHOR_GAP + below_drop)
        slots = [base]
        slots.extend(
            base.move(0, -LABEL_NUDGE_PX * step) for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        slots.append(below)
        slots.extend(
            below.move(0, LABEL_NUDGE_PX * step) for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        kept: list[pygame.Rect] = []
        for slot in slots:
            # The padded card sticks out LABEL_PAD_Y px on every side: keep slots
            # whose *card* stays fully on-screen.
            if slot.top - LABEL_PAD_Y < 0 or slot.bottom + LABEL_PAD_Y > screen_height:
                continue  # off-screen: not a real option
            slot.left = max(0, slot.left)
            slot.right = min(screen_width, slot.right)
            kept.append(slot)
        return kept

    def _blit_label(
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
        self.display_surface.blit(panel, background_rect.topleft)
        # Top accent edge in the entity's faction color: a 2 px rule just
        # inside the top border, spanning the card width. It marks the
        # faction at a glance without cutting through the card and its
        # divider the way a full-height side stripe did.
        accent_edge = pygame.Rect(
            background_rect.left + 1,
            background_rect.top + 1,
            background_rect.width - 2,
            2,
        )
        self.display_surface.fill(accent, accent_edge)
        # Header row (bold).
        cursor_x = label_rect.left
        cursor_y = label_rect.top
        for surface in header:
            self.display_surface.blit(surface, (cursor_x, cursor_y))
            cursor_x += surface.get_width()
        cursor_y += row_height + LABEL_DIVIDER_TOP
        # Divider rule, inset by the card padding.
        rule_left = max(background_rect.left + LABEL_PAD_X, 0)
        rule_right = min(background_rect.right - LABEL_PAD_X, screen_width)
        if rule_right > rule_left:
            pygame.draw.line(
                self.display_surface,
                PANEL_BORDER,
                (rule_left, cursor_y),
                (rule_right, cursor_y),
                1,
            )
        cursor_y += 1 + LABEL_DIVIDER_BOTTOM
        for line in rows:
            cursor_x = label_rect.left
            for surface in line:
                self.display_surface.blit(surface, (cursor_x, cursor_y))
                cursor_x += surface.get_width()
            cursor_y += row_height + LABEL_LINE_GAP

    def draw_health_bars(self, entities: Iterable[pygame.sprite.Sprite], camera: Camera) -> None:
        for entity in entities:
            max_health = getattr(entity, "max_health", 0)
            if not max_health:
                continue

            health = getattr(entity, "health", 0)
            rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
            if rect is None:
                continue

            screen_rect = camera.apply(rect)
            background_rect = self._health_bar_rect(entity, screen_rect)
            if background_rect is None:
                continue

            pygame.draw.rect(self.display_surface, (35, 37, 40), background_rect)
            health_ratio = max(0.0, min(1.0, health / max_health))
            health_width = background_rect.width * health_ratio
            color = (
                TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT
            )
            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    (background_rect.x, background_rect.y, health_width, background_rect.height),
                )
            pygame.draw.rect(self.display_surface, PANEL_BORDER, background_rect, width=1)
