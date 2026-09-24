from types import MappingProxyType

import pygame

from src.application.input_dispatcher import InputDispatcher
from src.core.input.event_router import EventRouter, InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings, MenuBindings


def test_router_maps_keyboard_mouse_and_gamepad_buttons() -> None:
    router = EventRouter()

    keyboard = router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    mouse = router.route(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(12, 24)))
    gamepad = router.route(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0))

    assert keyboard == RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD)
    assert mouse == RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=(12, 24))
    assert gamepad == RoutedInput(InputAction.UI_CONFIRM, InputDevice.GAMEPAD)
    cancel = router.route(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    assert cancel == RoutedInput(InputAction.UI_CANCEL, InputDevice.GAMEPAD)


def test_router_maps_hat_and_axis_with_release_threshold() -> None:
    router = EventRouter()

    hat = router.route(pygame.event.Event(pygame.JOYHATMOTION, value=(0, -1)))
    press = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.8))
    repeated = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.9)
    )
    release = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.1)
    )

    assert hat == RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD, value=-1.0)
    assert press == RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.8)
    assert repeated == RoutedInput(
        InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.9, variant="repeat"
    )
    assert release == RoutedInput(
        InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.1, variant="release"
    )


def test_router_preserves_new_game_and_cancel_variants() -> None:
    router = EventRouter()
    rebound_router = EventRouter(InputBindings(menu=MenuBindings(new_game_key=pygame.K_x)))

    new_game = router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n))
    rebound_new_game = rebound_router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x))
    cancel = router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))

    assert new_game == RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD, variant="new_game")
    assert rebound_new_game == new_game
    assert cancel == RoutedInput(InputAction.UI_CANCEL, InputDevice.KEYBOARD)


def test_router_uses_custom_menu_axis_and_hat_bindings() -> None:
    menu = MenuBindings(
        gamepad_axes=MappingProxyType(
            {
                InputAction.UI_LEFT: 7,
                InputAction.UI_RIGHT: 7,
                InputAction.UI_UP: 8,
                InputAction.UI_DOWN: 8,
            }
        ),
        gamepad_hats=MappingProxyType(
            {
                InputAction.UI_LEFT: 3,
                InputAction.UI_RIGHT: 3,
                InputAction.UI_UP: 3,
                InputAction.UI_DOWN: 3,
            }
        ),
    )
    router = EventRouter(InputBindings(menu=menu))

    axis = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=1, axis=7, value=-1.0))
    hat = router.route(pygame.event.Event(pygame.JOYHATMOTION, instance_id=1, hat=3, value=(-1, 0)))

    assert axis == RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD, value=-1.0)
    assert hat == RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD, value=-1.0)


def test_router_reports_joystick_removal() -> None:
    router = EventRouter()

    removed = router.route(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=9))

    assert removed == RoutedInput(
        InputAction.UI_CANCEL, InputDevice.GAMEPAD, variant="device_removed"
    )


def test_dispatcher_forwards_raw_and_routed_inputs() -> None:
    class RecordingScene:
        def __init__(self) -> None:
            self.raw = 0
            self.routed: list[RoutedInput] = []

        def handle_event(self, _event: pygame.event.Event) -> None:
            self.raw += 1

        def handle_routed(self, routed: RoutedInput) -> None:
            self.routed.append(routed)

    scene = RecordingScene()
    dispatcher = InputDispatcher(EventRouter())
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)

    dispatcher.dispatch(scene, event)  # type: ignore[arg-type]

    assert scene.raw == 1
    assert scene.routed == [RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD)]
