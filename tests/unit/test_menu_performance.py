"""Structural guards against the menu per-frame cost regressions.

The menu screens are the only place where a whole UI is redrawn 60 times a
second, and the failures that matter here are silent: a dropped cache, a
rebuild per frame or a repeated surface allocation costs a millisecond or two
without breaking a single behavioural assertion.

Every test below therefore counts *how many times* something happens instead
of measuring elapsed time, which keeps them deterministic and free of the
flakiness a timing budget would introduce on shared CI runners.
"""

import os
from dataclasses import replace

import pygame
import pytest

from src.application.scenes.pause_scene import PauseScene
from src.application.scenes.video_scene import VideoScene
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import letterbox
from src.core.display.mode import DisplayMode
from src.core.game import Game
from src.core.input.event_router import EventRouter, InputDevice
from src.core.input.input_actions import InputAction
from src.core.settings import Input as InputSettings
from src.ui.controls_view import BindingCell, BindingRow, ControlsView
from src.ui.fonts import ui_font  # noqa: F401 (patched by the font-build counter)
from src.ui.grid_view import GridView
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import GOLD


@pytest.fixture(scope="module", autouse=True)
def _menu_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1280, 720))


@pytest.fixture()
def game(tmp_path):
    """A runtime bound to a temporary settings file, without the main loop."""
    runtime = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    runtime.initialize_display()
    runtime.clock = pygame.time.Clock()
    return runtime


@pytest.fixture()
def surface() -> pygame.Surface:
    return pygame.display.get_surface()


@pytest.fixture()
def manager(game):
    return game.scene_manager


@pytest.fixture()
def counter(monkeypatch):
    """Count calls to a target attribute, keeping the original behaviour.

    Returns a factory so each test installs its own spy and reads its own
    count: ``count = counter(pygame.display, "set_mode")``.
    """

    def install(target, name: str):
        calls: list[tuple] = []
        original = getattr(target, name)

        def wrapper(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(target, name, wrapper)
        return lambda: len(calls)

    return install


def _count_font_builds(monkeypatch):
    """Count font constructions, returning a counter."""
    made: list[tuple] = []
    original = ui_font
    monkeypatch.setattr(
        "src.ui.menu_view.ui_font", lambda *a, **k: made.append(a) or original(*a, **k)
    )
    return lambda: len(made)


def test_unchanged_scale_does_not_rebuild_menu_fonts(monkeypatch, surface) -> None:
    """``set_scale`` is called from ``draw()`` by several scenes.

    Fonts are created lazily by the first draw after a reset, so the regression
    only shows up if the test actually draws in between: an unchanged scale
    must keep the cached fonts instead of rebuilding two ``SysFont`` objects
    and re-rendering every label on every frame.
    """
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView(1.0)
    view.draw(surface, "TITLE", model, top=120)
    made = _count_font_builds(monkeypatch)

    view.set_scale(1.0)
    view.draw(surface, "TITLE", model, top=120)
    view.draw(surface, "TITLE", model, top=120)

    assert made() == 0


def test_changed_scale_still_rebuilds_menu_fonts(monkeypatch, surface) -> None:
    """The early return must not turn ``set_scale`` into a no-op."""
    model = MenuModel([MenuItem("one", "One")])
    view = MenuView(1.0)
    view.draw(surface, "TITLE", model, top=120)
    made = _count_font_builds(monkeypatch)

    view.set_scale(1.2)
    view.draw(surface, "TITLE", model, top=120)

    assert made() > 0


def test_menu_view_caches_rendered_text(surface) -> None:
    """Labels are re-rendered only when their text, row or scale changes."""
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView(1.0)
    view.draw(surface, "TITLE", model, top=120)
    first = {id(text) for text in view._text_cache.values()}

    view.draw(surface, "TITLE", model, top=120)

    assert {id(text) for text in view._text_cache.values()} == first


def test_video_scene_does_not_rebuild_when_settings_are_stable(manager) -> None:
    """The Video screen used to rebuild all six rows on every frame.

    Rebuilding also produced fresh label strings, which invalidated the view's
    text cache, so it cost a rebuild *and* a full re-render each frame.
    """
    scene = VideoScene(manager.game)
    manager.switch(scene)
    scene.draw(pygame.display.get_surface())
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]

    scene.draw(pygame.display.get_surface())
    scene.draw(pygame.display.get_surface())

    assert rebuilt == []


def test_video_scene_rebuilds_once_when_a_setting_changes(manager) -> None:
    scene = VideoScene(manager.game)
    manager.switch(scene)
    scene.draw(pygame.display.get_surface())
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]

    manager.game.settings = replace(manager.game.settings, vsync=not manager.game.settings.vsync)
    scene.draw(pygame.display.get_surface())

    assert len(rebuilt) == 1


def test_the_video_screen_does_not_rebuild_when_settings_are_stable(manager) -> None:
    """The video rows and their text cache must survive an idle frame.

    Rebuilding the rows per frame would mint fresh label strings and invalidate
    the panel's text cache, which is exactly the cost the memoisation exists to
    avoid. The screen also has a line that reports the window, so it is the one
    place where "nothing changed" has to mean the window did not move either.
    """
    scene = VideoScene(manager.game)
    manager.switch(scene)
    scene.draw(pygame.display.get_surface())
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]
    items = scene.model.items

    scene.draw(pygame.display.get_surface())
    scene.draw(pygame.display.get_surface())

    assert rebuilt == []
    assert scene.model.items is items


def test_the_video_screen_rebuilds_once_when_the_window_moves(manager) -> None:
    """The reported window is part of what the screen draws, so it is watched.

    A drag of the window changes the density, and the screen says so. One
    rebuild per change: the signature has to notice, or the row would report a
    window the game is no longer in.
    """
    scene = VideoScene(manager.game)
    manager.switch(scene)
    scene.draw(pygame.display.get_surface())
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]

    manager.game.presentation.stage = pygame.Surface((1920, 1080))  # type: ignore[assignment]
    scene.draw(pygame.display.get_surface())

    assert len(rebuilt) == 1


def test_controls_view_allocates_no_new_surface_when_stable(surface, counter) -> None:
    """The panel and the focus strip are cached by size, not rebuilt per frame."""
    rows = [
        BindingRow("Move up", BindingCell("Up"), BindingCell("button 12")),
        BindingRow("Move down", BindingCell("Down"), BindingCell("button 13")),
    ]
    view = ControlsView(1.0)
    view.draw(surface, "MENU CONTROLS", "Keyboard", rows, selected_row=0, selected_column=0, top=80)

    count = counter(pygame, "Surface")
    view.draw(surface, "MENU CONTROLS", "Keyboard", rows, selected_row=0, selected_column=0, top=80)

    assert count() == 0


def test_controls_view_caches_rendered_text(surface) -> None:
    rows = [BindingRow("Move up", BindingCell("Up"), BindingCell("button 12"))]
    view = ControlsView(1.0)
    view.draw(surface, "MENU CONTROLS", "Keyboard", rows, selected_row=0, selected_column=0, top=80)
    first = {id(text) for text in view._grid._text_cache.values()}
    assert first

    view.draw(surface, "MENU CONTROLS", "Keyboard", rows, selected_row=0, selected_column=0, top=80)

    assert {id(text) for text in view._grid._text_cache.values()} == first


@pytest.mark.parametrize(
    ("text", "max_width", "expected"),
    [
        ("Escape", 200, "Escape"),
        ("", 200, ""),
        ("Escape", 0, ""),
        ("Left Shift", 200, "Left Shift"),
    ],
)
def test_fit_leaves_short_labels_untouched(text: str, max_width: int, expected: str) -> None:
    font = pygame.font.SysFont("Consolas", 22)
    rendered = GridView._fit(font, text, max_width, (255, 255, 255))
    assert rendered.get_width() == font.size(expected)[0]


def test_fit_truncates_with_an_ellipsis() -> None:
    font = pygame.font.SysFont("Consolas", 22)
    text = "Left Joystick Axis 2 (Down)"
    narrow = GridView._fit(font, text, 40, (255, 255, 255))

    assert narrow.get_width() <= 40
    assert narrow.get_width() < font.size(text)[0]


def test_fit_handles_a_very_long_label_quickly() -> None:
    """The previous shrink-one-char-at-a-time loop was quadratic in the length.

    A label long enough to be truncated used to cost 4.8ms in a single call,
    which a 60fps frame cannot absorb.
    """
    font = pygame.font.SysFont("Consolas", 22)
    text = "Left Joystick Axis 2 (Down) extended label " * 12

    start = pygame.time.get_ticks()
    GridView._fit(font, text, 60, (255, 255, 255))
    elapsed_ms = pygame.time.get_ticks() - start

    assert elapsed_ms < 50


class _CountingSurface(pygame.Surface):
    """A surface that records how many times it was filled."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fills = 0

    def fill(self, *args, **kwargs):
        self.fills += 1
        return super().fill(*args, **kwargs)


def test_pause_overlay_is_not_refilled_per_frame(manager) -> None:
    """The overlay is a constant colour, so refilling it per frame is wasted.

    A full-screen ``SRCALPHA`` fill was the most expensive operation in the
    pause frame, and the result was pixel-identical every time.
    """
    scene = PauseScene(manager.game, level_id=0)
    manager.switch(scene)
    scene.draw(pygame.display.get_surface())
    overlay = _CountingSurface(scene._overlay.get_size(), pygame.SRCALPHA)
    overlay.fill(scene._overlay_color)
    scene._overlay = overlay
    overlay.fills = 0

    scene.draw(pygame.display.get_surface())
    scene.draw(pygame.display.get_surface())

    assert overlay.fills == 0


def test_applying_only_the_ui_scale_keeps_the_window(manager, counter) -> None:
    """``set_mode`` on a pure scale change tore the window down and flickered."""
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(pygame.display, "set_mode")

    game.apply_settings(replace(game.settings, ui_scale=1.2))

    assert count() == 0


def test_applying_a_display_mode_change_rebuilds_the_window(manager, counter) -> None:
    """A mode is the only thing left that can replace the window."""
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(pygame.display, "set_mode")
    before = game.presentation.surface

    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW))

    assert count() == 1
    # The target is only replaced when its *size* moved. Under the dummy driver
    # both modes hand back the same size, so the picture keeps its size. It is
    # the window's letterbox, not the window: comparing the two directly used
    # to read `or True`, which was hiding that the assertion is false whenever
    # the aspect ratio bars are not zero.
    assert game.presentation.surface.get_size() == before.get_size()
    assert game.presentation.surface.get_size()[1] <= game.stage.size[1]


def test_whole_pixel_art_rebuilds_the_target_without_rebuilding_the_window(
    manager, counter
) -> None:
    """The letterbox changes, so the target does, and the window does not.

    The one setting that resizes the picture without touching the window. It used
    to be a row that could not exist -- a fixed target had nothing to snap -- and
    it is the reason the letterbox is not a constant any more.
    """
    game = manager.game
    manager.switch(VideoScene(game))
    # Pinned: whole-pixel art needs a window with room for a whole multiple of
    # the framing, and under the dummy driver the desktop is whatever the last
    # test left behind.
    window = pygame.Surface((2560, 1440))
    game.presentation.retarget(window)  # type: ignore[arg-type]
    count = counter(pygame.display, "set_mode")
    before = game.presentation.surface

    game.apply_settings(replace(game.settings, pixel_perfect=True))

    assert count() == 0, "the window must survive a letterbox change"
    assert game.presentation.surface is not before
    assert game.presentation.rect.size == (2304, 1296)
    assert game.presentation.rect.size[0] % round(DEFAULT_FRAMING.width) == 0
    assert game.presentation.density == 2.0


def test_the_letterbox_setting_and_the_letterbox_itself_cannot_disagree(manager) -> None:
    """The setting, the presentation and the picture: one truth, three readers.

    Found by the acceptance run, which applies a display change and a sharpness
    change in the same pass and then watches a window that does not match the
    menu. The cause was ordering: the flag was written on the branch that does
    *not* rebuild the window, so a change that did rebuild it left the
    presentation snapping to whole pixels with the setting saying otherwise, and
    nothing failed -- the target was simply the wrong size.

    So this walks every combination, on a window where both answers differ.
    """
    game = manager.game
    manager.switch(VideoScene(game))
    fitted = letterbox((2560, 1440), DEFAULT_FRAMING).size
    whole = letterbox((2560, 1440), DEFAULT_FRAMING, pixel_perfect=True).size
    assert fitted != whole, "this test needs a window where the two answers differ"

    for display in (DisplayMode.WINDOW, DisplayMode.BORDERLESS, DisplayMode.FULLSCREEN):
        for pixel_perfect in (False, True):
            game.apply_settings(
                replace(game.settings, display=display, pixel_perfect=pixel_perfect)
            )

            # The setting reached the letterbox, whichever path was taken.
            assert game.presentation.pixel_perfect is pixel_perfect

            # And on a window where the two answers differ, the picture is the
            # one the flag asks for. Pinned after the change, because applying a
            # display mode rebuilds the window from the desktop.
            game.presentation.retarget(pygame.Surface((2560, 1440)))  # type: ignore[arg-type]
            game._retarget()
            expected = whole if pixel_perfect else fitted
            assert game.presentation.rect.size == expected, (
                f"{display.value} pixel_perfect={pixel_perfect}: the picture is "
                f"{game.presentation.rect.size}, expected {expected}"
            )
            assert game.presentation.surface.get_size() == expected


def test_whole_pixel_art_is_a_no_op_on_a_window_that_cannot_hold_one(manager, counter) -> None:
    """Nothing to snap to, so nothing changes -- and the row says so.

    A window narrower than the framing has no whole multiple to snap to, and
    clamping one down to the window would hand back a rectangle of the wrong
    aspect: a target whose two axes imply different densities, which is refused.
    """
    game = manager.game
    manager.switch(VideoScene(game))
    window = pygame.Surface((800, 600))
    game.presentation.retarget(window)  # type: ignore[arg-type]
    before = game.presentation.surface
    count = counter(pygame.display, "set_mode")

    game.apply_settings(replace(game.settings, pixel_perfect=True))

    assert game.presentation.surface is before
    assert game.presentation.rect.size == (800, 450)
    assert count() == 0


def test_applying_only_the_ui_scale_still_updates_the_scenes(manager) -> None:
    """The layout is the preference times the density, and both reach the views."""
    game = manager.game
    scene = VideoScene(game)
    manager.switch(scene)

    game.apply_settings(replace(game.settings, ui_scale=1.2))

    assert scene.view._scale == pytest.approx(1.2 * game.presentation.density)


def test_settings_writes_are_coalesced(manager, counter) -> None:
    """The JSON rewrite blocked the frame on every keypress in the menus."""
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(game.settings_store, "save")

    game.apply_settings(replace(game.settings, ui_scale=1.2))
    game.apply_settings(replace(game.settings, ui_scale=0.8))

    assert count() == 0

    game.flush_settings()
    game.flush_settings()

    assert count() == 1


def test_pending_settings_are_flushed_when_the_game_ends(manager, counter) -> None:
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(game.settings_store, "save")
    game.apply_settings(replace(game.settings, ui_scale=1.2))

    game.flush_settings()

    assert count() == 1


def _router(clock) -> EventRouter:
    return EventRouter(clock=clock)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_held_navigation_key_repeats() -> None:
    clock = _Clock()
    router = _router(clock)
    router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))

    clock.now = InputSettings.UI_REPEAT_INITIAL_DELAY + 0.01
    repeats = router.poll_repeats()

    assert [item.action for item in repeats] == [InputAction.UI_DOWN]
    assert repeats[0].device is InputDevice.KEYBOARD
    assert repeats[0].variant == "repeat"


def test_a_navigation_key_does_not_repeat_before_the_delay() -> None:
    clock = _Clock()
    router = _router(clock)
    router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))

    clock.now = InputSettings.UI_REPEAT_INITIAL_DELAY - 0.01

    assert router.poll_repeats() == []


def test_releasing_a_key_stops_the_repeat() -> None:
    clock = _Clock()
    router = _router(clock)
    router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    router.route(pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN))

    clock.now = 10.0

    assert router.poll_repeats() == []


def test_a_router_reset_silences_a_held_key() -> None:
    """Every push, pop and switch calls ``reset``.

    This is what makes the keyboard repeat safe: a key held across a scene
    transition cannot keep firing into the scene that just appeared.
    """
    clock = _Clock()
    router = _router(clock)
    router.route(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    clock.now = 10.0
    assert router.poll_repeats() != []

    router.reset()

    assert router.poll_repeats() == []


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_ESCAPE])
def test_confirm_and_back_never_repeat(key: int) -> None:
    """A repeating confirm or back would open and close a menu in a loop."""
    clock = _Clock()
    router = _router(clock)
    router.route(pygame.event.Event(pygame.KEYDOWN, key=key))

    clock.now = 30.0

    assert router.poll_repeats() == []


def test_new_game_shortcut_keeps_its_variant() -> None:
    router = EventRouter(clock=_Clock())
    routed = router.route(
        pygame.event.Event(pygame.KEYDOWN, key=router._bindings.menu.new_game_key)
    )

    assert routed is not None
    assert routed.variant == "new_game"


def test_the_flash_colour_differs_from_the_selected_row() -> None:
    """Both are amber in the same panel, so the flash would be invisible."""
    from src.ui.styles import TEXT_WARN

    assert GOLD != TEXT_WARN
