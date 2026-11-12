from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import pygame

from src.core.input.input_actions import InputAction

type KeyBinding = int | tuple[int, ...]
# Gamepad button: one SDL index, or a (left, right) pair for MOVE_X when the
# d-pad is exposed as buttons rather than a hat (Xbox/SDL2 pads).
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


#: An Xbox One pad's buttons as SDL's joystick API numbers them (Windows and
#: Linux alike for these eight).
XBOX_A, XBOX_B, XBOX_X, XBOX_Y = 0, 1, 2, 3
XBOX_LB, XBOX_RB, XBOX_VIEW, XBOX_START = 4, 5, 6, 7


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
                InputAction.GUARD: pygame.K_q,
                InputAction.RESET: pygame.K_r,
            }
        )
    )
    #: An Xbox pad's layout, as SDL numbers it: A 0, B 1, X 2, Y 3, LB 4,
    #: RB 5, View 6, Start 7. The action-game convention: A jumps, X is the
    #: light attack, Y the heavy one; Start is left to the pause
    #: (``MenuBindings.gamepad_buttons``), so the reset is on View.
    gamepad_buttons: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.JUMP: XBOX_A,
                InputAction.ATTACK_1: XBOX_X,
                InputAction.ATTACK_2: XBOX_Y,
                InputAction.GUARD: XBOX_LB,
                InputAction.RESET: XBOX_VIEW,
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
        # The two attack buttons side by side on top of the pad: X + Y.
        default_factory=lambda: _immutable_combos({InputAction.SPECIAL_ATTACK: (XBOX_X, XBOX_Y)})
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
                # Escape is Back in the menus and the pause in the game; the
                # router emits Back for it, and the game pauses on a keyboard
                # Back. Listed so the controls screen says what pauses.
                InputAction.UI_PAUSE: pygame.K_ESCAPE,
                InputAction.UI_PAGE_UP: pygame.K_PAGEUP,
                InputAction.UI_PAGE_DOWN: pygame.K_PAGEDOWN,
                InputAction.UI_HOME: pygame.K_HOME,
                InputAction.UI_END: pygame.K_END,
            }
        )
    )
    mouse_buttons: ButtonMap = field(default_factory=lambda: _immutable({InputAction.UI_BACK: 3}))
    gamepad_buttons: ButtonMap = field(
        default_factory=lambda: _immutable(
            {
                InputAction.UI_CONFIRM: XBOX_A,
                InputAction.UI_BACK: XBOX_B,
                InputAction.UI_CANCEL: XBOX_B,
                # Start pauses the game and resumes it from the pause menu. B
                # stays "back" in the menus, but it is an attack in the game,
                # so it must not be what pauses.
                InputAction.UI_PAUSE: XBOX_START,
                # The shoulders page a menu, as they page a list anywhere
                # else. Without them a gamepad player walks a 28-row list
                # one row at a time while the keyboard gets two keys for it,
                # and the shoulders were sitting there free in this context --
                # 4 and 5 are Guard and Attack 4 in *gameplay*, which is a
                # separate map, so borrowing them here costs nothing.
                InputAction.UI_PAGE_UP: 4,
                InputAction.UI_PAGE_DOWN: 5,
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
