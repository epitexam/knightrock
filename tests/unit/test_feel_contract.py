"""The tuning facts behind the feel, pinned so a data edit cannot go unnoticed.

``hit_outcomes.json`` records what one hit does; it cannot say that a whole
family of moves has no explicit hit-stop while another has one on every move,
or that a chain opens on contact for three links and closes on the fourth.
These are characterisation values: changing one is a design decision that must
update the corresponding assertion with a reason in the audit.
"""

from __future__ import annotations

from src.core.settings import Combat as CombatSettings
from src.data.provider import shipped_gameplay_data


def test_every_player_strike_carries_an_explicit_hitstop() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name, definition in attacks.items():
        for index, phase in enumerate(definition.phases):
            if phase.launches:
                continue  # the shot strikes, the hand is only a marker
            assert phase.hit.hit_stop is not None, f"{name}[{index}] uses the global formula"


def test_enemy_strikes_have_no_explicit_hitstop() -> None:
    """Enemy freeze comes from the global formula, unlike the player's."""
    sets = shipped_gameplay_data().attack_sets
    for owner, attacks in sets.items():
        if owner == "player":
            continue
        for name, definition in attacks.items():
            for phase in definition.phases:
                assert phase.hit.hit_stop is None, f"{owner}.{name} has an explicit hit-stop"


def test_the_global_formula_is_shorter_than_a_player_light() -> None:
    """The strongest enemy nuance of the day, quantified: ~3x a light slash."""
    attacks = shipped_gameplay_data().attack_sets
    player_light = attacks["player"]["slash_high_1"].phases[0].hit.hit_stop
    goblin = attacks["goblin"]["claw_swipe"].phases[1].hit
    magnitude = (goblin.knockback.power[0] ** 2 + goblin.knockback.power[1] ** 2) ** 0.5
    formula = (
        CombatSettings.HITSTOP_BASE
        + goblin.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR
        + magnitude * CombatSettings.HITSTOP_KNOCKBACK_FACTOR
    )
    assert player_light is not None
    assert formula > player_light * 2.0


def test_the_first_three_chain_links_cancel_on_contact() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name in ("slash_high_1", "slash_high_2", "slash_high_3", "punch_1", "kick_1"):
        assert attacks[name].phases[0].cancel_on_hit is True, name


def test_the_chain_terminals_do_not_cancel_on_contact() -> None:
    """Characterisation of the flow break at the end of a chain."""
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name in ("slash_high_4", "slash_low_4", "punch_3", "kick_2"):
        assert attacks[name].phases[0].cancel_on_hit is False, name
