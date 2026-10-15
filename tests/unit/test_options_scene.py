"""The Options screen is a navigation hub: no setting of its own.

Each value lives in the screen that owns it (Video settings, Controls), so a
setting has a single source of truth and a single place to change it.
"""

from types import SimpleNamespace

import pygame

from src.application.scenes.controls_category_scene import ControlsCategoryScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import UserSettings
from src.core.display.monitors import Monitor, Topology, degraded
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.core.settings import Debug


def _game(topology=None) -> SimpleNamespace:
    desk = degraded(((1152, 648),)) if topology is None else topology
    game = SimpleNamespace(
        settings=UserSettings(),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
        # The views are laid out at the preference times the density, and the
        # video screen reports the window it is in; a stand-in provides both.
        ui_scale=1.0,
        presentation=SimpleNamespace(
            stage=pygame.Surface((1152, 648)),
            pixel_perfect=False,
            window_size=(1152, 648),
            density=1.0,
        ),
        # The video screen asks the runtime what displays exist, so a stand-in
        # has to answer. One screen with no names by default: enough for the rows
        # about pacing and scaling, and it keeps the screen picker out of a test
        # that is about navigation.
        topology=lambda: desk,
        # The screen the window is on, which is what the VSync row reports -- the
        # primary's rate is a claim about a screen the window may not be on.
        window_monitor=lambda: desk.primary,
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
    """Every display row, and none of them a fixed number about the player's screen.

    The rows that stayed away are the ones that could not be honoured: a
    hardcoded resolution list is a claim about a monitor the game cannot measure,
    and a render scale and a smoothing flag described a fixed target that no
    longer exists -- the sharpness was also the setting that went stale, written
    back once at launch and then believed forever.

    The resolution that came back is the one the game can check. The fullscreen
    mode list is read from the driver on this machine rather than written down
    here, and the screen row lists the displays SDL actually reports. Both can
    be wrong about a machine, which is why they are re-read rather than stored.

    The single-screen stand-in here has no names, so the screen row is absent --
    the row that only means something with a choice to make.
    """
    expected = [
        "display",
        "resolution",
        "fit",
        "vsync",
        "frame_limit",
        "scale",
    ]
    # The debug row is conditional on the overlay being on, and this file is run
    # both with and without DEBUG=1 -- so it is placed by where it belongs in the
    # order rather than asserted absent, which would fail the debug run outright.
    if Debug.is_enabled():
        expected.append("panel_scale")
    expected += ["reset", "back", "info"]

    assert _actions(VideoScene(_game())) == expected


def test_the_screen_picker_appears_only_where_there_is_a_choice() -> None:
    """One display means nothing to pick, so the row is not offered.

    A row that always reads "Screen 1" and cannot be acted on is the dead-row
    failure this screen has already produced once, six rows of which highlighted
    on click and changed nothing.
    """
    assert "monitor" not in _actions(VideoScene(_game()))

    desk = Topology(
        monitors=(
            Monitor(0, "DP-1", (0, 0, 2560, 1440), (0, 0, 2560, 1440), 144),
            Monitor(1, "HDMI-1", (2560, 0, 1920, 1080), (2560, 0, 1920, 1080), 60),
        ),
        named=True,
    )
    assert "monitor" in _actions(VideoScene(_game(topology=desk)))
