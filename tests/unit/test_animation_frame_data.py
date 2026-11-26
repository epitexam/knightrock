"""The player's attack art follows the frame data, not a wall clock.

The shipped clip has three poses and a fixed 0.07 s frame time, while moves
run 12 to 42 frames at 60 Hz. Driving the pose from startup/active/recovery
aligns the sprite with the hitbox and makes attack-speed multipliers (fury,
rush, blitz) move the art along with the frame data.
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame

from src.simulation.combat.frame_data import PhaseState
from src.simulation.data.provider import shipped_gameplay_data
from src.simulation.entities.components.animation_publisher import AnimationPublisher, _attack_frame
from src.simulation.entities.player_animation import PLAYER_ANIMATIONS


class _RecordingAnimator:
    def __init__(self) -> None:
        self.current = "attack"
        self.frames: list[int] = []
        self.updates: list[float] = []

    def play(self, name: str) -> None:
        self.current = name

    def set_frame(self, index: int) -> None:
        self.frames.append(index)

    def update(self, delta_time: float) -> None:
        self.updates.append(delta_time)

    def surface(self, size: tuple[int, int], facing_right: bool) -> pygame.Surface | None:
        return None


def test_phase_maps_to_windup_impact_and_follow_through() -> None:
    state = SimpleNamespace(is_attacking=True, sub_state=PhaseState.STARTUP)
    assert _attack_frame(state) == 0
    state.sub_state = PhaseState.ACTIVE
    assert _attack_frame(state) == 1
    state.sub_state = PhaseState.RECOVERY
    assert _attack_frame(state) == 2
    state.is_attacking = False
    assert _attack_frame(state) is None


def test_publisher_drives_the_pose_when_the_owner_asks_for_it() -> None:
    animator = _RecordingAnimator()
    state = SimpleNamespace(is_attacking=True, sub_state=PhaseState.ACTIVE)
    owner = SimpleNamespace(
        animator=animator,
        combat=SimpleNamespace(state=state),
        rect=pygame.FRect(0, 0, 40, 48),
        facing_right=True,
        image=pygame.Surface((1, 1)),
        _animation_name=lambda: "attack",
        _phase_driven_attack_art=True,
    )

    AnimationPublisher(owner).update(1 / 60)  # type: ignore[arg-type]

    assert animator.frames == [1]
    assert animator.updates == []


def test_non_attack_clips_still_use_the_wall_clock() -> None:
    animator = _RecordingAnimator()
    animator.current = "run"
    owner = SimpleNamespace(
        animator=animator,
        combat=SimpleNamespace(state=SimpleNamespace(is_attacking=False)),
        rect=pygame.FRect(0, 0, 40, 48),
        facing_right=True,
        image=pygame.Surface((1, 1)),
        _animation_name=lambda: "run",
        _phase_driven_attack_art=True,
    )

    AnimationPublisher(owner).update(1 / 60)  # type: ignore[arg-type]

    assert animator.frames == []
    assert animator.updates == [1 / 60]


def test_every_player_move_names_a_clip_that_exists() -> None:
    attacks = shipped_gameplay_data().attack_sets["player"]
    for name, definition in attacks.items():
        assert definition.animation in PLAYER_ANIMATIONS, name
