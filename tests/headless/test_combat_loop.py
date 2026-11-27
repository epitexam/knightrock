"""The combat loop, played: slashes and guards, doom and the death blow, throws,
blade locks, the battery, fury and the dark side, the dark step, the slot machine.

Every test drives a real ``Player`` against real enemies in a flat arena
(``tests/headless/arena.py``), so the whole tick is on the path.
"""

from __future__ import annotations

import math
import random

import pytest

from src.shared.input_actions import InputAction
from src.simulation.combat.combatant_protocol import Finish
from src.simulation.combat.frame_data import Height, PhaseState
from src.simulation.entities.enemies.enemy import Enemy
from src.simulation.entities.enemies.schema import EnemyMove
from src.simulation.entities.player import Player
from src.simulation.entities.player_kit import Direction, Power, PromptKind
from src.simulation.level.level import Level
from src.simulation.settings import Battery, Clash, Finisher, Fury, Rush, Slot, Throw
from src.simulation.settings import Guard as GuardSettings
from src.simulation.states.player_states import PlayerState
from tests.headless.arena import (
    BEAT,
    DARK_SIDE,
    DASH,
    DOWN,
    DT,
    GUARD,
    PLAYER_X,
    SLASH,
    Pad,
    arena,
    foe,
    run_out_hit_stop,
    settle,
    tap,
)

UP = InputAction.MOVE_UP

#: An enemy with its states, its gauges and its guard that never comes for the player.
STILL = {"vision_range": 0.0, "chase_speed": 0.0}

#: What to give for each direction a prompt asks.
ANSWER = {
    Direction.LEFT: (-1.0, frozenset()),
    Direction.RIGHT: (1.0, frozenset()),
    Direction.UP: (0.0, frozenset({UP})),
    Direction.DOWN: (0.0, frozenset({DOWN})),
}


def _state(fighter: Player | Enemy) -> str:
    name = fighter.state_machine.current_state_name
    return str(getattr(name, "value", name))


def _answer(level: Level, pad: Pad, direction: Direction) -> None:
    """Give ``direction``: a tick at rest, then a tick of the push."""
    pad.axis, pad.held = 0.0, frozenset()
    level.update(DT)
    pad.axis, pad.held = ANSWER[direction]
    level.update(DT)
    pad.axis, pad.held = 0.0, frozenset()


def _wrong(direction: Direction) -> Direction:
    return Direction.LEFT if direction is not Direction.LEFT else Direction.RIGHT


def _doomed_goblin() -> tuple[Level, Pad, Player, Enemy]:
    """A goblin a slash has just brought to nothing: the death blow is asked."""
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    goblin.health = 1.0
    tap(level, pad, SLASH, ticks=8)
    run_out_hit_stop(level)
    level.update(DT)
    assert goblin.is_doomed
    assert player.prompt.kind is PromptKind.DEATH_BLOW
    return level, pad, player, goblin


# -- the death blow ---------------------------------------------------------------


def test_a_slash_that_would_kill_leaves_the_foe_doomed_and_freezes_the_fight() -> None:
    _level, _pad, player, goblin = _doomed_goblin()

    assert not goblin.is_dead
    assert goblin.health == Finisher.DOOM_HEALTH
    assert player.world_time_scale == Finisher.TIME_SCALE
    assert _state(player) == PlayerState.PROMPT.value
    assert player.is_invincible


def test_the_right_direction_lands_the_death_blow_and_spins_the_slot() -> None:
    level, pad, player, goblin = _doomed_goblin()
    direction = player.prompt.expected
    assert direction is not None

    _answer(level, pad, direction)
    for _ in range(30):
        level.update(DT)

    assert goblin.is_dead
    assert not player.prompt.active
    assert player.fury.amount >= Fury.DEATH_BLOW
    assert player.slot.reels is not None


def test_the_wrong_direction_lets_the_foe_get_back_up() -> None:
    level, pad, player, goblin = _doomed_goblin()
    direction = player.prompt.expected
    assert direction is not None

    _answer(level, pad, _wrong(direction))

    assert not player.prompt.active
    assert player.world_time_scale == 1.0
    assert player.slot.reels is None
    assert not goblin.is_doomed and not goblin.is_dead
    assert goblin.health == pytest.approx(goblin.max_health * Finisher.RECOVER_RATIO)


def test_a_prompt_left_unanswered_runs_out_and_the_foe_gets_back_up() -> None:
    level, _pad, player, goblin = _doomed_goblin()

    for _ in range(math.ceil(Finisher.WINDOW / DT) + 2):
        level.update(DT)

    assert not player.prompt.active
    assert not goblin.is_dead
    assert goblin.health == pytest.approx(goblin.max_health * Finisher.RECOVER_RATIO)


def test_a_doomed_foe_no_prompt_asks_for_dies_alone() -> None:
    level, _pad, player, goblin = _doomed_goblin()
    player.prompt.reset()

    for _ in range(math.ceil(Finisher.DOOM_TIME / DT) + 5):
        level.update(DT)

    assert goblin.is_dead


def test_only_the_death_blow_reaches_a_doomed_foe() -> None:
    level, pad, player, goblin = _doomed_goblin()
    player.prompt.reset()
    level.update(DT)

    tap(level, pad, SLASH, ticks=10)

    assert goblin.is_doomed and not goblin.is_dead


# -- guards -------------------------------------------------------------------------


def _guarding_goblin(height: Height) -> tuple[Level, Pad, Player, Enemy]:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = height
    goblin.guard_timer = 60.0
    goblin.facing_right = False
    return level, pad, player, goblin


def test_a_high_guard_stops_the_high_slash_and_not_the_low_one() -> None:
    level, pad, _player, goblin = _guarding_goblin(Height.HIGH)
    goblin.moves = ()  # no counter: this is about the guard alone
    health = goblin.health

    tap(level, pad, SLASH, ticks=12)
    assert goblin.health == health

    pad.held = frozenset({DOWN})
    level.update(DT)
    pad.held = frozenset({DOWN, SLASH})
    level.update(DT)
    pad.held = frozenset()
    for _ in range(12):
        level.update(DT)
    assert goblin.health < health


def test_a_low_guard_stops_the_low_slash() -> None:
    level, pad, _player, goblin = _guarding_goblin(Height.LOW)
    health = goblin.health

    pad.held = frozenset({DOWN})
    level.update(DT)
    pad.held = frozenset({DOWN, SLASH})
    level.update(DT)
    pad.held = frozenset()
    for _ in range(12):
        level.update(DT)

    assert goblin.health == health


def test_a_punch_breaks_the_guard_it_meets() -> None:
    level, pad, _player, goblin = _guarding_goblin(Height.HIGH)
    health = goblin.health

    tap(level, pad, BEAT, ticks=12)

    assert goblin.health < health
    assert goblin.guard is None
    assert goblin.guard_broken_timer > 0.0


def test_the_raised_guard_stops_a_claw_and_costs_battery() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 50.0, guards=False)
    settle(level, 10)
    pad.held = frozenset({GUARD})

    for _ in range(240):
        level.update(DT)

    assert _state(player) == PlayerState.GUARD.value
    assert player.health == player.max_health
    assert player.battery.amount < Battery.MAX
    assert not goblin.is_dead


# -- stun, throw, stab ---------------------------------------------------------------


def test_beats_stun_and_the_beat_button_then_throws() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)

    for tick in range(240):
        pad.held = frozenset({BEAT}) if tick % 2 == 0 else frozenset()
        level.update(DT)
        if goblin.is_stunned:
            break
        if not goblin.is_dead and abs(goblin.hitbox.centerx - player.hitbox.centerx) > 70:
            goblin.hitbox.centerx = player.hitbox.centerx + 52.0
            goblin.sync_rects()
    assert goblin.is_stunned
    pad.held = frozenset()
    run_out_hit_stop(level)
    goblin.hitbox.centerx = player.hitbox.centerx + 52.0
    goblin.sync_rects()
    # The slower catalogue leaves the beat that stunned the foe still in its
    # follow-through, and the blow may have lifted it off its feet. A grab
    # needs the fighter ready and the foe on the floor.
    for _ in range(60):
        if _state(player) == PlayerState.IDLE.value and goblin.on_surface.get("floor"):
            break
        level.update(DT)

    tap(level, pad, BEAT)

    assert player.prompt.kind is PromptKind.THROW
    assert len(player.prompt.steps) == Throw.STEPS
    for _ in range(Throw.STEPS):
        direction = player.prompt.expected
        assert direction is not None
        _answer(level, pad, direction)
    for _ in range(40):
        level.update(DT)

    assert goblin.is_dead
    assert player.fury.amount >= Fury.THROW


def test_a_beat_pressed_during_the_throw_does_not_cut_it_short() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    goblin.add_stun(goblin.stun_max or 0.0)
    tap(level, pad, BEAT)
    for _ in range(Throw.STEPS):
        direction = player.prompt.expected
        assert direction is not None
        _answer(level, pad, direction)
    assert player.combat.state.attack_name == "throw"

    tap(level, pad, BEAT, ticks=30)

    assert goblin.is_dead
    assert not player.prompt.active


def test_a_failed_throw_leaves_the_player_open() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    goblin.add_stun(goblin.stun_max or 0.0)

    tap(level, pad, BEAT)
    assert player.prompt.kind is PromptKind.THROW
    direction = player.prompt.expected
    assert direction is not None
    _answer(level, pad, _wrong(direction))

    assert _state(player) == PlayerState.STAGGER.value
    assert not goblin.is_dead


def test_a_launched_foe_lies_downed_and_the_low_slash_stabs_it() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    goblin.health = 500.0

    # The rising cut that ends the low chain lifts it off its feet.
    for move in ("slash_low_4",):
        player.combat.cancel_attack()
        assert player.start_move(move).name == "NONE"
        for _ in range(40):
            level.update(DT)
            if goblin.is_downed:
                break
    for _ in range(90):
        if goblin.is_downed:
            break
        level.update(DT)
    assert goblin.is_downed
    player.hitbox.centerx = goblin.hitbox.centerx - 50.0
    player.facing_right = True
    player.sync_rects()

    pad.held = frozenset({DOWN})
    level.update(DT)
    pad.held = frozenset({DOWN, SLASH})
    level.update(DT)
    pad.held = frozenset()
    assert player.combat.state.attack_name == "stab"
    for _ in range(30):
        level.update(DT)

    assert goblin.is_dead


# -- blade lock ----------------------------------------------------------------------


def test_two_blades_that_meet_lock_and_mashing_wins() -> None:
    """A high slash thrown just before the claw comes down meets it blade to blade.

    The claw swings from above, so a low slash passes under it: the lock is
    decided by where the two blades are, not by timing alone.
    """
    level, pad, player = arena()
    goblin = foe(
        level, "goblin", PLAYER_X + 50.0, guards=False, moves=(EnemyMove("claw_swipe", 90.0),)
    )
    goblin.rng.seed(1)
    settle(level, 20)
    for _ in range(600):
        state = goblin.combat.state
        phase = state.current_phase_def
        if (
            phase is not None
            and state.sub_state is PhaseState.STARTUP
            and phase.startup_frames - state.frame_counter == 2
        ):
            break
        level.update(DT)
    pad.held = frozenset({SLASH})
    level.update(DT)
    pad.held = frozenset()
    for _ in range(10):
        if player.prompt.kind is PromptKind.CLASH:
            break
        level.update(DT)
    assert player.prompt.kind is PromptKind.CLASH

    for tick in range(60):
        if not player.prompt.active:
            break
        pad.held = frozenset({SLASH}) if tick % 2 == 0 else frozenset()
        level.update(DT)

    assert not player.prompt.active
    # Won, the lock throws the goblin off balance: an opening, not a stun.
    assert not goblin.is_stunned
    assert goblin.state_machine.current_state_name == "stagger"
    assert not goblin.combat.is_attacking


def test_a_blade_lock_left_unmashed_is_lost_and_costs_health() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 50.0, guards=False, **STILL)
    settle(level, 10)

    player.on_clash(goblin)
    assert player.prompt.kind is PromptKind.CLASH
    for _ in range(math.ceil(Clash.WINDOW / DT) + 2):
        level.update(DT)

    assert not player.prompt.active
    assert player.health == player.max_health - Clash.LOSS_DAMAGE
    assert not goblin.is_stunned


# -- battery ------------------------------------------------------------------------


def test_guard_and_down_recharge_the_battery() -> None:
    level, pad, player = arena()
    settle(level, 10)
    player.battery.amount = 0.0
    pad.held = frozenset({GUARD, DOWN})

    for _ in range(30):
        level.update(DT)

    assert _state(player) == PlayerState.RECHARGE.value
    # Through the guard for a tick or two first, then filling at its rate.
    assert player.battery.amount >= Battery.RECHARGE_PER_S * 20 * DT
    assert player.battery.amount <= Battery.RECHARGE_PER_S * 30 * DT


def test_an_empty_battery_makes_the_slashes_weak() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    health = goblin.health
    tap(level, pad, SLASH, ticks=12)
    full = health - goblin.health

    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    player.battery.amount = 0.0
    tap(level, pad, SLASH, ticks=12)
    weak = health - goblin.health

    assert weak == pytest.approx(full * Battery.EMPTY_POWER, rel=0.05)


def test_holding_the_slash_charges_a_blow_that_breaks_the_guard() -> None:
    """The press throws a slash that bounces off the guard; held on, it charges through it."""
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = Height.HIGH
    goblin.guard_timer = 60.0
    goblin.facing_right = False
    goblin.moves = ()  # no counter: this is about the charge alone
    pad.held = frozenset({SLASH})

    for _ in range(60):
        level.update(DT)
    pad.held = frozenset()
    for _ in range(30):
        level.update(DT)

    assert goblin.guard is None
    assert goblin.health < goblin.max_health


# -- fury and the dark side -----------------------------------------------------------


def test_fury_speeds_the_slashes_up_in_tiers() -> None:
    _level, _pad, player = arena()
    assert player.attack_speed == 1.0
    for level_, speed in Fury.TIERS:
        player.fury.reset()
        player.fury.gain(level_)
        assert player.attack_speed == speed


def test_the_chord_on_a_full_gauge_opens_the_dark_side_where_every_blow_kills() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    player.fury.gain(Fury.MAX)

    tap(level, pad, DARK_SIDE, ticks=2)
    assert player.fury.in_dark
    assert player.finish is Finish.KILL
    tap(level, pad, SLASH, ticks=12)

    assert goblin.is_dead, "one blow"
    assert not player.prompt.active


def test_nothing_hurts_on_the_dark_side() -> None:
    _level, _pad, player = arena()
    player.fury.gain(Fury.MAX)
    player.fury.start_dark()

    assert player.is_invincible


def test_a_hit_taken_costs_fury() -> None:
    _level, _pad, player = arena()
    player.fury.gain(60.0)

    player.receive_damage(10.0)

    assert player.fury.amount == pytest.approx(60.0 - Fury.HURT_LOSS)


# -- the dark step -------------------------------------------------------------------


def test_a_dash_just_before_the_claw_slows_the_world() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 50.0, guards=False)
    settle(level, 30)
    for _ in range(600):
        state = goblin.combat.state
        if state.is_attacking and state.sub_state is PhaseState.STARTUP:
            phase = state.current_phase_def
            assert phase is not None
            if phase.startup_frames - state.frame_counter == 3:
                break
        level.update(DT)
    player.dash.charges = 1

    tap(level, pad, DASH, ticks=6)

    assert player.rush_timer > 0.0
    assert player.world_time_scale == Rush.TIME_SCALE
    assert player.dash.charges == player.dash.max_charges
    assert player.health == player.max_health


def test_slashes_cost_nothing_and_run_fast_during_a_dark_step() -> None:
    level, pad, player = arena()
    settle(level, 10)
    player.rush_timer = Rush.DURATION

    tap(level, pad, SLASH, ticks=2)

    assert player.battery.amount == Battery.MAX
    assert player.attack_speed == Rush.ATTACK_SPEED


# -- the slot machine ----------------------------------------------------------------


def test_a_jackpot_grants_its_power_for_a_while() -> None:
    _level, _pad, player = arena()
    rng = random.Random(0)
    while True:
        player.slot.reset()
        player.slot.spin(rng)
        granted = player.slot.update(Slot.SPIN_TIME)
        if granted is not None:
            break

    assert player.slot.power is granted
    assert player.slot.power_timer == Slot.POWER_DURATION
    player.slot.update(Slot.POWER_DURATION)
    assert player.slot.power is None


@pytest.mark.parametrize("power", [Power.STASIS, Power.BLITZ])
def test_stasis_and_blitz_make_every_blow_kill(power: Power) -> None:
    _level, _pad, player = arena()
    player.slot.power = power
    player.slot.power_timer = 1.0

    assert player.finish is Finish.KILL


def test_stasis_slows_the_world_and_blitz_the_player_speeds_up() -> None:
    _level, _pad, player = arena()
    player.slot.power, player.slot.power_timer = Power.STASIS, 1.0
    assert player.world_time_scale == Slot.STASIS_TIME_SCALE
    assert player.attack_speed == Slot.STASIS_ATTACK_SPEED

    player.slot.power = Power.BLITZ
    player._sync_speeds()
    assert player.attack_speed == Slot.BLITZ_ATTACK_SPEED
    assert player.speed > player._run_speed


def test_cleave_makes_the_slashes_harder() -> None:
    level, pad, player = arena()
    foe(level, "goblin", PLAYER_X + 52.0, guards=False, **STILL)
    settle(level)
    player.slot.power, player.slot.power_timer = Power.CLEAVE, 5.0

    tap(level, pad, SLASH, ticks=2)

    assert player.combat.charge_multiplier == Slot.CLEAVE_MULT


def test_three_of_a_kind_comes_only_from_the_jackpot_draw() -> None:
    from src.simulation.entities.player_kit import SlotMachine

    rng = random.Random(7)
    jackpots = 0
    for _ in range(2000):
        slot = SlotMachine()
        slot.spin(rng)
        assert slot.reels is not None
        if len(set(slot.reels)) == 1:
            jackpots += 1
            assert slot.reels[0] < len(Power)
    assert jackpots / 2000 == pytest.approx(Slot.JACKPOT_CHANCE, abs=0.03)


# -- no mashing -----------------------------------------------------------------------


def _mash(level: Level, pad: Pad, ticks: int, *buttons: object) -> None:
    for tick in range(ticks):
        pad.held = frozenset(buttons) if tick % 2 == 0 else frozenset()  # type: ignore[arg-type]
        level.update(DT)
    pad.held = frozenset()


def _front(goblin: Enemy, player: Player) -> float:
    goblin.facing_right = player.hitbox.centerx >= goblin.hitbox.centerx
    return player.hitbox.centerx


def test_the_third_blow_in_a_row_is_braced_against_at_its_height() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = None
    goblin.state_machine.change_state("stagger", force=True)
    goblin.stagger_timer = 0.5
    source = _front(goblin, player)

    stopped = [goblin.guards_against(Height.LOW, False, source) for _ in range(3)]

    assert stopped == [False, False, True]
    assert goblin.guard is Height.LOW
    assert _state(goblin) == "idle", "the stagger is shaken off"
    assert goblin.counter_timer > 0.0


def test_a_blow_from_behind_or_a_beat_does_not_count_toward_the_brace() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = None
    goblin.facing_right = True  # its back to the player, on its left

    assert not any(
        goblin.guards_against(Height.HIGH, False, player.hitbox.centerx) for _ in range(5)
    )
    goblin.facing_right = False
    assert not any(
        goblin.guards_against(Height.HIGH, True, player.hitbox.centerx) for _ in range(5)
    )


def test_the_streak_lapses_without_blows() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = None
    source = _front(goblin, player)
    goblin.guards_against(Height.HIGH, False, source)
    goblin.guards_against(Height.HIGH, False, source)

    goblin._tick_counter(GuardSettings.STREAK_WINDOW + 0.01)

    assert goblin.hit_streak == 0


def test_the_counter_is_thrown_behind_the_guard() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, guards=True)
    settle(level, 5)
    goblin.guard = Height.HIGH
    source = _front(goblin, player)
    assert goblin.guards_against(Height.HIGH, False, source)

    goblin._tick_counter(DT)

    assert _state(goblin) == "attack"
    assert goblin.countering
    assert goblin.guards_against(Height.LOW, False, source), "nothing blockable stops it"
    assert not goblin.guards_against(Height.LOW, True, source), "but a beat still does"


def _mash_duel(name: str, seed: int, answer_prompts: bool) -> tuple[Enemy, Player]:
    """Twelve seconds of the slash mashed against ``name``, kept in reach."""
    level, pad, player = arena()
    enemy = foe(level, name, PLAYER_X + 60.0)
    enemy.rng.seed(seed)
    player.rng.seed(seed)
    settle(level, 20)

    for tick in range(720):
        if enemy.is_dead or player.is_dead:
            break
        dx = enemy.hitbox.centerx - player.hitbox.centerx
        gap = abs(dx) - (enemy.hitbox.w + player.hitbox.w) / 2
        pad.axis = (1.0 if dx > 0 else -1.0) if gap > 12 else 0.0
        pad.held = frozenset({SLASH}) if tick % 2 == 0 else frozenset()
        expected = player.prompt.expected if player.prompt.active else None
        if answer_prompts and expected is not None and tick % 2 == 1:
            pad.axis, pad.held = ANSWER[expected]
        level.update(DT)
    return enemy, player


def test_mashing_the_slash_alone_does_not_win() -> None:
    goblin, player = _mash_duel("goblin", seed=0, answer_prompts=False)

    assert not goblin.is_dead
    assert player.health < player.max_health


@pytest.mark.parametrize("name", ["goblin", "tooth", "shell"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_mashing_the_slash_does_not_win_even_answering_the_prompts(name: str, seed: int) -> None:
    """The prompts answered, a guarding enemy still beats the masher.

    The mashed slash bounces off the guard into the counter, a slash that
    meets the counter bounces off too instead of locking, and a lock won is
    an opening rather than a stun -- so nothing in the loop pays the masher.
    """
    enemy, player = _mash_duel(name, seed, answer_prompts=True)

    assert not enemy.is_dead
    assert player.health <= player.max_health / 2


def test_a_slash_stopped_by_the_guard_bounces_off() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = Height.HIGH
    goblin.guard_timer = 60.0
    goblin.facing_right = False
    goblin.moves = ()
    battery = player.battery.amount

    tap(level, pad, SLASH, ticks=6)

    assert goblin.health == goblin.max_health
    assert not player.combat.is_attacking, "the slash is cut short"
    assert _state(player) == "stagger"
    assert player.velocity.x < 0.0, "pushed back, away from the goblin"
    assert player.battery.amount == pytest.approx(
        battery - Battery.SLASH_COST - Battery.DEFLECT_COST
    )


def test_a_slash_that_meets_the_counter_bounces_off_and_locks_nothing() -> None:
    level, _pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 50.0, guards=True)
    settle(level, 5)
    goblin.guard = Height.HIGH
    source = _front(goblin, player)
    assert goblin.guards_against(Height.HIGH, False, source)
    goblin._tick_counter(DT)
    assert goblin.counter_covered
    player.facing_right = True

    player.start_move("slash_low_1")
    for _ in range(20):
        level.update(DT)
        if not player.combat.is_attacking:
            break

    assert player.prompt.kind is not PromptKind.CLASH
    assert not player.combat.is_attacking


def test_a_lock_won_breaks_the_guard_only_briefly() -> None:
    level, _pad, _player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 52.0, **STILL)
    settle(level)
    goblin.guard = Height.HIGH

    goblin.lose_lock()

    assert goblin.guard is None
    assert not goblin.is_stunned
    assert goblin.guard_broken_timer == Clash.WIN_OPEN < GuardSettings.BROKEN_TIME
