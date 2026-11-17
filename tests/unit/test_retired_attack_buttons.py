"""A settings file from before the two-button catalogue still loads.

The third and fourth attack buttons were retired when the moves became light
and heavy chains. A file that still binds them must not be rejected -- that
would throw away every other binding the player made -- so the two entries are
dropped and the rest is read as it was written.
"""

from __future__ import annotations

import pygame

from src.core.input.bindings_codec import bindings_from_dict, bindings_to_dict
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings


def _old_file() -> dict:
    data = bindings_to_dict(InputBindings())
    gameplay = data["gameplay"]
    gameplay["keyboard"]["attack3"] = pygame.K_d
    gameplay["keyboard"]["attack4"] = pygame.K_f
    gameplay["keyboard"]["jump"] = pygame.K_w  # a choice of the player's
    gameplay["gamepad_buttons"]["attack3"] = 1
    gameplay["gamepad_buttons"]["attack4"] = 5
    return data


def test_a_file_binding_the_retired_buttons_still_loads() -> None:
    bindings = bindings_from_dict(_old_file())

    assert bindings.gameplay.keyboard[InputAction.JUMP] == pygame.K_w
    assert bindings.gameplay.keyboard[InputAction.ATTACK_1] == pygame.K_a


def test_the_retired_buttons_are_simply_gone() -> None:
    bindings = bindings_from_dict(_old_file())

    names = {str(action) for action in bindings.gameplay.keyboard}
    names |= {str(action) for action in bindings.gameplay.gamepad_buttons}
    assert "attack3" not in names and "attack4" not in names


def test_an_unknown_action_is_still_refused() -> None:
    """Only the two retired names are forgiven; a typo is not."""
    data = _old_file()
    data["gameplay"]["keyboard"]["atack1"] = pygame.K_z

    try:
        bindings_from_dict(data)
    except ValueError as error:
        assert "atack1" in str(error)
    else:
        raise AssertionError("an unknown action was accepted")
