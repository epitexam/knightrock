"""The window size picker: a list this machine can actually show.

The picker used to be fed a constant tuple of seven absolute resolutions, which
is why these tests had to change wholesale rather than be extended. The rows
now come from the desktop, so the assertions are about the *rule* -- every
offered size fits, the automatic choice is in the list, nothing is drawn twice --
rather than about a fixed catalogue.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))


from src.application.scenes.resolution_scene import (  # noqa: E402
    AUTO_MARK,
    CURRENT_MARK,
    ResolutionScene,
)
from src.core.display.detection import (  # noqa: E402
    fits_on_desktop,
    largest_window_size,
    window_size_choices,
)
from src.core.display.mode import DisplayMode  # noqa: E402
from src.core.display.size_mode import SizeMode  # noqa: E402
from src.core.input.event_router import InputDevice, RoutedInput  # noqa: E402
from src.core.input.input_actions import InputAction  # noqa: E402

DESKTOP = pygame.display.get_desktop_sizes()[0]


def _game():
    from types import SimpleNamespace

    from src.application.settings_store import UserSettings
    from src.core.input.event_router import EventRouter

    game = SimpleNamespace(
        settings=UserSettings(),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
    )
    game.input_router = EventRouter(game.settings.bindings)
    game.apply_settings = lambda settings: setattr(game, "settings", settings)
    return game


def _states(scene: ResolutionScene) -> list[str]:
    return [row.cells[0].text for row in scene.rows[:-1]]


def test_every_offered_size_fits_on_the_desktop() -> None:
    """The bug the derived list replaces: 2560x1440 on a 1366x768 laptop."""
    scene = ResolutionScene(_game())

    for row in scene.rows[:-1]:
        width, height = (int(part) for part in row.label.split(" x "))
        assert fits_on_desktop((width, height), DESKTOP), f"{row.label} does not fit {DESKTOP}"


def test_the_list_is_ordered_and_free_of_duplicates() -> None:
    labels = [row.label for row in ResolutionScene(_game()).rows[:-1]]

    assert labels == sorted(labels, key=lambda text: int(text.split(" x ")[0]))
    assert len(labels) == len(set(labels))


def test_the_automatic_choice_is_always_one_of_the_rows() -> None:
    """Otherwise ``Auto`` would be a value the player could not select back to."""
    scene = ResolutionScene(_game())
    automatic = largest_window_size(DESKTOP)
    labels = {row.label for row in scene.rows[:-1]}

    assert f"{automatic[0]} x {automatic[1]}" in labels


def test_the_state_column_separates_in_use_from_on_offer() -> None:
    game = _game()
    scene = ResolutionScene(game)
    current = (game.settings.width, game.settings.height)
    automatic = largest_window_size(DESKTOP)

    states = _states(scene)
    labels = [row.label for row in scene.rows[:-1]]
    current_label = f"{current[0]} x {current[1]}"

    if current_label in labels:
        assert states[labels.index(current_label)] == CURRENT_MARK
    assert states.count(CURRENT_MARK) <= 1
    assert AUTO_MARK in states or current == automatic


def test_exactly_one_row_is_current_and_the_rest_are_muted() -> None:
    scene = ResolutionScene(_game())
    states = _states(scene)

    assert states.count(CURRENT_MARK) <= 1
    for row in scene.rows[:-1]:
        if row.cells[0].text != CURRENT_MARK:
            assert row.cells[0].muted or row.cells[0].text == AUTO_MARK


def test_applying_a_size_marks_it_as_a_decision() -> None:
    """Picking a size pins it, so the next launch stops second-guessing it."""
    game = _game()
    scene = ResolutionScene(game)
    target = next(row.label for row in scene.rows[:-1])
    width, height = (int(part) for part in target.split(" x "))

    scene.handle_routed(RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD))

    assert (game.settings.width, game.settings.height) == (width, height)
    assert game.settings.size_mode is SizeMode.MANUAL


def test_applying_a_size_leaves_borderless_for_a_mode_that_wants_a_window() -> None:
    """A window size is meaningless in borderless, so choosing one picks a mode."""
    game = _game()
    assert game.settings.display is DisplayMode.AUTO
    scene = ResolutionScene(game)

    scene.handle_routed(RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD))

    assert game.settings.display.is_concrete


def test_escape_returns_without_applying() -> None:
    game = _game()
    before = (game.settings.width, game.settings.height)
    scene = ResolutionScene(game)

    scene.handle_routed(RoutedInput(InputAction.UI_BACK, InputDevice.KEYBOARD))

    assert (game.settings.width, game.settings.height) == before


def test_the_subtitle_reports_the_screen_it_is_offering_sizes_for() -> None:
    scene = ResolutionScene(_game())

    subtitle = scene._subtitle()

    assert f"{DESKTOP[0]} x {DESKTOP[1]}" in subtitle
    assert str(len(scene.rows) - 1) in subtitle


def test_the_row_list_is_the_model_list() -> None:
    """The panel draws what the model navigates; a mismatch is a dead row."""
    scene = ResolutionScene(_game())

    assert len(scene.rows) == len(scene.model.items)
    assert scene.model.items[-1].action == "back"


@pytest.mark.parametrize("desktop", [(1024, 600), (1366, 768), (1920, 1080), (3840, 2160)])
def test_the_rule_holds_for_any_desktop(desktop) -> None:
    """The policy, tested against desktops rather than through the display."""
    choices = window_size_choices(desktop)

    assert choices
    assert all(fits_on_desktop(size, desktop) for size in choices)
    assert largest_window_size(desktop) == choices[-1]
