"""The rules that make a fight read and flow: what a hit shows, what it pays, how enemies take turns.

Driven on a real ``Player`` and real enemies in a flat arena, with the pad
played tick by tick, except where a rule is a single function worth pinning on
its own.
"""

from __future__ import annotations

import random
from dataclasses import replace
from unittest.mock import Mock

import pygame
import pytest

from src.combat.combatant_protocol import DamageResult
from src.combat.frame_data import HitProperties, PhaseState
from src.combat.knockback import KnockbackConfig
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.feedback_system import FeedbackSystem
from src.core.settings import AI, CameraShake
from src.core.settings import Combat as CombatSettings
from src.core.sprite_groups import SpriteGroups
from src.core.sprites import Sprite
from src.data.enemies import read_enemy_config
from src.data.errors import GameplayDataError
from src.data.provider import shipped_gameplay_data
from src.entities.enemies.enemy import Enemy
from src.entities.enemies.factory import create_enemy
from src.entities.enemies.schema import EnemyMove
from src.entities.player import Player
from src.states.enemy_states import EnemyState
from tests.unit.helpers import make_active_attacker, make_entity

DT = 1 / 60
LIGHT = InputAction.ATTACK_1
DATA = shipped_gameplay_data()


class _Pad(InputProvider):
    def __init__(self) -> None:
        self.held: frozenset[InputAction] = frozenset()
        self.axis = 0.0

    def poll(self) -> InputState:
        return InputState(move_axis=self.axis, held_actions=self.held)


def _arena() -> tuple[Level, _Pad, Player]:
    pad = _Pad()
    spawn = ObjectData(
        name="player",
        x=1000.0,
        y=300.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )
    level = Level(
        pygame.Surface((1152, 648)),
        LevelData(
            width=80,
            height=12,
            tile_size=64,
            object_layers={"E": ObjectLayerData(name="E", objects=[spawn])},
            config=LevelConfig(),
        ),
        InputManager(pad),
        gameplay_data=DATA,
    )
    floor = Sprite(
        (0.0, 400.0), surf=pygame.Surface((5000, 64)), groups=(level.groups.collision_sprites,)
    )
    level.spatial_hash.add(floor)
    level.player.animator = None
    return level, pad, level.player


def _foe(level: Level, name: str, x: float, **changes: object) -> Enemy:
    config = replace(DATA.enemies[name], **changes) if changes else DATA.enemies[name]
    foe = create_enemy(
        name,
        (x, 340.0),
        (level.groups.all_sprites,),
        level.groups.collision_sprites,
        level.player,
        config=config,
        spatial_hash=level.spatial_hash,
    )
    foe.animator = None
    level.groups.add_fighter(foe)
    return foe


def _settle(level: Level, ticks: int = 60) -> None:
    for _ in range(ticks):
        level.update(DT)


# -- What a hit shows ---------------------------------------------------------


def test_a_landed_hit_is_reported_with_its_strength() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="player")
    attacker = make_active_attacker(target)
    system = CombatSystem()

    system.process_attacks([attacker, target])

    [event] = system.impact_events
    assert event.strength == pytest.approx(100.0)
    assert not event.killed


def test_a_hit_with_its_own_hit_stop_freezes_for_exactly_that() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="player")
    attacker = make_active_attacker(target)
    attacker.combat.current_phase.hit = HitProperties(damage=5, hit_stop=0.25)
    system = CombatSystem()

    system.process_attacks([attacker, target])

    assert system.hit_stop_timer == pytest.approx(0.25)


def test_a_killing_blow_holds_the_world_at_least_the_kill_freeze() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="player", health=1.0)
    attacker = make_active_attacker(target)
    system = CombatSystem()

    system.process_attacks([attacker, target])

    assert target.is_dead
    assert system.hit_stop_timer >= CombatSettings.KILL_HITSTOP
    assert system.impact_events[0].killed


def test_a_flinch_hit_does_not_push_a_grounded_target_but_still_carries_a_juggle() -> None:
    hit = HitProperties(damage=5, knockback=KnockbackConfig(power=(120.0, -40.0)), flinch=True)
    grounded = make_entity(pos=(100.0, 100.0), faction="player")
    grounded.on_surface["floor"] = True
    attacker = make_active_attacker(grounded)
    attacker.combat.current_phase.hit = hit
    CombatSystem().process_attacks([attacker, grounded])
    assert grounded.velocity.x == 0.0

    airborne = make_entity(pos=(100.0, 100.0), faction="player")
    airborne.on_surface["floor"] = False
    attacker = make_active_attacker(airborne)
    attacker.combat.current_phase.hit = hit
    CombatSystem().process_attacks([attacker, airborne])
    assert airborne.velocity.x == pytest.approx(120.0)


def test_every_landed_hit_shakes_a_little() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="player")
    attacker = make_active_attacker(target)
    system = CombatSystem()
    system.process_attacks([attacker, target])
    groups = SpriteGroups()
    camera = Mock()
    player = Mock(dash_started_this_frame=False)

    FeedbackSystem(groups).after_combat(system.impact, [], player, camera, system.impact_events)

    assert len(groups.fx_sprites) == 0, "a hit draws nothing of its own"
    camera.add_trauma.assert_called_once_with(
        pytest.approx(CameraShake.HIT_TRAUMA + 100.0 / CameraShake.HIT_DIV)
    )


# -- What a hit pays ------------------------------------------------------------

#: An ordinary hit that took health off its target.
_LANDED = DamageResult(applied=True, actual_damage=8.0)


def test_every_fourth_hit_of_a_combo_gives_a_dash_charge_back() -> None:
    _level, _pad, player = _arena()
    player.dash.charges = 0
    for count in range(1, 9):
        player.combat.combo.count = count
        player.on_hit_confirmed(player, True, _LANDED)
    assert player.dash.charges == 2

    player.combat.combo.count = 4
    player.on_hit_confirmed(player, False, _LANDED)
    assert player.dash.charges == 2, "the second target of one swing pays nothing"


def test_a_combo_never_fills_the_dash_past_its_charges() -> None:
    _level, _pad, player = _arena()
    player.combat.combo.count = CombatSettings.COMBO_DASH_REFILL_HITS
    player.on_hit_confirmed(player, True, _LANDED)
    assert player.dash.charges == player.dash.max_charges


def test_the_combo_pays_out_in_a_real_fight() -> None:
    level, pad, player = _arena()
    _foe(level, "goblin", 1052.0, has_ai=False, health=1e6, max_health=1e6)
    _settle(level)
    player.dash.charges = 0
    for tick in range(240):
        pad.held = frozenset({LIGHT}) if tick % 2 == 0 else frozenset()
        level.update(DT)
    assert player.dash.charges > 0


# -- What a hit lets the player do ----------------------------------------------


def _first_hit(level: Level, pad: _Pad, player: Player) -> None:
    pad.held = frozenset({LIGHT})
    for _ in range(30):
        level.update(DT)
        pad.held = frozenset()
        if player.combat.state.targets_hit:
            return
    raise AssertionError("the light attack never landed")


def test_a_jump_cancels_an_attack_that_has_hit() -> None:
    level, pad, player = _arena()
    _foe(level, "goblin", 1052.0, has_ai=False, health=1e6, max_health=1e6)
    _settle(level)
    _first_hit(level, pad, player)
    while level.gameplay_loop.combat_system.in_hit_stop:
        level.update(DT)

    pad.held = frozenset({InputAction.JUMP})
    level.update(DT)

    assert player.state_machine.current_state_name == "jump"
    assert player.velocity.y < 0.0
    assert not player.combat.is_attacking


def test_a_whiffed_attack_stays_committed_to_its_recovery() -> None:
    level, pad, player = _arena()
    _settle(level)
    pad.held = frozenset({LIGHT})
    level.update(DT)
    pad.held = frozenset()
    while player.combat.state.sub_state is not PhaseState.ACTIVE:
        level.update(DT)

    pad.held = frozenset({InputAction.JUMP})
    level.update(DT)

    assert player.state_machine.current_state_name == "attack"


def test_dashing_through_an_enemy_costs_the_player_nothing() -> None:
    level, pad, player = _arena()
    _foe(level, "goblin", 1120.0, has_ai=False)
    _settle(level)
    health = player.health
    pad.axis = 1.0
    pad.held = frozenset({InputAction.DASH})
    for _ in range(40):
        level.update(DT)
        pad.held = frozenset()
    assert player.health == health


# -- How enemies choose and take turns ---------------------------------------


def test_the_shipped_enemies_choose_between_moves() -> None:
    goblin = DATA.enemies["goblin"]
    assert [move.name for move in goblin.moves] == ["claw_swipe", "claw_reach"]
    assert all(move.name in goblin.attacks for move in goblin.moves)


@pytest.mark.parametrize(
    ("moves", "message"),
    [
        ([{"name": "nope", "range": 60}], "not one of this enemy's attacks"),
        ([{"name": "claw_swipe", "range": 0}], "above 0"),
        ([{"name": "claw_swipe", "range": 60, "speed": 2}], "speed"),
        ({"name": "claw_swipe"}, "must be a list"),
    ],
)
def test_a_bad_moves_list_is_refused_with_its_place(moves: object, message: str) -> None:
    raw = {"size": [36, 48], "color": [1, 2, 3], "health": 10, "attacks": "goblin"}
    raw["moves"] = moves
    with pytest.raises(GameplayDataError, match=message):
        read_enemy_config(raw, "enemies.json#goblin", DATA.attack_sets)


def test_a_single_move_type_draws_nothing_from_its_random_stream() -> None:
    level, _pad, _player = _arena()
    shell = _foe(level, "shell", 1300.0, moves=())
    state = shell.rng.getstate()
    assert shell.plan_move() == "shell_bash"
    assert shell.rng.getstate() == state


def test_a_choosing_type_plays_every_move_by_its_weight() -> None:
    level, _pad, _player = _arena()
    goblin = _foe(level, "goblin", 1300.0)
    goblin.rng = random.Random(3)
    picks = [goblin.plan_move() for _ in range(600)]
    share = picks.count("claw_swipe") / len(picks)
    assert share == pytest.approx(2 / 3, abs=0.06)


def test_a_chase_throws_the_move_it_closed_in_for() -> None:
    level, _pad, player = _arena()
    goblin = _foe(level, "goblin", 1250.0)
    thrown: set[str] = set()
    for seed in range(12):
        goblin.rng = random.Random(seed)
        goblin.state_machine.change_state(EnemyState.CHASE, force=True)
        planned = goblin.state_machine.states[EnemyState.CHASE].planned_move
        for _ in range(240):
            level.update(DT)
            if goblin.combat.is_attacking:
                break
        assert goblin.combat.state.attack_name == planned
        thrown.add(planned)
        goblin.combat.state.end()
        goblin.hitbox.centerx = player.hitbox.centerx + 250.0
    assert thrown == {"claw_swipe", "claw_reach"}


def test_a_crowd_takes_turns_at_the_player() -> None:
    level, _pad, player = _arena()
    player.vitals.max_health = player.vitals.health = 1e6
    # One move with the reach to strike from behind another goblin, so all
    # three are in range together and only the slots keep the third out.
    reach = (EnemyMove("claw_reach", 140.0),)
    foes = [_foe(level, "goblin", x, moves=reach) for x in (940.0, 1060.0, 1100.0)]
    most = 0
    waited = False
    for _ in range(900):
        level.update(DT)
        attacking = [
            foe for foe in foes if foe.state_machine.current_state_name == EnemyState.ATTACK
        ]
        most = max(most, len(attacking))
        waited |= len(attacking) == AI.MAX_ATTACKERS and any(
            foe.state_machine.current_state_name == EnemyState.CHASE
            and foe.is_player_in_range(foe.move_range(None))
            for foe in foes
        )
    assert most == AI.MAX_ATTACKERS
    assert waited, "a third goblin in reach waited for a slot"
    assert all(foe.combat.attacks_started > 0 for foe in foes), "every goblin got its turn"
