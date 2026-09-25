from typing import Any

import pygame

from src.core.settings import Separation as Sep
from src.physics.entity_grid import EntityGrid, overlapping_pairs


class SeparationSystem:
    def process(
        self,
        entity_sprites: pygame.sprite.Group,
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Push overlapping entities apart on the dominant overlap axis.

        Pair candidates come from the per-tick :class:`EntityGrid` when one
        is provided (O(n · k) instead of the legacy exhaustive O(n²)); pair
        order is preserved, so behaviour is unchanged (see
        :func:`overlapping_pairs`).  Without a grid the pairs are tested
        exhaustively — still correct, just slower.
        """
        entities = [e for e in entity_sprites if hasattr(e, "hitbox") and hasattr(e, "on_surface")]

        if entity_grid is not None:
            pairs = overlapping_pairs(entities, entity_grid)
        else:
            pairs = (
                (ent_a, entities[j])
                for i, ent_a in enumerate(entities)
                for j in range(i + 1, len(entities))
            )

        for ent_a, ent_b in pairs:
            # Skip separation if either entity is invincible (e.g., dashing) - allows phasing through
            if getattr(ent_a, "is_invincible", False) or getattr(ent_b, "is_invincible", False):
                continue
            if not (ent_a.pushable or ent_b.pushable):
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

            a_grounded = ent_a.on_surface.get("floor", False)
            b_grounded = ent_b.on_surface.get("floor", False)
            both_airborne = not a_grounded and not b_grounded
            clearly_stacked = overlap_y < overlap_x * Sep.VERTICAL_STACK_RATIO

            if clearly_stacked and both_airborne:
                push = overlap_y * Sep.STRENGTH
                dir_a = -1.0 if ent_a.hitbox.centery <= ent_b.hitbox.centery else 1.0
                self._push(ent_a, ent_b, push * dir_a, push * -dir_a, axis="y")
            else:
                push = overlap_x * Sep.STRENGTH
                dir_a = -1.0 if ent_a.hitbox.centerx <= ent_b.hitbox.centerx else 1.0
                self._push(ent_a, ent_b, push * dir_a, push * -dir_a, axis="x")

            ent_a.sync_rects()
            ent_b.sync_rects()

    @staticmethod
    def _push(ent_a: Any, ent_b: Any, delta_a: float, delta_b: float, axis: str) -> None:
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
