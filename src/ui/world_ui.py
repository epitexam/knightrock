"""World-space UI overlays for entities and combat debugging."""

from collections.abc import Iterable

import pygame

from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN


class WorldUI:
    """Render health bars and optional world-space diagnostics."""

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        self.display_surface = renderer.display_surface

    def draw_debug_overlays(
        self, all_sprites: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> None:
        screen_width = self.display_surface.get_width()

        for sprite in all_sprites:
            collider = getattr(sprite, "hitbox", None)
            hurtbox = getattr(sprite, "hurtbox", None)
            combat = getattr(sprite, "combat", None)
            attack_box = getattr(combat, "attack_box", None)

            if collider is not None:
                pygame.draw.rect(
                    self.display_surface,
                    (80, 140, 210),
                    camera.apply(collider),
                    width=1,
                )
            if hurtbox is not None:
                pygame.draw.rect(
                    self.display_surface,
                    (80, 210, 120),
                    camera.apply(hurtbox),
                    width=1,
                )
            if attack_box is not None:
                pygame.draw.rect(
                    self.display_surface,
                    (230, 120, 60),
                    camera.apply(attack_box),
                    width=2,
                )

            state_machine = getattr(sprite, "state_machine", None)
            if state_machine is None:
                continue

            label = self._debug_label(sprite, state_machine, combat)
            label_surface = self.renderer.render_text(
                label, self.renderer.label_font, TEXT_MUTED
            )
            reference = collider or getattr(sprite, "rect", None)
            if reference is None:
                continue

            screen_rect = camera.apply(reference)
            label_rect = label_surface.get_rect(
                midbottom=(screen_rect.centerx, screen_rect.top - 8)
            )
            label_rect.left = max(0, label_rect.left)
            label_rect.right = min(screen_width, label_rect.right)
            label_rect.top = max(0, label_rect.top)

            background_rect = label_rect.inflate(12, 6)
            panel = pygame.Surface(background_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 20, 24, 210), panel.get_rect())
            pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
            self.display_surface.blit(panel, background_rect.topleft)
            self.display_surface.blit(label_surface, label_rect.topleft)

    @staticmethod
    def _debug_label(sprite, state_machine, combat) -> str:
        state_name = state_machine.current_state_name or "None"
        label = f"{sprite.__class__.__name__}: {state_name}"
        attack_state = getattr(combat, "state", None)
        attack_name = getattr(attack_state, "attack_name", None)
        if attack_name is None:
            return label

        sub_state = getattr(attack_state, "sub_state", None)
        sub_state_name = getattr(sub_state, "value", sub_state)
        phase_index = getattr(attack_state, "phase_index", 0)
        frame_counter = getattr(attack_state, "frame_counter", 0)
        target_count = len(getattr(combat, "targets_hit", ()))
        return (
            f"{label} | {attack_name} p{phase_index} "
            f"{sub_state_name}:{frame_counter} hits:{target_count}"
        )

    def draw_health_bars(
        self, entities: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> None:
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
                TEXT_OK
                if health_ratio > 0.5
                else TEXT_WARN
                if health_ratio > 0.25
                else TEXT_CRIT
            )
            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    (bar_x, bar_y, health_width, bar_height),
                )
            pygame.draw.rect(
                self.display_surface, PANEL_BORDER, background_rect, width=1
            )
