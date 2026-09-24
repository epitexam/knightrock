from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import pygame

from src.core.input.input_actions import InputAction

type KeyBinding = int | tuple[int, ...]
type ActionMap = Mapping[InputAction, KeyBinding]
type ButtonMap = Mapping[InputAction, int]
type AxisMap = Mapping[InputAction, int]
type ComboMap = Mapping[InputAction, tuple[int, ...]]


def _immutable(values: dict[InputAction, int]) -> ButtonMap:
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
        default_factory=lambda: _immutable(
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
                InputAction.UI_CANCEL: pygame.K_ESCAPE,
            }
        )
    )
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
        default_factory=lambda: _immutable(
            {
                InputAction.UI_LEFT: 0,
                InputAction.UI_RIGHT: 0,
                InputAction.UI_UP: 1,
                InputAction.UI_DOWN: 1,
            }
        )
    )


@dataclass(frozen=True)
class InputBindings:
    gameplay: GameplayBindings = field(default_factory=GameplayBindings)
    menu: MenuBindings = field(default_factory=MenuBindings)
