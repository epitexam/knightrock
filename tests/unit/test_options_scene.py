from types import SimpleNamespace

from src.application.scenes.options_scene import OptionsScene
from src.application.settings_store import UserSettings
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction


def _game() -> SimpleNamespace:
    game = SimpleNamespace(
        settings=UserSettings(),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
    )

    def apply_settings(settings: UserSettings) -> None:
        game.settings = settings

    game.apply_settings = apply_settings
    return game


def test_options_cycles_ui_scale_and_persists_runtime_settings() -> None:
    game = _game()
    scene = OptionsScene(game)

    scene.handle_routed(RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD))

    assert game.settings.ui_scale == 1.2
    assert scene.model.current_item is not None
    assert scene.model.current_item.action == "scale"


def test_options_can_return_to_previous_scene() -> None:
    calls: list[str] = []
    game = _game()
    game.scene_manager.pop = lambda: calls.append("pop")
    scene = OptionsScene(game)

    scene.handle_routed(RoutedInput(InputAction.UI_BACK, InputDevice.KEYBOARD))

    assert calls == ["pop"]


def test_options_back_via_gamepad_and_mouse() -> None:
    """Bouton B (manette) et clic droit = retour, comme ESC."""
    calls: list[str] = []
    game = _game()
    game.scene_manager.pop = lambda: calls.append("pop")

    OptionsScene(game).handle_routed(RoutedInput(InputAction.UI_BACK, InputDevice.GAMEPAD))
    OptionsScene(game).handle_routed(RoutedInput(InputAction.UI_BACK, InputDevice.MOUSE))
    OptionsScene(game).handle_routed(RoutedInput(InputAction.UI_CANCEL, InputDevice.GAMEPAD))

    assert calls == ["pop", "pop", "pop"]
