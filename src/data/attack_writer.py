"""Backward-compatible path for :mod:`src.simulation.data.attack_writer`."""

from src.simulation.data.attack_writer import (
    ATTACKS_VERSION as ATTACKS_VERSION,
)
from src.simulation.data.attack_writer import (
    AnchorKind as AnchorKind,
)
from src.simulation.data.attack_writer import (
    Any as Any,
)
from src.simulation.data.attack_writer import (
    AttackDefinition as AttackDefinition,
)
from src.simulation.data.attack_writer import (
    EasingKind as EasingKind,
)
from src.simulation.data.attack_writer import (
    HitboxKeyframe as HitboxKeyframe,
)
from src.simulation.data.attack_writer import (
    HitboxSpec as HitboxSpec,
)
from src.simulation.data.attack_writer import (
    Mapping as Mapping,
)
from src.simulation.data.attack_writer import (
    MoveId as MoveId,
)
from src.simulation.data.attack_writer import (
    Path as Path,
)
from src.simulation.data.attack_writer import (
    ShapeKind as ShapeKind,
)
from src.simulation.data.attack_writer import (
    _hitbox_spec_to_dict as _hitbox_spec_to_dict,
)
from src.simulation.data.attack_writer import (
    _keyframe_to_dict as _keyframe_to_dict,
)
from src.simulation.data.attack_writer import (
    annotations as annotations,
)
from src.simulation.data.attack_writer import (
    attack_definition_to_dict as attack_definition_to_dict,
)
from src.simulation.data.attack_writer import (
    attack_definition_to_v2_dict as attack_definition_to_v2_dict,
)
from src.simulation.data.attack_writer import (
    attacks_document as attacks_document,
)
from src.simulation.data.attack_writer import (
    write_attacks_file as write_attacks_file,
)
