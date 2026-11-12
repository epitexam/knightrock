"""Two attack buttons, and the moves they become: chains, dash, dive, riposte.

The catalogue is light and heavy. What a press throws depends on what the
fighter is doing: the next link of the running chain, a lunge out of a dash, a
dive with Down held in the air, a riposte just after a parry, else the
button's move for the posture. These tests drive a real ``Player`` against a
real target in a flat arena, with the pad played tick by tick.
"""

from __future__ import annotations

from dataclasses import replace

import pygame

from src.combat.frame_data import AttackButton, Stance, move_id
from src.combat.refusal import Refusal
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.sprites import Sprite
from src.data.provider import shipped_gameplay_data
from src.entities.attack_moves import MoveContext, resolve_move
from src.entities.enemies.factory import create_enemy
from src.entities.player import Player

DT = 1 / 60
LIGHT, HEAVY = InputAction.ATTACK_1, InputAction.ATTACK_2
CATALOGUE = shipped_gameplay_data().attack_sets["player"]


class _Pad(InputProvider):
    def __init__(self) -> None:
        self.held: frozenset[InputAction] = frozenset()
        self.axis = 0.0

    def poll(self) -> InputState:
        return InputState(move_axis=self.axis, held_actions=self.held)


def _arena(with_target: bool = True) -> tuple[Level, _Pad, Player, list[str]]:
    """A floor, the player, a passive goblin in reach; the moves started, in order."""
    pad = _Pad()
    data = shipped_gameplay_data()
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
        gameplay_data=data,
    )
    floor = Sprite(
        (0.0, 400.0), surf=pygame.Surface((5000, 64)), groups=(level.groups.collision_sprites,)
    )
    level.spatial_hash.add(floor)
    player = level.player
    player.animator = None
    if with_target:
        target = create_enemy(
            "goblin",
            (1052.0, 340.0),
            (level.groups.all_sprites,),
            level.groups.collision_sprites,
            player,
            config=replace(data.enemies["goblin"], has_ai=False, health=1e6, max_health=1e6),
            spatial_hash=level.spatial_hash,
        )
        target.animator = None
        level.groups.add_fighter(target)
    for _ in range(40):
        level.update(DT)
    player.facing_right = True
    started: list[str] = []
    start = player.combat.start_attack

    def recording(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        refusal = start(name, *args, **kwargs)
        if refusal is Refusal.NONE:
            started.append(str(name))
        return refusal

    player.combat.start_attack = recording  # type: ignore[method-assign]
    return level, pad, player, started


def _play(level: Level, pad: _Pad, presses: dict[int, InputAction], ticks: int) -> None:
    for tick in range(ticks):
        pad.held = frozenset({presses[tick]}) if tick in presses else frozenset()
        level.update(DT)


def _every(button: InputAction, step: int, count: int) -> dict[int, InputAction]:
    return {index * step: button for index in range(count)}


# -- resolution, without a fighter --------------------------------------------------


def test_with_nothing_going_on_a_button_throws_its_posture_move() -> None:
    assert resolve_move(LIGHT, MoveContext(Stance.GROUND)) == "light_attack"
    assert resolve_move(HEAVY, MoveContext(Stance.GROUND)) == "heavy_attack"
    assert resolve_move(LIGHT, MoveContext(Stance.AIR)) == "air_attack"
    assert resolve_move(HEAVY, MoveContext(Stance.CROUCH)) == "crouch_sweep"


def test_a_running_move_hands_the_button_to_its_chain() -> None:
    running = CATALOGUE[move_id("light_attack")]

    assert resolve_move(LIGHT, MoveContext(Stance.GROUND, running=running)) == "twin_fangs"
    assert resolve_move(HEAVY, MoveContext(Stance.GROUND, running=running)) == "uppercut"


def test_the_riposte_comes_before_everything() -> None:
    running = CATALOGUE[move_id("light_attack")]
    context = MoveContext(Stance.GROUND, running=running, dashing=True, riposte=True)

    assert resolve_move(HEAVY, context) == "riposte"


def test_a_dash_turns_the_light_button_into_the_dash_attack() -> None:
    assert resolve_move(LIGHT, MoveContext(Stance.GROUND, dashing=True)) == "dash_attack"
    assert resolve_move(HEAVY, MoveContext(Stance.GROUND, dashing=True)) == "heavy_attack"


def test_down_in_the_air_turns_the_heavy_button_into_the_dive() -> None:
    assert resolve_move(HEAVY, MoveContext(Stance.AIR, diving=True)) == "air_sweep"
    assert resolve_move(LIGHT, MoveContext(Stance.AIR, diving=True)) == "air_attack"


# -- the catalogue -----------------------------------------------------------------


def test_the_ground_light_chain_is_three_links_and_a_finisher() -> None:
    first = CATALOGUE[move_id("light_attack")]
    second = CATALOGUE[first.follow_up(AttackButton.LIGHT)]  # type: ignore[index]
    third = CATALOGUE[second.follow_up(AttackButton.LIGHT)]  # type: ignore[index]

    assert third.follow_ups == ()
    assert third.phases[-1].hit.knockback.power[0] > 4 * first.phases[0].hit.knockback.power[0]


def test_two_attack_buttons_and_the_special_are_all_the_game_reads() -> None:
    names = {action.value for action in InputAction}

    assert "attack3" not in names and "attack4" not in names


def test_the_test_bench_moves_are_not_in_the_players_catalogue() -> None:
    for name in ("p5_shapes", "circle_burst", "sky_launcher", "otg_slam"):
        assert name not in CATALOGUE


# -- playing it ----------------------------------------------------------------


def test_three_light_presses_play_the_chain_in_order() -> None:
    level, pad, _player, started = _arena()

    _play(level, pad, _every(LIGHT, 10, 3), 60)

    assert started == ["light_attack", "twin_fangs", "sweeping_arc"]


def test_a_press_made_early_in_a_link_is_played_as_the_next_link() -> None:
    """Pressed during the first link's startup: buffered, then played on contact."""
    level, pad, _player, started = _arena()

    _play(level, pad, {0: LIGHT, 2: LIGHT}, 40)

    assert started[:2] == ["light_attack", "twin_fangs"]


def test_a_chain_continues_on_contact_without_waiting_for_the_recovery() -> None:
    level, pad, _player, started = _arena()
    first = CATALOGUE[move_id("light_attack")].phases[0]
    second_at = None
    for tick in range(40):
        pad.held = frozenset({LIGHT}) if tick in (0, 2) else frozenset()
        level.update(DT)
        if len(started) == 2:
            second_at = tick
            break

    assert started == ["light_attack", "twin_fangs"]
    assert second_at is not None
    # Before the first link's recovery could even begin, hit-stop included.
    assert second_at < first.startup_frames + first.active_frames + 6


def test_each_link_lunges_again() -> None:
    level, pad, player, started = _arena(with_target=False)
    lunges: list[float] = []
    for tick in range(30):
        pad.held = frozenset({LIGHT}) if tick in (0, 9) else frozenset()
        before = len(started)
        level.update(DT)
        if len(started) > before:
            lunges.append(player.velocity.x)

    assert started == ["light_attack", "twin_fangs"]
    assert all(speed > 100.0 for speed in lunges), lunges


def test_a_parry_opens_one_riposte() -> None:
    level, pad, player, started = _arena()
    player.guard.riposte_timer = 0.5

    _play(level, pad, {0: HEAVY, 30: HEAVY}, 50)

    assert started[0] == "riposte"
    assert started[1:] == ["heavy_attack"]
    assert player.guard.riposte_timer == 0.0


def test_a_heavy_tap_played_from_the_buffer_does_not_charge_forever() -> None:
    """Tapped during a move that cannot be cancelled, and released before it plays.

    The riposte cancels into nothing, so the tap waits in the buffer and plays
    when the riposte ends -- by then the button is up. It used to start a charge
    that waited for a release which had already happened.
    """
    level, pad, player, started = _arena()
    player.guard.riposte_timer = 0.5

    _play(level, pad, {0: HEAVY, 22: HEAVY}, 60)

    assert started == ["riposte", "heavy_attack"]
    assert not player.combat.charging.is_charging


def test_a_dash_then_light_is_the_dash_attack() -> None:
    level, pad, player, started = _arena(with_target=False)

    _play(level, pad, {0: InputAction.DASH, 3: LIGHT}, 30)

    assert started == ["dash_attack"]
