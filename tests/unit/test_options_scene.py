"""The Options screen is a navigation hub: no setting of its own.

Each value lives in the screen that owns it (Video settings, Controls), so a
setting has a single source of truth and a single place to change it.
"""

from types import SimpleNamespace

from src.application.scenes.controls_category_scene import ControlsCategoryScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.video_scene import VideoScene
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


def _confirm() -> RoutedInput:
    return RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD)


def _actions(scene) -> list[str]:
    return [item.action for item in scene.model.items]


def test_options_is_a_category_hub_without_duplicated_settings() -> None:
    """No toggle in the hub: the display/control values live elsewhere."""
    scene = OptionsScene(_game())

    assert _actions(scene) == ["video", "controls", "back"]


def test_options_holds_no_video_or_stick_toggle() -> None:
    """The previous Fullscreen/VSync/UI scale/Stick Y rows are gone here."""
    scene = OptionsScene(_game())
    labels = " ".join(item.label.lower() for item in scene.model.items)

    for removed in ("fullscreen", "vsync", "scale", "stick"):
        assert removed not in labels


def test_options_has_no_reset_because_it_owns_nothing() -> None:
    """Each sub-menu resets what it owns; a hub with no value has no reset."""
    assert "reset" not in _actions(OptionsScene(_game()))


def test_options_opens_the_video_and_controls_screens() -> None:
    pushed: list[object] = []
    game = _game()
    game.scene_manager.push = pushed.append
    scene = OptionsScene(game)

    scene.handle_routed(_confirm())
    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    scene.handle_routed(_confirm())

    assert isinstance(pushed[0], VideoScene)
    assert isinstance(pushed[1], ControlsCategoryScene)


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


def test_video_menu_owns_every_display_setting() -> None:
    assert _actions(VideoScene(_game())) == [
        "resolution",
        "fullscreen",
        "vsync",
        "scale",
        "reset",
        "back",
    ]
