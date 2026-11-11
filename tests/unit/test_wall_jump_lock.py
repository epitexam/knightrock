"""The wall-jump lock reaches the real Player, not only a stand-in.

``apply_horizontal_movement`` damps the run for ``wall_jump_lock_duration``
after a wall jump, and it finds out whether an entity has a lock with
``isinstance(entity, WallJumpLock)``. On Python 3.12+ that check reads the
class with ``inspect.getattr_static``, which does not see attributes served by
``__getattr__`` -- and the player's jump attributes used to come from there,
so the check answered no for the player and the lock never applied. The tests
of the lock used stand-ins with real attributes, which is why nobody saw it.
"""

from __future__ import annotations

import inspect

import pygame
import pytest

from src.core import asset_library
from src.core.input.input_manager import InputManager
from src.entities.player import Player
from src.physics.movement import WallJumpLock, apply_horizontal_movement

LOCK_MEMBERS = ("wall_jump_lock_timer", "wall_jump_lock_duration", "wall_jump_min_lock")


@pytest.mark.parametrize("name", LOCK_MEMBERS)
def test_the_lock_is_a_real_attribute_of_the_player_class(name: str) -> None:
    inspect.getattr_static(Player, name)


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


def test_the_player_satisfies_the_lock_protocol(player: Player) -> None:
    assert isinstance(player, WallJumpLock)


def test_a_wall_jump_damps_the_players_run(player: Player) -> None:
    """Holding toward the wall right after a wall jump does not steer at once."""
    player.wall_jump_lock_timer = player.wall_jump_lock_duration
    player.velocity.x = 400.0
    player.move_axis = 1.0

    apply_horizontal_movement(player, 1 / 60)

    assert player.wall_jump_lock_timer == pytest.approx(player.wall_jump_lock_duration - 1 / 60)
    assert player.jump.wall_jump_lock_timer == player.wall_jump_lock_timer
    assert player.velocity.x < 400.0, "the lock damps toward zero, it does not accelerate"
