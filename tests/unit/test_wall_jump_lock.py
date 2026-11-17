"""The wall-jump lock reaches the real Player, not only a stand-in.

``apply_horizontal_movement`` damps the run for ``wall_jump_lock_duration``
after a wall jump, through ``entity.wall_jump_lock``. It used to find the lock
with ``isinstance(entity, WallJumpLock)`` on a runtime-checkable Protocol, which
reads the class statically and did not see the player's jump attributes, then
served by ``__getattr__``: the check answered no for the player and the lock
never applied. The tests of the lock used stand-ins, which is why nobody saw it.
"""

from __future__ import annotations

import pygame
import pytest

from src.core import asset_library
from src.core.input.input_manager import InputManager
from src.entities.player import Player
from src.physics.movement import apply_horizontal_movement


@pytest.fixture
def player(monkeypatch: pytest.MonkeyPatch) -> Player:
    """A real Player; its animation frames are stand-ins, the rest is the game's."""
    pygame.init()
    pygame.display.set_mode((100, 100))
    frame = pygame.Surface((64, 64), pygame.SRCALPHA)
    monkeypatch.setattr(asset_library.AssetLibrary, "frames", lambda self, path: [frame])
    return Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=InputManager(),
    )


def test_the_players_lock_is_its_jump_controller(player: Player) -> None:
    assert player.wall_jump_lock is player.jump


def test_a_wall_jump_damps_the_players_run(player: Player) -> None:
    """Holding toward the wall right after a wall jump does not steer at once."""
    jump = player.jump
    jump.wall_jump_lock_timer = jump.wall_jump_lock_duration
    player.velocity.x = 400.0
    player.move_axis = 1.0

    apply_horizontal_movement(player, 1 / 60)

    assert jump.wall_jump_lock_timer == pytest.approx(jump.wall_jump_lock_duration - 1 / 60)
    assert player.velocity.x < 400.0, "the lock damps toward zero, it does not accelerate"


def test_an_enemy_has_no_lock() -> None:
    from src.entities.entity import Entity

    entity = Entity((0, 0), (10, 10), (0, 0, 0), pygame.sprite.Group(), pygame.sprite.Group())
    assert entity.wall_jump_lock is None
