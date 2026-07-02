import pygame


class SeparationSystem:
    """Resolves physical overlaps between entities (no damage logic)."""

    def process(self, entity_sprites: pygame.sprite.Group) -> None:
        """Process the current state."""
        entities = list(entity_sprites)

        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1 :]:
                if ent_a.faction == ent_b.faction:
                    continue

                if not ent_a.hitbox.colliderect(ent_b.hitbox):
                    continue

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
