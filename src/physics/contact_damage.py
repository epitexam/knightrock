import pygame
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings


class ContactDamageSystem:
    """Applies contact damage when entities overlap, based on momentum threshold."""

    def process(self, entity_sprites: pygame.sprite.Group) -> None:
        """Process the current state."""
        entities = list(entity_sprites)

        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1:]:
                if ent_a.is_dead or ent_b.is_dead:
                    continue
                if ent_a.faction == ent_b.faction:
                    continue
                if not ent_a.hitbox.colliderect(ent_b.hitbox):
                    continue

                speed_a = ent_a.velocity.length()
                speed_b = ent_b.velocity.length()

                if max(speed_a, speed_b) < CombatSettings.CONTACT_DAMAGE_THRESHOLD:
                    continue

                if speed_a > speed_b:
                    self._apply_contact_damage(ent_b, ent_a)
                elif speed_b > speed_a:
                    self._apply_contact_damage(ent_a, ent_b)
                else:

                    self._apply_contact_damage(ent_a, ent_b)
                    self._apply_contact_damage(ent_b, ent_a)

    def _apply_contact_damage(self, receiver, source):
        """Internal helper for apply contact damage."""
        null_knockback = KnockbackConfig(power=(0.0, 0.0))

        if not receiver.combat.is_hurt:
            receiver.receive_damage(
                amount=CombatSettings.CONTACT_DAMAGE_AMOUNT,
                source_center_x=source.hitbox.centerx,
                knockback=null_knockback,
                interrupt=False
            )
