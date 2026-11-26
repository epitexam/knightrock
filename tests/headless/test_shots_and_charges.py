"""The shot (B) and the charges, played: a bolt, a piercing one, a lobbed glob,
and the two tiers of a held slash.

Every test drives a real ``Player`` against real enemies in a flat arena, so the
launch -- a phase turning active, the level putting the shot in flight, the
contact pipeline resolving it -- is on the path.
"""

from __future__ import annotations

from src.platform.input.bindings_codec import bindings_from_dict, bindings_to_dict
from src.platform.input.input_bindings import XBOX_B, InputBindings
from src.shared.input_actions import InputAction
from src.simulation.combat.frame_data import Height
from src.simulation.entities.enemies.enemy import Enemy
from src.simulation.entities.enemies.schema import EnemyMove
from src.simulation.entities.projectile import Projectile
from src.simulation.level.level import Level
from src.simulation.settings import Battery
from src.simulation.settings import Input as InputSettings
from tests.headless.arena import (
    BEAT,
    DT,
    PLAYER_X,
    SHOOT,
    SLASH,
    Pad,
    arena,
    foe,
    settle,
    tap,
)

STILL = {"vision_range": 0.0, "chase_speed": 0.0}


def _shots(level: Level) -> list[Projectile]:
    return [s for s in level.groups.projectile_sprites if isinstance(s, Projectile)]


def _hold(level: Level, pad: Pad, button: InputAction, seconds: float) -> None:
    """Hold ``button`` for ``seconds``, then let it go for a tick."""
    pad.held = frozenset({button})
    for _ in range(round(seconds / DT)):
        level.update(DT)
    pad.held = frozenset()
    level.update(DT)


def _run(level: Level, ticks: int) -> None:
    for _ in range(ticks):
        level.update(DT)


def test_b_shoots_on_the_pad_and_d_on_the_keyboard() -> None:
    gameplay = InputBindings().gameplay
    assert gameplay.gamepad_buttons[InputAction.SHOOT] == XBOX_B
    assert InputAction.SHOOT in gameplay.keyboard


def test_a_settings_file_from_before_the_shot_gets_it_where_it_is_free() -> None:
    data = bindings_to_dict(InputBindings())
    gameplay = data["gameplay"]
    assert isinstance(gameplay, dict)
    del gameplay["keyboard"]["shoot"]
    del gameplay["gamepad_buttons"]["shoot"]

    restored = bindings_from_dict(data).gameplay

    assert restored.gamepad_buttons[InputAction.SHOOT] == XBOX_B
    assert InputAction.SHOOT in restored.keyboard


def test_a_shot_flies_out_of_reach_of_the_blade_and_hits() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 180.0, guards=False, **STILL)
    settle(level)
    battery = player.battery.amount

    tap(level, pad, SHOOT, ticks=4)

    assert len(_shots(level)) == 1
    assert player.battery.amount == battery - Battery.SHOT_COST
    _run(level, 30)
    assert goblin.health < goblin.max_health
    assert not _shots(level), "a bolt stops on what it hits"


def test_an_empty_battery_fires_nothing() -> None:
    level, pad, player = arena()
    settle(level)
    player.battery.amount = 0.0

    tap(level, pad, SHOOT, ticks=6)

    assert not _shots(level)


def test_a_bolt_breaks_a_wind_up_from_afar() -> None:
    level, pad, player = arena()
    goblin = foe(level, "goblin", PLAYER_X + 120.0, guards=False)
    goblin.moves = (EnemyMove("claw_reach", 400.0),)
    settle(level, 5)
    for _ in range(120):
        if goblin.combat.is_attacking:
            break
        level.update(DT)
    assert goblin.combat.is_attacking

    tap(level, pad, SHOOT, ticks=12)

    assert not goblin.combat.is_attacking, "the wind-up is cut short"


def test_a_full_charge_of_the_shot_pierces_guards_and_lines() -> None:
    level, pad, player = arena()
    first = foe(level, "goblin", PLAYER_X + 120.0, **STILL)
    second = foe(level, "goblin", PLAYER_X + 200.0, **STILL)
    settle(level)
    for goblin in (first, second):
        goblin.facing_right = False
        goblin.guard = Height.HIGH
        goblin.guard_timer = 60.0

    _hold(level, pad, SHOOT, InputSettings.CHARGE_DELAY + 0.9)
    _run(level, 40)

    assert first.health < first.max_health
    assert second.health < second.max_health


def _slash_charge(seconds: float) -> tuple[str | None, int]:
    level, pad, player = arena()
    settle(level)
    seen: str | None = None
    pad.held = frozenset({SLASH})
    for _ in range(round(seconds / DT)):
        level.update(DT)
    pad.held = frozenset()
    for _ in range(12):
        level.update(DT)
        name = player.combat.state.attack_name
        if name is not None and name.startswith("charged"):
            seen = name
    return seen, len(_shots(level))


def test_a_slash_let_go_early_is_the_charged_cut() -> None:
    move, shots = _slash_charge(InputSettings.CHARGE_DELAY + 0.4)

    assert move == "charged_slash"
    assert shots == 0


def test_a_slash_held_to_the_end_throws_a_crescent() -> None:
    move, _ = _slash_charge(InputSettings.CHARGE_DELAY + 1.2)

    assert move == "charged_slash_full"


def test_the_full_cut_throws_its_crescent_forward() -> None:
    level, pad, player = arena()
    settle(level)
    _hold(level, pad, SLASH, InputSettings.CHARGE_DELAY + 1.2)
    for _ in range(30):
        if _shots(level):
            break
        level.update(DT)

    shots = _shots(level)
    assert shots and shots[0].config.look == "crescent"
    assert shots[0].velocity.x > 0.0


def test_the_body_held_charges_a_kick_through_armour() -> None:
    level, pad, player = arena()
    settle(level)
    seen = set()
    pad.held = frozenset({BEAT})
    for _ in range(round((InputSettings.CHARGE_DELAY + 0.5) / DT)):
        level.update(DT)
    pad.held = frozenset()
    for _ in range(12):
        level.update(DT)
        seen.add(player.combat.state.attack_name)

    assert "charged_kick" in seen


def test_the_slime_lobs_a_glob_that_falls() -> None:
    level, _pad, player = arena()
    slime: Enemy = foe(level, "slime", PLAYER_X + 130.0)
    slime.moves = (EnemyMove("slime_spit", 400.0),)
    settle(level, 5)
    glob = None
    for _ in range(180):
        level.update(DT)
        shots = [s for s in _shots(level) if s.faction == slime.faction]
        if shots:
            glob = shots[0]
            break
    assert glob is not None, "the slime spat"
    rising = glob.velocity.y
    level.update(DT)

    assert rising < 0.0 < glob.config.gravity
    assert glob.velocity.y > rising, "it falls back"
    assert player.facing_right is not None
