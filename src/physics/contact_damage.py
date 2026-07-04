import pygame

from src.combat.attack_types import KnockbackConfig


class ContactDamageSystem:
    """Applies contact damage when entities overlap, independent of separation."""

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

                self._apply_contact_damage(ent_a, ent_b)

    def _apply_contact_damage(self, ent_a, ent_b):
        """Internal helper for apply contact damage."""
        null_knockback = KnockbackConfig(power=(0.0, 0.0))
        for receiver, source in ((ent_a, ent_b), (ent_b, ent_a)):
            if not receiver.combat.is_hurt and source.combat.contact_damage > 0:
                receiver.receive_damage(
                    source.combat.contact_damage,
                    source_center_x=source.hitbox.centerx,
                    knockback=null_knockback
                )
