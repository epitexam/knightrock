"""Ground braking: the plant half of a reversal.

The rule these hold is that acceleration and braking are separate rates aimed
at different places. A single exponential ease toward the target is symmetric,
and a symmetric curve does not plant -- it crosses zero without dwelling, which
is why a reversal could be decelerating and still read as instant.
"""

import math
from itertools import pairwise
from types import SimpleNamespace

import pytest

from src.core.settings import Physics, Turn
from src.physics.movement import _braking, apply_horizontal_movement

TICK = 1 / 60
TOP = Physics.PLAYER_SPEED


def _runner(
    *,
    axis: float,
    velocity: float,
    grounded: bool = True,
    turn_enabled: bool = True,
    brake: float | None = None,
):
    """The slice of an entity ``apply_horizontal_movement`` reads.

    The turn knobs are on the entity, not read from the settings block, so this
    double carries its own -- which is what lets the tests below vary them per
    fighter rather than by patching a global.
    """
    return SimpleNamespace(
        move_axis=axis,
        velocity=SimpleNamespace(x=velocity, y=0.0),
        speed=TOP,
        floor_control=25.0,
        air_control=12.0,
        on_surface={"floor": grounded, "left": False, "right": False},
        combat=SimpleNamespace(movement_multiplier=1.0),
        turn_enabled=turn_enabled,
        turn_brake_control=Turn.BRAKE_CONTROL if brake is None else brake,
        turn_plant_px_s=Turn.PLANT_PX_S,
    )


def _trace(entity, frames: int) -> list[float]:
    """The velocity curve over ``frames`` ticks."""
    out = []
    for _ in range(frames):
        apply_horizontal_movement(entity, TICK)
        out.append(entity.velocity.x)
    return out


def test_a_reversal_bleeds_toward_zero_and_not_toward_the_new_direction() -> None:
    """Aiming the brake at the target is what makes a plant impossible.

    At the braking rate and aimed at the *new* direction the velocity would
    curve straight through the crossing; aimed at zero it has to arrive there
    first. The trace is the whole claim.

    Traced until the plant rather than for a fixed number of frames: the length
    of the bleed is what ``BRAKE_CONTROL`` sets, and a test that hardcoded it
    would fail on every retune without ever checking the shape.
    """
    entity = _runner(axis=-1.0, velocity=TOP)

    trace: list[float] = []
    while abs(entity.velocity.x) >= entity.turn_plant_px_s and len(trace) < 40:
        apply_horizontal_movement(entity, TICK)
        trace.append(entity.velocity.x)

    assert all(b < a for a, b in pairwise(trace)), (
        f"the brake must shed speed monotonically, got {trace}"
    )
    assert len(trace) >= 4, f"and it must take several frames to do it: {trace}"
    assert all(v > 0 for v in trace), "the brake must never push on its own"
    assert entity.velocity.x < entity.turn_plant_px_s, "and it must reach the plant"


def test_the_brake_is_not_the_acceleration_renamed() -> None:
    """A single symmetric rate is what this replaces, so the two must differ.

    Both are measured in the same direction -- towards ``-TOP`` -- because the
    reversal and the launch are the same fighter asking for the same thing from
    different speeds, and that is the pair that has to disagree.

    Only the first frame is compared. A reversal starts at full speed and bleeds,
    a launch starts at rest and builds, so the gap closes and then inverts --
    by the third frame the launch is the faster of the two, which is correct
    and is not what is under test. The claim is about the rate on the frame
    each of them begins.

    If braking and accelerating were one number again the reversal would cross
    zero in a frame or two, and this test would pass on the old curve.
    """
    reversal = _trace(_runner(axis=-1.0, velocity=TOP), 1)
    launch = _trace(_runner(axis=-1.0, velocity=0.0), 1)

    assert abs(reversal[0]) > abs(launch[0]), "a reversal sheds more than a launch builds"


def test_the_push_resumes_from_the_plant() -> None:
    """Once planted, the ordinary acceleration takes the fighter the other way."""
    entity = _runner(axis=-1.0, velocity=Turn.PLANT_PX_S * 0.5)

    trace = _trace(entity, 8)

    assert all(b < a for a, b in pairwise(trace)), "still pushing left"
    assert trace[-1] < -TOP * 0.5, "and gets up to speed"


def test_coasting_to_a_stop_keeps_the_original_curve() -> None:
    """Releasing the stick is not a reversal, and must feel unchanged.

    The brake is gated on the input opposing the velocity. Without that gate,
    letting go of the stick would plant the fighter before every stop, and the
    deceleration out of a run would go with it -- which is the common case, and
    the one nobody asked to change.
    """
    entity = _runner(axis=0.0, velocity=TOP)
    floor_alpha = 1.0 - math.exp(-25.0 * TICK)

    trace = _trace(entity, 1)

    assert trace[0] == pytest.approx(TOP + (0.0 - TOP) * floor_alpha, rel=1e-6)
    assert abs(trace[0]) > TOP * 0.6, "a stop should still be brisk"


def test_a_reversal_in_the_air_is_untouched() -> None:
    """A mid-air reversal is a jump turn, and the tighter curve is the point.

    Braking in the air would make air dashes feel heavy, and the air curve is
    what makes an air dash read as an air dash.
    """
    entity = _runner(axis=-1.0, velocity=TOP, grounded=False)
    air_alpha = 1.0 - math.exp(-12.0 * TICK)

    trace = _trace(entity, 2)

    expected = TOP + (-TOP - TOP) * air_alpha
    assert trace[0] == pytest.approx(expected, rel=1e-6)
    assert trace[1] == pytest.approx(expected + (-TOP - expected) * air_alpha, rel=1e-6)


def test_the_brake_gate_recognises_its_own_conditions() -> None:
    """The gate is four conditions and each of them is load-bearing."""
    moving_right = _runner(axis=-1.0, velocity=TOP)
    moving_left = _runner(axis=1.0, velocity=-TOP)
    same_way = _runner(axis=1.0, velocity=TOP)
    stopped = _runner(axis=-1.0, velocity=0.0)
    planted = _runner(axis=-1.0, velocity=Turn.PLANT_PX_S - 1.0)
    coasting = _runner(axis=0.0, velocity=TOP)
    opted_out = _runner(axis=-1.0, velocity=TOP, turn_enabled=False)
    no_brake = _runner(axis=-1.0, velocity=TOP, brake=0.0)

    assert _braking(moving_right, -TOP) is True
    assert _braking(moving_left, TOP) is True
    assert _braking(same_way, TOP) is False, "same direction is not a reversal"
    assert _braking(stopped, -TOP) is False, "nothing to bleed"
    assert _braking(planted, -TOP) is False, "already planted: let the push own it"
    assert _braking(coasting, 0.0) is False, "no input is no target"
    assert _braking(opted_out, -TOP) is False, "a fighter that opted out does not brake"
    assert _braking(no_brake, -TOP) is False, "and neither does one with the rate at 0"


def test_a_fighter_that_opts_out_gets_the_legacy_curve() -> None:
    """``turn_enabled = False`` has to be exactly "before this feature".

    This is the whole reason the flag gates the brake and not only the hold.
    ``apply_horizontal_movement`` is shared by every fighter in the game, so
    without the gate an enemy would plant and push differently while never
    being turned around -- a change of handling with nothing on screen to
    explain it. The enemy is the fighter that has to look untouched, because
    nobody asked for it to change.
    """
    opting_in = _trace(_runner(axis=-1.0, velocity=TOP, turn_enabled=True), 3)
    opting_out = _trace(_runner(axis=-1.0, velocity=TOP, turn_enabled=False), 3)

    alpha = 1.0 - math.exp(-25.0 * TICK)
    legacy = TOP
    expected = []
    for _ in range(3):
        legacy += (-TOP - legacy) * alpha
        expected.append(legacy)

    assert opting_out == pytest.approx(expected, rel=1e-9), "the legacy curve, untouched"
    assert opting_in != pytest.approx(expected, rel=1e-3), "and the opted-in one differs"


def test_no_brake_at_all_restores_the_single_rate_curve() -> None:
    """``turn_brake_control = 0`` is the legacy curve, not a fighter stuck at zero."""
    alpha = 1.0 - math.exp(-25.0 * TICK)
    entity = _runner(axis=-1.0, velocity=TOP, brake=0.0)

    trace = _trace(entity, 1)

    assert trace[0] == pytest.approx(TOP + (-TOP - TOP) * alpha, rel=1e-6)
    assert _braking(entity, -TOP) is False


def test_the_brake_rate_is_per_fighter_and_not_global() -> None:
    """A goblin and a boss should not plant like each other.

    The knobs live on the entity for the same reason ``floor_control`` does,
    and the test is here to hold that: patching a settings constant would
    change every fighter at once, which is the thing this makes impossible.
    """
    heavy = _trace(_runner(axis=-1.0, velocity=TOP, brake=6.0), 2)
    light = _trace(_runner(axis=-1.0, velocity=TOP, brake=60.0), 2)

    assert heavy[0] > light[0], "a slow brake sheds less per frame"
    assert _runner(axis=1.0, velocity=0.0, brake=6.0).turn_brake_control == 6.0


def test_the_brake_is_aimed_at_zero_and_overshoots_nothing() -> None:
    """A brake that could cross would be a curve again.

    Every tick of the brake must move the velocity *towards* zero and stop
    short of it, which is the mechanical difference between planting and merely
    changing rate.
    """
    entity = _runner(axis=-1.0, velocity=TOP)

    for _ in range(8):
        before = entity.velocity.x
        apply_horizontal_movement(entity, TICK)
        after = entity.velocity.x
        if after == 0.0 or abs(after) >= Turn.PLANT_PX_S:
            break
        assert 0.0 < after < before, f"the brake overshot: {before} -> {after}"
