"""
Resolves physical overlaps between entities and handles contact damage.
"""

import pygame
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.entities.entity import Entity


class SeparationSystem:
    """Separates overlapping entities and applies contact damage if configured."""

    def process(self, entity_sprites: pygame.sprite.Group) -> None:
        entities = list(entity_sprites)

        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1 :]:
                if type(ent_a) is type(ent_b):
                    continue

                if not ent_a.hitbox.colliderect(ent_b.hitbox):
                    continue

                if not ent_a.combat.is_hurt and ent_b.combat.contact_damage > 0:
                    ent_a.combat.take_damage(
                        ent_b.combat.contact_damage,
                        source_center_x=ent_b.hitbox.centerx,
                    )
                elif not ent_b.combat.is_hurt and ent_a.combat.contact_damage > 0:
                    ent_b.combat.take_damage(
                        ent_a.combat.contact_damage,
                        source_center_x=ent_a.hitbox.centerx,
                    )

                overlap_x = min(ent_a.hitbox.right, ent_b.hitbox.right) - max(
                    ent_a.hitbox.left, ent_b.hitbox.left
                )
                overlap_y = min(ent_a.hitbox.bottom, ent_b.hitbox.bottom) - max(
                    ent_a.hitbox.top, ent_b.hitbox.top
                )

                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                if overlap_x <= overlap_y:
                    dir_a = -1.0 if ent_a.hitbox.centerx < ent_b.hitbox.centerx else 1.0
                    dir_b = -dir_a
                    if ent_a.pushable and ent_b.pushable:
                        ent_a.hitbox.x += (overlap_x / 2.0) * dir_a
                        ent_b.hitbox.x += (overlap_x / 2.0) * dir_b
                    elif ent_a.pushable:
                        ent_a.hitbox.x += overlap_x * dir_a
                    elif ent_b.pushable:
                        ent_b.hitbox.x += overlap_x * dir_b
                else:
                    dir_a = -1.0 if ent_a.hitbox.centery < ent_b.hitbox.centery else 1.0
                    dir_b = -dir_a
                    if ent_a.pushable and ent_b.pushable:
                        ent_a.hitbox.y += (overlap_y / 2.0) * dir_a
                        ent_b.hitbox.y += (overlap_y / 2.0) * dir_b
                    elif ent_a.pushable:
                        ent_a.hitbox.y += overlap_y * dir_a
                    elif ent_b.pushable:
                        ent_b.hitbox.y += overlap_y * dir_b

                ent_a.sync_rects()
                ent_b.sync_rects()
