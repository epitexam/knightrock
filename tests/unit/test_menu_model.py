import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel


def test_menu_model_moves_with_wrap_and_skips_disabled_items() -> None:
    model = MenuModel(
        [
            MenuItem("one", "One"),
            MenuItem("locked", "Locked", False),
            MenuItem("two", "Two"),
        ]
    )

    assert model.current_index == 0
    assert model.move(1) == "move_down"
    assert model.current_index == 2
    assert model.move(1) == "move_down"
    assert model.current_index == 0
    assert model.move(-1) == "move_up"
    assert model.current_index == 2


def test_menu_model_handles_hover_activation_and_empty_state() -> None:
    empty = MenuModel()
    assert empty.current_item is None
    assert empty.move(1) is None

    model = MenuModel([MenuItem("one", "One"), MenuItem("locked", "Locked", False)])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    assert model.hover((1, 1), rects) == "hover"
    assert model.activate() == "one"
    assert model.hover((1, 15), rects) is None
    assert model.activate() == "one"


def test_menu_model_routes_pointer_down_and_confirm() -> None:
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(0, 10, 10, 10)]

    action, _ = model.handle_routed(InputAction.UI_POINTER_DOWN, (1, 15), rects)
    assert action == "two"

    model.set_items([MenuItem("one", "One"), MenuItem("two", "Two")])
    action, _ = model.handle_routed(InputAction.UI_CONFIRM, None, rects)
    assert action == "one"


def test_menu_model_rejects_invalid_scale() -> None:
    from src.ui.menu_view import MenuView

    with pytest.raises(ValueError, match="UI scale"):
        MenuView(scale=2.0)
