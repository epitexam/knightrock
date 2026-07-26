import pygame
from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_MUTED, TEXT_WARN, TEXT_CRIT, TEXT_OK

class WorldUI:
    """Gère le rendu des overlays sur les entités (Hitboxes, barres de vie)."""
    
    def __init__(self, renderer: PanelRenderer):
        self.renderer = renderer
        self.display_surface = renderer.display_surface

    def draw_debug_overlays(self, all_sprites: pygame.sprite.Group, camera: Camera) -> None:
        screen_w = self.display_surface.get_width()
        screen_h = self.display_surface.get_height()

        for sprite in all_sprites:
            hitbox = getattr(sprite, "hitbox", None)
            if hitbox:
                pygame.draw.rect(self.display_surface, (100, 140, 160), camera.apply(hitbox), width=1)

            combat = getattr(sprite, "combat", None)
            if combat and getattr(combat, "attack_box", None):
                pygame.draw.rect(self.display_surface, (170, 120, 80), camera.apply(combat.attack_box), width=2)

            sm = getattr(sprite, "state_machine", None)
            if not sm: continue

            state = sm.current_state_name or "None"
            text = f"{sprite.__class__.__name__}: {state}"

            label_surf = self.renderer.render_text(text, self.renderer.label_font, TEXT_MUTED)
            ref = hitbox if hitbox else getattr(sprite, "rect", None)
            if not ref: continue

            screen_rect = camera.apply(ref)
            label_rect = label_surf.get_rect(midbottom=(screen_rect.centerx, screen_rect.top - 8))

            if label_rect.left < 0: label_rect.left = 0
            if label_rect.right > screen_w: label_rect.right = screen_w
            if label_rect.top < 0: label_rect.top = 0

            bg_rect = label_rect.inflate(12, 6)
            panel = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 20, 24, 210), (0, 0, *bg_rect.size))
            pygame.draw.rect(panel, PANEL_BORDER, (0, 0, *bg_rect.size), width=1)

            self.display_surface.blit(panel, bg_rect.topleft)
            self.display_surface.blit(label_surf, label_rect.topleft)

    def draw_health_bars(self, entities: pygame.sprite.Group | list, camera: Camera) -> None:
        for entity in entities:
            if getattr(entity, "is_dead", False): continue
            max_hp = getattr(entity, "max_health", 0)
            if not max_hp: continue

            hp = getattr(entity, "health", 0)
            rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
            if not rect: continue

            screen_rect = camera.apply(rect)
            bar_width = max(30, min(screen_rect.width * 0.8, 60))
            bar_height = 6

            bar_x = screen_rect.centerx - (bar_width / 2)
            base_offset = 8

            if Debug.ENABLED:
                base_offset += self.renderer.label_font.get_height() + 4

            bar_y = screen_rect.top - base_offset - bar_height
            bg_rect = (bar_x, bar_y, bar_width, bar_height)

            pygame.draw.rect(self.display_surface, (35, 37, 40), bg_rect)

            health_ratio = max(0.0, min(1.0, hp / max_hp))
            health_width = bar_width * health_ratio
            color = TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT

            if health_width > 0:
                pygame.draw.rect(self.display_surface, color, (bar_x, bar_y, health_width, bar_height))

            pygame.draw.rect(self.display_surface, PANEL_BORDER, bg_rect, width=1)