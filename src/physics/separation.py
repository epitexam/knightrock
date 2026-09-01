import pygame
from src.core.settings import Separation as Sep
from src.physics.spatial_hash import SpatialHash


class SeparationSystem:
    def process(self, entity_sprites: pygame.sprite.Group, spatial_hash: SpatialHash | None = None) -> None:
        """Process entity separation, optionally using spatial hash for optimization.
        
        If spatial_hash is provided, only checks entities in nearby cells.
        Falls back to O(n^2) check if spatial_hash is None (PERF-02).
        """
        entities = [e for e in entity_sprites if hasattr(
            e, "hitbox") and hasattr(e, "on_surface")]

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
                if not (ent_a.pushable or ent_b.pushable):
                    continue

                if not ent_a.hitbox.colliderect(ent_b.hitbox):
                    continue

                overlap_x = (
                    min(ent_a.hitbox.right, ent_b.hitbox.right)
                    - max(ent_a.hitbox.left, ent_b.hitbox.left)
                )
                overlap_y = (
                    min(ent_a.hitbox.bottom, ent_b.hitbox.bottom)
                    - max(ent_a.hitbox.top, ent_b.hitbox.top)
                )

                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                a_grounded = ent_a.on_surface.get("floor", False)
                b_grounded = ent_b.on_surface.get("floor", False)
                both_airborne = not a_grounded and not b_grounded
                clearly_stacked = overlap_y < overlap_x * Sep.VERTICAL_STACK_RATIO

                if clearly_stacked and both_airborne:
                    push = overlap_y * Sep.STRENGTH
                    dir_a = -1.0 if ent_a.hitbox.centery <= ent_b.hitbox.centery else 1.0
                    self._push(ent_a, ent_b, push * dir_a,
                               push * -dir_a, axis="y")
                else:
                    push = overlap_x * Sep.STRENGTH
                    dir_a = -1.0 if ent_a.hitbox.centerx <= ent_b.hitbox.centerx else 1.0
                    self._push(ent_a, ent_b, push * dir_a,
                               push * -dir_a, axis="x")

                ent_a.sync_rects()
                ent_b.sync_rects()

    @staticmethod
    def _push(ent_a, ent_b, delta_a: float, delta_b: float, axis: str) -> None:
        if ent_a.pushable and ent_b.pushable:
            setattr(ent_a.hitbox, axis, getattr(ent_a.hitbox, axis) + delta_a)
            setattr(ent_b.hitbox, axis, getattr(ent_b.hitbox, axis) + delta_b)
            if axis == "x":
                ent_a.velocity.x = 0
                ent_b.velocity.x = 0
            else:
                ent_a.velocity.y = 0
                ent_b.velocity.y = 0
                
        elif ent_a.pushable:
            setattr(ent_a.hitbox, axis, getattr(ent_a.hitbox, axis) + delta_a * 2)
            if axis == "x":
                ent_a.velocity.x = 0
            else:
                ent_a.velocity.y = 0
                
        elif ent_b.pushable:
            setattr(ent_b.hitbox, axis, getattr(ent_b.hitbox, axis) + delta_b * 2)
            if axis == "x":
                ent_b.velocity.x = 0
            else:
                ent_b.velocity.y = 0