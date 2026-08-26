"""Behavioral tests for hitbox timing, geometry, lifecycle, and trades."""

import pytest
from pygame.sprite import Group

from src.combat.attack_state import AttackStateMachine
from src.combat.combat_system import CombatSystem
from src.combat.frame_data import AttackDefinition, HitProperties, PhaseDefinition
from src.combat.knockback import KnockbackConfig
from src.core.gameplay.gameplay_loop import GameplayLoop
from src.entities.entity import Entity


def phase(
    *,
    startup: int = 1,
    active: int = 2,
    recovery: int = 1,
    size: tuple[float, float] = (30.0, 20.0),
    offset: tuple[float, float] = (20.0, 0.0),
    damage: int = 10,
    reset_targets: bool = True,
) -> PhaseDefinition:
    return PhaseDefinition(
        startup_frames=startup,
        active_frames=active,
        recovery_frames=recovery,
        hitbox_size=size,
        hitbox_offset=offset,
        hit=HitProperties(
            damage=damage,
            knockback=KnockbackConfig(power=(0.0, 0.0)),
        ),
        reset_targets=reset_targets,
    )


def attack(
    *phases: PhaseDefinition, lock_direction: bool = True
) -> AttackDefinition:
    return AttackDefinition(
        phases=phases,
        cooldown=0.0,
        lock_direction=lock_direction,
    )


def entity_at(
    x: float,
    *,
    faction: str = "neutral",
    definition: AttackDefinition | None = None,
    hurtbox_inflate: tuple[float, float] = (0.0, 0.0),
) -> Entity:
    attacks = {"test": definition} if definition is not None else None
    return Entity(
        pos=(x, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        faction=faction,
        attacks=attacks,
        hurtbox_inflate=hurtbox_inflate,
    )


def activate(entity: Entity) -> None:
    assert entity.combat.start_attack("test")
    entity.combat.update(1 / 60)
    entity.combat.sync_attack_box()
    assert entity.combat.attack_box is not None


def test_attack_state_never_skips_an_active_window_on_large_delta() -> None:
    machine = AttackStateMachine({"test": attack(phase(active=1))})
    assert machine.start("test")

    machine.update(0.2)

    assert machine.is_active
    assert machine.frame_counter == 0


def test_hitbox_tracks_facing_and_reuses_its_rectangle() -> None:
    owner = entity_at(
        100.0,
        definition=attack(
            phase(offset=(25.0, -5.0)),
            lock_direction=False,
        ),
    )
    activate(owner)
    first_rect = owner.combat.attack_box
    assert first_rect is not None
    assert first_rect.center == (
        owner.hitbox.centerx + 25.0,
        owner.hitbox.centery - 5.0,
    )

    owner.hitbox.x += 10.0
    owner.facing_right = False
    owner.combat.sync_attack_box()

    assert owner.combat.attack_box is first_rect
    assert first_rect.center == (
        owner.hitbox.centerx - 25.0,
        owner.hitbox.centery - 5.0,
    )


def test_entity_update_syncs_attack_box_after_movement() -> None:
    owner = entity_at(0.0, definition=attack(phase(offset=(20.0, 0.0))))
    owner.velocity.x = 600.0
    assert owner.combat.start_attack("test")

    owner.update(1 / 60)

    assert owner.combat.attack_box is not None
    assert owner.combat.attack_box.centerx == pytest.approx(
        owner.hitbox.centerx + 20.0
    )


def test_attack_box_is_resynchronized_after_entity_separation() -> None:
    definition = attack(phase(size=(20.0, 20.0), offset=(0.0, 0.0)))
    attacker = entity_at(0.0, faction="same", definition=definition)
    other = entity_at(10.0, faction="same")
    activate(attacker)
    initial_center = attacker.combat.attack_box.center
    loop = GameplayLoop()

    loop.process_combat_and_separation(
        1 / 60,
        Group(attacker, other),
        Group(attacker, other),
    )

    assert attacker.hitbox.center != initial_center
    assert attacker.combat.attack_box.center == attacker.hitbox.center


def test_simultaneous_attacks_trade_independently_of_resolution_order() -> None:
    definition = attack(phase(size=(60.0, 40.0), offset=(0.0, 0.0)))
    left = entity_at(0.0, faction="left", definition=definition)
    right = entity_at(10.0, faction="right", definition=definition)
    activate(left)
    activate(right)

    CombatSystem().process_attacks([left, right])

    assert left.health == 90.0
    assert right.health == 90.0


def test_combat_system_materializes_generators_once() -> None:
    definition = attack(phase(size=(60.0, 40.0), offset=(0.0, 0.0)))
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    target = entity_at(10.0, faction="target")
    activate(attacker)
    system = CombatSystem()

    system.process_attacks(entity for entity in (attacker, target))

    assert target.health == 90.0
    assert system.metrics.pairs_tested == 1
    assert system.metrics.overlaps == 1
    assert system.metrics.contacts == 1


def test_rollback_restore_synchronizes_derived_attack_geometry() -> None:
    owner = entity_at(0.0, definition=attack(phase()))
    activate(owner)
    snapshot = owner.combat.save_state()
    owner.combat.reset()
    assert owner.combat.attack_box is None

    owner.hitbox.x = 50.0
    owner.combat.load_state(snapshot)

    assert owner.combat.attack_box is not None
    assert owner.combat.attack_box.centerx == pytest.approx(
        owner.hitbox.centerx + 20.0
    )


def test_death_clears_active_offensive_state() -> None:
    owner = entity_at(0.0, definition=attack(phase()))
    activate(owner)

    owner.die()

    assert owner.is_dead
    assert owner.combat.attack_box is None
    assert not owner.combat.is_attacking


def test_hurtbox_is_distinct_and_synchronized_with_collider() -> None:
    owner = entity_at(0.0, hurtbox_inflate=(-8.0, -4.0))
    assert owner.hurtbox is not owner.hitbox
    assert owner.hurtbox.size == (32.0, 36.0)

    owner.hitbox.center = (120.0, 80.0)
    owner.sync_rects()

    assert owner.hurtbox.center == owner.hitbox.center


@pytest.mark.parametrize(
    ("reset_targets", "expected_contact"),
    [(False, True), (True, False)],
)
def test_phase_policy_controls_repeat_contacts(
    reset_targets: bool, expected_contact: bool
) -> None:
    machine = AttackStateMachine(
        {
            "test": attack(
                phase(active=1),
                phase(active=1, reset_targets=reset_targets),
            )
        }
    )
    assert machine.start("test")
    machine.update(1 / 60)
    machine.targets_hit.add("target")
    machine.update(1 / 60)
    machine.update(1 / 60)

    assert ("target" in machine.targets_hit) is expected_contact


def test_invalid_frame_data_fails_fast() -> None:
    with pytest.raises(ValueError, match="active frame"):
        phase(active=0)
    with pytest.raises(ValueError, match="at least one phase"):
        AttackDefinition(phases=(), cooldown=0.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        HitProperties(damage=-1)

    invalid_cancel = PhaseDefinition(
        startup_frames=1,
        active_frames=1,
        recovery_frames=1,
        hitbox_size=(10.0, 10.0),
        hitbox_offset=(0.0, 0.0),
        hit=HitProperties(damage=1),
        cancel_into=("missing",),
    )
    with pytest.raises(ValueError, match="unknown cancels"):
        entity_at(0.0, definition=attack(invalid_cancel))
