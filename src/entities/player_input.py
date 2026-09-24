"""Player input reading extracted from ``Player`` (audit F1.1, Phase 2 #3).

``Player`` used to concentrate keyboard/gamepad reading (axes, jump/dash
buffers, charge attacks and combos) on top of physics, states and combat.
:class:`PlayerInputHandler` takes over that single responsibility: it reads
the :class:`InputManager` every tick and drives the controllers + the combat
component.  ``Player`` only keeps orchestration (``_pre_update``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.input.input_actions import InputAction
from src.core.settings import GameFeel
from src.core.settings import Input as InputSettings
from src.physics.movement import apply_jump_cut

if TYPE_CHECKING:
    from src.entities.player import Player


class PlayerInputHandler:
    """Reads every input each tick and drives abilities and attacks."""

    def __init__(self, player: Player) -> None:
        self._player = player
        self.buffered_attack_name: str | None = None

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
        if not player.can_attack():
            player.combat.charging.cancel()
            return True
        if im.just_released(InputAction.ATTACK_2):
            player.combat.release_charge()
        return True

    def _handle_attack_request(self) -> None:
        player = self._player
        im = player.input_manager
        if not player.can_attack():
            return

        if im.just_pressed(InputAction.SPECIAL_ATTACK):
            player.combat.start_attack("special_attack")
            return

        if im.just_pressed(InputAction.ATTACK_1):
            attack_name = "light_attack" if player.on_surface["floor"] else "air_attack"
            if not player.combat.start_attack(attack_name):
                self.buffered_attack_name = attack_name
                player.state_machine.buffer_input(
                    "attack", window=InputSettings.ATTACK_BUFFER_WINDOW
                )
        elif im.just_pressed(InputAction.ATTACK_2):
            if player.combat.start_charge("heavy_attack"):
                player.state_machine.change_state("charge", force=True)
            else:
                player.combat.start_attack("heavy_attack")
        elif im.just_pressed(InputAction.ATTACK_3):
            player.combat.start_attack("uppercut")
        elif im.just_pressed(InputAction.ATTACK_4):
            player.combat.start_attack("dash_attack")
