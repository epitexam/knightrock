"""The crouch posture: the hurtbox height, owned by the fighter rather than a state.

Height used to live in :class:`~src.states.player_states.PlayerCrouchState`, which
made it the property of a *state*. That is the wrong owner, and the reason is
visible in one transition: attacking or guarding out of a crouch left the state
on the tick the interrupt fired, so the release blend had no tick left to run in
and the collider snapped to full height in one step -- the same pop the blend
exists to remove, just moved to the exit.

Owning it here instead means every tick asks the same question (is the crouch
wanted?) and eases toward the answer, so the height is smooth through *any*
transition rather than only the one the crouch state runs itself. It also makes
the posture composable: a fighter guarding with Down held guards low, which is
what makes the crouching half of ``Guard.HEIGHT_BLOCK`` reachable through play
instead of only from a test that pokes the state name.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pygame

from src.combat.frame_data import Stance
from src.core.settings import Locomotion, Physics


@dataclass(frozen=True)
class CrouchSnapshot:
    """Serializable capture of the crouch posture's runtime state."""

    wanted: bool
    stood_height: float
    target_height: float


class CrouchPosture:
    """Eases the collider between standing height and the crouched one.

    The fighter's standing height is captured once, on the first tick, and is
    the reference every blend is measured against. Re-deriving it from the live
    height each time would let a partially blended height compound into a new
    "standing" height, and a fighter would shrink a little every time they
    crouched.
    """

    def __init__(self) -> None:
        self._wanted: bool = False
        self._stood_height: float = 0.0
        self._target_height: float = 0.0

    @property
    def is_crouched(self) -> bool:
        """Whether the collider is (or is heading towards) the crouched height."""
        return self._wanted

    def is_fully_stood(self, entity: Any) -> bool:
        """Whether the blend has arrived at the full standing height.

        Never true under a low ceiling, which is the point: the posture is left
        once there is room to leave it, not on the tick the button came up.
        """
        if self._stood_height <= 0:
            return True
        current = float(entity.hitbox.height)
        return abs(current - self._stood_height) <= Locomotion.VELOCITY_EPSILON

    @property
    def stood_height(self) -> float:
        """The fighter's full standing collider height."""
        return self._stood_height

    @property
    def stance(self) -> Stance:
        """The posture the fighter is in, for anything that gates on it.

        Only ``CROUCH`` versus not: the crouch requires a floor, so an airborne
        fighter is never in it even mid-release. What the fighter is *not* doing
        -- airborne, on a wall -- is the entity's business, so the full
        resolution lives in ``Entity.stance`` rather than here.
        """
        return Stance.CROUCH if self._wanted else Stance.GROUND

    def restore(self, snapshot: CrouchSnapshot) -> None:
        """Restore posture state from a validated rollback snapshot."""
        self._wanted = bool(snapshot.wanted)
        self._stood_height = max(0.0, snapshot.stood_height)
        self._target_height = max(0.0, snapshot.target_height)

    def save_state(self) -> CrouchSnapshot:
        """Capture the posture state for a rollback frame."""
        return CrouchSnapshot(
            wanted=self._wanted,
            stood_height=self._stood_height,
            target_height=self._target_height,
        )

    def update(self, entity: Any, delta_time: float, wanted: bool) -> None:
        """Ease the collider toward the height ``wanted`` implies.

        Parameters
        ----------
        entity : Entity
            The fighter whose collider is driven.
        delta_time : float
            Elapsed time in seconds.
        wanted : bool
            Whether the crouch is being held this tick.
        """
        if self._stood_height <= 0:
            self._stood_height = float(entity.hitbox.height)
            self._target_height = self._stood_height * Physics.CROUCH_HEIGHT_FACTOR
        self._wanted = wanted

        current = float(entity.hitbox.height)
        target = self._target_height if wanted else min(self._stood_height, _headroom(entity))
        if abs(current - target) <= Locomotion.VELOCITY_EPSILON:
            self._set_height(entity, target)
            return

        step = (self._stood_height / max(Physics.CROUCH_HEIGHT_BLEND_TIME, 1e-6)) * delta_time
        if current > target:
            # Settling into the posture: the collider only ever shrinks here, so
            # a ceiling overhead is irrelevant and nothing needs re-testing.
            self._set_height(entity, max(target, current - step))
        else:
            self._set_height(entity, min(target, current + step))

    def _set_height(self, entity: Any, height: float) -> None:
        """Resize the collider about its feet and re-derive the dependent rects.

        The early return when the height is already there is load-bearing rather
        than tidy: ``pygame.FRect`` derives ``left``/``top`` from the other
        edges, so re-assigning ``height`` and then ``bottom`` on a rect whose
        edges are fractional rounds ``y`` by a part in ten thousand. Done every
        tick, that is a silent drift of the fighter's position -- small enough to
        look like nothing and exactly enough to move a golden digest.
        """
        if float(entity.hitbox.height) == height:
            return
        bottom = entity.hitbox.bottom
        entity.hitbox.height = height
        entity.hitbox.bottom = bottom
        entity.sync_rects()


def _headroom(entity: Any) -> float:
    """The tallest feet-anchored collider that clears every solid here.

    The collider of height ``h`` spans ``[bottom - h, bottom]``, so it grows
    *upward* as ``h`` grows and its top is ``bottom - h``. It therefore stops
    short of a solid whose lower edge sits above the feet at ``h = bottom -
    box.bottom`` -- that gap is the headroom, in screen terms, since smaller
    ``y`` is higher up.

    Three filters keep a floor from being read as a ceiling, which is the
    failure that would wedge a fighter crouched forever: a solid must end above
    the feet (the floor under them does not), must reach down to their level or
    above (a pit below does not), and must span the fighter horizontally (a wall
    beside them is not overhead).

    When the entity carries the level's spatial hash -- which every entity in a
    real level does, assigned in ``Level.__init__`` -- the candidates come from
    the grid instead of from a walk of every collidable on the map. On the
    shipped stage that is 461 sprites turned into 2, and this function ran once
    per player per tick precisely because the fighter is usually *not* holding
    the crouch, so there was nothing about the posture that made it cheap.

    The query is only the fighter's own column, from the feet up to the
    standing height, and that bound is sound rather than convenient: ``tallest``
    starts at the standing height and is only ever lowered by a ``min``, so a
    solid more than a full standing height above the feet cannot change the
    answer. Without the bound the query would be the whole screen, which is the
    scan this is replacing.

    The linear walk stays for an entity with no hash -- a fighter built outside
    a level -- and is what the unit tests exercise, since they assemble their
    own collision group. ``get_nearby_sprites`` already resolves collision
    through the same grid with the same fallback, so this leans on an invariant
    that is already load-bearing rather than adding a second one.
    """
    hitbox = entity.hitbox
    bottom = hitbox.bottom
    stood = _stand_height(entity)
    tallest = max(0.0, stood)

    spatial_hash = getattr(entity, "spatial_hash", None)
    if spatial_hash is None:
        candidates: Iterable[Any] = entity.collision_sprites
    else:
        column = pygame.FRect(hitbox.left, bottom - stood, hitbox.width, stood)
        candidates = spatial_hash.get_nearby(column)

    for sprite in candidates:
        # Not ``getattr(sprite, "hitbox", getattr(sprite, "rect", None))``:
        # the default is evaluated before the call, so the fallback lookup runs
        # for every sprite including the tiles that all have a ``rect``.
        box = getattr(sprite, "hitbox", None)
        if box is None:
            box = getattr(sprite, "rect", None)
        if box is None:
            continue
        if not float(box.bottom) < bottom or float(box.top) > bottom:
            continue
        if float(box.right) <= hitbox.left or float(box.left) >= hitbox.right:
            continue
        tallest = min(tallest, max(0.0, bottom - float(box.bottom)))
    return tallest


def _stand_height(entity: Any) -> float:
    """The fighter's full standing collider height, from the posture if it has one."""
    posture = getattr(entity, "crouch", None)
    stood = float(getattr(posture, "stood_height", 0.0) or 0.0)
    return stood if stood > 0.0 else float(entity.hitbox.height)
