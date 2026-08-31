"""Regression tests for combat orchestration, buffering, and rollback state."""

import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
from pygame.sprite import Group

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.combat.combat_system import CombatSystem
from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.entities.entity import Entity
from src.entities.player import Player
from src.entities.player_config import PlayerConfig
from src.states.player_states import PlayerAttackState


class InputStub:
    """Constructor-only input provider used by Player tests."""


def make_entity(*, attacks=None, invincibility: float = 0.0) -> Entity:
    return Entity(
        pos=(0.0, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        attacks=attacks,
        invincibility_duration=invincibility,
    )


def make_active_attacker(target: Entity):
    hit = HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(100.0, 0.0)),
    )
    targets_hit: set[str] = set()
    combat = SimpleNamespace(
        state=SimpleNamespace(is_active=True),
        attack_box=target.hurtbox.copy(),
        current_phase=SimpleNamespace(hit=hit),
        charge_multiplier=1.0,
        targets_hit=targets_hit,
        can_contact=lambda target_id: target_id not in targets_hit,
        record_contact=targets_hit.add,
    )
    return SimpleNamespace(
        id="attacker",
        is_dead=False,
        faction="enemy",
        hitbox=pygame.FRect(-20.0, 0.0, 10.0, 10.0),
        combat=combat,
    )


def test_combat_system_ignores_immune_contact_without_hit_stop() -> None:
    target = make_entity(invincibility=0.2)
    target.faction = "player"
    target.invincibility_timer = 0.1
    attacker = make_active_attacker(target)
    system = CombatSystem()

    system.process_attacks([attacker, target])  # type: ignore[list-item]

    assert target.id not in attacker.combat.targets_hit
    assert system.hit_stop_timer == 0.0


def test_combat_system_consumes_blocked_contact_once() -> None:
    player = Player(
        pos=(0.0, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.state_machine.current_state_name = "block"
    attacker = make_active_attacker(player)
    system = CombatSystem()
    initial_stamina = player.block.block_stamina

    combatants = [attacker, player]  # type: ignore[list-item]
    system.process_attacks(combatants)
    stamina_after_first_contact = player.block.block_stamina
    system.hit_stop_timer = 0.0
    system.process_attacks(combatants)

    assert stamina_after_first_contact < initial_stamina
    assert player.block.block_stamina == stamina_after_first_contact
    assert player.id in attacker.combat.targets_hit


def test_buffered_attack_restarts_the_attack_state() -> None:
    combat = SimpleNamespace(
        is_attacking=False,
        start_attack=Mock(return_value=True),
        state=SimpleNamespace(current_attack_def=None, end=Mock()),
    )
    state_machine = SimpleNamespace(consume_input=Mock(return_value=True))
    entity = SimpleNamespace(
        combat=combat,
        state_machine=state_machine,
        _buffered_attack_name="light_attack",
        apply_horizontal_movement=Mock(),
        on_surface={"floor": False},
        facing_right=True,
        velocity=pygame.Vector2(),
        speed=450.0,
    )
    state = PlayerAttackState(entity)

    transition = state.update(1 / 60)
    state.exit("attack")

    assert transition == ("attack", {"force": True})
    combat.start_attack.assert_called_once_with("light_attack")
    combat.state.end.assert_not_called()
    assert entity._buffered_attack_name is None


def test_combat_snapshot_restores_cooldowns_charge_and_combo() -> None:
    entity = make_entity(attacks=PLAYER_ATTACKS)
    combat = entity.combat
    assert isinstance(combat, CombatComponent)

    assert combat.start_attack("light_attack")
    combat.state.end()
    assert combat.start_charge("heavy_attack")
    combat.update(0.1)
    snapshot = combat.save_state()
    json.dumps(asdict(snapshot))

    combat.charging.cancel()
    combat.update(1.0)
    combat.load_state(snapshot)

    assert combat.save_state() == snapshot


def test_null_combat_component_is_reset_substitutable() -> None:
    combat = NullCombatComponent()
    combat.is_hurt = True
    combat.hurt_timer = 1.0
    combat.targets_hit.add("target")

    combat.reset()
    combat.hitbox.clear()
    combat.charging.cancel()

    assert combat.is_hurt is False
    assert combat.hurt_timer == 0.0
    assert combat.targets_hit == set()


def test_player_copies_all_behavioral_configuration() -> None:
    config = PlayerConfig(
        block_cooldown_normal=0.9,
        block_cooldown_broken=3.4,
        dash_recharge_time=0.85,
        dash_gravity_mult=0.4,
    )
    player = Player(
        pos=(0.0, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
        config=config,
    )

    assert player.block.block_cooldown_normal == 0.9
    assert player.block.block_cooldown_broken == 3.4
    assert player.dash.recharge_time == 0.85
    assert player.dash.gravity_mult == 0.4
