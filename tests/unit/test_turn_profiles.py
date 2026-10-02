"""Group and sub-group resolution for the ground pivot.

The pivot's configuration surface is a table of named profiles layered on each
other by inheritance, and an entity adopts one by name. That is the whole of it:
"the enemies take it, except the slimes" is a group switched on and a
sub-group switched off, and nothing in the simulation has to know either exists.

These tests are about the *resolution* -- which layer wins, what a missing
name does, whether the shipped table is a no-op -- rather than about the pivot
itself, which ``test_turn_state`` and ``test_turn_braking`` cover.
"""

import dataclasses

import pygame
import pytest

from src.core.input.input_manager import InputManager
from src.core.settings import (
    PROFILES,
    Turn,
    TurnProfile,
    resolve_turn_profile,
)
from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.enemy import Enemy
from src.entities.player import Player


@pytest.fixture
def clean_profiles():
    """Restore the shipped profile table after a test changes it.

    The table is module-level state, like every settings block, and the tests
    below edit it on purpose. A snapshot and restore is enough; there is no
    monkeypatching involved because a dict's own methods cannot be replaced.
    """
    snapshot = dict(PROFILES)
    try:
        yield PROFILES
    finally:
        PROFILES.clear()
        PROFILES.update(snapshot)


def _enemy(**overrides):
    return Enemy(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        player_reference=None,
        config=dataclasses.replace(ENEMY_CONFIGS["goblin"], **overrides),
    )


# --- Resolution -------------------------------------------------------------


def test_the_defaults_are_the_shipped_numbers() -> None:
    """A profile with nothing set in it still has to produce real numbers."""
    resolved = resolve_turn_profile("default")

    assert resolved.enabled is False
    assert resolved.delay_s == Turn.DELAY_S
    assert resolved.brake_control == Turn.BRAKE_CONTROL
    assert resolved.plant_px_s == Turn.PLANT_PX_S
    assert resolved.min_speed_px_s == Turn.MIN_SPEED_PX_S
    assert resolved.lead_px == Turn.LEAD_PX
    assert resolved.skew_px == Turn.SKEW_PX


def test_an_unknown_profile_is_the_defaults_and_not_a_crash() -> None:
    """A level naming a group nobody defined still gets a fighter that moves.

    Raising here would mean a typo in a data file stops the game spawning at
    all, over a tuning value. The cost of guessing wrong is a fighter with the
    shipped pivot, which is recoverable; the cost of refusing to boot is not.
    """
    resolved = resolve_turn_profile("nobody-defined-this")

    assert resolved == resolve_turn_profile("default")


def test_an_inheritance_cycle_costs_the_most_specific_values(clean_profiles) -> None:
    """A profile pointing at its own descendant must not hang the game.

    Two profiles each claiming the other as their parent is the obvious typo,
    and walking it naively is an infinite loop -- at import time, on a class
    body, before anything has a chance to fail loudly.
    """
    clean_profiles["a"] = TurnProfile(inherits="b", enabled=True, delay_s=0.5)
    clean_profiles["b"] = TurnProfile(inherits="a", skew_px=30.0)

    resolved = resolve_turn_profile("a")

    assert resolved.enabled is True
    assert resolved.delay_s == 0.5
    assert resolved.skew_px == 30.0


def test_the_nearest_layer_wins(clean_profiles) -> None:
    clean_profiles["base"] = TurnProfile(enabled=True, delay_s=0.3, skew_px=10.0)
    clean_profiles["child"] = TurnProfile(inherits="base", delay_s=0.1)

    resolved = resolve_turn_profile("child")

    assert resolved.delay_s == 0.1, "the sub-group's own number"
    assert resolved.skew_px == 10.0, "and the group's where it stayed silent"
    assert resolved.enabled is True, "and the group's where it stayed silent"


def test_a_group_that_only_switches_the_pivot_on_need_not_restate_it(clean_profiles) -> None:
    """The reason a profile is partial: a switch is not a whole configuration."""
    clean_profiles["on"] = TurnProfile(enabled=True)

    resolved = resolve_turn_profile("on")

    assert resolved.enabled is True
    assert resolved.delay_s == Turn.DELAY_S
    assert resolved.brake_control == Turn.BRAKE_CONTROL


def test_a_chain_of_three_layers(clean_profiles) -> None:
    """Group -> sub-group -> type, which is the shape the feature is for."""
    clean_profiles["base"] = TurnProfile(delay_s=0.4, lead_px=10.0)
    clean_profiles["mid"] = TurnProfile(inherits="base", lead_px=20.0)
    clean_profiles["leaf"] = TurnProfile(inherits="mid", skew_px=30.0)

    resolved = resolve_turn_profile("leaf")

    assert resolved.delay_s == 0.4
    assert resolved.lead_px == 20.0
    assert resolved.skew_px == 30.0


# --- What entities adopt ---------------------------------------------------


def test_the_shipped_table_changes_nothing_but_the_player() -> None:
    """The defaults should keep saying nothing.

    Only the player takes the pivot out of the box, and every enemy type
    inherits that off. A test that only checks the player is on would pass with
    a table that switched everything on by accident.
    """
    player = Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=InputManager(),
    )

    assert player.turn_profile == "player"
    assert player.turn_enabled is True
    for kind in ("goblin", "slime", "dummy"):
        enemy = Enemy(
            pos=(0, 0),
            groups=pygame.sprite.Group(),
            collision_sprites=pygame.sprite.Group(),
            player_reference=None,
            config=ENEMY_CONFIGS[kind],
        )
        assert enemy.turn_profile == "enemy", kind
        assert enemy.turn_enabled is False, kind


def test_a_group_switches_on_every_enemy_type_that_inherits_it(clean_profiles) -> None:
    """The group is the faction: one entry reaches every enemy."""
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)

    for kind in ("goblin", "slime", "dummy"):
        enemy = Enemy(
            pos=(0, 0),
            groups=pygame.sprite.Group(),
            collision_sprites=pygame.sprite.Group(),
            player_reference=None,
            config=ENEMY_CONFIGS[kind],
        )
        assert enemy.turn_enabled is True, kind


def test_a_sub_group_switches_one_type_off_inside_a_group_that_is_on(
    clean_profiles,
) -> None:
    """ "All the enemies take it, except the slimes", said declaratively."""
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)
    clean_profiles["enemy_slime"] = TurnProfile(inherits="enemy", enabled=False)

    # No sub-group at all: the goblin takes the group exactly as it is.
    goblin = _enemy()
    slime = _enemy(turn_profile="enemy_slime")

    assert goblin.turn_profile == "enemy"
    assert goblin.turn_enabled is True, "a type with no sub-group takes the group"
    assert slime.turn_profile == "enemy_slime"
    assert slime.turn_enabled is False


def test_a_sub_group_tunes_one_type_and_leaves_the_rest(clean_profiles) -> None:
    """A heavy type that plants more slowly, without restating the group."""
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)
    clean_profiles["enemy_goblin"] = TurnProfile(inherits="enemy", brake_control=12.0, skew_px=28.0)

    goblin = _enemy(turn_profile="enemy_goblin")
    slime = _enemy(turn_profile="enemy_slime")

    assert goblin.turn_enabled is True
    assert goblin.turn_brake_control == 12.0, "the sub-group's own number"
    assert goblin.turn_skew_px == 28.0
    assert goblin.turn_delay_s == Turn.DELAY_S, "and the group's where it stayed silent"

    assert slime.turn_brake_control == Turn.BRAKE_CONTROL, "the group, untouched"
    assert slime.turn_skew_px == Turn.SKEW_PX


def test_a_sub_group_reaching_a_group_does_not_move_the_group(clean_profiles) -> None:
    """Layering onto a group must not retune the group for everyone else."""
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)
    clean_profiles["enemy_goblin"] = TurnProfile(inherits="enemy", brake_control=8.0)

    _enemy(turn_profile="enemy_goblin")
    other = _enemy(turn_profile="enemy_slime")

    assert resolve_turn_profile("enemy").brake_control == Turn.BRAKE_CONTROL
    assert other.turn_brake_control == Turn.BRAKE_CONTROL


# --- The layer above the profiles ------------------------------------------


def test_a_value_set_in_code_outranks_the_profile(clean_profiles) -> None:
    """Resolution happens in the constructor, so an assignment after it wins.

    This is what makes a profile usable as a *default* for a class rather than
    as a ceiling: the class adopts the group and then says a number of its own
    for whatever reason.
    """
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)

    enemy = _enemy(turn_profile="enemy_goblin")
    enemy.turn_brake_control = 44.0

    assert enemy.turn_brake_control == 44.0


def test_the_drawing_numbers_travel_with_the_profile(clean_profiles) -> None:
    """The lean is part of the tuning, so the renderer must read it off the
    sprite rather than off the settings block.

    A fighter that leans differently is the same decision as one that brakes
    differently, and leaving these two in ``settings.Turn`` would make a group
    look tunable while the drawing quietly ignored it.
    """
    clean_profiles["enemy"] = TurnProfile(inherits="default", enabled=True)
    clean_profiles["enemy_goblin"] = TurnProfile(inherits="enemy", lead_px=44.0, skew_px=8.0)

    enemy = _enemy(turn_profile="enemy_goblin")

    assert enemy.turn_lead_px == 44.0
    assert enemy.turn_skew_px == 8.0
