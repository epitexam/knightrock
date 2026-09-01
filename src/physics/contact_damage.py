import pygame
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.physics.spatial_hash import SpatialHash


class ContactDamageSystem:
    """Applies contact damage when entities overlap, based on momentum threshold."""

    def process(self, entity_sprites: pygame.sprite.Group, spatial_hash: SpatialHash | None = None) -> None:
        """Process the current state.
        
        If spatial_hash is provided, only checks entities in nearby cells.
        Falls back to O(n^2) check if spatial_hash is None (PERF-02).
        """
        entities = list(entity_sprites)

        # If spatial hash is available, only check entities in nearby cells
        if spatial_hash is not None:
            # Get all entities from spatial hash cells
            all_entities_in_hash = []
            for cell, sprites in spatial_hash.grid.items():
                for sprite in sprites:
                    if sprite in entities and sprite not in all_entities_in_hash:
                        all_entities_in_hash.append(sprite)
            entities = all_entities_in_hash

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
