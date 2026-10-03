"""A player who dies must leave the picture as still as one who pauses.

This is the sibling of ``test_halted_scene_is_a_still_picture.py``, and it is
here because the bug was the same one twice.

Pausing stops the world by halting the simulation, and the picture stopped with
it. Dying stops the world a different way: the level keeps ticking, the corpse
and every hazard keep living, and only the *camera* declines to move. So
``render_alpha`` kept returning a live fraction there, wandering frame to frame
because it is residual real time -- and the camera had a permanent
pending-tick gap for that fraction to be applied to.

That gap is the whole mechanism. ``follow`` opens one every tick to interpolate
across, and the next ``follow`` closes it; while the camera is held there is no
next ``follow``, so the gap froze at one tick's worth of travel (4 world px,
measured) and stayed for the whole respawn window. Four permanent pixels times a
wandering fraction is the entire frame sliding up and down several times a
second for two seconds. Reported as "the screen trembles when the character
dies"; not reproducible from the pause path, and not visible in any camera
offset, any trauma value or any shake offset -- ``offset`` was provably frozen
and ``trauma`` provably zero throughout.

Which is why the assertion has to be about the presented pixels of the whole
repaint. Every other number in the camera was telling the truth.
"""

import pathlib

import pygame
import pytest

from src.application.scenes.gameplay_scene import GameplayScene
from src.core.game import Game
from src.core.settings import Debug, Respawn, Simulation

#: Ticks after the death before the picture is expected to have settled. The
#: killing blow's impact and the corpse's own death animation both land in the
#: first dozen ticks (measured: nothing moves from tick 12 on), and this is the
#: margin over that. It is counted in ticks and not in frames because a frame
#: may run several of them, so a frame count would be a statement about the
#: machine this test happens to run on.
SETTLED_AFTER_TICKS = 15


@pytest.mark.skipif(
    Debug.is_enabled(),
    reason="the debug overlay reports live frame times, so the frame is meant to change",
)
def test_a_dead_player_leaves_the_picture_perfectly_still(tmp_path: pathlib.Path) -> None:
    """Every frame of the settled respawn window is the same frame, at any frame rate.

    ``Game.step`` feeds its accumulator real elapsed time, so the number of ticks
    a frame runs -- and therefore the interpolation fraction -- genuinely differs
    from frame to frame. That is the point: the window has to be still because
    there is nothing to interpolate, not because the fraction happened to sit
    still.
    """
    game = Game(save_path=tmp_path / "savegame.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    game.scene_manager.switch(GameplayScene(game))
    for _ in range(30):
        game.step()

    level = game.scene_manager._stack[0].level
    assert level is not None
    assert game.stage is not None
    target = game.stage.surface

    previous = _snapshot(target)
    death_tick = level.tick
    level.player.die()
    assert level.player.is_dead

    window_ticks = round(Respawn.DELAY_S / Simulation.TIMESTEP)
    first_compared: int | None = None
    last_compared = 0

    while level.player.is_dead:
        pygame.event.clear()
        game.step()
        current = _snapshot(target)
        # Read the death back *after* the step: the respawn lands inside it, so
        # the last frame of the window is a frame of a live player and is
        # allowed to move.
        if level.player.is_dead and level.tick - death_tick >= SETTLED_AFTER_TICKS:
            if current != previous:
                changed = sum(1 for a, b in zip(current, previous, strict=True) if a != b)
                pytest.fail(
                    f"{changed} bytes of the frame moved {level.tick - death_tick} ticks "
                    f"into the respawn window, which is meant to be a still picture"
                )
            first_compared = first_compared or level.tick - death_tick
            last_compared = level.tick - death_tick
        previous = current

    assert first_compared is not None, "the window ended before it had settled"
    covered = last_compared - first_compared
    assert covered > 0.8 * window_ticks, (
        f"only {covered} of the window's {window_ticks} ticks were checked to be still"
    )


def _snapshot(target: pygame.Surface) -> bytes:
    """The frame's raw buffer.

    Raw rather than sampled: the drift being hunted is sub-pixel, so a test that
    samples can watch a frame slide without noticing. Comparing buffers is also
    C-speed, which is what lets the assertion be exact on every frame.
    """
    return pygame.image.tobytes(target, "RGBA")
