"""Lecture d'input du joueur extraite de ``Player`` (audit F1.1, Phase 2 #3).

``Player`` concentrait la lecture du clavier/manette (axes, buffers de
saut/dash, attaques avec charge et combos) en plus de la physique, des
états et du combat.  :class:`PlayerInputHandler` reprend cette unique
responsabilité : il lit l':class:`InputManager` à chaque tick et pilote
les controllers + le composant combat.  ``Player`` ne fait plus que
l'orchestration (``_pre_update``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.settings import Input as InputSettings

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
        player.move_axis = im.move_axis
        player.left_held = im.left_held
        player.right_held = im.right_held
        player.block_held = im.block_held

        player.face_movement()

        if im.jump_just_pressed:
            player.jump.buffer_press()

        if im.dash_just_pressed:
            player.dash.request()

        if im.reset_just_pressed:
            player.reset_position()

    def _handle_attack_input(self) -> None:
        """Process attack input with charge attacks, buffering, and combos."""
        player = self._player
        im = player.input_manager

        if player.combat.charging.is_charging:
            if not player.can_attack():
                player.combat.charging.cancel()
                return
            if im.attack2_just_released:
                player.combat.release_charge()
            return

        if not player.can_attack():
            return

        if im.special_attack_just_pressed:
            player.combat.start_attack("special_attack")
            return

        if im.attack1_just_pressed:
            attack_name = "light_attack" if player.on_surface["floor"] else "air_attack"
            if not player.combat.start_attack(attack_name):
                self.buffered_attack_name = attack_name
                player.state_machine.buffer_input(
                    "attack", window=InputSettings.ATTACK_BUFFER_WINDOW
                )
        elif im.attack2_just_pressed:
            if player.combat.start_charge("heavy_attack"):
                player.state_machine.change_state("charge", force=True)
            else:
                player.combat.start_attack("heavy_attack")
        elif im.attack3_just_pressed:
            player.combat.start_attack("uppercut")
        elif im.attack4_just_pressed:
            player.combat.start_attack("dash_attack")
