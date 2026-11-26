"""Backward-compatible path for :mod:`src.simulation.physics.movement`."""

from src.simulation.physics.movement import (
    VELOCITY_EPSILON as VELOCITY_EPSILON,
)
from src.simulation.physics.movement import (
    Any as Any,
)
from src.simulation.physics.movement import (
    Collision as Collision,
)
from src.simulation.physics.movement import (
    CollisionSprite as CollisionSprite,
)
from src.simulation.physics.movement import (
    GameFeel as GameFeel,
)
from src.simulation.physics.movement import (
    HorizontalMovementEntity as HorizontalMovementEntity,
)
from src.simulation.physics.movement import (
    Input as Input,
)
from src.simulation.physics.movement import (
    Iterable as Iterable,
)
from src.simulation.physics.movement import (
    JumpEntity as JumpEntity,
)
from src.simulation.physics.movement import (
    JumpState as JumpState,
)
from src.simulation.physics.movement import (
    Locomotion as Locomotion,
)
from src.simulation.physics.movement import (
    MovableEntity as MovableEntity,
)
from src.simulation.physics.movement import (
    MovementCombat as MovementCombat,
)
from src.simulation.physics.movement import (
    MovingPlatform as MovingPlatform,
)
from src.simulation.physics.movement import (
    PlatformRide as PlatformRide,
)
from src.simulation.physics.movement import (
    PlatformRider as PlatformRider,
)
from src.simulation.physics.movement import (
    Protocol as Protocol,
)
from src.simulation.physics.movement import (
    Separation as Separation,
)
from src.simulation.physics.movement import (
    Simulation as Simulation,
)
from src.simulation.physics.movement import (
    SpatialHash as SpatialHash,
)
from src.simulation.physics.movement import (
    Vector2 as Vector2,
)
from src.simulation.physics.movement import (
    WallJumpLock as WallJumpLock,
)
from src.simulation.physics.movement import (
    _braking as _braking,
)
from src.simulation.physics.movement import (
    _revert_carry_crush as _revert_carry_crush,
)
from src.simulation.physics.movement import (
    _snap_to_ground as _snap_to_ground,
)
from src.simulation.physics.movement import (
    _sticky_snap as _sticky_snap,
)
from src.simulation.physics.movement import (
    apply_entity_gravity as apply_entity_gravity,
)
from src.simulation.physics.movement import (
    apply_horizontal_movement as apply_horizontal_movement,
)
from src.simulation.physics.movement import (
    apply_jump_cut as apply_jump_cut,
)
from src.simulation.physics.movement import (
    apply_moving_platform as apply_moving_platform,
)
from src.simulation.physics.movement import (
    collider_box as collider_box,
)
from src.simulation.physics.movement import (
    get_nearby_sprites as get_nearby_sprites,
)
from src.simulation.physics.movement import (
    is_one_way as is_one_way,
)
from src.simulation.physics.movement import (
    math as math,
)
from src.simulation.physics.movement import (
    move_entity as move_entity,
)
from src.simulation.physics.movement import (
    pygame as pygame,
)
from src.simulation.physics.movement import (
    resolve_collisions as resolve_collisions,
)
from src.simulation.physics.movement import (
    resolve_jump as resolve_jump,
)
from src.simulation.physics.movement import (
    update_contact_state as update_contact_state,
)
