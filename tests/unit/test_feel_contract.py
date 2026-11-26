"""The tuning facts behind the feel, pinned so a data edit cannot go unnoticed.

``hit_outcomes.json`` records what one hit does; it cannot say that a whole
family of moves has no explicit hit-stop while another has one on every move,
or that a chain opens on contact for three links and closes on the fourth.
These are characterisation values: changing one is a design decision that must
update the corresponding assertion with a reason in the audit.
"""

from __future__ import annotations

from src.simulation.data.provider import shipped_gameplay_data


def test_every_player_strike_carries_an_explicit_hitstop() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name, definition in attacks.items():
        for index, phase in enumerate(definition.phases):
            if phase.launches:
                continue  # the shot strikes, the hand is only a marker
            assert phase.hit.hit_stop is not None, f"{name}[{index}] uses the global formula"


def test_enemy_strikes_carry_a_short_explicit_hitstop() -> None:
    """Enemy freeze is no longer the ~0.088 s the global formula produced."""
    sets = shipped_gameplay_data().attack_sets
    for owner, attacks in sets.items():
        if owner == "player":
            continue
        for name, definition in attacks.items():
            for phase in definition.phases:
                if phase.hit.damage <= 0:
                    continue  # a marker box throws a shot, it does not strike
                assert phase.hit.hit_stop == 0.04, f"{owner}.{name} uses the old formula"


def test_enemy_hitstop_is_close_to_a_player_light() -> None:
    attacks = shipped_gameplay_data().attack_sets
    player_light = attacks["player"]["slash_high_1"].phases[0].hit.hit_stop
    enemy = attacks["goblin"]["claw_swipe"].phases[1].hit.hit_stop
    assert player_light is not None
    assert enemy is not None
    assert enemy <= player_light * 1.5


def test_the_first_three_chain_links_cancel_on_contact() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name in ("slash_high_1", "slash_high_2", "slash_high_3", "punch_1", "kick_1"):
        assert attacks[name].phases[0].cancel_on_hit is True, name


def test_the_blade_chain_terminals_cancel_on_contact() -> None:
    """The 4th slash is no longer the flow break it used to be."""
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name in ("slash_high_4", "slash_low_4", "air_slash"):
        assert attacks[name].phases[0].cancel_on_hit is True, name


def test_the_blade_chain_terminals_are_less_committed() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name in ("slash_high_4", "slash_low_4"):
        assert attacks[name].phases[0].recovery_frames == 11, name
