"""A scene that stops the world must also stop the picture.

The bug this file is about was reported as "the game trembles when I press
pause", and it is worth being precise about where it lived, because the obvious
place to look was clean.

Pausing freezes the simulation correctly: ``SceneManager.update`` advances only
the top scene, so the level stops ticking and the world genuinely stops. The
*picture* did not. ``SceneManager.draw`` repaints the whole stack every frame --
by design, so a translucent overlay can cover a frozen scene -- and the frozen
scene's draw was not producing the same pixels twice.

The reason is that the camera interpolates. ``begin_frame`` blends between the
offset the last tick started from and the one it ended at, and only a tick can
close that gap. With no ticks, the gap stayed open at its full width, and
``render_alpha`` -- the fraction of the leftover accumulator -- kept wandering,
because the accumulator is still fed real time and drained by ticks that do
nothing. Every wandering fraction was drawn as motion.

So a test that looks at the pause screen's own pixels passes either way. The
moving part is the scene underneath, and the assertion has to be about the
whole repaint.
"""

import pathlib

import pygame
import pytest

from src.application.scenes.gameover_scene import GameOverScene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.pause_scene import PauseScene
from src.core.game import Game
from src.core.settings import Debug, Simulation

pytestmark = pytest.mark.usefixtures("_headless_pygame_display")


def _changed_bytes(target: pygame.Surface, previous: bytes) -> int:
    """How many bytes of the frame differ from the previous frame's.

    Compares the raw buffers rather than sampling pixels. The drift this is
    looking for is *sub-pixel* -- about 0.4 world units a frame, under a pixel of
    target at 2x -- so a test that samples every third pixel can watch a frame
    slide without noticing, and then pass with the bug still in place. Counting
    bytes is also C-speed, so this can afford to be exact.
    """
    return sum(
        1 for a, b in zip(pygame.image.tobytes(target, "RGBA"), previous, strict=True) if a != b
    )


def _snapshot(target: pygame.Surface) -> bytes:
    return pygame.image.tobytes(target, "RGBA")


def _advance(game: Game) -> None:
    """One frame with the event queue emptied first.

    The queue is drained because a paused frame is supposed to depend on the
    simulation and nothing else, and a device event that arrives late -- the
    dummy driver enumerates hardware after a few dozen frames -- has no business
    changing the picture. Draining is the honest way to say so: the test is
    about the world standing still, not about what the event queue was doing.
    """
    pygame.event.clear()
    game.step()


def _stack_names(game: Game) -> list[str]:
    return [type(scene).__name__ for scene in game.scene_manager._stack]


@pytest.fixture()
def playing(tmp_path: pathlib.Path):
    """A game in a level whose camera was moving on the frame the world stopped.

    The camera only has a gap to interpolate across if it moved, so a pause
    from a standing start shows nothing -- and the gap is the whole mechanism,
    so the fixture creates it rather than hoping the player physics happened to
    produce one. Leaving it to chance made this test pass with the fix removed,
    which is worse than having no test: it looked like the invariant was being
    checked and was not.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    game.scene_manager.switch(GameplayScene(game))
    for _ in range(20):
        game.step()

    level = game.scene_manager._stack[0].level
    assert level is not None
    # Where a tick leaves the camera: offset has moved, _previous_offset has not.
    # Exactly the state the last tick before a pause leaves behind.
    level.camera.offset.x += 10.0
    level.camera.offset.y += 10.0
    assert game.viewport is not None
    return game


@pytest.mark.skipif(
    Debug.is_enabled(),
    reason="the debug overlay reports live frame times, so the frame is meant to change",
)
def test_a_halted_scene_repaints_identical_pixels(playing: Game) -> None:
    """Every frame of a frozen game is the same frame.

    Not "almost the same": the same. A repaint that differs at all is motion the
    player can see, and the pause menu does not move.

    Two things are deliberately out of scope, and both are worth naming.

    Only the pause screen is checked, because it is the only translucent
    overlay: the frozen world shows through it, so the trembling is visible.
    ``GameOverScene`` fills the target opaquely and hides the world completely,
    so no pixel test could ever see this there -- its version of the invariant
    is the camera test below, which does not care what covers the pixels.

    And the test is skipped with ``DEBUG=1``, because the debug overlay prints
    live frame times in the top right and *should* change every frame. Without
    the skip, this test failed under the debug build and the only honest
    response was to weaken the assertion, which would have thrown away the
    exactness that makes it worth having.
    """
    playing.scene_manager.push(PauseScene(playing, 0))
    for _ in range(3):
        _advance(playing)

    target = playing.viewport.surface if playing.viewport is not None else None
    assert target is not None
    stack = _stack_names(playing)
    previous = _snapshot(target)

    for frame in range(4):
        _advance(playing)
        # The stack is checked before the pixels, on purpose. This test drove a
        # menu, and a menu can be navigated: when something in the headless
        # environment pushed the pause screen into Options, the failure surfaced
        # as a byte count -- "7143 differing bytes" -- which says nothing about
        # what went wrong. Asserting the stack first names it.
        assert _stack_names(playing) == stack, (
            f"the scene stack changed to {_stack_names(playing)}; the frame below "
            "is a different screen, not a moved world"
        )
        changed = _changed_bytes(target, previous)
        assert changed == 0, f"frame {frame} repainted {changed} differing bytes"
        previous = _snapshot(target)


@pytest.mark.parametrize("halted", [PauseScene, GameOverScene])
def test_the_camera_stops_drifting_when_the_world_stops(playing: Game, halted: type) -> None:
    """The narrower version, on the number that was moving.

    Worth having on its own for two reasons. It names the cause: the camera's
    transform is a pure function of a frozen simulation only if the
    interpolation fraction is constant, and it was not, because the accumulator
    kept draining through no-op ticks. And it holds for an opaque overlay too,
    where the pixels cannot show the drift but the camera is still being
    redrawn underneath it.
    """
    playing.scene_manager.push(halted(playing, 0))
    for _ in range(3):
        _advance(playing)

    stack = _stack_names(playing)
    level = playing.scene_manager._stack[0].level
    assert level is not None
    before = (level.camera._shift, level.camera._shift_y)

    for _ in range(5):
        _advance(playing)

    assert _stack_names(playing) == stack, "a different screen was pushed mid-test"
    assert (level.camera._shift, level.camera._shift_y) == before


def test_a_halted_scene_reports_that_it_halts(playing: Game) -> None:
    """The declaration is the mechanism, so it is asserted on its own.

    A scene that overrides ``update`` to do nothing and forgets this gets the
    sliding world back, and nothing else in the system would tell it.
    """
    playing.scene_manager.push(PauseScene(playing, 0))
    assert playing.scene_manager.halts_simulation is True

    playing.scene_manager.pop()
    assert playing.scene_manager.halts_simulation is False


@pytest.mark.parametrize("accumulator", [0.0, 0.004, 0.008, 0.016])
def test_the_interpolation_fraction_ignores_the_accumulator_while_halted(
    playing: Game, accumulator: float
) -> None:
    """The fix, stated as the mapping it changes.

    Written against a set accumulator rather than sampled from real frames,
    because the bug *is* that the fraction tracks the accumulator, and a test
    that watches it vary across thirty frames of wall-clock depends on the
    machine being fast enough to leave a residue. It was flaky, and it failed
    for the wrong reason when the residue happened to be zero every frame.
    """
    playing.scene_manager.push(PauseScene(playing, 0))
    playing._accumulator = accumulator

    assert playing.render_alpha() == 1.0


def test_a_running_game_still_interpolates(playing: Game) -> None:
    """The fix must not cost the smooth motion it was protecting.

    Pinning the fraction while the world is stopped is only right because the
    fraction is still free while it runs. A game that stopped interpolating
    would look smooth and be slightly wrong, which is harder to notice than
    judder and worse to play.
    """
    playing._accumulator = 0.004

    fraction = playing.render_alpha()

    assert fraction != 1.0
    assert fraction == pytest.approx(0.004 / Simulation.TIMESTEP)
    assert playing.scene_manager.halts_simulation is False
