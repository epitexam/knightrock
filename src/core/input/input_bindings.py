from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import pygame

from src.core.input.input_actions import InputAction

type KeyBinding = int | tuple[int, ...]
# Bouton manette : un index SDL, ou une paire (gauche, droite) pour MOVE_X
# quand le d-pad est exposé en boutons et pas en hat (pads Xbox/SDL2).
type PadBinding = int | tuple[int, ...]
type ActionMap = Mapping[InputAction, KeyBinding]
type ButtonMap = Mapping[InputAction, PadBinding]
type AxisMap = Mapping[InputAction, int]
type ComboMap = Mapping[InputAction, tuple[int, ...]]


def _immutable(values: dict[InputAction, PadBinding]) -> ButtonMap:
    return MappingProxyType(values)


def _immutable_axes(values: dict[InputAction, int]) -> AxisMap:
    return MappingProxyType(values)


def _immutable_keys(values: dict[InputAction, KeyBinding]) -> ActionMap:
    return MappingProxyType(values)


def _immutable_combos(values: dict[InputAction, tuple[int, ...]]) -> ComboMap:
    return MappingProxyType(values)


@dataclass(frozen=True)
class GameplayBindings:
    keyboard: ActionMap = field(
        default_factory=lambda: _immutable_keys(
            {
                InputAction.MOVE_X: (pygame.K_LEFT, pygame.K_RIGHT),
                InputAction.MOVE_DOWN: pygame.K_DOWN,
                InputAction.JUMP: pygame.K_SPACE,
                InputAction.DASH: pygame.K_LSHIFT,
                InputAction.ATTACK_1: pygame.K_a,
                InputAction.ATTACK_2: pygame.K_s,
                InputAction.ATTACK_3: pygame.K_d,
                InputAction.ATTACK_4: pygame.K_f,
                InputAction.GUARD: pygame.K_q,
                InputAction.RESET: pygame.K_r,
            }
        )
    )
    gamepad_buttons: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.JUMP: 0,
                InputAction.ATTACK_1: 1,
                InputAction.ATTACK_2: 2,
                InputAction.ATTACK_3: 3,
                InputAction.GUARD: 4,
                InputAction.ATTACK_4: 5,
                InputAction.RESET: 7,
            }
        )
    )
    gamepad_axes: AxisMap = field(
        default_factory=lambda: _immutable_axes(
            {
                InputAction.MOVE_X: 0,
                InputAction.DASH: 2,
                InputAction.MOVE_DOWN: 1,
            }
        )
    )
    gamepad_hats: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.MOVE_X: 0,
                InputAction.MOVE_DOWN: 0,
            }
        )
    )
    keyboard_combos: ComboMap = field(
        default_factory=lambda: _immutable_combos(
            {InputAction.SPECIAL_ATTACK: (pygame.K_g, pygame.K_h)}
        )
    )
    gamepad_combos: ComboMap = field(
        default_factory=lambda: _immutable_combos({InputAction.SPECIAL_ATTACK: (1, 3)})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "keyboard", _immutable_keys(dict(self.keyboard)))
        object.__setattr__(self, "gamepad_buttons", _immutable(dict(self.gamepad_buttons)))
        object.__setattr__(self, "gamepad_axes", _immutable_axes(dict(self.gamepad_axes)))
        object.__setattr__(self, "gamepad_hats", _immutable(dict(self.gamepad_hats)))
        object.__setattr__(
            self,
            "keyboard_combos",
            _immutable_combos(
                {action: tuple(keys) for action, keys in self.keyboard_combos.items()}
            ),
        )
        object.__setattr__(
            self,
            "gamepad_combos",
            _immutable_combos(
                {action: tuple(keys) for action, keys in self.gamepad_combos.items()}
            ),
        )


@dataclass(frozen=True)
class MenuBindings:
    keyboard: ActionMap = field(
        default_factory=lambda: _immutable_keys(
            {
                InputAction.UI_UP: pygame.K_UP,
                InputAction.UI_DOWN: pygame.K_DOWN,
                InputAction.UI_LEFT: pygame.K_LEFT,
                InputAction.UI_RIGHT: pygame.K_RIGHT,
                InputAction.UI_CONFIRM: (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE),
                InputAction.UI_BACK: pygame.K_ESCAPE,
                InputAction.UI_CANCEL: pygame.K_q,
            }
        )
    )
    mouse_buttons: ButtonMap = field(default_factory=lambda: _immutable({InputAction.UI_BACK: 3}))
    gamepad_buttons: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.UI_CONFIRM: 0,
                InputAction.UI_BACK: 1,
                InputAction.UI_CANCEL: 1,
            }
        )
    )
    gamepad_hats: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.UI_UP: 0,
                InputAction.UI_DOWN: 0,
                InputAction.UI_LEFT: 0,
                InputAction.UI_RIGHT: 0,
            }
        )
    )
    gamepad_axes: AxisMap = field(
        default_factory=lambda: _immutable_axes(
            {
                InputAction.UI_LEFT: 0,
                InputAction.UI_RIGHT: 0,
                InputAction.UI_UP: 1,
                InputAction.UI_DOWN: 1,
            }
        )
    )
    new_game_key: int | None = pygame.K_n
    invert_y: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "keyboard", _immutable_keys(dict(self.keyboard)))
        object.__setattr__(self, "mouse_buttons", _immutable(dict(self.mouse_buttons)))
        object.__setattr__(self, "gamepad_buttons", _immutable(dict(self.gamepad_buttons)))
        object.__setattr__(self, "gamepad_hats", _immutable(dict(self.gamepad_hats)))
        object.__setattr__(self, "gamepad_axes", _immutable(dict(self.gamepad_axes)))


@dataclass(frozen=True)
class InputBindings:
    gameplay: GameplayBindings = field(default_factory=GameplayBindings)
    menu: MenuBindings = field(default_factory=MenuBindings)
