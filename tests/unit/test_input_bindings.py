import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings


def test_default_bindings_are_separated_by_context() -> None:
    bindings = InputBindings()

    assert bindings.gameplay.keyboard[InputAction.JUMP] == pygame.K_SPACE
    assert bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 0
    assert bindings.menu.keyboard[InputAction.UI_CONFIRM] == (
        pygame.K_RETURN,
        pygame.K_KP_ENTER,
        pygame.K_SPACE,
    )
    assert bindings.menu.gamepad_buttons[InputAction.UI_CONFIRM] == 0


def test_default_bindings_cover_analog_axes() -> None:
    bindings = InputBindings()

    assert bindings.gameplay.keyboard[InputAction.MOVE_X] == (
        pygame.K_LEFT,
        pygame.K_RIGHT,
    )
    assert bindings.gameplay.gamepad_axes[InputAction.MOVE_X] == 0
    assert bindings.gameplay.gamepad_axes[InputAction.MOVE_DOWN] == 1
    assert bindings.menu.gamepad_axes[InputAction.UI_UP] == 1


def test_default_bindings_are_immutable() -> None:
    bindings = InputBindings()

    with pytest.raises(TypeError):
        bindings.gameplay.keyboard[InputAction.JUMP] = pygame.K_x


def test_default_combos_are_typed_and_nonempty() -> None:
    bindings = InputBindings()

    assert bindings.gameplay.keyboard_combos[InputAction.SPECIAL_ATTACK] == (
        pygame.K_g,
        pygame.K_h,
    )
    assert bindings.gameplay.gamepad_combos[InputAction.SPECIAL_ATTACK] == (1, 3)
