"""The ground pivot: ``turn``, the state a reversal on the floor enters.

The claim under test is that a reversal is *held* -- the feet already rolling
the other way while the fighter still faces the way he came from -- and that
everything which has to commit to a direction still lands where the player is
pointing. Those are the two halves of one change, and the second is the one
that makes the first affordable.

The tests are driven through ``InputManager`` and a real ``Player`` rather than
by poking the state directly. That is not a style preference: an earlier
version of this feature had every piece correct in isolation and did nothing in
the game, because the pieces were only ever exercised one at a time. The
end-to-end ones below are the ones that would have caught it.
"""

import dataclasses
import math
import os
from itertools import pairwise

import pygame
import pytest

from src.core.display.framing import Framing
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import (
    Renderer,
    _sheared,
    turn_frame,
    turn_offset_px,
    turn_skew_px,
)
from src.core.settings import FootstepDust, Turn
from src.entities.player import Player
from src.states.player_states import PlayerState
from src.states.state_machine import StateMachine
from src.states.turn_state import request_turn

TICK = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    """Dummy SDL display, for the renderer tests in here."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def _enemy(kind: str = "goblin", **overrides):
    """An enemy whose pivot behaviour this test decides for itself.

    ``turn_profile`` is forced to ``None`` unless a test asks otherwise, so
    every fighter built here takes the group its faction names and nothing
    more. Without that, a test inherits whatever the shipped config for that
    type happens to say -- and "which fighters take the pivot" is a decision
    that changes, whereas "the group is applied and the flag is read at the
    right moment" is the mechanism and does not.
    """
    from src.entities.enemies.configs import ENEMY_CONFIGS
    from src.entities.enemies.enemy import Enemy

    config = dataclasses.replace(ENEMY_CONFIGS[kind], **{"turn_profile": None, **overrides})
    return Enemy(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        player_reference=None,
        config=config,
    )


def _player(input_manager: InputManager | None = None) -> Player:
    return Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=input_manager or InputManager(),
    )


def _run(
    player: Player,
    input_manager: InputManager,
    *,
    frames: int,
    axis: float = 0.0,
    attack: bool = False,
    down: bool = False,
) -> None:
    """Drive a real player for ``frames`` ticks on an assumed floor.

    The floor is asserted rather than collided with: none of these tests is
    about where a wall ended up, and all of them are about the facing.
    """
    for index in range(frames):
        actions: set[InputAction] = set()
        if attack and index == 0:
            actions.add(InputAction.ATTACK_1)
        if down:
            actions.add(InputAction.MOVE_DOWN)
        input_manager.apply_remote_state(
            InputState(move_axis=axis, held_actions=frozenset(actions))
        )
        player.on_surface["floor"] = True
        player.velocity.y = 0.0
        player.update(TICK)


def _run_at_full_speed(player: Player, input_manager: InputManager, axis: float) -> None:
    """Get the fighter genuinely rolling, so a pivot is worth entering."""
    _run(player, input_manager, frames=45, axis=axis)
    assert abs(player.velocity.x) > Turn.MIN_SPEED_PX_S, "should be running, not shuffling"


def _state(player: Player) -> str | None:
    return player.state_machine.current_state_name


# --- Entering it ------------------------------------------------------------


def test_a_ground_reversal_enters_the_turn_state() -> None:
    """Running right, pressing left: the fighter is in ``turn``, still facing right."""
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    assert player.facing_right is True

    _run(player, input_manager, frames=1, axis=-1.0)

    assert _state(player) == PlayerState.TURN.value
    assert player.facing_right is True, "and the mirror has not happened"


def test_the_hold_covers_the_plant_and_not_the_whole_turn() -> None:
    """The hold spans the deceleration, and ends as the push begins.

    This is the alignment that makes the pivot read. The brake bleeds a full
    run down through the plant, and the hold covers exactly that many frames,
    so the fighter spends the hold visibly shedding speed and arrives at the
    facing flip standing still. Stretching the hold over the whole reversal
    leaves the sprite travelling one way and looking the other at 90% of top
    speed, which reads worse than no pivot at all.

    Looped to the end of the hold rather than for a fixed count of frames: the
    length is what ``BRAKE_CONTROL`` sets, and this is about the *end* landing
    on the plant, not about how many frames that takes.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    speeds: list[float] = []
    for _ in range(int(Turn.DELAY_S / TICK) + 4):
        _run(player, input_manager, frames=1, axis=-1.0)
        speeds.append(abs(player.velocity.x))
        if _state(player) != PlayerState.TURN.value:
            break

    held = speeds[:-1]
    assert all(b < a for a, b in pairwise(held)), (
        f"the hold should be shedding speed every frame, got {held}"
    )
    assert len(held) >= 4, "and that shedding has to last long enough to be seen"

    # The frame the facing flips on is the frame the plant lands, so the check
    # is on the velocity at the *end* of the hold rather than on the last frame
    # strictly inside it -- which is necessarily a shade above the plant,
    # because it is the frame the plant is reached on.
    assert abs(player.velocity.x) <= Turn.PLANT_PX_S, "the flip lands at the plant"
    assert player.facing_right is False, "the flip lands as the push begins"
    assert player.turn_ratio == 0.0, "and the lean is over with it"


def test_the_fighter_keeps_moving_through_the_hold() -> None:
    """A pivot that stopped the fighter would be a pose, not a turn.

    He does slow almost to a stop -- that is the point of the brake -- but he
    never freezes, so the reversal reads as the same fighter continuing in
    another direction rather than as a pause followed by a new movement.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=3, axis=-1.0)

    assert _state(player) == PlayerState.TURN.value
    assert player.velocity.x > 0.0, "still bleeding off, not planted yet"
    assert player.velocity.x < player.speed * 0.75


def test_the_hold_is_released_into_the_new_facing() -> None:
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=1, axis=-1.0)
    assert player.facing_right is True

    _run(player, input_manager, frames=int(Turn.DELAY_S / TICK) + 2, axis=-1.0)

    assert player.facing_right is False
    assert _state(player) != PlayerState.TURN.value


def test_a_pivot_to_the_left_is_held_too() -> None:
    """The effect is symmetric; testing one direction proves half of it."""
    input_manager = InputManager()
    player = _player(input_manager)
    player.facing_right = False
    _run_at_full_speed(player, input_manager, -1.0)

    _run(player, input_manager, frames=1, axis=1.0)

    assert _state(player) == PlayerState.TURN.value
    assert player.facing_right is False


def test_a_held_key_does_not_re_enter_after_the_hold_lands() -> None:
    """Once the facing has caught up there is nothing left to announce.

    The steady ``face_movement`` asking for the direction the fighter is now
    travelling must not start a second pivot, or the fighter settles into a
    loop of mirrored and unmirrored instead of running.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=int(Turn.DELAY_S / TICK) + 4, axis=-1.0)
    assert player.facing_right is False

    _run(player, input_manager, frames=8, axis=-1.0)

    assert _state(player) != PlayerState.TURN.value
    assert player.turn_ratio == 0.0


# --- The four ways not to ---------------------------------------------------


def test_a_turn_from_a_standstill_mirrors_immediately() -> None:
    """No momentum to announce, and no state to enter."""
    input_manager = InputManager()
    player = _player(input_manager)
    player.facing_right = True
    _run(player, input_manager, frames=2, axis=0.0)
    assert player.velocity.x == 0.0

    _run(player, input_manager, frames=1, axis=-1.0)

    assert _state(player) != PlayerState.TURN.value
    assert player.facing_right is False


def test_an_airborne_reversal_mirrors_immediately() -> None:
    """A mid-air flip is a jump turn, and the arc already reads it."""
    input_manager = InputManager()
    player = _player(input_manager)
    player.facing_right = True
    _run(player, input_manager, frames=30, axis=1.0)

    player.on_surface["floor"] = False
    input_manager.apply_remote_state(InputState(move_axis=-1.0))
    player.update(TICK)

    assert _state(player) != PlayerState.TURN.value
    assert player.facing_right is False


def test_a_guard_walk_pivot_is_still_announced() -> None:
    """The threshold sits below a guard walk, or the common case skips it.

    ``Guard.MOVE_MULT`` is 0.35 of top speed, so a fighter easing out of a
    block is the slowest thing genuinely travelling -- and the case the effect
    is tuned for.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    player.velocity.x = Turn.MIN_SPEED_PX_S + 5.0
    player.right_held = False
    player.left_held = False

    _run(player, input_manager, frames=1, axis=-1.0)

    assert _state(player) == PlayerState.TURN.value


def test_no_input_is_not_a_reversal() -> None:
    """Letting go of the stick must not start a pivot."""
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=1, axis=0.0)

    assert _state(player) != PlayerState.TURN.value
    assert player.facing_right is True


# --- Interrupts -------------------------------------------------------------


def test_an_attack_inside_the_hold_commes_out_the_new_way() -> None:
    """The regression this exists to prevent: an attack swinging backwards.

    ``PlayerAttackState.enter`` reads the facing to pick its side. Because the
    pivot is a state, the attack leaves it through ``exit``, which is where the
    facing is committed -- so no reader of the facing has to know the hold
    exists.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=2, axis=-1.0, attack=True)

    assert _state(player) == PlayerState.ATTACK.value
    assert player.facing_right is False, "the attack committed the pivot"
    assert player.velocity.x < 0.0, "and it lunged where the player is pointing"


def test_the_pivot_does_not_cost_the_player_a_move() -> None:
    """Two hundred milliseconds of lean must not take a button away.

    Crouch is the one that would: its gate enumerates the states it may be
    entered from, so a state nobody added is a state where the player cannot
    crouch.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=1, axis=-1.0, down=True)

    assert _state(player) in (PlayerState.TURN.value, PlayerState.CROUCH.value)
    if _state(player) == PlayerState.TURN.value:
        _run(player, input_manager, frames=1, axis=-1.0, down=True)
        assert _state(player) == PlayerState.CROUCH.value


def test_a_jump_inside_the_hold_still_turns_the_fighter() -> None:
    """Leaving for the air is an exit, so the facing has to land there too."""
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=1, axis=-1.0)
    assert _state(player) == PlayerState.TURN.value

    player.jump.buffer_press()
    _run(player, input_manager, frames=2, axis=-1.0)

    assert player.facing_right is False


# --- Cancelling -------------------------------------------------------------


def test_a_feint_cancels_the_pivot() -> None:
    """Pointing back at the held facing abandons the turn.

    Chaining two reversals is a feint, and answering it with a turn the player
    dropped is how a pivot becomes input lag.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=1, axis=-1.0)
    assert _state(player) == PlayerState.TURN.value

    _run(player, input_manager, frames=2, axis=1.0)

    assert _state(player) != PlayerState.TURN.value
    assert player.facing_right is True, "the abandoned pivot must not commit"


def test_releasing_the_stick_mid_pivot_still_turns() -> None:
    """Letting go is coming to a stop, and stopping facing the old way is wrong.

    The cancelled case is a *reversal* back, not a release.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=1, axis=-1.0)

    _run(player, input_manager, frames=int(Turn.DELAY_S / TICK) + 2, axis=0.0)

    assert player.facing_right is False


# --- The ratio the renderer reads -------------------------------------------


def test_the_ratio_falls_to_zero_exactly_as_the_facing_lands() -> None:
    """The offset reaching zero on the flip tick is what makes the flip land
    with nothing to correct.

    If the ratio outlived the state, the sprite would finish the pivot still
    dragged sideways, and the correction would read as the sprite settling
    after the turn rather than as part of it.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=1, axis=-1.0)
    assert player.turn_ratio > 0.0

    _run(player, input_manager, frames=int(Turn.DELAY_S / TICK) + 2, axis=-1.0)

    assert player.turn_ratio == 0.0
    assert player.facing_right is False


def test_the_ratio_is_cleared_by_every_exit() -> None:
    """An attack leaves through ``exit`` too, and the hint goes with it."""
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    _run(player, input_manager, frames=2, axis=-1.0, attack=True)

    assert player.turn_ratio == 0.0


def test_a_fighter_who_is_not_pivoting_reports_nothing() -> None:
    input_manager = InputManager()
    player = _player(input_manager)
    _run(player, input_manager, frames=4)

    assert player.turn_ratio == 0.0
    assert turn_offset_px(player) == 0.0
    assert turn_skew_px(player) == 0.0


def test_the_offset_keeps_one_sign_for_the_whole_hold() -> None:
    """The offset never reverses mid-hold, whatever the velocity is doing.

    Signing the offset off the live ``velocity.x`` looks equivalent and is not:
    the brake aims at zero, so the velocity *does* cross zero underneath the
    hold, and the sprite would jump the width of the effect in a single frame
    at the crossing. The held facing does not move for the duration, so that is
    what the sign is read from.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)

    offsets: list[float] = []
    for _ in range(int(Turn.DELAY_S / TICK)):
        _run(player, input_manager, frames=1, axis=-1.0)
        offsets.append(turn_offset_px(player))

    assert all(o < 0.0 for o in offsets), f"the offset changed sign mid-hold: {offsets}"
    assert offsets == sorted(offsets), "and it should only shrink toward zero"
    assert offsets[0] < 0.0, "starting off-axis, so the flip has nothing to correct"


def test_the_offset_and_the_lean_share_a_direction() -> None:
    """The figure is dragged as one piece, not slid one way and leaned another."""
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=1, axis=-1.0)

    offset = turn_offset_px(player)
    skew = turn_skew_px(player)
    assert offset != 0.0 and skew != 0.0
    assert (offset > 0) == (skew > 0)
    assert abs(skew) < abs(offset), "the feet lead the head"


# --- Rolling back -----------------------------------------------------------


def test_a_snapshot_carries_the_pivot_mid_hold() -> None:
    """The hold is state, so the rollback snapshot carries it for free.

    ``StateMachine.save_state`` captures every state's scalars, so ``timer``,
    ``held`` and ``target`` come along without the entity knowing anything
    about them. The test is here to prove that rather than to document it: if
    the state ever grew a non-scalar runtime field, the rollback would silently
    stop being complete and nothing else would notice.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=2, axis=-1.0)
    assert _state(player) == PlayerState.TURN.value
    turn_state = player.state_machine.states[PlayerState.TURN.value]
    snapshot = player.save_state()

    _run(player, input_manager, frames=int(Turn.DELAY_S / TICK) + 3, axis=-1.0)
    assert player.facing_right is False

    player.load_state(snapshot)

    assert _state(player) == PlayerState.TURN.value
    assert turn_state.timer > 0.0
    assert turn_state.target is False
    assert player.facing_right is True


def test_the_state_is_registered_and_reachable() -> None:
    """A state nobody registers is a class, not a state."""
    player = _player()
    sm = player.state_machine
    assert isinstance(sm, StateMachine)
    assert PlayerState.TURN.value in sm.states
    assert PlayerState.TURN.value in FootstepDust.TIER, "and it marks the floor"


# --- request_turn directly, for the gate -----------------------------------


def test_request_turn_declines_under_the_speed_floor() -> None:
    """The gate itself, with no state machine in the way.

    ``request_turn`` is the whole decision, and it is asked from the input read
    because that runs before the state machine -- a decision taken from a
    state's own update would be a frame too late to stop the mirror.
    """
    player = _player()
    player.on_surface["floor"] = True
    player.facing_right = True
    player.move_axis = -1.0
    player.velocity.x = Turn.MIN_SPEED_PX_S - 1.0

    assert request_turn(player) is False
    assert _state(player) != PlayerState.TURN.value


def test_the_pivot_is_switched_off_at_zero_delay() -> None:
    """A delay of 0 is the legacy behaviour, not a zero-length pivot.

    Set on the player, not on ``settings.Turn``: the fighter's own attribute is
    what ``request_turn`` reads, so patching the settings block would leave the
    player untouched and the test would pass for the wrong reason.
    """
    player = _player()
    player.on_surface["floor"] = True
    player.facing_right = True
    player.move_axis = -1.0
    player.velocity.x = 300.0
    player.turn_delay_s = 0.0

    assert request_turn(player) is False
    assert _state(player) != PlayerState.TURN.value


def test_a_fighter_that_opts_out_takes_neither_half() -> None:
    """One flag, both halves -- and this is the reason it is one flag.

    ``apply_horizontal_movement`` is shared by every fighter, so a flag that
    gated only the facing hold would leave the plant running on enemies: they
    would stop and push differently while never being turned around. This is
    the test that says opting out means opting out of the whole thing.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    before = player.velocity.x

    player.turn_enabled = False
    _run(player, input_manager, frames=3, axis=-1.0)

    assert _state(player) != PlayerState.TURN.value
    assert player.facing_right is False, "the mirror happens the same frame, as before"

    # The legacy single-rate curve, all three ticks: one exponential ease
    # straight at the target, crossing zero on the second.
    alpha = 1.0 - math.exp(-25.0 * TICK)
    legacy = before
    for _ in range(3):
        legacy += (-player.speed - legacy) * alpha
    assert player.velocity.x == pytest.approx(legacy, rel=1e-6), "no plant on the way"
    assert legacy < 0.0, "which is exactly the old too-snap crossing"


def test_the_facing_tag_is_what_holds_the_mirror() -> None:
    """Without the tag, the very next tick re-mirrors and cancels the pivot.

    This is the mechanism, stated once. ``face_movement`` runs in
    ``_pre_update``, before the state machine, so the only thing that can stop
    it is a question it asks the machine. The real order is used here:
    ``request_turn`` enters the state *instead of* calling ``face_movement``,
    and from then on the tag keeps it from calling it again.
    """
    player = _player()
    player.facing_right = True
    player.move_axis = -1.0
    player.on_surface["floor"] = True
    player.velocity.x = 300.0

    assert request_turn(player) is True
    assert player.state_machine.has_tag("facing_locked")

    player.face_movement()
    assert player.facing_right is True, "the mirror is held while the state lasts"

    player.state_machine.change_state(PlayerState.RUN)
    player.face_movement()
    assert player.facing_right is False, "and released with it"


# --- Drawing it -------------------------------------------------------------


def _block(width: int = 40, height: int = 56) -> pygame.Surface:
    """A solid rectangle, so a row can be located by scanning it."""
    block = pygame.Surface((width, height), pygame.SRCALPHA)
    block.fill((200, 60, 60, 255))
    return block


def _opaque_span(surface: pygame.Surface, y: int) -> tuple[int, int]:
    xs = [x for x in range(surface.get_width()) if surface.get_at((x, y))[3] > 0]
    assert xs, "the probe row is fully transparent"
    return xs[0], xs[-1]


def _blit_and_measure(image: pygame.Surface, rect: pygame.Rect):
    """Blit onto a scratch surface and report where the feet and head landed."""
    target = pygame.Surface((400, 400), pygame.SRCALPHA)
    target.fill((0, 0, 0, 0))
    target.blit(image, rect)
    return (
        _opaque_span(target, rect.y),
        _opaque_span(target, rect.y + rect.height - 1),
    )


def test_the_lean_keeps_the_feet_on_the_floor() -> None:
    """A pivot is a fighter turning on planted feet.

    Every row lands the same width, so the shear has to move the top and leave
    the bottom exactly where they were. A shear that moved the feet too would
    be a rotation, and at this amplitude the fighter appears to skid off its
    own hitbox.
    """
    for skew in (Turn.SKEW_PX, -Turn.SKEW_PX):
        _surface, rect = turn_frame(_block(), pygame.Rect(100, 200, 40, 56), 0.0, skew)
        top, bottom = _blit_and_measure(_sheared(_block(), int(skew)), rect)

        assert bottom[0] == 100, f"the feet moved on a {skew:+.0f}px lean"
        assert bottom[1] - bottom[0] == 39
        assert top != bottom, f"the {skew:+.0f}px lean did not lean anything"


def test_the_lean_goes_the_way_the_body_is_dragged() -> None:
    """Signed like the offset, so the figure is thrown as one piece.

    Everything comes back from :func:`turn_frame` on purpose. Asking
    ``_sheared`` for one skew and ``turn_frame`` for another builds a surface
    and a rect that disagree by a pixel, which is the kind of test that passes
    on the code it was written against and lies about the code after it.
    """
    right_surface, right_rect = turn_frame(_block(), pygame.Rect(100, 200, 40, 56), 0.0, 9.0)
    left_surface, left_rect = turn_frame(_block(), pygame.Rect(100, 200, 40, 56), 0.0, -9.0)
    right_top, right_feet = _blit_and_measure(right_surface, right_rect)
    left_top, left_feet = _blit_and_measure(left_surface, left_rect)

    assert right_feet == left_feet == (100, 139), "both feet stay planted"
    assert right_top[0] > right_feet[0], "a right lean carries the head right"
    assert left_top[0] < left_feet[0], "and a left lean carries it left"


def test_a_lean_widens_the_blit_rect_so_the_feet_are_not_cropped() -> None:
    """``blit`` crops to the rect, so a stale width would eat the bottom row.

    The shear returns something wider than the source by exactly the lean.
    Handing ``blit`` the original width crops the feet off the pivot, which is
    the one part of the fighter that has to stay put -- and it is silent: the
    sprite just comes out shorter.
    """
    _surf, rect = turn_frame(_block(), pygame.Rect(100, 200, 40, 56), 0.0, 9.0)

    assert rect.width > 40, "wide enough for the whole sheared surface"
    assert rect.height == 56


def test_a_one_pixel_lean_is_not_flattened_away() -> None:
    """The quantisation rounds *away from* zero, not towards it.

    Rounding to a multiple of two by truncation would turn a 1px lean into no
    lean at all, which looks like the quantisation being honoured while quietly
    deleting the smallest tilts it was introduced to keep.
    """
    from src.core.rendering.renderer import SKEW_STEP, _quantize_skew

    assert _quantize_skew(1) != 0
    assert _quantize_skew(-1) != 0
    assert _quantize_skew(0) == 0
    assert _quantize_skew(3) % SKEW_STEP == 0
    assert _quantize_skew(-3) % SKEW_STEP == 0


def test_the_shear_cache_survives_repeated_pivots() -> None:
    """The rebuild rate, which is the thing the cache exists to keep low.

    The lean is driven by a ratio that changes every frame, so a pivot wants
    its own integer lean on every frame. Keyed exactly, that is twenty-one
    entries per animation frame, and two or three frames of the run sheet in
    play is enough to overflow the cache -- which then wiped itself and rebuilt
    from scratch forever, at a measured hundred percent rebuild rate. The
    quantisation is what keeps the working set inside the cap.

    Two animation frames is what a real pivot sees: 140ms of a sheet playing at
    12.5 frames a second. The rate is asserted rather than the working set,
    because the rate is the property that matters and a bound on a count would
    only say the cache is big enough today.
    """
    from src.core.rendering.renderer import _SHEAR_CACHE, _quantize_skew, _sheared

    sources = [pygame.Surface((40, 56), pygame.SRCALPHA) for _ in range(2)]
    for surface in sources:
        surface.fill((200, 60, 60, 255))

    def ramp(pivot: int) -> int:
        return _quantize_skew(int(round(Turn.SKEW_PX * (1.0 - (pivot % 12) / 12.0))))

    _SHEAR_CACHE.clear()
    builds = 0
    frames = 30 * 12
    for pivot in range(30):
        for tick in range(12):
            source = sources[(pivot + tick) % len(sources)]
            key = (id(source), ramp(tick))
            if key not in _SHEAR_CACHE:
                builds += 1
                _sheared(source, key[1])

    assert builds / frames < 0.1, (
        f"{builds} rebuilds over {frames} frames: the cache is not holding, "
        "so the pivot pays for a fresh shear every frame forever"
    )


def test_the_lean_ramps_down_without_jumping_straight_to_zero() -> None:
    """A pivot with no lean at its start reads as no pivot at all.

    The quantisation costs resolution, so the thing it must not cost is the
    shape: still a ramp from most to least, never a cliff to nothing.
    """
    from src.core.rendering.renderer import _quantize_skew

    ramp = [_quantize_skew(int(round(Turn.SKEW_PX * (1.0 - tick / 12.0)))) for tick in range(12)]

    assert ramp[0] == Turn.SKEW_PX, "the lean starts at its maximum"
    assert all(a >= b for a, b in pairwise(ramp)), f"ramp: {ramp}"
    assert len(set(ramp)) >= 4, f"enough distinct leans to read as a ramp: {ramp}"
    assert ramp[-1] > 0


def test_turn_frame_without_a_lean_is_a_pure_slide() -> None:
    image = _block()
    returned, moved = turn_frame(image, pygame.Rect(100, 200, 40, 56), 6.0)

    assert returned is image, "a slide is a position, not a new frame"
    assert (moved.width, moved.height) == (40, 56)
    assert moved.x == 106


def test_turn_frame_at_nothing_returns_the_rect_untouched() -> None:
    image = _block()
    rect = pygame.Rect(100, 200, 40, 56)

    returned, moved = turn_frame(image, rect, 0.0)

    assert returned is image
    assert moved == rect


def test_a_pivot_does_not_distort_the_hitbox() -> None:
    """The offset and the lean are drawing instructions, and must stay ones.

    The renderer is handed a *screen* rect and returns another one; the
    simulation's ``hitbox`` is never an argument to it. So the invariant is not
    "the y does not move" -- gravity owns y -- but that the fighter's box is
    the same shape throughout, since a shear is exactly the kind of change that
    would resize one.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    size = (player.hitbox.width, player.hitbox.height)

    _run(player, input_manager, frames=4, axis=-1.0)

    assert turn_offset_px(player) != 0.0
    assert (player.hitbox.width, player.hitbox.height) == size


def test_the_renderer_resolves_the_pivoting_fighter_once() -> None:
    """The blit loop resolves it by identity, like the dash."""
    from src.core.sprite_groups import SpriteGroups

    surface = pygame.Surface((64, 64))
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    player = _player()
    groups.all_sprites.add(player)
    groups.entity_sprites.add(player)
    player.turn_ratio = 0.5

    renderer.draw(groups, dt=TICK)

    assert renderer._turning_player is player


def test_a_flash_lands_on_the_pivoting_body_and_not_where_it_was() -> None:
    """The wash is drawn from the rect, so it has to take the offset too.

    A hit landed during a pivot is exactly when the flash fires, and one left
    at the un-offset position is a silhouette of a fighter who is not there.
    """
    from src.core.sprite_groups import SpriteGroups

    surface = pygame.Surface((64, 64))
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    player = _player()
    player.hitbox.topleft = (10.0, 10.0)
    player.sync_rects()
    groups.all_sprites.add(player)
    groups.entity_sprites.add(player)
    player.flash_timer = 0.05
    player.facing_right = True
    player.turn_ratio = 0.5

    renderer.draw(groups, dt=TICK)
    flashed = renderer._collect_flashes(groups)

    assert len(flashed) == 1
    _, flashed_rect = flashed[0]
    _, still_rect = turn_frame(player.image, camera.apply_snapped(player.rect), 0.0, 0.0)
    assert flashed_rect.x - still_rect.x < 0, "the wash is dragged with the body"


# --- Availability across every fighter --------------------------------------


def test_every_machine_registers_the_pivot_under_the_same_name() -> None:
    """Availability is global; activation is not.

    Both machines register the state, so "the pivot is available to every
    fighter" is a structural fact rather than a thing the player's machine
    happens to have. The shared name is what lets ``request_turn`` be one
    function: if the two enums drifted apart it would still look right from the
    player and simply never fire for an enemy.
    """
    enemy = _enemy("goblin")
    fighter = _player()

    assert PlayerState.TURN.value == Turn.STATE
    assert Turn.STATE in fighter.state_machine.states
    assert Turn.STATE in enemy.state_machine.states


def test_a_fighter_can_opt_in_and_out_at_runtime() -> None:
    """The flag is the user's switch, and both positions are legal.

    Nothing about it is baked into a subclass: the same enemy instance is asked
    for the pivot above and refused below, which is the difference between
    "available" and "enabled".
    """
    enemy = _enemy("goblin")
    enemy.on_surface["floor"] = True
    enemy.move_axis = -1.0
    enemy.facing_right = True
    enemy.velocity.x = 300.0

    assert enemy.turn_enabled is False, "off unless a fighter opts in"
    assert request_turn(enemy) is False

    enemy.turn_enabled = True
    assert request_turn(enemy) is True
    assert enemy.state_machine.current_state_name == Turn.STATE


def test_the_knobs_are_per_fighter_and_default_from_settings() -> None:
    """A goblin and a boss should not turn like each other."""
    enemy = _enemy("goblin")
    fighter = _player()

    for attribute, default in (
        ("turn_delay_s", Turn.DELAY_S),
        ("turn_brake_control", Turn.BRAKE_CONTROL),
        ("turn_plant_px_s", Turn.PLANT_PX_S),
        ("turn_min_speed_px_s", Turn.MIN_SPEED_PX_S),
    ):
        assert getattr(fighter, attribute) == default, attribute
        assert getattr(enemy, attribute) == default, attribute

    enemy.turn_delay_s = 0.4
    enemy.turn_brake_control = 9.0
    assert fighter.turn_delay_s == Turn.DELAY_S, "one fighter does not move the other"


def test_a_machine_without_the_pivot_reports_that_nothing_was_entered() -> None:
    """Asking is not entering.

    A fighter with no AI has the null machine, whose ``change_state`` does
    nothing. Reporting "entered" there would tell the caller a hold is running
    when no state is, so the answer is read back off the machine.
    """
    dummy = _enemy("dummy")
    dummy.turn_enabled = True
    dummy.on_surface["floor"] = True
    dummy.move_axis = -1.0
    dummy.facing_right = True
    dummy.velocity.x = 300.0

    assert request_turn(dummy) is False


def test_an_enemy_pivots_when_it_opts_in() -> None:
    """The whole point of registering it in the enemy machine.

    An enemy reaching the end of its patrol beat is a reversal exactly as a
    stick reversal is for the player, and it is the one that reads well: the
    fighter is already turning and nothing about it announces the change.
    """
    from src.states.enemy_states import EnemyState  # noqa: F401

    enemy = _enemy("goblin")
    enemy.turn_enabled = True
    enemy.on_surface["floor"] = True
    enemy.patrol_speed = 200.0
    # Facing right while the axis asks for left. Setting the facing outright
    # rather than flipping it: a pivot needs the two to disagree, and
    # ``turn_around`` would have made them agree.
    enemy.facing_right = True
    enemy.move_axis = -1.0
    enemy.velocity.x = 200.0

    assert request_turn(enemy) is True
    assert enemy.state_machine.current_state_name == EnemyState.TURN.value

    # The hold runs, and it comes back out pointing the other way. Stopped the
    # moment it is over: the enemy's *next* state does its own facing, and a
    # ledge probe turns it round again -- which would make this assert against
    # a decision the pivot never made.
    for _ in range(int(enemy.turn_delay_s / TICK) + 3):
        if enemy.state_machine.current_state_name != Turn.STATE:
            break
        enemy.velocity.y = 0.0
        enemy.on_surface["floor"] = True
        enemy.state_machine.update(TICK)

    assert enemy.state_machine.current_state_name != Turn.STATE
    assert enemy.facing_right is False, "the pivot committed on the way out"
    assert enemy.turn_ratio == 0.0


# --- Leaving the hold early -------------------------------------------------


def test_walking_off_a_ledge_mid_pivot_goes_to_fall() -> None:
    """The pivot is a ground effect, and a fighter can be pulled off the floor
    in the middle of one -- by a platform moving out from under him, or a
    shove.

    Leaving the hold is the right answer and it is not the timer's: the hold
    assumes there is a floor to plant on, and there no longer is. The facing is
    still committed on the way out, so he does not fall off a ledge looking the
    way he came from.
    """
    input_manager = InputManager()
    player = _player(input_manager)
    _run_at_full_speed(player, input_manager, 1.0)
    _run(player, input_manager, frames=2, axis=-1.0)
    assert _state(player) == PlayerState.TURN.value

    # Driven by hand rather than through ``_run``, which asserts a floor on
    # every tick -- which is exactly what this test is taking away.
    input_manager.apply_remote_state(InputState(move_axis=-1.0))
    player.on_surface["floor"] = False
    player.update(TICK)

    assert _state(player) == PlayerState.FALL.value
    assert player.facing_right is False, "the pivot still committed"
    assert player.turn_ratio == 0.0


def test_an_enemy_that_loses_the_floor_just_resumes() -> None:
    """An enemy has no ``fall`` state to be sent to.

    Its whole air vocabulary is nothing, so dropping the hold *is* the answer,
    and it must not raise looking for a state that does not exist.
    """
    enemy = _enemy("goblin")
    enemy.turn_enabled = True
    enemy.on_surface["floor"] = True
    enemy.patrol_speed = 200.0
    enemy.facing_right = True
    enemy.move_axis = -1.0
    enemy.velocity.x = 200.0
    assert request_turn(enemy) is True

    enemy.on_surface["floor"] = False
    enemy.state_machine.update(TICK)

    assert enemy.state_machine.current_state_name not in (Turn.STATE, None)
    assert enemy.facing_right is False


def test_the_shared_body_refuses_to_run_on_its_own() -> None:
    """``TurnState`` is not a state -- it cannot answer "back to what".

    Both fighters implement :meth:`resume_state` and nothing else, so this is
    the one place the contract is enforced. Without it, a third fighter would
    silently get a ``NotImplementedError`` from wherever the hold happened to
    end rather than from the class that forgot the method.
    """
    from src.states.turn_state import TurnState

    class Unfinished(TurnState):
        """A pivot whose author forgot where the fighter goes afterwards."""

    with pytest.raises(NotImplementedError):
        Unfinished(_player()).resume_state()
