"""Backward-compatible path for :mod:`src.simulation.physics.collisions`."""

from src.simulation.physics.collisions import (
    Collision as Collision,
)
from src.simulation.physics.collisions import (
    CollisionEntity as CollisionEntity,
)
from src.simulation.physics.collisions import (
    CollisionSprite as CollisionSprite,
)
from src.simulation.physics.collisions import (
    GameFeel as GameFeel,
)
from src.simulation.physics.collisions import (
    Iterable as Iterable,
)
from src.simulation.physics.collisions import (
    Literal as Literal,
)
from src.simulation.physics.collisions import (
    Protocol as Protocol,
)
from src.simulation.physics.collisions import (
    SpatialHash as SpatialHash,
)
from src.simulation.physics.collisions import (
    Vector2 as Vector2,
)
from src.simulation.physics.collisions import (
    _extract_collider as _extract_collider,
)
from src.simulation.physics.collisions import (
    _flag_crushed as _flag_crushed,
)
from src.simulation.physics.collisions import (
    _is_eligible as _is_eligible,
)
from src.simulation.physics.collisions import (
    _resolve_horizontal as _resolve_horizontal,
)
from src.simulation.physics.collisions import (
    _resolve_vertical as _resolve_vertical,
)
from src.simulation.physics.collisions import (
    _resolve_with_cap as _resolve_with_cap,
)
from src.simulation.physics.collisions import (
    _shift_is_free as _shift_is_free,
)
from src.simulation.physics.collisions import (
    _try_corner_correct as _try_corner_correct,
)
from src.simulation.physics.collisions import (
    _try_step_up as _try_step_up,
)
from src.simulation.physics.collisions import (
    collider_box as collider_box,
)
from src.simulation.physics.collisions import (
    get_nearby_sprites as get_nearby_sprites,
)
from src.simulation.physics.collisions import (
    hitbox_collide as hitbox_collide,
)
from src.simulation.physics.collisions import (
    is_one_way as is_one_way,
)
from src.simulation.physics.collisions import (
    make_query as make_query,
)
from src.simulation.physics.collisions import (
    pygame as pygame,
)
from src.simulation.physics.collisions import (
    resolve_collisions as resolve_collisions,
)
from src.simulation.physics.collisions import (
    update_contact_state as update_contact_state,
)
