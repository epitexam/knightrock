import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings
from src.core.settings import Input as InputSettings


class InputDevice(StrEnum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    GAMEPAD = "gamepad"


@dataclass(frozen=True)
class RoutedInput:
    action: InputAction
    device: InputDevice
    position: tuple[int, int] | None = None
    value: float | None = None
    variant: str | None = None


# Priorité fixe des boutons de menu : l'écran Contrôles réécrit les maps, donc
# l'ordre du dict du fichier n'est plus un contrat. UI_BACK passe avant
# UI_CANCEL pour que le bouton B reste le retour même quand les deux actions le
# partagent (défaut historique), UI_CONFIRM avant tout le reste.
UI_BUTTON_PRIORITY: tuple[InputAction, ...] = (
    InputAction.UI_CONFIRM,
    InputAction.UI_BACK,
    InputAction.UI_CANCEL,
)

# Seules les directions de navigation.auto-répètent au clavier : répéter une
# validation ou un retour ferait ouvrir puis refermer un menu en boucle.
REPEATABLE_UI_ACTIONS: frozenset[InputAction] = frozenset(
    {
        InputAction.UI_UP,
        InputAction.UI_DOWN,
        InputAction.UI_LEFT,
        InputAction.UI_RIGHT,
    }
)


class EventRouter:
    def __init__(
        self,
        bindings: InputBindings | None = None,
        clock: Callable[[], float] | None = None,
        joystick_reader: Callable[[], object] | None = None,
    ) -> None:
        self._bindings = bindings or InputBindings()
        self._active_axes: dict[tuple[int, int], InputAction] = {}
        self._axis_next_repeat: dict[tuple[int, int], float] = {}
        self._axis_last_value: dict[tuple[int, int], float] = {}
        self._active_hats: dict[tuple[int, int], tuple[InputAction | None, int, int]] = {}
        self._hat_next_repeat: dict[tuple[int, int], float] = {}
        self._active_keys: dict[int, InputAction] = {}
        self._key_next_repeat: dict[int, float] = {}
        self._clock = clock or time.monotonic
        self._joystick_reader = joystick_reader
        self._connected_joysticks: dict[int, object] = {}

    def route(self, event: pygame.event.Event) -> RoutedInput | None:
        if event.type == pygame.KEYDOWN:
            return self._route_keyboard(getattr(event, "key", -1))
        if event.type == pygame.KEYUP:
            self._release_key(getattr(event, "key", -1))
            return None
        if event.type == pygame.MOUSEMOTION:
            return RoutedInput(
                InputAction.UI_POINTER_MOVE,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 1:
            return RoutedInput(
                InputAction.UI_POINTER_DOWN,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) != 1:
            action = self._mouse_button_action(getattr(event, "button", -1))
            if action is not None:
                return RoutedInput(action, InputDevice.MOUSE)
        if event.type == pygame.MOUSEBUTTONUP and getattr(event, "button", 0) == 1:
            return RoutedInput(
                InputAction.UI_POINTER_UP,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type in (
            pygame.JOYBUTTONDOWN,
            pygame.JOYDEVICEREMOVED,
            pygame.JOYHATMOTION,
            pygame.JOYAXISMOTION,
        ):
            return self._route_gamepad(event)
        return None

    def _route_gamepad(self, event: pygame.event.Event) -> RoutedInput | None:
        if event.type == pygame.JOYBUTTONDOWN:
            return self._route_gamepad_button(getattr(event, "button", -1))
        if event.type == pygame.JOYDEVICEREMOVED:
            instance_id = getattr(event, "instance_id", 0)
            self.notify_joystick_removed(instance_id)
            return RoutedInput(
                InputAction.UI_CANCEL,
                InputDevice.GAMEPAD,
                variant="device_removed",
            )
        if event.type == pygame.JOYHATMOTION:
            return self._route_hat(
                getattr(event, "instance_id", 0),
                getattr(event, "hat", 0),
                getattr(event, "value", (0, 0)),
            )
        return self._route_axis(
            getattr(event, "instance_id", 0),
            getattr(event, "axis", 0),
            float(getattr(event, "value", 0.0)),
        )

    def _route_keyboard(self, key: int) -> RoutedInput | None:
        if key == self._bindings.menu.new_game_key:
            self._arm_key(key, InputAction.UI_CONFIRM, repeatable=False)
            return RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD, variant="new_game")
        for action, binding in self._bindings.menu.keyboard.items():
            keys = binding if isinstance(binding, tuple) else (binding,)
            if key in keys:
                self._arm_key(key, action, repeatable=action in REPEATABLE_UI_ACTIONS)
                return RoutedInput(action, InputDevice.KEYBOARD)
        return None

    def _arm_key(self, key: int, action: InputAction, *, repeatable: bool) -> None:
        """Arm or disarm a key's auto-repeat when it is pressed.

        The stick and the d-pad already auto-repeat while held, so a keyboard
        doing a single step per press made menu navigation feel broken: a long
        menu needed one press per row. Repeats are limited to the four
        navigation directions, because repeating a confirm or a back would make
        a held key open a menu, close it, and open it again.
        """
        if not repeatable:
            self._release_key(key)
            return
        self._active_keys[key] = action
        self._key_next_repeat[key] = self._clock() + InputSettings.UI_REPEAT_INITIAL_DELAY

    def _release_key(self, key: int) -> None:
        """Stop repeating a key, called on release and on every router reset."""
        self._active_keys.pop(key, None)
        self._key_next_repeat.pop(key, None)

    def _route_gamepad_button(self, button: int) -> RoutedInput | None:
        action = self._menu_button_action(button)
        if action is None:
            return None
        return RoutedInput(action, InputDevice.GAMEPAD)

    def _mouse_button_action(self, button: int) -> InputAction | None:
        bindings = self._bindings.menu.mouse_buttons
        for action in UI_BUTTON_PRIORITY:
            if bindings.get(action) == button:
                return action
        for action, binding in bindings.items():
            if binding == button:
                return action
        return None

    def _menu_button_action(self, button: int) -> InputAction | None:
        """Action de menu émise par ``button`` (priorité fixe, pas d'ordre dict)."""
        bindings = self._bindings.menu.gamepad_buttons
        for action in UI_BUTTON_PRIORITY:
            if bindings.get(action) == button:
                return action
        for action, binding in bindings.items():
            if binding == button:
                return action
        return None

    def notify_joystick_connected(self, instance_id: int, joystick: object) -> None:
        self._connected_joysticks[instance_id] = joystick

    def notify_joystick_removed(self, instance_id: int) -> None:
        self._connected_joysticks.pop(instance_id, None)
        for key in tuple(self._active_axes):
            if key[0] == instance_id:
                self._active_axes.pop(key, None)
                self._axis_next_repeat.pop(key, None)
                self._axis_last_value.pop(key, None)
        for key in tuple(self._active_hats):
            if key[0] == instance_id:
                self._active_hats.pop(key, None)
                self._hat_next_repeat.pop(key, None)

    def reset(self) -> None:
        self._active_axes.clear()
        self._axis_next_repeat.clear()
        self._axis_last_value.clear()
        self._active_hats.clear()
        self._hat_next_repeat.clear()
        self._active_keys.clear()
        self._key_next_repeat.clear()

    def set_bindings(self, bindings: InputBindings) -> None:
        self._bindings = bindings
        self.reset()

    def would_route_key(self, key: int) -> bool:
        """Whether a ``KEYDOWN`` of ``key`` emits an action (peek, no state).

        Utilisé par l'écran Contrôles : l'événement qui termine une capture ne
        doit pas exécuter l'action qu'il route (valider, revenir…).
        """
        if key == self._bindings.menu.new_game_key:
            return True
        return any(
            key in (binding if isinstance(binding, tuple) else (binding,))
            for binding in self._bindings.menu.keyboard.values()
        )

    def would_route_button(self, button: int) -> bool:
        """Whether a ``JOYBUTTONDOWN`` of ``button`` emits an action (peek)."""
        return self._menu_button_action(button) is not None

    def would_route_axis(self, axis: int, value: float) -> bool:
        """Whether a ``JOYAXISMOTION`` emits a UI action (peek, no state)."""
        return self._axis_action(axis, value) is not None

    def would_route_hat(self, hat: int, value: tuple[int, int]) -> bool:
        """Whether a ``JOYHATMOTION`` emits a UI action (peek, no state)."""
        return self._hat_action(hat, value) is not None

    def poll_repeats(self) -> list[RoutedInput]:
        now = self._clock()
        repeats: list[RoutedInput] = []
        repeats.extend(self._poll_axis_repeats(now))
        repeats.extend(self._poll_hat_repeats(now))
        repeats.extend(self._poll_key_repeats(now))
        return repeats

    def _poll_key_repeats(self, now: float) -> list[RoutedInput]:
        """Auto-repeat the navigation keys still held down.

        ``reset()`` clears the held keys, and every push, pop and switch calls
        it, so a key held across a scene transition cannot keep repeating into
        the new scene: it has to be pressed again.
        """
        repeats: list[RoutedInput] = []
        for key, action in tuple(self._active_keys.items()):
            next_repeat = self._key_next_repeat.get(key)
            if next_repeat is None:
                continue
            if now < next_repeat:
                continue
            self._key_next_repeat[key] = now + InputSettings.UI_REPEAT_INTERVAL
            repeats.append(RoutedInput(action, InputDevice.KEYBOARD, variant="repeat"))
        return repeats

    def _poll_axis_repeats(self, now: float) -> list[RoutedInput]:
        """Repeat a held direction -- but only a *committed* one.

        This is the other half of "one push, one row". A stick has no press, so
        every hold is a hold: the auto-repeat used to be armed by the trigger
        threshold, which meant that resting a thumb at a third of the stick's
        travel and leaving it there for four tenths of a second walked four rows
        -- on a five-row menu, the whole thing. There is no key to release and
        nothing to tap, so the only way a player could tell "I am pushing" from
        "I am holding on purpose" is how far they push.

        So repeating asks for more than moving: a light touch moves one row and
        stays there however long it is held, and only a deliberate push past
        :data:`UI_AXIS_REPEAT_THRESHOLD` scrolls. Easing back is the brake, and
        it is not a step backwards: the direction is still held, so the repeat
        stops and nothing is announced. A D-pad has no partial deflection to
        read, so it keeps repeating on a hold -- see ``_poll_hat_repeats``.
        """
        repeats: list[RoutedInput] = []
        for (instance_id, axis), action in tuple(self._active_axes.items()):
            value = self._read_axis(instance_id, axis)
            if value is None:
                continue
            self._axis_last_value[(instance_id, axis)] = value
            if abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
                self._active_axes.pop((instance_id, axis), None)
                self._axis_next_repeat.pop((instance_id, axis), None)
                continue
            if abs(value) < InputSettings.UI_AXIS_REPEAT_THRESHOLD:
                continue
            next_repeat = self._axis_next_repeat.get((instance_id, axis))
            if next_repeat is None or now < next_repeat:
                continue
            self._axis_next_repeat[(instance_id, axis)] = now + InputSettings.UI_REPEAT_INTERVAL
            repeats.append(RoutedInput(action, InputDevice.GAMEPAD, value=value, variant="repeat"))
        return repeats

    def _poll_hat_repeats(self, now: float) -> list[RoutedInput]:
        repeats: list[RoutedInput] = []
        for (instance_id, hat), (action, x, y) in tuple(self._active_hats.items()):
            if action is None:
                continue
            live = self._read_hat(instance_id, hat)
            if live is None:
                # Pas de lecture live (test sans joystick, driver sans
                # get_hat) : on expire le bras au lieu de repeter a l'infini
                # sur la derniere valeur SDL connue.
                self._active_hats.pop((instance_id, hat), None)
                self._hat_next_repeat.pop((instance_id, hat), None)
                continue
            if live == (0, 0):
                self._active_hats.pop((instance_id, hat), None)
                self._hat_next_repeat.pop((instance_id, hat), None)
                continue
            if live is not None and live != (0, 0):
                live_action = self._hat_action(hat, live)
                if live_action is None:
                    continue
                action = live_action
                x, y = live
                self._active_hats[(instance_id, hat)] = (action, x, y)
            next_repeat = self._hat_next_repeat.get((instance_id, hat))
            if next_repeat is None or now < next_repeat:
                continue
            self._hat_next_repeat[(instance_id, hat)] = now + InputSettings.UI_REPEAT_INTERVAL
            value = float(x if action in (InputAction.UI_LEFT, InputAction.UI_RIGHT) else y)
            repeats.append(RoutedInput(action, InputDevice.GAMEPAD, value=value, variant="repeat"))
        return repeats

    def _resolve_joystick(self, instance_id: int) -> object | None:
        if instance_id in self._connected_joysticks:
            return self._connected_joysticks[instance_id]
        if self._joystick_reader is not None:
            try:
                joysticks = self._joystick_reader()
            except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
                return None
            if isinstance(joysticks, dict):
                joystick = joysticks.get(instance_id)
                if joystick is not None:
                    self._connected_joysticks[instance_id] = joystick
                return joystick
        return None

    def _read_axis(self, instance_id: int, axis: int) -> float | None:
        joystick = self._resolve_joystick(instance_id)
        if joystick is None:
            return None
        get_axis = getattr(joystick, "get_axis", None)
        if not callable(get_axis):
            return None
        try:
            return float(get_axis(axis))
        except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
            return None

    def _read_hat(self, instance_id: int, hat: int) -> tuple[int, int] | None:
        joystick = self._resolve_joystick(instance_id)
        if joystick is None:
            return None
        get_hat = getattr(joystick, "get_hat", None)
        if not callable(get_hat):
            return None
        try:
            return self._hat_xy(get_hat(hat))
        except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
            return None

    def _route_hat(self, instance_id: int, hat: int, value: object) -> RoutedInput | None:
        x, y = self._hat_xy(value)
        action = self._hat_action(hat, (x, y))
        key = (instance_id, hat)
        if action is None:
            self._active_hats.pop(key, None)
            self._hat_next_repeat.pop(key, None)
            return None
        previous = self._active_hats.get(key)
        now = self._clock()
        if previous is not None and previous[0] is action:
            if key not in self._hat_next_repeat:
                self._hat_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
            return None
        self._active_hats[key] = (action, x, y)
        self._hat_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
        return RoutedInput(action, InputDevice.GAMEPAD, value=float(x or y))

    def _route_axis(self, instance_id: int, axis: int, value: float) -> RoutedInput | None:
        """Route one ``JOYAXISMOTION``, remembering what the stick is *doing*.

        A stick is a position, not a press, so this carries a small state
        machine, and both of its rules are about not announcing itself twice:

        * **The band between the release and the trigger is hysteresis, not a
          release.** Letting the held direction go there -- which is what this
          used to do -- meant every dip into the band and back out of it fired
          the direction again. A stick resting at a third of its travel, with
          the noise a real one has, announced itself twelve times in four tenths
          of a second: one push, and the whole menu, several times over. The
          repeat poller never made that mistake, because it keeps the direction
          in the band, so the event path and the poller disagreed about what
          "held" meant and only the event path decided the *first* step.
        * **A direction is announced once, and a new one has to be committed.**
          Sweeping from up to down announces the down, once, when it crosses the
          trigger -- and a value inside the band never clears the direction that
          is already held, so coming back out of the band is not a second step.
        """
        key = (instance_id, axis)
        active = self._active_axes.get(key)
        if value == 0.0 or abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
            self._active_axes.pop(key, None)
            self._axis_next_repeat.pop(key, None)
            self._axis_last_value.pop(key, None)
            if active is None:
                return None
            return RoutedInput(active, InputDevice.GAMEPAD, value=value, variant="release")
        action = self._axis_action(axis, value)
        if action is active:
            # The same direction, held harder or eased back into the band. The
            # repeat is the only thing that may speak now, and it is the poller's
            # to decide -- see ``_poll_axis_repeats`` for why a light hold is
            # not a request to walk the list.
            if key not in self._axis_next_repeat:
                self._axis_next_repeat[key] = self._clock() + InputSettings.UI_REPEAT_INITIAL_DELAY
            return None
        if action is None or abs(value) < InputSettings.UI_AXIS_TRIGGER_THRESHOLD:
            # A direction that is not committed yet. The held one stays held: an
            # uncommitted value is the band, and treating it as a release is
            # what made every crossing of the threshold a new step.
            return None
        self._axis_last_value[key] = value
        self._active_axes[key] = action
        self._axis_next_repeat[key] = self._clock() + InputSettings.UI_REPEAT_INITIAL_DELAY
        return RoutedInput(action, InputDevice.GAMEPAD, value=value)

    def _axis_action(self, axis: int, value: float) -> InputAction | None:
        for action, bound_axis in self._bindings.menu.gamepad_axes.items():
            if bound_axis != axis:
                continue
            if action in (InputAction.UI_LEFT, InputAction.UI_RIGHT):
                if (value < 0.0) == (action is InputAction.UI_LEFT):
                    return action
                continue
            if action in (InputAction.UI_UP, InputAction.UI_DOWN):
                is_up = value > 0.0 if self._bindings.menu.invert_y else value < 0.0
                if is_up == (action is InputAction.UI_UP):
                    return action
                continue
        return None

    def _hat_action(self, hat: int, value: tuple[int, int]) -> InputAction | None:
        """The direction a hat position means.

        A hat is *not* an axis, and this is the whole reason the vertical case
        needs saying. SDL axes follow the mathematical convention: pushed up,
        the Y axis reads negative. A hat follows the screen, because it is a
        direction and not a measurement -- pygame documents ``(0, 1)`` as **up**
        (``(0, -1)`` is down), which is ``SDL_HAT_UP``, and so is every D-pad
        and every hat switch on a console. So the two halves of this class
        deliberately disagree: ``_axis_action`` calls up negative, this one
        calls it positive.

        The menu had it backwards. It was "fixed" once in the other direction
        on the belief that a hat is reported in screen coordinates, meaning
        ``y = +1`` is down -- which is true of a *window* and false of a hat.
        The D-pad had been correct until then, and the test that was supposed
        to prove it agreed with the bug instead of the hardware: it fired the
        hat up and the stick up and only compared where the selection landed,
        so a pair of consistent inversions looked like a pass. The proof that
        does not have that hole is
        ``test_the_menu_and_the_game_read_one_hat_the_same_way``: the menu and
        the gameplay provider are handed the *same* hat value and asked for the
        same direction, so the two cannot disagree again.

        ``invert_y`` is honoured here as the axis path honours it, so the
        setting moves the D-pad too instead of only the stick.
        """
        x, y = value
        inverted = self._bindings.menu.invert_y
        for action, bound_hat in self._bindings.menu.gamepad_hats.items():
            if bound_hat != hat:
                continue
            is_up = y < 0.0 if inverted else y > 0.0
            if is_up and action is InputAction.UI_UP:
                return action
            if not is_up and y != 0.0 and action is InputAction.UI_DOWN:
                return action
            if x < 0 and action is InputAction.UI_LEFT:
                return action
            if x > 0 and action is InputAction.UI_RIGHT:
                return action
        return None

    @staticmethod
    def _hat_xy(value: object) -> tuple[int, int]:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            try:
                return int(value[0]), int(value[1])
            except (TypeError, ValueError):
                return 0, 0
        return 0, 0
