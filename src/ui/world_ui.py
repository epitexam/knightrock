"""World-space UI overlays for entities and combat debugging.

UX rules (debug readability pass):
- Viewport culling: off-screen sprites draw nothing, not even labels.
- Color by faction: blue hitbox = player, red = foe, grey = neutral. Hurtboxes
  stay green, offensive boxes orange, projectiles draw their flight vector.
- Label hierarchy: one short line by default (class + state + HP); a second
  line only while attacking or while a status flag (stagger/OTG/juggle/air)
  is active. Static geometry (hazards, platforms, exits) gets an outline
  only — no text.
- Labels never stack: each label dodges upward (then below its entity) to a
  free slot, and is dropped rather than overdrawn when no slot is left.
- Layers are toggleable at runtime (F1 boxes, F2 labels, F3 velocities,
  F4 statics) via :meth:`WorldUI.toggle`, wired in ``GameplayScene``.
"""

from collections.abc import Iterable

import pygame

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.entities.components.reaction import VELOCITY_KINDS, ReactionStatus
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_OK, TEXT_WARN

#: Velocity vectors show where the sprite heads in this many seconds.
VELOCITY_PREVIEW_S = 0.15

#: Hide near-stationary drift vectors below this speed (px/s).
VELOCITY_MIN_SPEED = 60.0

#: World margin around the viewport: sprites grazing the edge still draw.
CULL_MARGIN_PX = 64.0

#: Vertical step a label takes when dodging another label (px). A one-line
#: panel is 22 px tall (16 px font + padding): one step leaves a >= 6 px gap.
LABEL_NUDGE_PX = 28

#: How many dodge steps a label may take above (then below) its entity
#: before being dropped: ~2 label heights of travel is plenty readable.
LABEL_MAX_NUDGES = 6

#: Toggleable overlay layers (F1-F5).
OVERLAY_LAYERS = ("boxes", "labels", "velocities", "statics", "panels")


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
        requests: list[tuple[int, float, float, list[str], Color, pygame.FRect]] = []
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
            lines = self._label_lines(sprite)
            if not lines:
                continue
            anchor = camera.apply(reference)
            priority = self._label_priority(sprite, anchor)
            requests.append((*priority, lines, self._label_color(sprite), anchor))

        if requests:
            requests.sort(key=lambda request: request[:3])
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
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            return self._entity_lines(sprite, state_machine)
        if getattr(sprite, "hitbox", None) is not None:
            return [self._projectile_line(sprite)]
        return None

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

    def _draw_labels(
        self,
        requests: list[tuple[int, float, float, list[str], Color, pygame.FRect]],
        screen_width: int,
    ) -> None:
        """Draw collected labels, each dodging the ones already placed."""
        screen_height = self.display_surface.get_height()
        placed: list[pygame.Rect] = []
        for _, _, _, lines, color, anchor in requests:
            rect = self._place_label(lines, color, anchor, placed, screen_width, screen_height)
            if rect is not None:
                placed.append(rect)

    def _place_label(
        self,
        lines: list[str],
        color: Color,
        anchor: pygame.Rect | pygame.FRect,
        placed: list[pygame.Rect],
        screen_width: int,
        screen_height: int,
    ) -> pygame.Rect | None:
        """Render a label in the first free slot near its entity.

        Slots run above the entity (nudging upward), then below it (nudging
        downward). Returns the padded rect the label occupies, or ``None``
        when every slot is taken or off-screen — a dropped label beats an
        unreadable stack.
        """
        font = self.renderer.label_font
        rendered = [self.renderer.render_text(line, font, color) for line in lines]
        width = max(surface.get_width() for surface in rendered)
        height = sum(surface.get_height() for surface in rendered) + 4 * (len(rendered) - 1)
        base = pygame.Rect(0, 0, width, height)
        base.midbottom = (anchor.centerx, anchor.top - 8)
        for label_rect in self._candidate_slots(base, anchor, screen_width, screen_height):
            background_rect = label_rect.inflate(12, 6)
            if all(not background_rect.colliderect(other) for other in placed):
                self._blit_label(rendered, label_rect, background_rect)
                return background_rect
        return None

    @staticmethod
    def _candidate_slots(
        base: pygame.Rect,
        anchor: pygame.Rect | pygame.FRect,
        screen_width: int,
        screen_height: int,
    ) -> list[pygame.Rect]:
        """Slots to try, best first: above the entity, then below it."""
        below = base.copy()
        below.midtop = (anchor.centerx, anchor.bottom + 8)
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
            # The padded panel sticks out 3 px on every side: keep slots whose
            # *panel* stays fully on-screen.
            if slot.top - 3 < 0 or slot.bottom + 3 > screen_height:
                continue  # off-screen: not a real option
            slot.left = max(0, slot.left)
            slot.right = min(screen_width, slot.right)
            kept.append(slot)
        return kept

    def _blit_label(
        self,
        rendered: list[pygame.Surface],
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
    ) -> None:
        """Blit the padded panel and the text lines at a resolved position."""
        panel = pygame.Surface(background_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (18, 20, 24, 210), panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.display_surface.blit(panel, background_rect.topleft)
        cursor_y = label_rect.top
        for surface in rendered:
            self.display_surface.blit(surface, (label_rect.left, cursor_y))
            cursor_y += surface.get_height() + 4

    def draw_health_bars(self, entities: Iterable[pygame.sprite.Sprite], camera: Camera) -> None:
        for entity in entities:
            if getattr(entity, "is_dead", False):
                continue
            max_health = getattr(entity, "max_health", 0)
            if not max_health:
                continue

            health = getattr(entity, "health", 0)
            rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
            if rect is None:
                continue

            screen_rect = camera.apply(rect)
            bar_width = max(30, min(screen_rect.width * 0.8, 60))
            bar_height = 6
            bar_x = screen_rect.centerx - bar_width / 2
            base_offset = 8
            if Debug.is_enabled():
                base_offset += self.renderer.label_font.get_height() + 4
            bar_y = screen_rect.top - base_offset - bar_height
            background_rect = (bar_x, bar_y, bar_width, bar_height)

            pygame.draw.rect(self.display_surface, (35, 37, 40), background_rect)
            health_ratio = max(0.0, min(1.0, health / max_health))
            health_width = bar_width * health_ratio
            color = (
                TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT
            )
            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    (bar_x, bar_y, health_width, bar_height),
                )
            pygame.draw.rect(self.display_surface, PANEL_BORDER, background_rect, width=1)
