"""The combo counter counts hits that landed, not swings that started."""

import pytest

from src.combat.combat_component import CombatComponent
from src.combat.combo_tracker import ComboTracker


def test_a_whiffed_swing_never_reaches_the_counter() -> None:
    """The bug this file exists for: throwing a swing into empty air counted.

    Starting an attack only arms the counter now. Nothing the HUD can read has
    moved, which is the whole point: the player swung, connected with nothing,
    and the combo they did not earn does not exist.
    """
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)

    assert tracker.count == 0
    assert tracker.timer == 0.0
    assert tracker.is_armed is True

    tracker.disarm()

    assert tracker.count == 0
    assert tracker.is_armed is False


def test_a_landed_hit_opens_the_combo_at_one() -> None:
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)

    assert tracker.count == 1
    assert tracker.timer == pytest.approx(0.5)
    assert tracker.is_armed is False


def test_two_landed_hits_inside_the_window_make_two() -> None:
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)
    tracker.update(0.2)
    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)

    assert tracker.count == 2


def test_one_swing_hitting_twice_counts_once() -> None:
    """Multi-contact on a single attack is one hit, not a combo step.

    The arming is spent by the first contact, so an attack that catches two
    bodies in one swing reads as one hit in the combo.
    """
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)
    tracker.on_hit_landed(airborne=False)

    assert tracker.count == 1


def test_a_hit_with_no_armed_attack_does_not_count() -> None:
    """Contact damage and stray projectiles are not combo steps.

    The hit is real and the air tally still takes it, but nothing armed vouched
    for it, so the counter stays where the player's own attacks left it.
    """
    tracker = ComboTracker(0.5)

    tracker.on_hit_landed(airborne=True)

    assert tracker.count == 0
    assert tracker.air_count == 1


def test_a_combo_resetting_attack_starts_the_next_one_from_scratch() -> None:
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)
    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)
    assert tracker.count == 2

    tracker.on_attack_started(resets_combo=True)
    assert tracker.count == 0

    tracker.on_hit_landed(airborne=False)

    assert tracker.count == 1


def test_a_hit_after_the_window_lapsed_still_opens_a_chain() -> None:
    """An expiry does not void a swing that was already in flight.

    The window is a *counting* window: once it closes the old chain is gone. But
    an attack thrown before it closed and landing after is a real hit, and it has
    to start the new chain rather than fall on the floor.
    """
    tracker = ComboTracker(0.5)

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)
    tracker.update(0.6)
    assert tracker.count == 0

    tracker.on_attack_started(resets_combo=False)
    tracker.on_hit_landed(airborne=False)

    assert tracker.count == 1


def test_taking_a_hit_kills_the_combo() -> None:
    """The counter is dropped, not merely paused, when the player is hit."""
    from src.combat.attack_data import PLAYER_ATTACKS
    from tests.unit.helpers import make_entity

    entity = make_entity(attacks=PLAYER_ATTACKS)
    combat = entity.combat
    assert isinstance(combat, CombatComponent)

    assert combat.start_attack("light_attack")
    combat.record_hit_landed(airborne=False)
    assert combat.combo_count == 1
    # Let the cooldown lapse and the swing recover, standing in for the
    # follow-up a player would land inside the combo window.
    combat.state.end()
    combat.update(0.4)
    assert combat.start_attack("light_attack")
    combat.record_hit_landed(airborne=False)
    assert combat.combo_count == 2

    combat.on_hit()

    assert combat.combo_count == 0
    assert combat.combo_timer == 0.0


def test_taking_a_hit_cannot_be_credited_to_the_attack_it_interrupted() -> None:
    """The attack is cancelled, so its arming goes with it.

    Without this the attack that was interrupted on its first frame would sit
    armed until recovery, and the next contact the player made -- possibly
    several attacks later -- would be billed to it.
    """
    from src.combat.attack_data import PLAYER_ATTACKS
    from tests.unit.helpers import make_entity

    entity = make_entity(attacks=PLAYER_ATTACKS)
    combat = entity.combat
    assert isinstance(combat, CombatComponent)

    assert combat.start_attack("light_attack")
    combat.on_hit()

    assert combat.combo.is_armed is False


def test_the_arming_rolls_back_with_the_frame_it_belongs_to() -> None:
    """An arming taken on a rolled-back frame has to come back with it.

    The counter and its window were already in the snapshot; the arming is the
    same kind of state -- it decides what the *next* hit does -- so restoring
    the counter without it would resurrect an attack the rollback undid.
    """
    from src.combat.attack_data import PLAYER_ATTACKS
    from tests.unit.helpers import make_entity

    entity = make_entity(attacks=PLAYER_ATTACKS)
    combat = entity.combat
    assert isinstance(combat, CombatComponent)

    assert combat.start_attack("light_attack")
    armed_snapshot = combat.save_state()

    combat.on_hit()
    assert combat.combo.is_armed is False

    combat.load_state(armed_snapshot)

    assert combat.combo.is_armed is True
