"""Hazard contact damage system (saws, spikes, floor spikes)."""

from collections.abc import Iterable

from src.combat.knockback import KnockbackConfig


class HazardDamageSystem:
    """Apply configured damage to entities overlapping an active hazard.

    The per-hazard ``damage``/``knockback`` attributes take precedence when
    present (they can be set through the TMX ``damage`` object property).
    """

    DEFAULT_DAMAGE = 20.0
    DEFAULT_KNOCKBACK = KnockbackConfig(power=(150.0, -60.0))

    def process(self, entity_sprites: Iterable, hazard_sprites: Iterable) -> None:
        """Apply damage for every overlap between a hazard and a live entity."""
        for hazard in hazard_sprites:
            box = getattr(hazard, "hitbox", getattr(hazard, "rect", None))
            if box is None:
                continue

            damage = float(getattr(hazard, "damage", self.DEFAULT_DAMAGE))
            knockback = getattr(hazard, "knockback", self.DEFAULT_KNOCKBACK)

            for entity in entity_sprites:
                if getattr(entity, "is_dead", False):
                    continue
                if not box.colliderect(entity.hitbox):
                    continue
                entity.receive_damage(
                    amount=damage,
                    source_center_x=box.centerx,
                    knockback=knockback,
                    interrupt=False,
                )