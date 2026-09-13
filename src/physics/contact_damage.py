import pygame

from src.combat.knockback import NULL_KNOCKBACK
from src.core.settings import Combat as CombatSettings
from src.physics.entity_grid import EntityGrid, overlapping_pairs


class ContactDamageSystem:
    """Applies contact damage when entities overlap, based on momentum threshold."""

    def process(
        self,
        entity_sprites: pygame.sprite.Group,
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Process the current state.

        Pair candidates come from the per-tick :class:`EntityGrid` when one
        is provided (O(n · k) instead of the legacy exhaustive O(n²)); pair
        order is preserved, so behaviour is unchanged (see
        :func:`overlapping_pairs`).  Without a grid the pairs are tested
        exhaustively — still correct, just slower.
        """
        entities = list(entity_sprites)

        if entity_grid is not None:
            pairs = overlapping_pairs(entities, entity_grid)
        else:
            pairs = (
                (ent_a, entities[j])
                for i, ent_a in enumerate(entities)
                for j in range(i + 1, len(entities))
            )

        for ent_a, ent_b in pairs:
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
        if not receiver.combat.is_hurt:
            receiver.receive_damage(
                amount=CombatSettings.CONTACT_DAMAGE_AMOUNT,
                source_center_x=source.hitbox.centerx,
                knockback=NULL_KNOCKBACK,
                interrupt=False,
            )
