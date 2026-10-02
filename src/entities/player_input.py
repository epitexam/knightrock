"""Player input reading extracted from ``Player`` (audit F1.1, Phase 2 #3).

``Player`` used to concentrate keyboard/gamepad reading (axes, jump/dash
buffers, charge attacks and combos) on top of physics, states and combat.
:class:`PlayerInputHandler` takes over that single responsibility: it reads
the :class:`InputManager` every tick and drives the controllers + the combat
component.  ``Player`` only keeps orchestration (``_pre_update``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.combat.frame_data import MoveId
from src.core.input.input_actions import InputAction
from src.core.settings import GameFeel
from src.core.settings import Input as InputSettings
from src.entities.attack_moves import move_for_button
from src.physics.movement import apply_jump_cut
from src.states.turn_state import request_turn

if TYPE_CHECKING:
    from src.entities.player import Player

#: The attack buttons, in the order they are considered.
#:
#: The order is the contract of :meth:`PlayerInputHandler._handle_attack_request`:
#: a tick can only start one attack, so the first button pressed wins. It was
#: implicit in the branch order of an ``if``/``elif`` ladder and pinned by a test
#: that scraped the source text; naming it states the same thing without the
#: scraping. SPECIAL first, then the numbered attacks in order, so a light does
#: not eat a heavy thrown on the same tick.
#:
#: Step 4 of the spine refactor replaces this with a lookup into the move table
#: declared in ``player.json``; it stays here until then.
ATTACK_BUTTONS: tuple[InputAction, ...] = (
    InputAction.SPECIAL_ATTACK,
    InputAction.ATTACK_1,
    InputAction.ATTACK_2,
    InputAction.ATTACK_3,
    InputAction.ATTACK_4,
)


class PlayerInputHandler:
    """Reads every input each tick and drives abilities and attacks."""

    def __init__(self, player: Player) -> None:
        self._player = player
        self.buffered_attack_name: MoveId | None = None

    def update(self) -> None:
        """Read movement/ability input, then process attack input."""
        self._read_input()
        self._handle_attack_input()

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

        if im.just_pressed(InputAction.RESET):
            player.reset_position()

    def _handle_attack_input(self) -> None:
        """Process attack input with charge attacks, buffering, and combos."""
        if self._handle_charging():
            return
        self._handle_attack_request()

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

    def _handle_attack_request(self) -> None:
        """Start the highest-priority attack button that was pressed this tick.

        No gate here: every "can I attack" question is answered by
        ``CombatComponent.start_attack``, which is the only place that knows
        about cooldowns, cancellations, the fighter's state and its posture. A
        gate in front of it would be a second answer to the same question, and
        the two are exactly what used to drift apart.
        """
        player = self._player
        for action in ATTACK_BUTTONS:
            if not player.input_manager.just_pressed(action):
                continue
            self._start(action)
            return

    def _start(self, action: InputAction) -> None:
        """Throw the move bound to one button, or buffer it if it can be retried.

        The buffer is the reason the refusal has to be read rather than
        discarded: a press refused on cooldown is worth keeping, because the
        same press unchanged will work once the timer runs down. One refused
        because the fighter is in the wrong posture or is hurt is not -- keeping
        it would fire a move the player has long since stopped asking for.
        """
        player = self._player
        if not player.may_attack_now():
            return
        move = move_for_button(action, player.stance)
        if move is None:
            # Nothing on this button from here. Dropped without a buffer, and
            # without falling back to the standing version: a fighter who holds
            # Down and presses the uppercut gets nothing, rather than a
            # standing uppercut from a crouched collider.
            return

        if action is InputAction.ATTACK_2 and player.combat.start_charge(move):
            player.state_machine.change_state("charge", force=True)
            return

        refusal = player.combat.start_attack(move)
        if refusal.is_retryable:
            self.buffered_attack_name = move
            player.state_machine.buffer_input("attack", window=InputSettings.ATTACK_BUFFER_WINDOW)
