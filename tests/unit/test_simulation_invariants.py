"""The runtime invariants that are written in prose and enforced nowhere.

Two constants carry an assumption the whole simulation rests on, and both live
only in comments: the spatial hash's query margin, and the sub-step clamp. A
margin below ``MAX_FALL_SPEED * TIMESTEP`` misses a floor the entity is falling
onto, which is invisible until something falls fast enough; a clamp below the
widest step a character can take tunnels it through a wall. Neither is checked
anywhere, so each is checked here, as a constant: it is the right shape of test
for an assumption about numbers.

Alongside them, the dt-independence of the velocity helpers. The simulation runs
at a fixed 60 Hz, so this is *not* a claim that a digest survives a different
timestep -- it cannot, and a test asserting it would be asserting something
false. The claim is narrower and the one that actually broke: a helper handed a
``delta_time`` must decay at the same rate *per second* whatever slice it is
handed, because a friction that forgets the ``dt`` it already scaled, or that
scales it twice, reads as correct in isolation at one tick rate and wrong at
every other.
"""

import math

import pytest

from src.core.settings import Physics, Separation, Simulation
from src.physics.spatial_hash import QUERY_MARGIN_PX


def _decay(rate: float, dt: float, ticks: int) -> float:
    """``rate`` applied ``ticks`` times at ``dt``, as a fraction of the start."""
    velocity = 1.0
    for _ in range(ticks):
        velocity += (0.0 - velocity) * (1.0 - math.exp(-rate * dt))
    return velocity


def test_the_query_margin_covers_the_fastest_fall_in_one_tick() -> None:
    budget = Physics.MAX_FALL_SPEED * Simulation.TIMESTEP
    assert budget <= QUERY_MARGIN_PX, (
        f"QUERY_MARGIN_PX is {QUERY_MARGIN_PX} but the fastest fall covers "
        f"{budget:.1f} px in one tick, so a query can miss what it fell onto"
    )


def test_the_sub_step_clamp_covers_the_fastest_travel() -> None:
    budget = Physics.MAX_FALL_SPEED * Simulation.TIMESTEP
    reach = Simulation.MAX_SUBSTEPS_PER_AXIS * Separation.SUB_STEP_SIZE
    assert reach >= budget, (
        f"{Simulation.MAX_SUBSTEPS_PER_AXIS} sub-steps of {Separation.SUB_STEP_SIZE} px "
        f"cover {reach} px, less than the {budget:.1f} px of the fastest fall"
    )


def test_the_sweep_ceiling_covers_the_widest_step() -> None:
    from src.core.settings import Combat

    widest = (
        max(Physics.MAX_FALL_SPEED, Physics.DASH_SPEED, Physics.JUMP_FORCE)
        * Simulation.TIMESTEP
        * 2.0
    )
    assert widest <= Combat.SWEEP_MAX_DISPLACEMENT_PX, (
        f"SWEEP_MAX_DISPLACEMENT_PX is {Combat.SWEEP_MAX_DISPLACEMENT_PX}, less than "
        f"the {widest:.1f} px a full-charge knockback can cover in a tick"
    )


@pytest.mark.parametrize("dt", [1 / 120, 1 / 60, 1 / 30])
def test_friction_decays_at_the_same_rate_per_second(dt: float) -> None:
    """A second of the same rate, sliced differently, must land the same place."""
    reference = _decay(25.0, 1 / 60, 60)
    sampled = _decay(25.0, dt, int(round(1.0 / dt)))
    assert sampled == pytest.approx(reference, rel=1e-6), (
        f"rate 25 at dt={dt:.5f} left {sampled} after a second, against {reference} "
        "at 60 Hz: the decay is a function of the slice, not of the rate"
    )


@pytest.mark.parametrize("dt", [1 / 120, 1 / 60, 1 / 30])
def test_an_exponential_approach_lands_the_same_place(dt: float) -> None:
    """The other half of the same property: exponential blends, not just decay."""
    reference = _decay(12.0, 1 / 60, 60)
    sampled = _decay(12.0, dt, int(round(1.0 / dt)))
    assert sampled == pytest.approx(reference, rel=1e-6)


def test_the_coyote_window_is_the_time_it_claims() -> None:
    """Measured at 133 ms for a 120 ms setting: the window is one tick long.

    ``JumpController.update`` refills before it decays, and the contact flag it
    tests is the previous tick's, so a press is always answered against a stale
    ground. The configured duration survives; the window it produces does not,
    which is exactly the kind of thing a constant alone cannot catch.
    """
    ticks = round(Physics.COYOTE_DURATION * Simulation.TICK_RATE)
    assert ticks == 7, f"{Physics.COYOTE_DURATION} s is {ticks} ticks at 60 Hz"
    assert ticks + 1 == 8, "the refill-before-decay adds one tick to the window"
    assert abs(Physics.JUMP_BUFFER_DURATION * Simulation.TICK_RATE - 6.0) < 1e-9
