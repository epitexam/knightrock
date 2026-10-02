"""Crouch as a usable posture: it moves, it attacks, it guards, it undoes itself.

Driven through a real ``Player`` and a real ``InputManager`` rather than by
poking the state machine, for the same reason ``test_turn_state.py`` does it: the
defects this file exists for were all *combinations* -- crouch reachable but not
attackable, crouch-guard refused, a one-tick crouch flickering on a key tap --
and every one of them passed a test that exercised a single state in isolation.
"""

import os

import pygame
import pytest

from src.combat.attack_data import move_id
from src.combat.frame_data import Stance
from src.combat.refusal import Refusal
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState
from src.core.settings import Physics
from src.entities.player import Player
from src.states.player_states import PlayerState

TICK = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


FLOOR_TOP = 56.0
"""Where the fighter's feet rest, matching the 56px standing hitbox at pos y=0."""

CROUCH_TOP = FLOOR_TOP - 56.0 * Physics.CROUCH_HEIGHT_FACTOR
"""The top of a fully crouched collider (22.4): below this there is no ceiling."""

TIGHT_CEILING = 12.0
"""A ceiling that a crouched fighter fits under but a standing one does not."""


class Solid(pygame.sprite.Sprite):
    """A slab of level geometry, spanning the given vertical band."""

    def __init__(self, top: float, height: float, *, x: float = -500.0, width: float = 2000.0):
        super().__init__()
        self.rect = pygame.FRect(x, top, width, height)
        self.hitbox = self.rect


def _player(
    input_manager: InputManager | None = None,
    *,
    ceiling_top: float | None = None,
) -> Player:
    """A fighter standing on a real floor, optionally under a low ceiling.

    The floor is a real solid rather than an ``on_surface`` assertion so gravity
    and vertical collision resolve as they do in a level. Several assertions here
    are about where the feet end up, and a fighter sinking through a fake floor
    would answer those questions about the harness instead of about crouch.
    """
    collision = pygame.sprite.Group()
    collision.add(Solid(FLOOR_TOP, 400.0))
    manager = input_manager or InputManager()
    player = Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=collision,
        moving_platforms=[],
        input_manager=manager,
    )
    # Land before handing the fighter to a test. A freshly spawned player has not
    # touched the floor yet, so its first tick is a fall, and a test that pressed
    # Down immediately would be measuring that transition instead of the crouch.
    _run(player, manager, frames=3)
    assert _state(player) == PlayerState.IDLE.value
    # The ceiling goes in last. A fighter spawned into it overlaps it while
    # standing, so vertical resolution pushes them straight back out and the
    # settle above would never settle.
    if ceiling_top is not None:
        player.collision_sprites.add(Solid(ceiling_top - 400.0, 400.0))
    return player


def _run(
    player: Player,
    input_manager: InputManager,
    *,
    frames: int,
    axis: float = 0.0,
    down: bool = False,
    guard: bool = False,
    attack: bool = False,
) -> None:
    for index in range(frames):
        actions: set[InputAction] = set()
        if down:
            actions.add(InputAction.MOVE_DOWN)
        if guard:
            actions.add(InputAction.GUARD)
        if attack and index == 0:
            actions.add(InputAction.ATTACK_1)
        input_manager.apply_remote_state(
            InputState(move_axis=axis, held_actions=frozenset(actions))
        )
        player.update(TICK)
        if player.on_surface["floor"]:
            # Park on the floor line so a crouched fighter's smaller collider
            # does not get pushed up out of it by the floor it is standing on.
            player.hitbox.bottom = FLOOR_TOP
            player.sync_rects()


def _state(player: Player) -> str | None:
    return player.state_machine.current_state_name


# --- Movement ---------------------------------------------------------------


def test_crouching_keeps_the_speed_the_fighter_carried_in() -> None:
    """Pressing Down mid-run must not erase the run.

    The crouch used to zero ``velocity.x`` on entry, so a fighter at full speed
    lost every pixel of momentum the instant they pressed Down and had to
    re-accelerate from nothing on the way out. Crouch is a posture, not a brake
    the player has to pay a second acceleration to get out of.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=45, axis=1.0)
    speed_at_press = player.velocity.x
    assert abs(speed_at_press) > 0.5

    _run(player, input_manager, frames=1, axis=1.0, down=True)

    assert _state(player) == PlayerState.CROUCH.value
    assert abs(player.velocity.x) > 0.0, "the crouch consumed the run"


def test_a_crouched_fighter_can_still_walk() -> None:
    """Crouching is a posture, not a stop: Down+direction has to travel.

    A crouch you cannot move in is strictly worse than not crouching, because it
    trades the hurtbox for the ability to reposition.
    """
    input_manager = InputManager()
    player = _player(input_manager)

    _run(player, input_manager, frames=30, axis=1.0, down=True)

    assert _state(player) == PlayerState.CROUCH.value
    assert player.velocity.x > 0.0, "the crouched fighter did not travel"


def test_the_crouched_shuffle_is_slower_than_standing() -> None:
    """The crouch-walk is a shuffle, not a second run speed.

    Without this the posture would just be a free hurtbox discount to hold down
    while crossing a room.
    """
    input_manager = InputManager()
    standing = _player(input_manager)
    _run(standing, input_manager, frames=60, axis=1.0)
    crouched = _player(input_manager)
    _run(crouched, input_manager, frames=60, axis=1.0, down=True)

    assert crouched.velocity.x < standing.velocity.x
    assert crouched.velocity.x > 0.0


# --- Attacks and guard ------------------------------------------------------


def test_attacking_from_a_crouch_is_refused_for_the_right_reason() -> None:
    """Down+attack no longer reaches an attack, and that is the fix, not a regression.

    ``CROUCH`` used to sit in ``ATTACK_FORBIDDEN_STATES``, so holding Down cost
    the player their whole offence -- and once the state stopped being forbidden,
    the honest answer turned out to be worse: *every* move in the table became
    available from down there, including the chargeable one and the lunging one,
    both of which throw the fighter standing up.

    The restriction now lives on the move (``AttackDefinition.stances``) instead
    of on a list of states, and this pins the reason it reports. A refusal that
    said ``UNKNOWN`` or ``BUSY`` would be the same silence as before with a
    different cause.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=5, down=True)
    assert _state(player) == PlayerState.CROUCH.value
    assert player.stance is Stance.CROUCH

    refusal = player.combat.start_attack(move_id("light_attack"))

    assert refusal is Refusal.STANCE
    assert _state(player) == PlayerState.CROUCH.value


def test_guarding_from_a_crouch_is_not_swallowed() -> None:
    """Down+guard has to reach the guard state.

    ``_can_guard`` refused crouch outright while ``guard_held`` stayed true, so
    the press vanished and the guard popped a tick *after* Down was released --
    with no tap of the player's own. That also left the entire crouching half of
    ``Guard.HEIGHT_BLOCK`` unreachable, since :meth:`Player.receive_damage`
    resolves those rows off the crouch state.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=5, down=True)
    assert _state(player) == PlayerState.CROUCH.value

    _run(player, input_manager, frames=1, down=True, guard=True)

    assert _state(player) == PlayerState.GUARD.value


def test_a_low_attack_is_blocked_by_a_crouched_guard() -> None:
    """The height rules have to be reachable through actual play.

    ``HEIGHT_BLOCK[("low", True)]`` has always been in the table and has never
    been reachable, because nothing let the player hold a guard while crouched.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    player.faction = "B"
    _run(player, input_manager, frames=5, down=True, guard=True)
    assert _state(player) == PlayerState.GUARD.value
    # Past the parry window: the first frames of a guard are a parry by design,
    # and this is about which *height rows* resolve, not about the active frames.
    player.guard.parry_timer = 0.0
    posture = player.guard.posture

    outcome, chip, _parried = player.guard.take_hit(10.0, False, height="low", crouching=True)

    assert outcome == "guard"
    assert player.guard.posture < posture


# --- Height ----------------------------------------------------------------


def test_the_hurtbox_is_shrunk_over_a_blend_not_in_one_tick() -> None:
    """The transition is eased, so it reads as a body moving.

    It used to be applied on entry in a single tick. More than one distinct
    intermediate height is the whole claim: a single-step change is a pop.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    stood = player.hitbox.height
    crouched = stood * Physics.CROUCH_HEIGHT_FACTOR

    heights = _heights_while(player, input_manager, 0.5, down=True)

    assert heights[-1] == pytest.approx(crouched)
    intermediates = [h for h in heights if crouched < h < stood]
    assert intermediates, f"the shrink jumped straight from {stood} to {crouched}"


def _heights_while(
    player: Player,
    input_manager: InputManager,
    seconds: float,
    *,
    down: bool = True,
) -> list[float]:
    """Record the collider height across a hold, one sample per tick."""
    actions = frozenset({InputAction.MOVE_DOWN}) if down else frozenset()
    heights: list[float] = []
    for _ in range(round(seconds * 60)):
        input_manager.apply_remote_state(InputState(move_axis=0.0, held_actions=actions))
        player.update(TICK)
        heights.append(player.hitbox.height)
    return heights


def test_releasing_down_stands_the_fighter_back_up() -> None:
    input_manager = InputManager()
    player = _player(input_manager)
    stood = player.hitbox.height
    _run(player, input_manager, frames=20, down=True)
    assert player.hitbox.height < stood

    _run(player, input_manager, frames=20)

    assert _state(player) == PlayerState.IDLE.value
    assert player.hitbox.height == pytest.approx(stood)


def test_the_feet_stay_planted_through_the_blend() -> None:
    """Resizing the hurtbox must not lift the fighter off the floor.

    The height is anchored at the bottom every tick, which is what keeps a
    crouch from being a hop.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    floor_line = player.hitbox.bottom

    _run(player, input_manager, frames=1, down=True)
    _run(player, input_manager, frames=20, down=True)

    assert player.hitbox.bottom == pytest.approx(floor_line)


# --- Headroom ---------------------------------------------------------------


def test_releasing_under_a_low_ceiling_stops_at_the_headroom() -> None:
    """No headroom, no standing up: the fighter rises as far as the gap allows.

    The release blend is capped by the ceiling rather than being refused
    outright, so the fighter comes part of the way up and holds there -- the
    honest geometry. Growing to the full standing height regardless would put
    the head through the ceiling and leave it clipping until vertical resolution
    pushed the fighter out on some later tick.
    """
    input_manager = InputManager()
    player = _player(input_manager, ceiling_top=TIGHT_CEILING)
    _run(player, input_manager, frames=20, down=True)
    crouched = player.hitbox.height
    assert player.hitbox.top >= TIGHT_CEILING, "the crouch has to actually fit"
    stood = crouched / Physics.CROUCH_HEIGHT_FACTOR

    _run(player, input_manager, frames=30)

    assert player.hitbox.height < stood, "it stood up into a ceiling"
    assert player.hitbox.top >= TIGHT_CEILING - 0.01, "and put its head through it"
    assert player.hitbox.height > crouched, "and did not rise at all"


def test_a_crouched_fighter_still_crouches_under_a_ceiling() -> None:
    """The posture itself is unaffected: a tight ceiling still allows it.

    The headroom cap only applies to growing. A crouched fighter fitting under
    the ceiling is the case that has to keep working, or the cap would leave
    them unable to crouch at all in a low corridor.
    """
    input_manager = InputManager()
    player = _player(input_manager, ceiling_top=TIGHT_CEILING)
    _run(player, input_manager, frames=20, down=True)
    free = _player(input_manager)
    _run(free, input_manager, frames=20, down=True)

    assert player.hitbox.height == pytest.approx(free.hitbox.height)


def test_a_dash_out_of_a_crouch_does_not_inflate_into_the_ceiling() -> None:
    """An interrupt out of crouch has to respect the same headroom test.

    ``exit()`` restored the full standing height unconditionally, so a dash or a
    hurt reaction from under a low ceiling popped the collider into it and left
    the head clipping until vertical resolution caught up on a later tick.
    """
    input_manager = InputManager()
    player = _player(input_manager, ceiling_top=TIGHT_CEILING)
    _run(player, input_manager, frames=20, down=True)
    crouched = player.hitbox.height

    player.dash.request(1.0)
    _run(player, input_manager, frames=2, down=True)

    assert player.hitbox.height == pytest.approx(crouched)


def test_the_ceiling_stops_a_partial_stand_up_midway() -> None:
    """Standing up stops at the tallest height that fits, not at full height.

    A blend that grows straight to the target would pass through the ceiling on
    the way and be pushed out by vertical resolution on a later tick, which is
    the stutter this whole rework is about.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    stood = player.hitbox.height

    _run(player, input_manager, frames=20, down=True)
    crouched = player.hitbox.height
    # Drop the ceiling in over a fighter who is already crouched, so the settle
    # in ``_player`` never has to fit a standing collider through it.
    player.collision_sprites.add(Solid(TIGHT_CEILING - 400.0, 400.0))

    _run(player, input_manager, frames=20)

    assert player.hitbox.height < stood
    assert player.hitbox.height > crouched


def test_attacking_out_of_a_crouch_eases_back_up() -> None:
    """The stand-up blend survives the interrupt, because it is not the state's.

    The height used to be owned by the crouch state, so attacking or guarding
    out of one left the state on the tick the interrupt fired and the release had
    no tick left to run in: the collider snapped to full height in one step. The
    pop did not go away, it moved to the exit -- which is the same stutter.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=20, down=True)
    crouched = player.hitbox.height
    stood = player.crouch.stood_height

    # Tick 0 interrupts out of the crouch *and* releases Down, which is the
    # combination that used to snap: the state left before it could blend.
    heights = []
    for frame in range(30):
        actions: set[InputAction] = set()
        if frame == 0:
            actions.add(InputAction.ATTACK_1)
        input_manager.apply_remote_state(InputState(move_axis=0.0, held_actions=frozenset(actions)))
        player.update(TICK)
        heights.append(player.hitbox.height)

    assert heights[-1] == pytest.approx(stood), "it never finished standing"
    # No single tick may cover more than a fraction of the way back: a jump from
    # crouched to full height is the whole defect, however it was reached.
    steps = [b - a for a, b in zip(heights, heights[1:], strict=False) if b > a]
    assert steps, "the fighter never stood back up"
    assert max(steps) < crouched / 2, f"the stand-up snapped in one tick: {steps}"


def test_guarding_out_of_a_crouch_keeps_the_low_guard() -> None:
    """Down+guard is a low guard, not a standing guard.

    ``Player.receive_damage`` resolves ``Guard.HEIGHT_BLOCK`` off the posture, so
    reading it off the state name would report a guarding-down fighter as
    standing and let every low attack through their guard.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=5, down=True, guard=True)

    assert _state(player) == PlayerState.GUARD.value
    assert player.crouch.is_crouched is True
    assert player.hitbox.height < player.crouch.stood_height


# --- Rollback ---------------------------------------------------------------


def test_the_crouch_input_rolls_back_with_the_frame() -> None:
    """``down_held`` was missing from the snapshot.

    A rollback restored a fighter mid-posture with ``down_held`` back at its
    pre-crouch value, so the crouch state and the input that drives it
    disagreed on the very next tick.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=20, down=True)
    assert player.down_held is True

    snapshot = player.save_state()
    player.down_held = False
    player.load_state(snapshot)

    assert player.down_held is True
    assert player.fast_fall is True


def test_a_rollback_keeps_the_crouched_height_it_captured() -> None:
    """The captured hurtbox is the crouched one, and it has to survive.

    ``PlayerCrouchState`` stores its reference heights in plain attributes that
    the state machine snapshots as scalars, and the hitbox in the entity
    snapshot. A rollback has to put both back, or the fighter stands up out of a
    posture the restored frame still says they are in.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=20, down=True)
    crouched = player.hitbox.height

    snapshot = player.save_state()
    _run(player, input_manager, frames=20)
    assert player.hitbox.height > crouched

    player.load_state(snapshot)

    assert player.hitbox.height == pytest.approx(crouched)
    assert _state(player) == PlayerState.CROUCH.value
