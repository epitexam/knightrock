"""The player's input, read once per tick: movement, stance, attacks and prompts.

While a prompt is up the fight is frozen around the player, so nothing but the
prompt is read: the directions it asks for, or the slash mashed in a blade
lock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.combat.frame_data import Stance
from src.core.input.input_actions import InputAction
from src.core.settings import Debug, GameFeel
from src.core.settings import Input as InputSettings
from src.entities.attack_moves import CHARGES, MoveContext, press_for, resolve_move
from src.entities.player_kit import Direction
from src.physics.movement import apply_jump_cut
from src.states.turn_state import request_turn

if TYPE_CHECKING:
    from src.entities.player import Player

#: The attack buttons, in the order they are considered: a tick starts one
#: attack, so the first in this order wins. The provider stores latches in a
#: set, so the order two presses arrived in is not available here; the
#: effective priority is SPECIAL > grab (ATTACK_2) > ATTACK_1 > ATTACK_2 > SHOOT.
ATTACK_BUTTONS: tuple[InputAction, ...] = (
    InputAction.ATTACK_1,
    InputAction.ATTACK_2,
    InputAction.SHOOT,
)


class PlayerInputHandler:
    """Reads every input each tick and drives movement, attacks and prompts."""

    def __init__(self, player: Player) -> None:
        self._player = player
        #: The attack button pressed and not yet played, the stance it was
        #: pressed in, and how long it is still worth playing. The *button*,
        #: not a move: the move is chosen when it fires, so a press made during
        #: one link of a chain becomes the next link once the first lets it
        #: through.
        self.buffered_action: InputAction | None = None
        self.buffered_low: bool = False
        self.buffer_timer: float = 0.0
        #: How long each attack button has been held, for the charge.
        self.held_for: dict[InputAction, float] = dict.fromkeys(ATTACK_BUTTONS, 0.0)
        #: The button whose charge is building, released to throw it.
        self.charge_button: InputAction | None = None
        #: The stick's side and Down on the last tick: a prompt reads a new push.
        self.last_axis: int = 0
        self.last_down: bool = False

    def update(self, delta_time: float = 1 / 60) -> None:
        """Read the prompt's input if one is up; movement and attacks otherwise."""
        directions = self._directions()
        if self._player.prompt.active:
            self._player.move_axis = 0.0
            self._feed_prompt(directions)
            return
        self._read_input()
        self._handle_attack_input(delta_time)

    def clear_buffer(self) -> None:
        """Forget a pending attack press."""
        self.buffered_action = None
        self.buffered_low = False
        self.buffer_timer = 0.0

    def _directions(self) -> list[Direction]:
        """The directions pushed this tick: a new side of the stick, Down, Up."""
        im = self._player.input_manager
        axis = im.axis(InputAction.MOVE_X)
        side = (
            1
            if axis > InputSettings.AXIS_DEADZONE
            else -1
            if axis < -InputSettings.AXIS_DEADZONE
            else 0
        )
        down = im.held(InputAction.MOVE_DOWN)
        pushed: list[Direction] = []
        if side != 0 and side != self.last_axis:
            pushed.append(Direction.RIGHT if side > 0 else Direction.LEFT)
        if down and not self.last_down:
            pushed.append(Direction.DOWN)
        if im.just_pressed(InputAction.MOVE_UP):
            pushed.append(Direction.UP)
        self.last_axis = side
        self.last_down = down
        return pushed

    def _feed_prompt(self, directions: list[Direction]) -> None:
        player = self._player
        for direction in directions:
            if not player.prompt.active:
                return
            player.answer_prompt(direction)
        if player.prompt.active and player.input_manager.just_pressed(InputAction.ATTACK_1):
            player.mash_prompt()

    def _read_input(self) -> None:
        """Read movement, guard, jump and dash, and face the stick."""
        player = self._player
        im = player.input_manager
        player.move_axis = im.axis(InputAction.MOVE_X)
        player.left_held = player.move_axis < -InputSettings.AXIS_DEADZONE
        player.right_held = player.move_axis > InputSettings.AXIS_DEADZONE
        player.down_held = im.held(InputAction.MOVE_DOWN)
        player.guard_held = im.held(InputAction.GUARD)
        player.fast_fall = player.down_held

        # A ground reversal enters the pivot state instead of mirroring, so the
        # facing is held while the feet are already rolling the other way.
        # Asked here, where the facing would otherwise be written: the input
        # read runs before the state machine, so a decision taken from a
        # state's own update would be a frame too late to stop the mirror.
        # The dash turns itself round (``PlayerDashState``): a ground pivot
        # entered from it would end the dash, its invincibility with it.
        if not player.is_dashing and not request_turn(player):
            player.face_movement()

        if im.just_pressed(InputAction.JUMP):
            player.jump.buffer_press()
        if im.just_released(InputAction.JUMP):
            apply_jump_cut(player, GameFeel.JUMP_CUT_DIVISOR)
        if im.just_pressed(InputAction.DASH):
            player.dash.request(player.move_axis)

        # A test-bench key: back to the spawn at full health. Debug builds only.
        if Debug.is_enabled() and im.just_pressed(InputAction.RESET):
            player.reset_position()

    def _handle_attack_input(self, delta_time: float) -> None:
        """The dark-side chord, then the charge, then the attack presses."""
        player = self._player
        im = player.input_manager
        if im.just_pressed(InputAction.SPECIAL_ATTACK):
            player.fury.start_dark()
            self.clear_buffer()
            return
        for button in ATTACK_BUTTONS:
            self.held_for[button] = self.held_for[button] + delta_time if im.held(button) else 0.0
        if self._handle_charging():
            return
        if im.just_pressed(InputAction.ATTACK_2) and player.try_grab():
            self.clear_buffer()
            return
        self._handle_attack_request(delta_time)
        self._maybe_start_charge()

    def _handle_charging(self) -> bool:
        """Hold a charge while its button is; let it go, a full one as its stronger move."""
        player = self._player
        charging = player.combat.charging
        if not charging.is_charging:
            self.charge_button = None
            return False
        if player.combat.is_hurt:
            charging.cancel()
            self.charge_button = None
            return True
        button = self.charge_button
        released = button is None or not player.input_manager.held(button)
        if released or (player.battery.is_empty and button is not InputAction.ATTACK_2):
            full = None if button is None else CHARGES[button].full
            player.combat.release_charge(full)
            self.charge_button = None
        return True

    def _maybe_start_charge(self) -> None:
        """A button held past ``CHARGE_DELAY`` with nothing running starts its charge.

        The blade and the shot draw on the battery, so an empty one charges
        neither; the body needs nothing.
        """
        player = self._player
        if player.combat.is_attacking or player.stance is not Stance.GROUND:
            return
        for button in ATTACK_BUTTONS:
            if self.held_for[button] < InputSettings.CHARGE_DELAY:
                continue
            if player.battery.is_empty and button is not InputAction.ATTACK_2:
                continue
            if player.combat.start_charge(CHARGES[button].move):
                self.charge_button = button
                # Charging short-circuits _handle_attack_request until release,
                # so a press buffered on this very tick would freeze here and
                # fire as a ghost attack afterwards.
                self.clear_buffer()
                player.state_machine.change_state("charge", force=True)
            return

    def _handle_attack_request(self, delta_time: float) -> None:
        """Buffer the attack button pressed this tick, then try to play the buffer.

        Every "can I attack" question is answered by
        ``CombatComponent.start_attack``. A press it refuses for a reason that
        will pass -- a cancel window not open yet -- stays buffered for
        ``ATTACK_BUFFER_WINDOW`` and is tried again every tick.
        """
        player = self._player
        pressed = next(
            (action for action in ATTACK_BUTTONS if player.input_manager.just_pressed(action)),
            None,
        )
        if pressed is not None:
            self.buffered_action = pressed
            self.buffered_low = player.low_stance
            self.buffer_timer = InputSettings.ATTACK_BUFFER_WINDOW
        elif self.buffered_action is not None:
            self.buffer_timer -= delta_time
            if self.buffer_timer <= 0.0:
                self.clear_buffer()
        if self.buffered_action is not None and not self._start(
            self.buffered_action, self.buffered_low
        ):
            return
        self.clear_buffer()

    def _context(self) -> MoveContext:
        player = self._player
        combat = player.combat
        return MoveContext(
            stance=player.stance,
            running=combat.current_attack_def if combat.is_attacking else None,
            downed_in_reach=player.downed_in_reach() is not None,
            dashing=player.is_dashing or player.dash.in_coyote(),
        )

    def _start(self, action: InputAction, low: bool) -> bool:
        """Throw the move for one press now; ``False`` while it is worth retrying."""
        player = self._player
        if not player.may_attack_now():
            return False
        press = press_for(action, low)
        move = None if press is None else resolve_move(press, self._context())
        if move is None:
            return True
        refusal = player.start_move(move)
        return not refusal.is_retryable
