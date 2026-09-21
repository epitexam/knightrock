"""P3t2 reception: crouch state + height/block_mask guard rules."""

import pytest
from pygame.sprite import Group

from src.core.level.systems.combat_system import CombatSystem
from src.entities.player import Player
from tests.unit.helpers import InputStub, entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _guard_player(x: float = 120.0) -> Player:
    player = Player(
        pos=(x, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.faction = "B"
    player.state_machine.current_state_name = "guard"
    player.facing_right = False
    return player


def _attacker(x: float, height: str) -> object:
    attacker = entity_at(
        x,
        faction="A",
        definition=attack(
            phase(
                startup=1,
                active=8,
                recovery=1,
                size=(60.0, 40.0),
                offset=(-20.0, 0.0),
                height=height,
            )
        ),
    )
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()
    return attacker


def _hit_health(player: Player, height: str) -> tuple[float, str]:
    attacker = _attacker(110.0, height)
    before = player.health
    system = CombatSystem()
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    kinds = [event.kind for event in system.guard_events]
    guard_kind = next((kind for kind in kinds if kind != "clash"), "none")
    return before - player.health, guard_kind


def test_mid_blocked_standing() -> None:
    player = _guard_player()
    lost, kind = _hit_health(player, "mid")
    assert kind in ("guard", "parry", "break")
    assert lost < 10.0


def test_low_unblocked_standing_full_damage() -> None:
    player = _guard_player()
    lost, kind = _hit_health(player, "low")
    assert kind == "none"
    assert lost == 10.0


def test_low_blocked_crouch_guarding() -> None:
    player = _guard_player()
    player.state_machine.current_state_name = "crouch"
    outcome_before = player.guard.take_hit(10.0, False, height="low", crouching=True)
    assert outcome_before[0] == "guard"


def test_overhead_hits_crouching_guard() -> None:
    from src.entities.player_controllers import GuardController

    guard = GuardController.__new__(GuardController)
    guard.posture = 100.0
    guard.lockout_timer = 0.0
    guard.parry_timer = 0.0
    guard.riposte_timer = 0.0
    outcome, _, _ = guard.take_hit(10.0, False, height="overhead", crouching=True)
    assert outcome == "none"
    outcome, _, _ = guard.take_hit(10.0, False, height="low", crouching=True)
    assert outcome == "guard"
    outcome, _, _ = guard.take_hit(10.0, False, height="low", crouching=False)
    assert outcome == "none"
    outcome, _, _ = guard.take_hit(10.0, False, height="high", crouching=False)
    assert outcome == "guard"


def test_crouch_state_shrinks_pushbox() -> None:
    player = _guard_player()
    player.state_machine.current_state_name = "idle"
    player.on_surface["floor"] = True
    stood = player.hitbox.height
    player.down_held = True
    player.state_machine.change_state("crouch", force=True)
    assert player.hitbox.height == pytest.approx(stood * 0.6)
