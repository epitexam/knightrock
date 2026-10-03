"""CameraSystem: the freeze on death must hold the framing, not the shake."""

from types import SimpleNamespace

import pygame
from pygame.math import Vector2

from src.core.level.systems.camera_system import CameraSystem
from src.core.rendering.camera import Camera
from src.core.settings import Respawn


def _player(alive: bool, hitbox: pygame.FRect | None = None):
    box = hitbox if hitbox is not None else pygame.FRect(0, 0, 64, 64)
    return SimpleNamespace(is_dead=not alive, hitbox=box)


def _ticks(system: CameraSystem, player, seconds: float, step: float = 1 / 60) -> None:
    ticks = round(seconds / step)
    for _ in range(ticks):
        system.process(step, player)


def test_a_dead_player_stops_the_camera() -> None:
    """The framing freeze is the point of the system: a corpse cannot be followed."""
    camera = Camera()
    camera.set_world_size(2560, 1920)
    system = CameraSystem(camera)
    far = _player(True, pygame.FRect(2000, 1500, 64, 64))
    _ticks(system, far, 0.25)

    system.process(1 / 60, _player(False, pygame.FRect(0, 0, 64, 64)))

    settled = camera.offset.copy()
    _ticks(system, _player(False, pygame.FRect(0, 0, 64, 64)), 1.0)
    assert camera.offset == settled


def test_the_whole_frame_does_not_move_while_the_player_is_dead() -> None:
    """The death window must not depend on the display's frame rate.

    ``follow`` leaves a pending-tick gap between ``_previous_offset`` and
    ``offset`` so ``begin_frame`` can interpolate across it, and normally the
    next ``follow`` closes it. While the camera is held there is no next
    ``follow``, so the gap used to freeze at one tick's worth of travel (4
    world px, measured) and stay there for the whole window.

    The simulation is not halted during a death, so the interpolation fraction
    stayed a live fraction rather than being pinned to 1 as it is behind the
    pause menu -- and it wanders every frame, because it is residual real time.
    A permanent gap times a wandering fraction is drawn as the entire frame
    sliding several pixels up and down, twice a second, for two seconds.

    So the picture while dead must be the picture for *any* fraction. This is
    the invariant that was broken, and it is asserted over the range rather than
    at one value: a single alpha would pass by luck.
    """
    camera = Camera()
    camera.set_world_size(2560, 1920)
    system = CameraSystem(camera)
    moving = _player(True, pygame.FRect(2000, 1500, 64, 64))
    _ticks(system, moving, 0.25)
    corpse = _player(False)
    _ticks(system, corpse, 0.5)

    shifts = set()
    for step in (0.0, 0.02, 0.25, 0.5, 0.75, 0.98, 1.0):
        camera.begin_frame(step)
        shifts.add((camera._shift, camera._shift_y))

    assert len(shifts) == 1, f"the frame moves with the frame rate: {sorted(shifts)}"


def test_holding_does_not_move_the_framing() -> None:
    """Closing the interpolation gap must not nudge where the camera sits.

    The gap is settled where the tick left the camera, so the picture on the
    tick a player dies corrects to the simulation's position -- at most the one
    tick of travel it had already earned -- rather than jumping anywhere new.
    """
    camera = Camera()
    camera.set_world_size(2560, 1920)
    system = CameraSystem(camera)
    _ticks(system, _player(True, pygame.FRect(2000, 1500, 64, 64)), 0.25)
    where_the_death_lands = camera.offset.copy()

    system.process(1 / 60, _player(False))

    assert camera.offset == where_the_death_lands


def test_the_shake_decays_while_the_player_is_dead() -> None:
    """A dead player used to freeze the shake at full amplitude for the whole window.

    The killing blow feeds trauma on the tick it lands, and the pipeline skips
    ``follow`` from that same tick, so the decay inside ``follow`` never ran:
    ``shake_offset`` returned the same vector every frame and the entire picture
    sat displaced for the full respawn delay.
    """
    camera = Camera()
    system = CameraSystem(camera)
    camera.add_trauma(1.0)
    corpse = _player(False)

    _ticks(system, corpse, Respawn.DELAY_S)

    assert camera.trauma == 0.0
    assert camera.shake_offset() == Vector2(0, 0)


def test_the_shake_ages_exactly_as_fast_as_it_does_for_a_living_player() -> None:
    """Splitting the decay out of ``follow`` must not change the alive path."""
    stepped, ticked = Camera(), Camera()
    stepped.add_trauma(1.0)
    ticked.add_trauma(1.0)
    living = _player(True)

    for _ in range(120):
        stepped.follow(living.hitbox, 1 / 60)
        ticked.advance_shake(1 / 60)

    assert stepped.trauma == ticked.trauma
    assert stepped.shake_offset() == ticked.shake_offset()


def test_the_shake_dies_out_long_before_the_respawn() -> None:
    """The decay has to outlast the intended feedback, not merely reach zero.

    Guards against a fix that merely slows the freeze instead of lifting it:
    full trauma is spent in a fraction of a second, so it has to be gone well
    inside one respawn delay.
    """
    camera = Camera()
    system = CameraSystem(camera)
    camera.add_trauma(1.0)
    corpse = _player(False)

    _ticks(system, corpse, 1.0)

    assert camera.trauma == 0.0, "full trauma must be spent in a fraction of a second"


def test_a_dead_player_with_trauma_still_shifts_the_frame_before_it_settles() -> None:
    """The shake is a per-frame offset, so it has to actually move between frames.

    A frozen ``_shake_time`` returns a constant vector, which reads as one
    displaced frame rather than a shake at all.
    """
    camera = Camera()
    system = CameraSystem(camera)
    camera.add_trauma(1.0)
    corpse = _player(False)

    offsets = set()
    for _ in range(6):
        system.process(1 / 60, corpse)
        offsets.add(tuple(camera.shake_offset()))

    assert len(offsets) > 1
