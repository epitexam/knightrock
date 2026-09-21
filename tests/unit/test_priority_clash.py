"""P3t1 reception: hit-vs-hit priority/clash and unblockable."""

from src.core.level.systems.combat_system import CombatSystem
from tests.unit.helpers import entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _pair(pa: int, pb: int, clash: str = "trade"):
    left = entity_at(
        100.0,
        faction="A",
        hurtbox_inflate=(-38.0, -38.0),
        definition=attack(
            phase(
                startup=1,
                active=8,
                recovery=1,
                size=(60.0, 40.0),
                priority=pa,
                clash=clash,
            )
        ),
    )
    right = entity_at(
        110.0,
        faction="B",
        hurtbox_inflate=(-38.0, -38.0),
        definition=attack(
            phase(
                startup=1,
                active=8,
                recovery=1,
                size=(60.0, 40.0),
                offset=(-20.0, 0.0),
                priority=pb,
                clash=clash,
            )
        ),
    )
    for entity in (left, right):
        entity.combat.capture_attack_origin()
        assert entity.combat.start_attack("test")
        entity.combat.update(1 / 60)
        entity.combat.sync_attack_box()
    return left, right


def test_higher_priority_wins() -> None:
    left, right = _pair(1, 0)
    system = CombatSystem()
    system.process_attacks([left, right])
    assert system.metrics.contacts == 1
    assert left.combat.state.is_attacking
    assert not right.combat.state.is_attacking


def test_equal_priority_trades() -> None:
    left, right = _pair(0, 0)
    system = CombatSystem()
    system.process_attacks([left, right])
    assert system.metrics.contacts == 2


def test_equal_priority_clash_cancels_both() -> None:
    left, right = _pair(1, 1, clash="clash")
    system = CombatSystem()
    system.process_attacks([left, right])
    assert system.metrics.contacts == 0
    assert not left.combat.state.is_attacking
    assert not right.combat.state.is_attacking
    kinds = [event.kind for event in system.guard_events]
    assert kinds == ["clash", "clash"]
    assert system.hit_stop_timer > 0.0


def test_unblockable_bypasses_guard() -> None:
    from pygame.sprite import Group

    from src.entities.player import Player
    from tests.unit.helpers import InputStub

    player = Player(
        pos=(120.0, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.faction = "B"
    player.state_machine.current_state_name = "guard"
    player.facing_right = True
    attacker = entity_at(
        110.0,
        faction="A",
        definition=attack(
            phase(
                startup=1,
                active=8,
                recovery=1,
                size=(60.0, 40.0),
                offset=(-20.0, 0.0),
                unblockable=True,
            )
        ),
    )
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()
    before = player.health
    system = CombatSystem()
    system.process_attacks([attacker, player])
    assert player.health < before
    assert all(event.kind != "guard" for event in system.guard_events)
