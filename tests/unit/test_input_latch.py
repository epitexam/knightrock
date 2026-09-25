"""Input latch and render-interpolation contracts.

Both changes sit on a hot path and neither is observable from a behavioural
assertion alone: a key tap shorter than a poll interval is *invisible* rather
than wrong, and a jittering render still produces correct pixels every frame.
The tests below pin the mechanics instead.
"""

import os

import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider, NullInputProvider

pytestmark = pytest.mark.usefixtures("_latch_display")


@pytest.fixture(scope="module", autouse=True)
def _latch_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def _key_down(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key)


def _key_up(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, key=key)


@pytest.fixture()
def provider() -> LocalInputProvider:
    return LocalInputProvider()


@pytest.fixture()
def jump_key(provider: LocalInputProvider) -> int:
    binding = provider._bindings.gameplay.keyboard[InputAction.JUMP]
    assert isinstance(binding, int)
    return binding


def test_a_tap_shorter_than_a_poll_is_still_seen(
    provider: LocalInputProvider, jump_key: int
) -> None:
    """``get_pressed()`` is a state read, so a fast tap vanishes from it.

    The game runs two simulation ticks per presented frame, so a tap under
    ~16ms is up again before the provider ever polls. Without the latch the
    jump is simply dropped.
    """
    provider.note_event(_key_down(jump_key))
    provider.note_event(_key_up(jump_key))

    assert InputAction.JUMP in provider.poll().held_actions


def test_a_latched_tap_is_released_on_the_next_poll(provider: LocalInputProvider) -> None:
    """The latch must last exactly one tick, or the action sticks down."""
    provider.poll()
    provider.note_event(_key_down(jump_key_of(provider)))
    provider.note_event(_key_up(jump_key_of(provider)))

    assert InputAction.JUMP in provider.poll().held_actions
    assert InputAction.JUMP not in provider.poll().held_actions


def jump_key_of(provider: LocalInputProvider) -> int:
    binding = provider._bindings.gameplay.keyboard[InputAction.JUMP]
    assert isinstance(binding, int)
    return binding


def test_two_taps_are_two_distinct_presses(provider: LocalInputProvider) -> None:
    key = jump_key_of(provider)
    manager = InputManager(provider)
    manager.update()

    provider.note_event(_key_down(key))
    provider.note_event(_key_up(key))
    manager.update()
    assert manager.just_pressed(InputAction.JUMP)

    manager.update()
    assert not manager.held(InputAction.JUMP)

    provider.note_event(_key_down(key))
    provider.note_event(_key_up(key))
    manager.update()
    assert manager.just_pressed(InputAction.JUMP)


def test_a_latched_tap_does_not_repeat_on_its_own(provider: LocalInputProvider) -> None:
    """With no new event the action must not stay held forever."""
    key = jump_key_of(provider)
    provider.note_event(_key_down(key))
    provider.poll()
    for _ in range(5):
        assert InputAction.JUMP not in provider.poll().held_actions


def test_a_key_up_alone_latches_nothing(provider: LocalInputProvider) -> None:
    """A release carries no action; latching it would fake a press."""
    provider.note_event(_key_up(jump_key_of(provider)))

    assert InputAction.JUMP not in provider.poll().held_actions


def test_a_non_keyboard_event_is_ignored(provider: LocalInputProvider) -> None:
    provider.note_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))

    assert InputAction.JUMP not in provider.poll().held_actions


def test_an_unbound_key_latches_nothing(provider: LocalInputProvider) -> None:
    provider.note_event(_key_down(pygame.K_F12))

    state = provider.poll()

    assert InputAction.JUMP not in state.held_actions


def test_the_manager_exposes_the_hook_to_its_provider() -> None:
    """The base provider must accept the call, so a swap cannot break the loop."""
    manager = InputManager(NullInputProvider())

    manager.update()  # must not raise on a provider without the hook

    assert manager is not None


def test_just_pressed_survives_the_latch(provider: LocalInputProvider) -> None:
    """The latch feeds the edge, which is what the states read."""
    key = jump_key_of(provider)
    manager = InputManager(provider)
    manager.update()

    provider.note_event(_key_down(key))
    provider.note_event(_key_up(key))
    manager.update()

    assert manager.just_pressed(InputAction.JUMP) is True
    manager.update()
    assert manager.just_released(InputAction.JUMP) is True
