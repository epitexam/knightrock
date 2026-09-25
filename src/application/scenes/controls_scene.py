"""Two-column keyboard/mouse and gamepad remapping screen."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

import pygame

from src.application.scene import Scene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import (
    GameplayBindings,
    InputBindings,
    MenuBindings,
    PadBinding,
)
from src.ui.controls_view import (
    GAMEPAD_COLUMN,
    KEYBOARD_COLUMN,
    BindingCell,
    BindingRow,
    ControlsView,
    RowKind,
)
from src.ui.menu_model import MenuItem, MenuModel

if TYPE_CHECKING:
    from src.core.game import Game

T = TypeVar("T")


@dataclass(frozen=True)
class RebindSpec:
    label: str
    action: InputAction | None
    pair: bool = False
    side: int | None = None


class ControlsScene(Scene):
    MENU_SECTION: str = "menu"
    GAMEPLAY_SECTION: str = "gameplay"
    _key_names: ClassVar[dict[int, str]] = {}
    SECTIONS: dict[str, tuple[RebindSpec, ...]] = {
        MENU_SECTION: (
            RebindSpec("Move up", InputAction.UI_UP),
            RebindSpec("Move down", InputAction.UI_DOWN),
            RebindSpec("Move left", InputAction.UI_LEFT),
            RebindSpec("Move right", InputAction.UI_RIGHT),
            RebindSpec("Confirm", InputAction.UI_CONFIRM),
            RebindSpec("Back", InputAction.UI_BACK),
            RebindSpec("Cancel", InputAction.UI_CANCEL),
            RebindSpec("New game shortcut", None),
        ),
        GAMEPLAY_SECTION: (
            RebindSpec("Move left", InputAction.MOVE_X, side=0),
            RebindSpec("Move right", InputAction.MOVE_X, side=1),
            RebindSpec("Crouch / fast fall", InputAction.MOVE_DOWN),
            RebindSpec("Jump", InputAction.JUMP),
            RebindSpec("Dash", InputAction.DASH),
            RebindSpec("Attack 1", InputAction.ATTACK_1),
            RebindSpec("Attack 2", InputAction.ATTACK_2),
            RebindSpec("Attack 3", InputAction.ATTACK_3),
            RebindSpec("Attack 4", InputAction.ATTACK_4),
            RebindSpec("Guard", InputAction.GUARD),
            RebindSpec("Reset position", InputAction.RESET),
        ),
    }

    def __init__(self, game: Game, section: str) -> None:
        super().__init__(game)
        if section not in self.SECTIONS:
            raise ValueError(f"unknown controls section: {section}")
        self.section = section
        self.specs = self.SECTIONS[section]
        items = tuple(
            MenuItem(f"rebind_{index}", spec.label) for index, spec in enumerate(self.specs)
        )
        if section == self.MENU_SECTION:
            # The invert-Y toggle is a real navigation row, not decoration:
            # it must be reachable with ↑↓ and activatable, like Reset/Back.
            items += (MenuItem("invert_y", "Invert stick Y"),)
        self.model = MenuModel(
            items + (MenuItem("reset", "Reset to defaults"), MenuItem("back", "Back"))
        )
        self.view = ControlsView(game.settings.ui_scale)
        self.selected_column = KEYBOARD_COLUMN
        self._capture: tuple[int, int] | None = None
        self._pending: list[int] = []
        self._status: str | None = None
        self._ignore_routed = False
        self._ignore_mouse_capture = False
        self._rows_cache: list[BindingRow] | None = None
        self._rows_bindings: object = None
        self._rows_capture: tuple[int, int] | None = None
        self._rows_index = -1

    @property
    def capturing(self) -> bool:
        return self._capture is not None

    @property
    def selected_row(self) -> int:
        return self.model.current_index

    @property
    def rows(self) -> list[BindingRow]:
        """The binding grid, memoised on everything the cells depend on.

        Building the row graph ran two cell formatters per row per frame,
        including a ``pygame.key.name`` lookup for every bound key. The result
        is a pure function of the bindings, the pending capture and the
        selected row, so it is rebuilt only when one of those changes.
        """
        bindings = self.game.settings.bindings
        if (
            self._rows_cache is None
            or self._rows_bindings is not bindings
            or self._rows_capture != self._capture
            or self._rows_index != self.model.current_index
        ):
            self._rows_cache = self._build_rows()
            self._rows_bindings = bindings
            self._rows_capture = self._capture
            self._rows_index = self.model.current_index
        return self._rows_cache

    def _build_rows(self) -> list[BindingRow]:
        result = [
            BindingRow(spec.label, self._keyboard_cell(spec), self._gamepad_cell(spec))
            for spec in self.specs
        ]
        if self.section == self.MENU_SECTION:
            # The stick Y inversion is a control setting, not a video one, so
            # it lives here next to the bindings it affects. It is a toggle,
            # not a remappable slot: no cell to capture.
            result.append(self._invert_y_row())
        result.append(
            BindingRow(
                "Reset to defaults",
                BindingCell("Reset this section"),
                BindingCell("Keyboard + gamepad"),
                RowKind.BACK,
            )
        )
        result.append(
            BindingRow(
                "Back",
                BindingCell("Esc / right click"),
                BindingCell("B / right click"),
                RowKind.BACK,
            )
        )
        return result

    def _invert_y_row(self) -> BindingRow:
        inverted = self.game.settings.bindings.menu.invert_y
        return BindingRow(
            "Invert stick Y",
            BindingCell("normal" if not inverted else "inverted"),
            BindingCell("left stick", muted=True),
            RowKind.BACK,
        )

    def _keyboard_cell(self, spec: RebindSpec) -> BindingCell:
        if self._capture == (self.model.current_index, KEYBOARD_COLUMN):
            return BindingCell("Press a key…", True)
        value: object
        if spec.action is None:
            value = self.game.settings.bindings.menu.new_game_key
        else:
            value = self._context().keyboard.get(spec.action)
        if spec.side is not None and isinstance(value, tuple):
            value = value[spec.side]
        key_text = self._key_text(value)
        if spec.action is not None and self.section == self.MENU_SECTION:
            mouse_button = self.game.settings.bindings.menu.mouse_buttons.get(spec.action)
            if mouse_button is not None:
                key_text = f"{key_text} / mouse {mouse_button}"
        return BindingCell(key_text, muted=value is None)

    def _gamepad_cell(self, spec: RebindSpec) -> BindingCell:
        if self._capture == (self.model.current_index, GAMEPAD_COLUMN):
            return BindingCell("Press button / axis / d-pad…", True)
        if spec.action is None:
            return BindingCell("not available", muted=True)
        return BindingCell(self._gamepad_text(spec))

    def _context(self) -> GameplayBindings | MenuBindings:
        bindings = self.game.settings.bindings
        return bindings.gameplay if self.section == self.GAMEPLAY_SECTION else bindings.menu

    def _gamepad_text(self, spec: RebindSpec) -> str:
        if spec.action is None:
            return "unbound"
        context = self._context()
        parts: list[str] = []
        button = context.gamepad_buttons.get(spec.action)
        if spec.side is not None and isinstance(button, tuple):
            button = button[spec.side]
        if button is not None:
            parts.append(f"button {self._index_text(button)}")
        axis = context.gamepad_axes.get(spec.action)
        if axis is not None:
            parts.append(f"axis {axis}")
        hat = context.gamepad_hats.get(spec.action)
        if hat is not None:
            parts.append(f"hat {self._index_text(hat)}")
        return " / ".join(parts) or "unbound"

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if self._ignore_routed:
            self._ignore_routed = False
            return
        if self._capture is not None:
            return
        # This screen moves the cursor through ``MenuModel.move`` directly
        # instead of ``MenuModel.handle_routed``, so it has to honour the same
        # release contract: the router emits one extra event carrying the held
        # action when the stick returns to neutral, and acting on it made a
        # single press skip two rows — the controls screens felt unresponsive
        # with a pad.
        if MenuModel.is_release(routed_input.variant):
            return
        self._navigate(routed_input)

    def _navigate(self, routed_input: RoutedInput) -> None:
        action = routed_input.action
        if action is InputAction.UI_BACK or (
            action is InputAction.UI_CANCEL and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.pop()
            return
        if action in (InputAction.UI_UP, InputAction.UI_DOWN):
            self.model.move(-1 if action is InputAction.UI_UP else 1)
        elif action is InputAction.UI_LEFT:
            self.selected_column = KEYBOARD_COLUMN
        elif action is InputAction.UI_RIGHT:
            self.selected_column = GAMEPAD_COLUMN
        elif action is InputAction.UI_POINTER_MOVE and routed_input.position:
            self._pointer(routed_input.position, False)
        elif action is InputAction.UI_POINTER_DOWN and routed_input.position:
            self._pointer(routed_input.position, True)
        elif action is InputAction.UI_CONFIRM:
            self._activate()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._capture is None:
            return
        if event.type == pygame.KEYDOWN:
            self._capture_key(getattr(event, "key", -1))
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._capture_mouse_button(getattr(event, "button", -1))
        elif event.type == pygame.JOYBUTTONDOWN:
            self._capture_button(getattr(event, "button", -1))
        elif event.type == pygame.JOYAXISMOTION:
            self._capture_axis(getattr(event, "axis", -1), float(getattr(event, "value", 0.0)))
        elif event.type == pygame.JOYHATMOTION:
            self._capture_hat(getattr(event, "hat", -1), getattr(event, "value", (0, 0)))

    def _pointer(self, position: tuple[int, int], activate: bool) -> None:
        """Hover moves the focus; a click acts exactly like Enter on that row.

        The whole row is a target, not just the two binding cells: the label
        gutter and the row padding carry no cell of their own, and leaving
        them dead made the pointer focus look like it skipped rows.
        """
        hit = self.view.cell_at(position)
        if hit is not None:
            self.model.set_items(self.model.items, hit.row)
            self.selected_column = hit.column
            if activate:
                # A non-rebindable row (invert Y, Reset, Back) focuses like any
                # other, but a click activates it instead of opening a capture
                # it could never fill.
                if hit.rebindable:
                    self._start_capture(hit.row, hit.column)
                else:
                    self._activate()
            return
        for index, rect in enumerate(self.view.row_rects):
            if not rect.collidepoint(position):
                continue
            self.model.set_items(self.model.items, index)
            if activate:
                self._activate()
            return

    def _activate(self) -> None:
        action = self.model.current_item.action if self.model.current_item else None
        if action == "invert_y":
            self._toggle_invert_y()
        elif action == "reset":
            self._reset()
        elif action == "back":
            self.game.scene_manager.pop()
        else:
            self._start_capture(self.model.current_index, self.selected_column)

    def _toggle_invert_y(self) -> None:
        menu = replace(
            self.game.settings.bindings.menu,
            invert_y=not self.game.settings.bindings.menu.invert_y,
        )
        self._apply_bindings(replace(self.game.settings.bindings, menu=menu))
        self._status = "Stick Y inverted" if menu.invert_y else "Stick Y normal"

    def _start_capture(self, row: int, column: int) -> None:
        if 0 <= row < len(self.specs):
            self._capture = (row, column)
            self._pending.clear()
            self._status = "Esc / right click cancels; Delete unbinds keyboard"

    def _cancel_capture(self) -> None:
        self._capture = None
        self._pending.clear()
        self._status = "Capture cancelled"

    def _clear_capture(self) -> None:
        capture = self._capture
        if capture is None or capture[1] != KEYBOARD_COLUMN:
            self._cancel_capture()
            return
        self._clear_keyboard(self.specs[capture[0]])

    def _capture_key(self, key: int) -> None:
        capture = self._capture
        if capture is None or capture[1] != KEYBOARD_COLUMN or key < 0:
            return
        if key == pygame.K_ESCAPE:
            self._ignore_routed = True
            self._cancel_capture()
            return
        spec = self.specs[capture[0]]
        if key == pygame.K_DELETE:
            self._clear_keyboard(spec)
            return
        if spec.side is not None:
            self._apply_keyboard(spec, (key,))
        elif spec.pair:
            if key not in self._pending:
                self._pending.append(key)
            if len(self._pending) == 2:
                self._apply_keyboard(spec, tuple(self._pending))
            return
        self._apply_keyboard(spec, (key,))

    def _capture_mouse_button(self, button: int) -> None:
        capture = self._capture
        if capture is None or button < 0:
            return
        if button == 1:
            self._ignore_routed = True
            self._clear_capture()
            return
        if capture[1] != KEYBOARD_COLUMN:
            self._cancel_capture()
            return
        spec = self.specs[capture[0]]
        if spec.action is None:
            self._status = "This shortcut is keyboard-only"
            return
        self._apply_mouse_button(spec, button)

    def _capture_button(self, button: int) -> None:
        capture = self._capture
        if capture is None or button < 0:
            return
        if capture[1] == KEYBOARD_COLUMN:
            # Un bouton physique est toujours un binding manette : on bascule
            # dans la colonne gamepad sans exiger un aller-retour UI.
            self._capture = (capture[0], GAMEPAD_COLUMN)
            self.selected_column = GAMEPAD_COLUMN
            capture = self._capture
        spec = self.specs[capture[0]]
        if spec.action is None:
            self._status = "This shortcut is keyboard-only"
            return
        if spec.side is not None:
            self._ignore_routed = True
            self._apply_buttons(spec, (button,))
        elif spec.pair:
            if button not in self._pending:
                self._pending.append(button)
            if len(self._pending) == 2:
                self._apply_buttons(spec, tuple(self._pending))
            return
        self._ignore_routed = True
        self._apply_buttons(spec, (button,))

    def _capture_axis(self, axis: int, value: float) -> None:
        capture = self._capture
        if capture is None or capture[1] != GAMEPAD_COLUMN or abs(value) < 0.6:
            return
        self._apply_axis(self.specs[capture[0]], axis)
        self._ignore_routed = self.game.input_router.would_route_axis(axis, value)

    def _capture_hat(self, hat: int, value: object) -> None:
        capture = self._capture
        if capture is None or capture[1] != GAMEPAD_COLUMN or not isinstance(value, (tuple, list)):
            return
        if len(value) < 2 or (int(value[0]) == 0 and int(value[1]) == 0):
            return
        self._apply_hat(self.specs[capture[0]], hat)
        normalized = (int(value[0]), int(value[1]))
        self._ignore_routed = self.game.input_router.would_route_hat(hat, normalized)

    def _reset(self) -> None:
        defaults = InputBindings()
        bindings = self.game.settings.bindings
        if self.section == self.GAMEPLAY_SECTION:
            bindings = replace(bindings, gameplay=defaults.gameplay)
        else:
            bindings = replace(bindings, menu=defaults.menu)
        self._apply_bindings(bindings)
        self._status = "Defaults restored"

    def _clear_keyboard(self, spec: RebindSpec) -> None:
        if spec.action is None:
            menu = replace(self.game.settings.bindings.menu, new_game_key=None)
            self._apply_bindings(replace(self.game.settings.bindings, menu=menu))
        else:
            self._apply_keyboard_map(spec, None)
        self._finish(f"{spec.label} keyboard unbound")

    def _apply_keyboard(self, spec: RebindSpec, keys: tuple[int, ...]) -> None:
        self._apply_keyboard_map(spec, keys[0] if len(keys) == 1 else keys)
        self._ignore_routed = self.game.input_router.would_route_key(keys[-1])
        self._finish(f"{spec.label} → {self._key_text(keys)}")

    def _apply_keyboard_map(self, spec: RebindSpec, value: int | tuple[int, ...] | None) -> None:
        if spec.action is None:
            menu = replace(
                self.game.settings.bindings.menu,
                new_game_key=cast(int | None, value),
            )
            self._apply_bindings(replace(self.game.settings.bindings, menu=menu))
            return
        context = self._context()
        keyboard = dict(context.keyboard)
        value = self._merge_side_value(context, spec, value)
        if spec.action is not None and spec.side is not None and value is None:
            return
        codes = set(self._codes(value))
        for action, other in list(keyboard.items()):
            if action == spec.action:
                continue
            overlap = codes & set(self._codes(other))
            if not overlap:
                continue
            remaining = tuple(code for code in self._codes(other) if code not in overlap)
            if not remaining:
                keyboard.pop(action)
            elif len(remaining) == 1:
                keyboard[action] = remaining[0]
            else:
                keyboard[action] = remaining
        if value is None:
            keyboard.pop(spec.action, None)
        else:
            keyboard[spec.action] = value
        self._replace_context(keyboard=keyboard)

    def _merge_side_value(
        self,
        context: GameplayBindings | MenuBindings,
        spec: RebindSpec,
        value: int | tuple[int, ...] | None,
    ) -> int | tuple[int, ...] | None:
        if spec.action is None or spec.side is None or value is None:
            return value
        current = context.keyboard.get(spec.action)
        if isinstance(current, tuple) and len(current) == 2:
            pair = [current[0], current[1]]
        else:
            pair = [pygame.K_LEFT, pygame.K_RIGHT]
        pair[spec.side] = cast(int, value)
        return pair[0], pair[1]

    def _apply_mouse_button(self, spec: RebindSpec, button: int) -> None:
        if spec.action is None:
            return
        current = dict(self.game.settings.bindings.menu.mouse_buttons)
        for action, other in list(current.items()):
            if action != spec.action and other == button:
                current.pop(action)
        current[spec.action] = button
        self._replace_context(mouse_buttons=current)
        self._ignore_routed = True
        self._finish(f"{spec.label} → mouse button {button}")

    def _apply_buttons(self, spec: RebindSpec, buttons: tuple[int, ...]) -> None:
        if spec.action is None:
            return
        context = self._context()
        current = dict(context.gamepad_buttons)
        if spec.side is not None and spec.action is not None:
            previous = context.gamepad_buttons.get(spec.action)
            if isinstance(previous, tuple) and len(previous) == 2:
                pair = [previous[0], previous[1]]
            else:
                pair = [0, 1]
            pair[spec.side] = buttons[0]
            value: PadBinding = (pair[0], pair[1])
        else:
            value = buttons[0] if len(buttons) == 1 else buttons
        for action, other in list(current.items()):
            if action != spec.action and set(self._codes(other)) & set(buttons):
                if self.section == self.MENU_SECTION and action in (
                    InputAction.UI_BACK,
                    InputAction.UI_CANCEL,
                ):
                    self._status = "B is reserved for Back; rebind Back first"
                    return
                current.pop(action)
        current[spec.action] = value
        if self.section == self.GAMEPLAY_SECTION:
            self._replace_context(
                gamepad_buttons=current,
                gamepad_axes=self._without_action(context.gamepad_axes, spec.action),
                gamepad_hats=self._without_action(context.gamepad_hats, spec.action),
            )
        else:
            self._replace_context(gamepad_buttons=current)
        self._ignore_routed = self.game.input_router.would_route_button(buttons[-1])
        self._finish(f"{spec.label} → button {self._index_text(value)}")

    def _apply_axis(self, spec: RebindSpec, axis: int) -> None:
        if spec.action is None:
            return
        context = self._context()
        current = dict(context.gamepad_axes)
        for action, old_axis in list(current.items()):
            if action != spec.action and old_axis == axis:
                current.pop(action)
        paired = self._paired_actions(spec.action)
        for action in paired:
            current[action] = axis
        self._replace_context(
            gamepad_axes=current,
            gamepad_buttons=self._without_action(context.gamepad_buttons, spec.action),
            gamepad_hats=self._without_action(context.gamepad_hats, spec.action),
        )
        self._finish(f"{spec.label} → axis {axis}")

    def _apply_hat(self, spec: RebindSpec, hat: int) -> None:
        if spec.action is None:
            return
        context = self._context()
        current = dict(context.gamepad_hats)
        for action in self._paired_actions(spec.action):
            current[action] = hat
        self._replace_context(
            gamepad_hats=current,
            gamepad_buttons=self._without_action(context.gamepad_buttons, spec.action),
            gamepad_axes=self._without_action(context.gamepad_axes, spec.action),
        )
        self._finish(f"{spec.label} → hat {self._index_text(hat)}")

    @staticmethod
    def _paired_actions(action: InputAction) -> tuple[InputAction, ...]:
        if action is InputAction.UI_UP:
            return InputAction.UI_UP, InputAction.UI_DOWN
        if action is InputAction.UI_DOWN:
            return InputAction.UI_UP, InputAction.UI_DOWN
        if action is InputAction.UI_LEFT:
            return InputAction.UI_LEFT, InputAction.UI_RIGHT
        if action is InputAction.UI_RIGHT:
            return InputAction.UI_LEFT, InputAction.UI_RIGHT
        return (action,)

    @staticmethod
    def _without_action(
        values: Mapping[InputAction, T], action: InputAction
    ) -> dict[InputAction, T]:
        return {key: value for key, value in values.items() if key != action}

    def _replace_context(self, **changes: Any) -> None:
        bindings = self.game.settings.bindings
        if self.section == self.GAMEPLAY_SECTION:
            self._apply_bindings(replace(bindings, gameplay=replace(bindings.gameplay, **changes)))
        else:
            self._apply_bindings(replace(bindings, menu=replace(bindings.menu, **changes)))

    def _apply_bindings(self, bindings: Any) -> None:
        self.game.apply_bindings(bindings)

    def _finish(self, message: str) -> None:
        self._capture = None
        self._pending.clear()
        self._status = message

    @staticmethod
    def _codes(value: object) -> tuple[int, ...]:
        if isinstance(value, tuple):
            return tuple(int(code) for code in value)
        if isinstance(value, int):
            return (value,)
        return ()

    @staticmethod
    def _key_text(value: object) -> str:
        if value is None:
            return "unbound"
        codes = ControlsScene._codes(value)
        names = (ControlsScene._key_name(code) for code in codes)
        return " / ".join(names)

    @staticmethod
    def _key_name(code: int) -> str:
        """``pygame.key.name`` uppercased, memoised.

        SDL looks the name up in a table on every call; the grid asks for one
        per bound key, per row, per frame.
        """
        cached = ControlsScene._key_names.get(code)
        if cached is None:
            cached = pygame.key.name(code).upper()
            ControlsScene._key_names[code] = cached
        return cached

    @staticmethod
    def _index_text(value: object) -> str:
        return "/".join(str(code) for code in ControlsScene._codes(value))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        self.view.set_scale(self.game.settings.ui_scale)
        title = "MENU CONTROLS" if self.section == self.MENU_SECTION else "GAMEPLAY CONTROLS"
        footers: tuple[str, ...] = ("↑↓ row · ←→ column · Enter capture · Esc/B back",)
        if self._status:
            footers = (self._status, *footers)
        self.view.draw(
            surface,
            title,
            "Keyboard / mouse" if self.selected_column == KEYBOARD_COLUMN else "Gamepad",
            self.rows,
            selected_row=self.model.current_index,
            selected_column=self.selected_column,
            top=80,
            footers=footers,
        )
        return None

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)
