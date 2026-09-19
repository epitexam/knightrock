"""ReactionStatus: the typed cause authority for hit reactions (B1+B2).

Property rule under test: ``Reaction`` owns the *cause* (kind, magnitude,
direction, freshness); the state machine owns the *category in progress*.
Both are written at the same sites in the same tick. The freshness age is
render-only: decayed in ``Entity.update``, excluded from snapshots.
"""

import pytest
from pygame.math import Vector2

from src.combat.knockback import KnockbackConfig
from src.core.settings import Guard as GuardSettings
from src.core.settings import ReactionMark
from src.entities.components.reaction import (
    VELOCITY_KINDS,
    ReactionComponent,
    ReactionKind,
    ReactionStatus,
)
from src.states.enemy_states import EnemyState
from src.states.player_states import PlayerState
from src.states.reaction_states import KNOCKBACK_STATE, STAGGER_STATE
from tests.unit.helpers import make_entity
from tests.unit.test_reaction_ownership import _narrow_owner


def test_shared_state_names_match_the_enums() -> None:
    """The shared vocabulary stays byte-identical to both state enums."""
    assert KNOCKBACK_STATE == PlayerState.KNOCKBACK == EnemyState.KNOCKBACK == "knockback"
    assert STAGGER_STATE == PlayerState.STAGGER == EnemyState.STAGGER == "stagger"


def test_velocity_kinds_cover_applied_pushes_only() -> None:
    """Overlay-red kinds: every applied push, never the stagger lock."""
    actual = set(VELOCITY_KINDS)
    assert actual == {ReactionKind.PUSH, ReactionKind.LAUNCH, ReactionKind.GUARDED}
    assert ReactionKind.STAGGER not in VELOCITY_KINDS
    assert ReactionKind.PARRIED not in VELOCITY_KINDS


def test_apply_knockback_arms_push_status() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.apply_knockback(KnockbackConfig(power=(300.0, -100.0)), source_center_x=None)

    assert component.status == ReactionStatus(
        kind=ReactionKind.PUSH,
        magnitude=pytest.approx(Vector2(300.0, -100.0).length()),
        direction=1.0,
    )
    assert owner.reaction_age == pytest.approx(ReactionMark.DURATION)


def test_apply_knockback_direction_follows_the_source_side() -> None:
    owner = _narrow_owner()  # hitbox centerx = 20
    component = ReactionComponent(owner)

    component.apply_knockback(KnockbackConfig(power=(300.0, 0.0)), source_center_x=1000.0)

    assert component.status is not None
    assert component.status.direction == -1.0


def test_apply_knockback_fixed_mode_arms_push() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.apply_knockback(
        KnockbackConfig(power=(-200.0, 0.0), mode="fixed"), source_center_x=None
    )

    assert owner.velocity.x == pytest.approx(-200.0)  # unchanged behaviour
    assert component.status == ReactionStatus(
        kind=ReactionKind.PUSH, magnitude=pytest.approx(200.0), direction=-1.0
    )


def test_zero_power_knockback_does_not_arm() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.apply_knockback(KnockbackConfig(power=(0.0, 0.0)), source_center_x=None)

    assert component.status is None
    assert owner.reaction_age == 0.0


def test_heavy_knockback_arms_launch_and_drives_the_state_machine() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    launched = component.handle_heavy_knockback(
        KnockbackConfig(power=(300.0, -400.0)), source_center_x=None
    )

    assert launched is True
    assert component.status == ReactionStatus(
        kind=ReactionKind.LAUNCH,
        magnitude=pytest.approx(Vector2(300.0, -400.0).length()),
        direction=1.0,
    )
    # Same tick, same site: the state machine moved with the shared name.
    assert owner.state_machine.changes[-1][0] == "knockback"


def test_light_knockback_keeps_the_push_status() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.apply_knockback(KnockbackConfig(power=(150.0, 0.0)), source_center_x=None)
    launched = component.handle_heavy_knockback(
        KnockbackConfig(power=(150.0, 0.0)), source_center_x=None
    )

    assert launched is False
    assert component.status is not None
    assert component.status.kind is ReactionKind.PUSH
    assert owner.state_machine.changes == []


def test_stagger_arms_stagger_status() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.stagger(0.3)

    assert component.status == ReactionStatus(
        kind=ReactionKind.STAGGER, magnitude=0.0, direction=0.0
    )
    assert owner.state_machine.changes[-1][0] == "stagger"


def test_absorbed_stagger_does_not_arm() -> None:
    owner = _narrow_owner(super_armor=True)  # below threshold: no stagger
    component = ReactionComponent(owner)

    component.stagger(0.2)

    assert component.status is None


def test_note_guard_push_arms_guarded_status() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.note_guard_push(KnockbackConfig(power=(300.0, -100.0)), source_center_x=None)

    assert component.status == ReactionStatus(
        kind=ReactionKind.GUARDED,
        magnitude=pytest.approx(300.0 * GuardSettings.PUSH_FACTOR),
        direction=1.0,
    )


def test_note_guard_push_parried_arms_parried_status() -> None:
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.note_guard_push(
        KnockbackConfig(power=(300.0, -100.0)), source_center_x=None, parried=True
    )

    assert component.status == ReactionStatus(
        kind=ReactionKind.PARRIED,
        magnitude=pytest.approx(0.0),
        direction=1.0,
    )


def test_heavy_hit_leaves_a_single_launch_cause() -> None:
    """Push then launch at the same sites: the launch cause wins, same tick."""
    owner = _narrow_owner()
    component = ReactionComponent(owner)

    component.apply_knockback(KnockbackConfig(power=(300.0, -400.0)), source_center_x=None)
    launched = component.handle_heavy_knockback(
        KnockbackConfig(power=(300.0, -400.0)), source_center_x=None
    )

    assert launched is True
    assert component.status is not None
    assert component.status.kind is ReactionKind.LAUNCH


def test_reaction_age_decays_in_entity_update() -> None:
    entity = make_entity()
    entity._reaction.apply_knockback(KnockbackConfig(power=(300.0, 0.0)), source_center_x=None)

    assert entity.reaction_age == pytest.approx(ReactionMark.DURATION)
    entity.update(0.1)
    assert entity.reaction_age == pytest.approx(ReactionMark.DURATION - 0.1)
    entity.update(ReactionMark.DURATION)
    assert entity.reaction_age == 0.0
    # The cause itself survives the freshness window; only freshness expires.
    assert entity.reaction_status is not None
    assert entity.reaction_status.kind is ReactionKind.PUSH


def test_reaction_age_is_excluded_from_snapshots() -> None:
    entity = make_entity()
    entity._reaction.apply_knockback(KnockbackConfig(power=(300.0, 0.0)), source_center_x=None)

    snapshot = entity.save_state()

    assert "reaction_age" not in snapshot.extra
    assert "reaction_status" not in snapshot.extra


def test_rollback_round_trip_without_the_field() -> None:
    """Save/load never touches the render-only reaction state (flash_timer precedent)."""
    entity = make_entity()
    entity._reaction.apply_knockback(KnockbackConfig(power=(300.0, 0.0)), source_center_x=None)
    snapshot = entity.save_state()

    entity.reaction_age = 0.123
    entity.load_state(snapshot)

    assert entity.reaction_age == pytest.approx(0.123)
    assert entity.reaction_status is not None
    assert entity.reaction_status.kind is ReactionKind.PUSH
