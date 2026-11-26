"""The stun gauge: what fills it, the stun a full one causes, and the execution it opens."""

from types import SimpleNamespace

import pygame
import pytest

from src.presentation.fx import OrbitParticle
from src.simulation.data.provider import shipped_gameplay_data
from src.simulation.entities.enemies.enemy import Enemy
from src.simulation.entities.player import Player
from src.simulation.level.systems.combat_system import CombatSystem
from src.simulation.level.systems.feedback_system import _spawn_guard_fx
from src.simulation.settings import Combat, Stun
from src.simulation.states.reaction_states import DIZZY_STATE
from tests.unit.helpers import InputStub

GOBLIN_CONFIG = shipped_gameplay_data().enemies["goblin"]
SLIME_CONFIG = shipped_gameplay_data().enemies["slime"]


def _player() -> Player:
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    p = Player(
        pos=(100.0, 0.0),  # Center of the test area
        groups=groups,
        collision_sprites=collision_sprites,
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    p.facing_right = True  # Default facing right
    return p


def _enemy(config=GOBLIN_CONFIG, player=None) -> Enemy:
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    enemy = Enemy(
        pos=(140.0, 0.0),
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=player,
        config=config,
    )
    enemy.facing_right = False
    # Grounded, so the goblin's ground-only move is startable. The postures a
    # move is legal from are declared on the move now, and a fresh entity is
    # airborne until something says otherwise.
    enemy.on_surface["floor"] = True
    assert enemy.combat.start_attack(enemy.attack_name)
    _advance_to_active(enemy)
    return enemy


def _advance_to_active(enemy: Enemy) -> None:
    """Run the enemy's attack through its startup, whatever its length is tuned to."""
    for _ in range(120):
        if enemy.combat.state.is_active:
            break
        enemy.combat.update(1 / 60)
    assert enemy.combat.state.is_active, "the attack never reached its active frames"
    enemy.combat.sync_attack_box()


def _make_attacker(config=GOBLIN_CONFIG, player=None) -> Enemy:
    """Create an enemy attacker, positioned and combat-ready."""
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    attacker = Enemy(
        pos=(140.0, 0.0),
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=None,
        config=config,
    )
    attacker.facing_right = False  # Face left towards player at x=100
    # Grounded: a fresh entity is airborne, and the moves these tests drive are
    # ground-only now that ``stances`` says so.
    attacker.on_surface["floor"] = True
    assert attacker.combat.start_attack(attacker.attack_name)
    _advance_to_active(attacker)
    return attacker


def test_enemy_copies_its_stun_gauge_from_the_config() -> None:
    e = _enemy()
    assert e.stun_max == GOBLIN_CONFIG.stun_max
    assert e.stun_duration == GOBLIN_CONFIG.stun_duration
    assert e.stun == 0.0


def _reset_attacker(attacker: Enemy) -> None:
    """Reset attacker for a new attack attempt, advancing to active phase."""
    attacker.combat.state.end()
    # Clear cooldown for testing
    attacker.combat._cooldowns.clear()
    attacker.on_surface["floor"] = True
    assert attacker.combat.start_attack(attacker.attack_name)
    _advance_to_active(attacker)


def _clear_hit_stop(system: CombatSystem) -> None:
    """Clear hit stop timer for testing consecutive attacks in same tick."""
    system.hit_stop_timer = 0.0


def test_a_fighter_with_no_gauge_is_never_stunned() -> None:
    attacker = _make_attacker()
    attacker.stun_max = None

    for _ in range(10):
        assert attacker.add_stun(1000.0) is False

    assert attacker.stun == 0.0
    assert attacker.state_machine.current_state_name != DIZZY_STATE


def test_a_stunned_fighter_takes_no_more_stun() -> None:
    enemy = _enemy()

    assert enemy.add_stun(enemy.stun_max) is True
    assert enemy.add_stun(enemy.stun_max) is False
    assert enemy.stun == 0.0


def test_the_gauge_holds_then_drains() -> None:
    enemy = _enemy()
    enemy.add_stun(30.0)

    enemy._tick_stun(Stun.DECAY_DELAY - 0.01)
    assert enemy.stun == pytest.approx(30.0), "it holds while blows keep coming"

    enemy._tick_stun(0.02)
    enemy._tick_stun(1.0)
    assert enemy.stun == pytest.approx(30.0 - Stun.DECAY_PER_S)

    enemy._tick_stun(10.0)
    assert enemy.stun == 0.0


def _strike(enemy: Enemy, **hit: object):
    from src.simulation.combat.frame_data import HitProperties
    from src.simulation.combat.hit_resolver import HitResolver
    from src.simulation.combat.knockback import KnockbackConfig
    from tests.unit.helpers import AttackerStub

    hit.setdefault("knockback", KnockbackConfig(power=(100.0, 0.0)))
    return HitResolver.resolve(AttackerStub(centerx=80.0), enemy, HitProperties(**hit))


def test_a_blow_fills_the_gauge_by_its_stun() -> None:
    enemy = _enemy()

    result = _strike(enemy, damage=5, stun=20.0)

    assert result.stunned is False
    assert enemy.stun == pytest.approx(20.0)


def test_the_blow_that_fills_the_gauge_stuns_and_says_so() -> None:
    enemy = _enemy()

    result = _strike(enemy, damage=5, stun=enemy.stun_max)

    assert result.stunned is True
    assert enemy.state_machine.current_state_name == DIZZY_STATE
    assert not enemy.combat.is_hurt, "the stun is the reaction: no hurt state on top of it"


def test_a_stunned_fighter_stays_stunned_under_the_blows() -> None:
    enemy = _enemy()
    enemy.add_stun(enemy.stun_max)
    enemy.velocity.update(0.0, 0.0)

    result = _strike(enemy, damage=5, stagger=0.3)

    assert result.applied is True
    assert enemy.state_machine.current_state_name == DIZZY_STATE
    assert not enemy.combat.is_hurt
    assert enemy.velocity.x == 0.0, "and is not pushed out of reach"


def test_dizzy_damage_multiplier() -> None:
    enemy = _enemy()
    enemy.add_stun(enemy.stun_max)

    result = _strike(enemy, damage=10)

    assert result.applied is True
    assert result.actual_damage == pytest.approx(10.0 * Combat.DIZZY_DAMAGE_MULT)


def test_an_executing_blow_kills_a_stunned_fighter_whatever_its_health() -> None:
    enemy = _enemy()
    enemy.add_stun(enemy.stun_max)
    health = enemy.health

    result = _strike(enemy, damage=1, execute=True)

    assert result.executed is True
    assert result.killed is True
    assert result.actual_damage == pytest.approx(health)
    assert enemy.is_dead


def test_an_executing_blow_is_an_ordinary_one_on_a_fighter_not_stunned() -> None:
    enemy = _enemy()

    result = _strike(enemy, damage=1, execute=True)

    assert result.executed is False
    assert result.actual_damage == pytest.approx(1.0)
    assert not enemy.is_dead


def test_dizzy_state_exits_after_duration() -> None:
    from src.simulation.states.enemy_states import EnemyDizzyState

    enemy = _enemy()
    enemy.state_machine.current_state_name = DIZZY_STATE
    enemy.stagger_timer = 1.0
    state = EnemyDizzyState(enemy)

    # The timer is owned by Vitals.tick_timers, not by the state: the state reads
    # it. Decaying it here too halved every configured dizzy window.
    assert state.update(0.5) is None
    assert enemy.stagger_timer == pytest.approx(1.0)

    enemy.vitals.tick_timers(0.5)
    assert state.update(0.0) is None
    assert enemy.stagger_timer == pytest.approx(0.5)

    enemy.vitals.tick_timers(0.6)
    assert state.update(0.0) == "idle"


def test_player_dizzy_state_exits_via_ground_return() -> None:
    from src.simulation.states.player_states import PlayerDizzyState

    player = _player()
    player.state_machine.current_state_name = DIZZY_STATE
    player.stagger_timer = 1.0
    player.on_surface = {"floor": True, "left": False, "right": False}

    state = PlayerDizzyState(player)
    assert state.update(0.3) is None
    assert player.stagger_timer == pytest.approx(1.0)

    player.vitals.tick_timers(1.0)
    assert state.update(0.0) == "idle"  # timer clears, ground_return -> idle


def test_dizzy_stars_come_from_the_dizzy_state_and_not_from_the_parry() -> None:
    """They circle the head for as long as the entity is dizzy.

    Spawned on the block that caused the stun they arrived as a constellation
    at the instant of the third parry, which read as part of the block rather
    than as the state the block earned. Emitted on a cadence they fade in with
    the dizzy state and are gone shortly after it ends.
    """
    from src.presentation.fx.tuning import FxDizzy
    from src.simulation.level.systems.feedback_system import FeedbackSystem
    from src.simulation.sprite_groups import SpriteGroups
    from tests.unit.helpers import make_entity

    entity = make_entity(pos=(100.0, 100.0))
    entity.state_machine = SimpleNamespace(current_state_name="idle")
    groups = SpriteGroups()
    groups.entity_sprites.add(getattr(entity, "presentation", entity))
    system = FeedbackSystem(groups)

    for _ in range(4):
        system._spawn_movement_fx(FxDizzy.STAR_SPAWN_EVERY)
    assert len(groups.fx_sprites) == 0, "an idle fighter gets no stars"

    entity.state_machine.current_state_name = DIZZY_STATE
    system._spawn_movement_fx(FxDizzy.STAR_SPAWN_EVERY)

    stars = [sprite for sprite in groups.fx_sprites if isinstance(sprite, OrbitParticle)]
    assert len(stars) == FxDizzy.STAR_BATCH
    assert all(star.ttl == pytest.approx(FxDizzy.STAR_TTL) for star in stars)
    assert all(star.velocity.length() == 0.0 for star in stars), "they orbit, they do not fall"

    entity.state_machine.current_state_name = "idle"
    system._spawn_movement_fx(FxDizzy.STAR_SPAWN_EVERY)

    assert all(star.ttl == pytest.approx(FxDizzy.STAR_TTL) for star in stars), (
        "and no more arrive once the state is over"
    )


def test_a_parry_that_stuns_spawns_no_stars_of_its_own() -> None:
    """The stun event carries the camera shake, and nothing else."""
    from pygame.sprite import Group

    from src.simulation.level.systems.contact_system import GuardEvent

    entity = SimpleNamespace(
        hitbox=pygame.FRect(100, 100, 40, 48),
        stun_duration=1.5,
        facing_right=True,
    )
    group = Group()
    _spawn_guard_fx(GuardEvent("stun", entity), group)

    assert len(group) == 0
