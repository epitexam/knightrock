"""What every shipped attack does to every kind of target, pinned.

A characterization test: the expected outcomes in
``tests/golden/hit_outcomes.json`` were recorded from the code as it was, not
written by hand. It exists so that the hit-resolution rules can be moved
around (they are spread over ``HitResolver``, ``Entity``, ``Player``,
``ReactionComponent`` and ``ContactSystem``) with proof that no outcome
changed.

Every hit goes through the real ``ContactSystem.resolve`` with real ``Player``
and ``Enemy`` objects, so parry, perfect dodge, armour, juggle, finisher, stun,
execution and hit-stop are all on the path. Nothing here ticks an entity, so the art in
``assets/`` is not needed.

After an *intentional* change to a combat rule, regenerate and read the diff::

    UPDATE_GOLDENS=1 uv run pytest tests/unit/test_hit_outcome_matrix.py
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pygame.sprite import Group

from src.platform.input.input_manager import InputManager
from src.simulation.combat.frame_data import AttackDefinition, Height, MoveId
from src.simulation.data.provider import GameplayData, load_gameplay_data
from src.simulation.entities.enemies.enemy import Enemy
from src.simulation.entities.entity import Entity
from src.simulation.entities.player import Player
from src.simulation.level.systems.contact_system import ContactSystem, OffensiveBox
from src.simulation.settings import Fury, Rush
from src.simulation.states.player_states import PlayerState

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "hit_outcomes.json"

#: Where the fighters stand: the attacker on the left, the target just right of it.
ATTACKER_X = 100.0
TARGET_X = 140.0
FLOOR_Y = 200.0


@pytest.fixture(scope="module")
def data() -> GameplayData:
    return load_gameplay_data()


def _ground(entity: Entity, x: float) -> None:
    entity.hitbox.midbottom = (x, FLOOR_Y)
    entity.sync_rects()
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    entity.velocity.update(0.0, 0.0)


def _player(data: GameplayData) -> Player:
    player = Player((0.0, 0.0), Group(), Group(), [], InputManager(), config=data.player)
    _ground(player, TARGET_X)
    player.facing_right = False  # facing the attacker on its left
    return player


def _enemy(data: GameplayData, name: str, x: float = TARGET_X) -> Enemy:
    enemy = Enemy((0.0, 0.0), Group(), Group(), None, data.enemies[name], enemy_type=name)
    _ground(enemy, x)
    enemy.facing_right = x < TARGET_X
    return enemy


# -- target situations ---------------------------------------------------------


def _player_idle(player: Player) -> None:
    pass


def _player_guard(player: Player) -> None:
    player.state_machine.change_state(PlayerState.GUARD, force=True)


def _player_guard_back(player: Player) -> None:
    _player_guard(player)
    player.facing_right = True  # back to the attacker


def _player_recharging(player: Player) -> None:
    player.state_machine.change_state(PlayerState.RECHARGE, force=True)


def _player_dash_early(player: Player) -> None:
    """A dodge that has only just begun: a hit through it is a dark step."""
    player.dash.request(-1.0)
    player.state_machine.change_state(PlayerState.DASH, force=True)


def _player_dash_late(player: Player) -> None:
    """A dodge whose window has run out: a hit through it is dodged, and that is all."""
    _player_dash_early(player)
    player.update_timers(Rush.WINDOW)


def _player_airborne(player: Player) -> None:
    player.on_surface["floor"] = False


def _player_low_health(player: Player) -> None:
    player.health = 6.0


def _player_dark_side(player: Player) -> None:
    player.fury.gain(Fury.MAX)
    player.fury.start_dark()


PLAYER_SITUATIONS: dict[str, Callable[[Player], None]] = {
    "idle": _player_idle,
    "guard": _player_guard,
    "guard_back": _player_guard_back,
    "recharging": _player_recharging,
    "dash_early": _player_dash_early,
    "dash_late": _player_dash_late,
    "airborne": _player_airborne,
    "low_health": _player_low_health,
    "dark_side": _player_dark_side,
}


def _nearly_stunned(enemy: Enemy) -> None:
    """One point short of a full stun gauge."""
    assert enemy.stun_max is not None
    enemy.stun = enemy.stun_max - 1.0


def _enemy_idle(enemy: Enemy) -> None:
    pass


def _guarding(height: Height) -> Callable[[Enemy], None]:
    def prepare(enemy: Enemy) -> None:
        enemy.facing_right = False  # facing the attacker, on its left
        enemy.guard = height

    return prepare


def _enemy_airborne(enemy: Enemy) -> None:
    enemy.on_surface["floor"] = False


def _enemy_stunned(enemy: Enemy) -> None:
    assert enemy.stun_max is not None
    enemy.add_stun(enemy.stun_max)


def _enemy_downed(enemy: Enemy) -> None:
    enemy.state_machine.change_state("downed", force=True)


def _enemy_doomed(enemy: Enemy) -> None:
    enemy.doom()


def _enemy_low_health(enemy: Enemy) -> None:
    enemy.health = 8.0


def _enemy_otg(enemy: Enemy) -> None:
    enemy.otg_timer = 0.3


ENEMY_SITUATIONS: dict[str, tuple[str, Callable[[Enemy], None]]] = {
    "goblin_idle": ("goblin", _enemy_idle),
    "goblin_guard_high": ("goblin", _guarding(Height.HIGH)),
    "goblin_guard_low": ("goblin", _guarding(Height.LOW)),
    "goblin_airborne": ("goblin", _enemy_airborne),
    "goblin_stunned": ("goblin", _enemy_stunned),
    "goblin_nearly_stunned": ("goblin", _nearly_stunned),
    "goblin_downed": ("goblin", _enemy_downed),
    "goblin_doomed": ("goblin", _enemy_doomed),
    "goblin_low_health": ("goblin", _enemy_low_health),
    "goblin_otg": ("goblin", _enemy_otg),
    "slime_idle": ("slime", _enemy_idle),
    "shell_armoured": ("shell", _enemy_idle),
    "dummy_armoured": ("dummy", _enemy_idle),
}


# -- one hit ---------------------------------------------------------------------


def _name(state: str | None) -> str:
    """A state name as its plain string, whatever enum it came from."""
    return str(getattr(state, "value", state))


def _round(value: float) -> float:
    return round(float(value), 4)


def _strike(attacker: Entity, target: Entity, definition: AttackDefinition, phase: int) -> dict:
    """Land one phase of ``definition`` on ``target`` and record what changed."""
    hit = definition.phases[phase].hit
    box = target.hitbox.copy()
    offensive = OffensiveBox(
        box=box,
        swept=(box,),
        hit=hit,
        faction=attacker.faction,
        owner_id=attacker.id,
        can_contact=attacker.combat.can_contact,
        record_contact=lambda landed: attacker.combat.record_contact(landed.id),
        attacker=attacker,
    )
    system = ContactSystem()
    system.begin_tick()
    outcome = system.resolve((offensive,), (target,))
    result: dict[str, Any] = {
        "contacts": outcome.metrics.contacts,
        "hit_stop": _round(outcome.hit_stop),
        "impact": _round(outcome.impact),
        "events": [event.kind for event in outcome.guard_events],
        "zone": [contact.zone_index for contact in system.zone_contacts],
        "health": _round(target.health),
        "dead": target.is_dead,
        "velocity": [_round(target.velocity.x), _round(target.velocity.y)],
        "state": _name(target.state_machine.current_state_name),
        "hurt": target.combat.is_hurt,
        "hurt_timer": _round(target.combat.hurt_timer),
        "stagger_timer": _round(target.stagger_timer),
        "invincibility_timer": _round(target.invincibility_timer),
        "gravity_scale": _round(target.gravity_scale),
        "juggle_timer": _round(target.juggle_timer),
        "super_armor_count": target.super_armor_count,
        "parries_given": target.parries_given,
        "stun": _round(target.stun),
        "attacker_state": _name(attacker.state_machine.current_state_name),
        "attacker_stun": _round(attacker.stun),
        "attacker_combo": attacker.combat.combo_count,
    }
    if isinstance(target, Player):
        result["battery"] = _round(target.battery.amount)
        result["fury"] = _round(target.fury.amount)
        result["rush_timer"] = _round(target.rush_timer)
    if isinstance(attacker, Player):
        result["attacker_fury"] = _round(attacker.fury.amount)
        result["attacker_prompt"] = (
            None if attacker.prompt.kind is None else attacker.prompt.kind.value
        )
    return result


def _phases(definition: AttackDefinition) -> range:
    return range(len(definition.phases))


def _all_attacks(data: GameplayData) -> list[tuple[str, MoveId, AttackDefinition]]:
    return [
        (owner, name, definition)
        for owner, table in sorted(data.attack_sets.items())
        for name, definition in sorted(table.items())
    ]


def _matrix(data: GameplayData) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    # Every attack in the game, thrown by a goblin at the player in each situation.
    for owner, name, definition in _all_attacks(data):
        for phase in _phases(definition):
            for situation, prepare in PLAYER_SITUATIONS.items():
                player = _player(data)
                prepare(player)
                attacker = _enemy(data, "goblin", ATTACKER_X)
                rows[f"{owner}.{name}[{phase}] -> player.{situation}"] = _strike(
                    attacker, player, definition, phase
                )
    # Every player attack, thrown by the player at each kind of enemy.
    for name, definition in sorted(data.attack_sets["player"].items()):
        for phase in _phases(definition):
            for situation, (enemy_name, prepare) in ENEMY_SITUATIONS.items():
                target = _enemy(data, enemy_name)
                prepare(target)
                attacker = _player(data)
                _ground(attacker, ATTACKER_X)
                attacker.facing_right = True
                rows[f"player.{name}[{phase}] -> {situation}"] = _strike(
                    attacker, target, definition, phase
                )
    return rows


def test_every_hit_outcome_matches_the_recorded_one(data: GameplayData) -> None:
    actual = _matrix(data)
    if os.environ.get("UPDATE_GOLDENS") == "1" or not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
        if os.environ.get("UPDATE_GOLDENS") != "1":
            pytest.fail(f"no reference yet; recorded {len(actual)} outcomes in {GOLDEN.name}")
    expected = json.loads(GOLDEN.read_text())
    assert sorted(actual) == sorted(expected), "the set of attacks or situations changed"
    changed = {
        key: (expected[key], actual[key]) for key in expected if expected[key] != actual[key]
    }
    assert not changed, f"{len(changed)} outcome(s) changed, first: {next(iter(changed.items()))}"


def test_the_matrix_exercises_every_kind_of_outcome(data: GameplayData) -> None:
    """A matrix in which nothing is guarded, dodged, stunned or doomed would pin nothing."""
    matrix = _matrix(data)
    rows = matrix.values()
    events = {kind for row in rows for kind in row["events"]}
    assert {"guard", "stun", "doom", "dodge"} <= events, events
    assert any(row.get("attacker_prompt") == "death_blow" for row in rows), "no death blow"
    assert any(row["dead"] for row in rows), "no finisher or kill in the matrix"
    executed = [
        key for key, row in matrix.items() if key.endswith("goblin_stunned") and row["dead"]
    ]
    spared = [
        key for key, row in matrix.items() if key.endswith("goblin_stunned") and not row["dead"]
    ]
    assert executed and spared, "a stunned goblin is executed by some moves and not by others"
    assert any(row["state"] == "knockback" for row in rows), "no launch in the matrix"
    assert any(row["contacts"] == 0 for row in rows), "nothing was ever refused"
