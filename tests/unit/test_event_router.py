from types import MappingProxyType

import pygame

from src.application.events import EventBus, UiEffect, UiFeedback
from src.application.input_dispatcher import InputDispatcher
from src.core.input.event_router import EventRouter, InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings, MenuBindings
from src.core.settings import Input as InputSettings
from src.ui.menu_model import MenuAction


def test_router_maps_keyboard_mouse_and_gamepad_buttons() -> None:
    router = EventRouter()

    keyboard = router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    mouse = router.route(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(12, 24)))
    right_click = router.route(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(5, 5)))
    gamepad = router.route(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0))

    assert keyboard == RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD)
    assert mouse == RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=(12, 24))
    assert right_click == RoutedInput(InputAction.UI_BACK, InputDevice.MOUSE)
    assert gamepad == RoutedInput(InputAction.UI_CONFIRM, InputDevice.GAMEPAD)
    cancel = router.route(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1))

    # B button (gamepad) = back: routed to UI_BACK and UI_CANCEL.
    assert cancel == RoutedInput(InputAction.UI_BACK, InputDevice.GAMEPAD)


def test_default_keyboard_navigation_actions_are_unique_and_routable() -> None:
    router = EventRouter()
    expected = {
        pygame.K_UP: InputAction.UI_UP,
        pygame.K_DOWN: InputAction.UI_DOWN,
        pygame.K_LEFT: InputAction.UI_LEFT,
        pygame.K_RIGHT: InputAction.UI_RIGHT,
        pygame.K_RETURN: InputAction.UI_CONFIRM,
        pygame.K_ESCAPE: InputAction.UI_BACK,
    }
    for key, action in expected.items():
        assert router.route(pygame.event.Event(pygame.KEYDOWN, key=key)) == RoutedInput(
            action, InputDevice.KEYBOARD
        )


def test_router_maps_hat_and_axis_with_release_threshold() -> None:
    now = [10.0]

    class Stick:
        def __init__(self, value: float) -> None:
            self.value = value

        def get_axis(self, _axis: int) -> float:
            return self.value

    stick = Stick(0.9)
    router = EventRouter(clock=lambda: now[0], joystick_reader=lambda: {4: stick})

    hat = router.route(pygame.event.Event(pygame.JOYHATMOTION, instance_id=7, hat=0, value=(0, 1)))
    press = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.8))
    flooded = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.9)
    )
    now[0] += InputSettings.UI_REPEAT_INITIAL_DELAY + 0.01
    repeated = router.poll_repeats()
    stick.value = 0.1
    release = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=0, value=0.1)
    )

    # A hat is a direction, not a measurement: pygame documents (0, 1) as *up*
    # (SDL_HAT_UP), the opposite of an axis, where up is negative. The two are
    # asserted from the same value by
    # ``test_the_menu_and_the_game_read_one_hat_the_same_way``; this one is the
    # place that says which way round it is.
    assert hat == RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD, value=1.0)
    assert press == RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.8)
    # Held stick: the intermediate events are filtered out (throttle).
    assert flooded is None
    assert repeated == [
        RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.9, variant="repeat")
    ]
    assert release == RoutedInput(
        InputAction.UI_RIGHT, InputDevice.GAMEPAD, value=0.1, variant="release"
    )


class Stick:
    """A joystick the router can re-read, which is how a hold is measured."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def get_axis(self, _axis: int) -> float:
        return self.value

    def get_hat(self, _hat: int) -> tuple[int, int]:
        return (0, 0)


def _stick_router(stick: Stick, now: list[float]) -> EventRouter:
    return EventRouter(clock=lambda: now[0], joystick_reader=lambda: {4: stick})


def _hold(
    router: EventRouter, stick: Stick, now: list[float], values: list[float], *, base: float = 0.0
) -> list[RoutedInput]:
    """Feed one frame per value: the event, then the repeat poll of that frame.

    ``base`` is the time the first frame happens at, so a test can run a second
    stretch of frames *after* the first one instead of restarting the clock and
    travelling backwards through it.
    """
    routed: list[RoutedInput] = []
    for frame, value in enumerate(values):
        now[0] = base + frame / 60.0
        stick.value = value
        press = router.route(
            pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=1, value=value)
        )
        if press is not None:
            routed.append(press)
        routed.extend(router.poll_repeats())
    return routed


def test_a_stick_held_at_a_light_deflection_moves_exactly_one_row() -> None:
    """The band between release and trigger is hysteresis, not a release.

    It was read as a release, so every dip into the band and back out of it
    announced the direction again. A thumb resting at a third of the travel,
    with the noise a real stick has, announced itself twelve times in four
    tenths of a second: one push, the whole menu, several times over.

    The repeat poller never made that mistake -- it keeps the direction in the
    band -- which is why the two halves of the router disagreed about what
    "held" meant, and why only the event path had to be fixed to make the pair
    agree. The values below are the ones that used to fire: 0.28 crosses the
    trigger, 0.22 falls into the band, 0.30 crosses again.
    """
    now = [0.0]
    stick = Stick()
    router = _stick_router(stick, now)

    routed = _hold(router, stick, now, [0.0, 0.28, 0.22, 0.30, 0.24, 0.28, 0.0])

    assert [item.variant for item in routed] == [None, "release"]
    assert routed[0] == RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD, value=0.28)


def test_a_light_hold_never_repeats_and_a_committed_one_does() -> None:
    """A stick is a position, so holding it is not a press.

    The repeat used to be armed by the trigger threshold, so a thumb resting at
    a third of the travel walked four rows in four tenths of a second -- the
    whole of a five-row menu, from one touch. Repeating now asks for most of the
    travel: a light hold moves one row and stays there, and only a deliberate
    push scrolls.
    """

    def hold_at(value: float) -> list:
        stick = Stick()
        now = [0.0]
        return _hold(_stick_router(stick, now), stick, now, [0.0] + [value] * 24 + [0.0])

    light = hold_at(InputSettings.UI_AXIS_TRIGGER_THRESHOLD + 0.05)
    committed = hold_at(0.9)

    assert [item.variant for item in light] == [None, "release"], "a light hold repeated"
    assert [item.variant for item in committed].count("repeat") >= 2, "a committed hold did not"


def test_easing_back_stops_the_repeat_without_stepping_back() -> None:
    """The stick is a brake, not a toggle.

    Coming off the gas below the repeat threshold stops the scrolling and
    announces nothing: the direction is still held, so there is no new step to
    take and no step backwards either.
    """
    now = [0.0]
    stick = Stick()
    router = _stick_router(stick, now)
    pushed = _hold(router, stick, now, [0.0] + [0.9] * 20)

    eased = _hold(router, stick, now, [0.4] * 20, base=now[0] + 1 / 60.0)

    assert [item.variant for item in pushed].count("repeat") >= 2, "it never scrolled"
    assert eased == [], "easing off the gas was not silent"


def test_sweeping_the_stick_announces_the_new_direction_once() -> None:
    """Up to down in one frame is one step, and the band in between is not two.

    The band must not clear the held direction -- that is what made every
    crossing of the threshold a fresh step -- but a *committed* direction in the
    other direction still has to be announced, or a fast sweep would be dropped.
    """
    now = [0.0]
    stick = Stick()
    router = _stick_router(stick, now)

    up = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=4, axis=1, value=-0.9))
    through = _hold(router, stick, now, [0.2])
    down = _hold(router, stick, now, [0.9, 0.9])
    released = _hold(router, stick, now, [0.0])

    assert up == RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD, value=-0.9)
    assert through == [], "a value inside the band announced the other direction"
    assert down == [RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD, value=0.9)]
    assert [item.variant for item in released] == ["release"], "the centre is a release"


def test_router_uses_inverted_y_and_ui_deadzone_for_xbox() -> None:
    router = EventRouter()
    inverted_router = EventRouter(InputBindings(menu=MenuBindings(invert_y=True)))
    deadzone = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=2, axis=1, value=0.2)
    )
    up = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=2, axis=1, value=-0.8))
    down = router.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=2, axis=1, value=0.8))
    inverted_up = inverted_router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=2, axis=1, value=0.8)
    )

    assert deadzone is None
    # And a partial push does act: the trigger threshold is 0.4, not the 0.5 it
    # used to be, which demanded half the stick's travel and read as lag. 0.2
    # is still inside the deadzone, 0.45 is not. A fresh router, because on
    # ``router`` that direction is already held and a same-direction value is
    # throttled to nothing -- the anti-flood behaviour, not a threshold.
    fresh = EventRouter()
    assert (
        fresh.route(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=2, axis=1, value=0.45))
        is not None
    )
    assert up == RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD, value=-0.8)
    assert down == RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD, value=0.8)
    assert inverted_up == RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD, value=0.8)


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

        def handle_routed(self, routed: RoutedInput) -> str | None:
            self.routed.append(routed)
            return None

    scene = RecordingScene()
    dispatcher = InputDispatcher(EventRouter(), EventBus())
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)

    dispatcher.dispatch(scene, event)  # type: ignore[arg-type]

    assert scene.raw == 1
    assert scene.routed == [RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD)]


def test_dispatcher_publishes_what_the_scene_reports() -> None:
    """The report is the only thing that becomes a published fact.

    A scene that acts nothing (returns None) publishes nothing, which is how
    the gameplay keys and a rebinding capture stay silent without either
    knowing that anything is listening.
    """

    class ReportingScene:
        def __init__(self, report: str | None) -> None:
            self.report = report

        def handle_event(self, _event: pygame.event.Event) -> None:
            return None

        def handle_routed(self, _routed: RoutedInput) -> str | None:
            return self.report

    published: list[UiFeedback] = []
    bus = EventBus()
    bus.subscribe(UiFeedback, published.append)
    dispatcher = InputDispatcher(EventRouter(), bus)
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)

    dispatcher.dispatch(ReportingScene("options"), event)  # type: ignore[arg-type]
    dispatcher.dispatch(ReportingScene(MenuAction.BACK), event)  # type: ignore[arg-type]
    dispatcher.dispatch(ReportingScene(MenuAction.MOVE_DOWN), event)  # type: ignore[arg-type]
    dispatcher.dispatch(ReportingScene(None), event)  # type: ignore[arg-type]

    assert published == [
        UiFeedback(UiEffect.CONFIRMED, action="options"),
        UiFeedback(UiEffect.DISMISSED, action=MenuAction.BACK),
        UiFeedback(UiEffect.NAVIGATED, action=MenuAction.MOVE_DOWN),
    ]


def test_dispatcher_does_not_publish_a_release_or_an_unplugged_pad() -> None:
    """Those two routed inputs carry no deliberate action, so they say nothing."""

    class ConfirmingScene:
        def handle_event(self, _event: pygame.event.Event) -> None:
            return None

        def handle_routed(self, _routed: RoutedInput) -> str | None:
            return "options"

    published: list[UiFeedback] = []
    bus = EventBus()
    bus.subscribe(UiFeedback, published.append)
    dispatcher = InputDispatcher(EventRouter(), bus)

    for variant in ("release", "device_removed"):
        dispatcher._apply(  # type: ignore[arg-type]
            ConfirmingScene(),
            RoutedInput(InputAction.UI_CONFIRM, InputDevice.GAMEPAD, variant=variant),
        )

    assert published == []


def test_router_peeks_whether_a_key_or_button_would_route() -> None:
    """``would_route_*``: a stateless peek for the controls screen (UI-5)."""
    router = EventRouter()

    assert router.would_route_key(pygame.K_DOWN) is True
    assert router.would_route_key(pygame.K_n) is True  # new-game shortcut
    assert router.would_route_key(pygame.K_x) is False
    assert router.would_route_button(1) is True
    assert router.would_route_button(9) is False

    # The peek follows the current bindings without consuming an event.
    router.set_bindings(
        InputBindings(
            menu=MenuBindings(
                keyboard=MappingProxyType({InputAction.UI_UP: pygame.K_x}),
                new_game_key=None,
            )
        )
    )

    assert router.would_route_key(pygame.K_x) is True
    assert router.would_route_key(pygame.K_DOWN) is False
    assert router.would_route_key(pygame.K_n) is False
    assert router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x)) == RoutedInput(
        InputAction.UI_UP, InputDevice.KEYBOARD
    )
