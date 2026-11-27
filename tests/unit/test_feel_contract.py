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


def test_enemy_strikes_carry_a_tiered_explicit_hitstop() -> None:
    """Enemy freeze is explicit and grows with the weight of the blow."""
    sets = shipped_gameplay_data().attack_sets
    expected = {"goblin": 0.06, "slime": 0.06, "tooth": 0.08, "shell": 0.10}
    for owner, attacks in sets.items():
        if owner not in expected:
            continue
        for name, definition in attacks.items():
            for phase in definition.phases:
                if phase.hit.damage <= 0:
                    continue  # a marker box throws a shot, it does not strike
                assert phase.hit.hit_stop == expected[owner], f"{owner}.{name} lost its tier"


def test_enemy_hitstop_stays_between_a_light_and_a_heavy_player_blow() -> None:
    attacks = shipped_gameplay_data().attack_sets
    light = attacks["player"]["slash_high_1"].phases[0].hit.hit_stop
    heavy = attacks["player"]["slash_high_4"].phases[0].hit.hit_stop
    goblin = attacks["goblin"]["claw_swipe"].phases[1].hit.hit_stop
    shell = attacks["shell"]["shell_roll"].phases[0].hit.hit_stop
    assert light is not None and heavy is not None
    assert goblin is not None and shell is not None
    assert light < goblin < heavy < shell


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
        assert attacks[name].phases[0].recovery_frames == 16, name
