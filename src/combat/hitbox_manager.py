"""Lifecycle and positioning of active offensive hitboxes."""

from __future__ import annotations

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitboxSpec, PhaseDefinition
from src.combat.shapes import AnchorKind, ShapeKind, ShapePose, SweptShape, broadphase_aabb
from src.combat.sweep import swept_box


class HitboxManager:
    """Own the offensive rectangles of an active attack phase.

    ``rect`` stays the primary offensive rectangle (legacy single-box
    attacks expose exactly one box). ``rects`` is the full
    pool — primary box first, then one slot per
    ``PhaseDefinition.extra_hitboxes`` entry. Both views share the same
    rectangles: ``rects[0] is rect`` whenever a box is live.

    P1 sweep: ``_prev_pool`` holds the geometry captured at the previous
    tick boundary (``capture_origin``), the sole other writers of which
    are the ``start_attack`` seed (D1) and ``clear`` (attack end).
    ``update`` never touches it: positioning is pure and idempotent, so
    the double sync (``Entity.update`` + gameplay loop) is harmless.
    """

    def __init__(self, entity: Combatant) -> None:
        self._entity: Combatant = entity
        self.rect: pygame.FRect | None = None
        self._pool: list[pygame.FRect] = []
        self._prev_pool: list[pygame.FRect] = []
        self._shape_pool: list[ShapePose] = []
        self._prev_shape_pool: list[ShapePose] = []

    @property
    def rects(self) -> tuple[pygame.FRect, ...]:
        """Live offensive rectangles: primary box first, then extras."""
        return tuple(self._pool)

    @property
    def prev_rects(self) -> tuple[pygame.FRect, ...]:
        """Copies of the rectangles captured at the previous tick boundary."""
        return tuple(rect.copy() for rect in self._prev_pool)

    @property
    def swept_rects(self) -> tuple[pygame.FRect, ...]:
        """Per-index swept rectangles between the captured origin and now.

        An index without a captured origin (spawn, resize) or whose
        displacement is out of the ``Combat`` sweep bounds yields ``cur``
        (D1/D4); otherwise the union of prev and cur.
        """
        return tuple(
            swept_box(
                self._prev_pool[index] if index < len(self._prev_pool) else None,
                rect,
            )
            for index, rect in enumerate(self._pool)
        )

    @property
    def shapes(self) -> tuple[ShapePose, ...]:
        """Live advanced shapes corresponding to the rectangle pool."""
        return tuple(self._shape_pool)

    @property
    def prev_shapes(self) -> tuple[ShapePose, ...]:
        """Copies of the advanced shapes captured at the tick boundary."""
        return tuple(self._prev_shape_pool)

    @property
    def swept_shapes(self) -> tuple[SweptShape, ...]:
        """Advanced shape pairs captured at the boundary and current state."""
        return tuple(
            SweptShape(
                self._prev_shape_pool[index] if index < len(self._prev_shape_pool) else None,
                shape,
            )
            for index, shape in enumerate(self._shape_pool)
        )

    def update(self, state: AttackStateMachine) -> None:
        """Synchronize geometry from attack state and owner position.

        Geometry is live during startup *and* active: the animated curve
        starts at phase frame 0 (windup), so the debug overlay and the
        per-frame sweep both track the swing from its first frame.
        Recovery clears the box, as before.
        """
        if not state.is_attacking or state.attack_name is None:
            self.clear()
            return

        phase = state.current_phase_def
        if phase is None:
            self.clear()
            return

        facing_right = state.effective_facing
        if facing_right is None:
            facing_right = self._entity.facing_right
        self._position_rects(phase, facing_right, state.animation_frame)

    def clear(self) -> None:
        """Remove offensive geometry immediately (end of attack)."""
        self.rect = None
        self._pool.clear()
        self._prev_pool.clear()
        self._shape_pool.clear()
        self._prev_shape_pool.clear()

    def capture_origin(self) -> None:
        """Copy the live pool as the sweep origin of the next tick.

        Called once per tick at the frontier, by the gameplay loop,
        before any movement or attack start of the tick. Deep copy: the
        pool rectangles are repositioned in place afterwards.
        """
        self._prev_pool = [rect.copy() for rect in self._pool]
        self._prev_shape_pool = list(self._shape_pool)

    def clear_origin(self) -> None:
        """Forget the sweep origin (rollback hygiene, re-derived on next capture)."""
        self._prev_pool.clear()
        self._prev_shape_pool.clear()

    def _position_rects(self, phase: PhaseDefinition, facing_right: bool, frame: int) -> None:
        """Create or reposition every rectangle and advanced shape."""
        primary_geometry, primary_angle = phase.hitbox_shape_at(frame)
        if not phase.hitbox_keyframes:
            primary_angle = phase.hitbox_angle
        shape_data = [
            (phase.hitbox_spec, primary_geometry, primary_angle),
        ]
        for index, spec in enumerate(phase.extra_hitboxes):
            geometry, angle = phase.extra_shape_at(index, frame)
            if not spec.keyframes:
                angle = spec.angle
            shape_data.append((spec, geometry, angle))
        while len(self._pool) < len(shape_data):
            self._pool.append(pygame.FRect(0, 0, 0, 0))
        while len(self._pool) > len(shape_data):
            self._pool.pop()
        while len(self._shape_pool) < len(shape_data):
            self._shape_pool.append(ShapePose(ShapeKind.AABB, (1.0, 1.0)))
        while len(self._shape_pool) > len(shape_data):
            self._shape_pool.pop()
        for index, (rect, (spec, (size, offset), angle)) in enumerate(
            zip(self._pool, shape_data, strict=True)
        ):
            anchor = self._anchor_position(spec, facing_right)
            offset_x, offset_y = offset
            if not facing_right:
                offset_x = -offset_x
            position = (anchor[0] + offset_x, anchor[1] + offset_y)
            shape_angle = -angle if not facing_right else angle
            shape = ShapePose(spec.shape, size, position, shape_angle)
            self._shape_pool[index] = shape
            rect.size = self._broadphase_size(shape)
            rect.center = position
        self.rect = self._pool[0]

    def _anchor_position(self, spec: HitboxSpec, facing_right: bool) -> tuple[float, float]:
        owner = self._entity.hitbox
        if spec.anchor is AnchorKind.HIP:
            position = (owner.centerx, owner.bottom)
        elif spec.anchor is AnchorKind.CHEST:
            position = (owner.centerx, owner.centery - owner.height * 0.25)
        else:
            position = owner.center
        anchor_offset_x, anchor_offset_y = spec.anchor_offset
        if not facing_right:
            anchor_offset_x = -anchor_offset_x
        return (position[0] + anchor_offset_x, position[1] + anchor_offset_y)

    @staticmethod
    def _broadphase_size(shape: ShapePose) -> tuple[float, float]:
        if shape.kind is ShapeKind.AABB:
            return shape.size
        bounds = broadphase_aabb(shape)
        return bounds.size
