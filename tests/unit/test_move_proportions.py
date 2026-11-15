"""Every strike is sized to the fighter who throws it, and goes one way.

The drawn fighter is about 24 x 33 inside its 40 x 56 hitbox; a blade, a fist
or a foot that outgrows it reads as a shape pasted on the scene, not a blow.
So the catalogue is held to a gauge -- how long a shape may be, how far in
front it may reach, how wide it may swing -- and a high blow stays above the
hips while a low one starts below them.
"""

from __future__ import annotations

import pytest

from src.combat.frame_data import AttackDefinition, Height, PhaseDefinition
from src.data.provider import shipped_gameplay_data

ATTACKS = shipped_gameplay_data().attack_sets

#: The longest shape and the farthest reach in front of the hitbox centre,
#: for the everyday moves and for the charged ones and the finishers.
MAX_LENGTH = 40.0
MAX_REACH = 48.0
#: The widest swing over a phase's active frames, in degrees: a cut, not a spin.
MAX_SWEEP = 150.0
#: The hip line, from the hitbox centre (y down): high blows stay above it,
#: low ones start below it.
HIP_LINE = 10.0

STRIKES = [
    (owner, name, index, phase)
    for owner, table in ATTACKS.items()
    if owner != "dummy"
    for name, definition in table.items()
    for index, phase in enumerate(definition.phases)
    if not phase.launches
]


def _active_poses(
    phase: PhaseDefinition,
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    poses = []
    for frame in range(phase.startup_frames, phase.startup_frames + phase.active_frames + 1):
        (size, offset), angle = phase.hitbox_shape_at(frame)
        poses.append((size, offset, angle))
    return poses


def _id(item: tuple[str, str, int, PhaseDefinition]) -> str:
    owner, name, index, _ = item
    return f"{owner}.{name}[{index}]"


@pytest.mark.parametrize("item", STRIKES, ids=[_id(item) for item in STRIKES])
def test_a_strike_is_the_size_of_a_blade_or_a_limb(
    item: tuple[str, str, int, PhaseDefinition],
) -> None:
    *_, phase = item
    for size, offset, _angle in _active_poses(phase):
        assert max(size) <= MAX_LENGTH
        assert offset[0] + max(size) / 2 <= MAX_REACH


@pytest.mark.parametrize("item", STRIKES, ids=[_id(item) for item in STRIKES])
def test_a_strike_swings_one_way_and_not_around(
    item: tuple[str, str, int, PhaseDefinition],
) -> None:
    *_, phase = item
    angles = [angle for *_, angle in _active_poses(phase)]
    assert max(angles) - min(angles) <= MAX_SWEEP


@pytest.mark.parametrize("item", STRIKES, ids=[_id(item) for item in STRIKES])
def test_a_high_blow_stays_up_and_a_low_one_starts_down(
    item: tuple[str, str, int, PhaseDefinition],
) -> None:
    *_, phase = item
    heights = [offset[1] for _, offset, _ in _active_poses(phase)]
    if phase.hit.height is Height.HIGH:
        assert max(heights) <= HIP_LINE
    if phase.hit.height is Height.LOW:
        assert heights[0] >= HIP_LINE


def _family(definition: AttackDefinition) -> tuple[object, ...]:
    """What a move looks like: its shapes, timing, and how it lands."""
    phase = definition.phases[0]
    hit = phase.hit
    return (
        len(definition.phases),
        phase.hitbox_shape,
        phase.launches,
        phase.startup_frames,
        phase.active_frames,
        hit.height,
        hit.damage_type,
        hit.unblockable,
        tuple(round(value) for value in hit.knockback.power),
    )


@pytest.mark.parametrize("owner", ["player", "goblin", "slime", "tooth", "shell"])
def test_no_two_moves_of_one_fighter_are_the_same_move(owner: str) -> None:
    """Two moves that share shape, timing, height and push are one move twice.

    The mirrored pairs of the blade chains are the one exception that is not:
    they differ by the way the blade turns, which this does not see.
    """
    table = ATTACKS[owner]
    seen: dict[tuple[object, ...], str] = {}
    for name, definition in table.items():
        family = _family(definition)
        twin = seen.get(family)
        if twin is not None and {name, twin} <= {
            "slash_high_1",
            "slash_high_2",
            "slash_low_1",
            "slash_low_2",
            "shot",
            "air_shot",
        }:
            continue
        assert twin is None, f"{name} and {twin} are the same move"
        seen[family] = name


def test_every_shot_a_phase_launches_exists() -> None:
    from src.entities.shots import SHOTS

    launched = {
        phase.launches
        for table in ATTACKS.values()
        for definition in table.values()
        for phase in definition.phases
        if phase.launches
    }
    assert launched <= set(SHOTS)
    assert launched, "something is thrown"
