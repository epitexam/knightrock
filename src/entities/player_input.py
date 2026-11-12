"""Player input reading extracted from ``Player``.

``Player`` used to concentrate keyboard/gamepad reading (axes, jump/dash
buffers, charge attacks and combos) on top of physics, states and combat.
:class:`PlayerInputHandler` takes over that single responsibility: it reads
the :class:`InputManager` every tick and drives the controllers + the combat
component.  ``Player`` only keeps orchestration (``_pre_update``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.combat.frame_data import Stance
from src.combat.refusal import Refusal
from src.core.input.input_actions import InputAction
from src.core.settings import Debug, GameFeel
from src.core.settings import Input as InputSettings
from src.entities.attack_moves import RIPOSTE, MoveContext, resolve_move
from src.physics.movement import apply_jump_cut
from src.states.turn_state import request_turn

if TYPE_CHECKING:
    from src.entities.player import Player

#: The attack buttons, in the order they are considered: a tick starts one
#: attack, so the first pressed wins. The special first, so a light does not eat
#: the special's chord.
ATTACK_BUTTONS: tuple[InputAction, ...] = (
    InputAction.SPECIAL_ATTACK,
    InputAction.ATTACK_1,
    InputAction.ATTACK_2,
)


class PlayerInputHandler:
    """Reads every input each tick and drives abilities and attacks."""

    def __init__(self, player: Player) -> None:
        self._player = player
        #: The attack button pressed and not yet played, and how long it is
        #: still worth playing. The *button*, not a move: the move is chosen
        #: when it fires, so a press made during the first link of a chain
        #: becomes the second link once the first lets it through.
        self.buffered_action: InputAction | None = None
        self.buffer_timer: float = 0.0

    def update(self, delta_time: float = 1 / 60) -> None:
        """Read movement/ability input, then process attack input."""
        self._read_input()
        self._handle_attack_input(delta_time)

    def clear_buffer(self) -> None:
        """Forget a pending attack press."""
        self.buffered_action = None
        self.buffer_timer = 0.0

    def _read_input(self) -> None:
        """Read all input and update facing direction and buffers."""
        player = self._player
        im = player.input_manager
        player.move_axis = im.axis(InputAction.MOVE_X)
        player.left_held = player.move_axis < -InputSettings.AXIS_DEADZONE
        player.right_held = player.move_axis > InputSettings.AXIS_DEADZONE
        player.guard_held = im.held(InputAction.GUARD)
        player.down_held = im.held(InputAction.MOVE_DOWN)
        player.fast_fall = player.down_held

        if im.just_pressed(InputAction.GUARD):
            player.guard.press()

        # A ground reversal enters the pivot state instead of mirroring, so the
        # facing is held while the feet are already rolling the other way.
        # This has to be asked here, where the facing would otherwise be
        # written: the input read runs before the state machine, so a decision
        # taken from a state's own update would be a frame too late to stop the
        # mirror it is meant to delay.
        if not request_turn(player):
            player.face_movement()

        if im.just_pressed(InputAction.JUMP):
            player.jump.buffer_press()

        if im.just_released(InputAction.JUMP):
            apply_jump_cut(player, GameFeel.JUMP_CUT_DIVISOR)

        if im.just_pressed(InputAction.DASH):
            player.dash.request(player.move_axis)

        # A test-bench key: it puts the player back at the spawn at full health,
        # which in a normal game is a free heal that never counts as a death
        # (audit C5). Only the debug build honours it.
        if Debug.is_enabled() and im.just_pressed(InputAction.RESET):
            player.reset_position()

    def _handle_attack_input(self, delta_time: float) -> None:
        """Process attack input with charge attacks, buffering, and combos."""
        if self._handle_charging():
            return
        self._handle_attack_request(delta_time)

    def _handle_charging(self) -> bool:
        player = self._player
        im = player.input_manager
        if not player.combat.charging.is_charging:
            return False
        # A charge is dropped when the fighter stops being able to use it, not
        # when a *press* would be refused. The old gate conflated the two, so a
        # fighter who charged while hurt had the charge cancelled by a condition
        # that had nothing to do with the charge.
        if player.combat.is_hurt:
            player.combat.charging.cancel()
            return True
        if im.just_released(InputAction.ATTACK_2):
            player.combat.release_charge()
        return True

    def _handle_attack_request(self, delta_time: float) -> None:
        """Buffer the attack button pressed this tick, then try to play the buffer.

        No gate here: every "can I attack" question is answered by
        ``CombatComponent.start_attack``, which is the only place that knows
        about cooldowns, cancellations, the fighter's state and its posture.
        A press it refuses for a reason that will pass -- a cooldown running
        out, a cancel window not open yet -- stays buffered for
        ``ATTACK_BUFFER_WINDOW`` and is tried again every tick, so a press made
        a little early during a chain is played the moment it can be.
        """
        player = self._player
        pressed = next(
            (action for action in ATTACK_BUTTONS if player.input_manager.just_pressed(action)),
            None,
        )
        if pressed is not None:
            self.buffered_action = pressed
            self.buffer_timer = InputSettings.ATTACK_BUFFER_WINDOW
        elif self.buffered_action is not None:
            self.buffer_timer -= delta_time
            if self.buffer_timer <= 0.0:
                self.clear_buffer()
        if self.buffered_action is not None and not self._start(self.buffered_action):
            return
        self.clear_buffer()

    def _context(self) -> MoveContext:
        player = self._player
        combat = player.combat
        return MoveContext(
            stance=player.stance,
            running=combat.current_attack_def if combat.is_attacking else None,
            dashing=player.is_dashing or player.dash.in_coyote(),
            diving=player.stance is Stance.AIR and player.down_held,
            riposte=player.guard.riposte_timer > 0.0 and combat.has_attack(RIPOSTE),
        )

    def _start(self, action: InputAction) -> bool:
        """Throw the move for one button now; ``False`` while it is worth retrying.

        ``True`` means the press is settled: it started, or it was refused for a
        reason that will not pass (wrong posture, hurt, nothing on the button).
        Keeping such a press would fire a move the player has long since
        stopped asking for.
        """
        player = self._player
        if not player.may_attack_now():
            return False
        move = resolve_move(action, self._context())
        if move is None:
            # Nothing on this button from here. Dropped, and without falling
            # back to the standing version: a fighter who holds Down gets the
            # crouching move or nothing.
            return True

        # Charge only on a button still held: a press played from the buffer may
        # have been released already, and a charge started then would wait for
        # a release that has come and gone -- and charge forever.
        if (
            action is InputAction.ATTACK_2
            and player.input_manager.held(InputAction.ATTACK_2)
            and player.combat.start_charge(move)
        ):
            player.state_machine.change_state("charge", force=True)
            return True

        refusal = player.combat.start_attack(move)
        if refusal is Refusal.NONE and move == RIPOSTE:
            player.guard.riposte_timer = 0.0  # one riposte per parry
        return not refusal.is_retryable
