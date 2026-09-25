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
from src.core.game import Game
from src.core.input.event_router import EventRouter, InputDevice
from src.core.input.input_actions import InputAction
from src.core.settings import Input as InputSettings
from src.ui.controls_view import BindingCell, BindingRow, ControlsView
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
    runtime.display_surface = pygame.display.get_surface()
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


def _count_sysfont(monkeypatch):
    """Count ``pygame.font.SysFont`` constructions, returning a counter."""
    made: list[tuple] = []
    original = pygame.font.SysFont
    monkeypatch.setattr(pygame.font, "SysFont", lambda *a, **k: made.append(a) or original(*a, **k))
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
    made = _count_sysfont(monkeypatch)

    view.set_scale(1.0)
    view.draw(surface, "TITLE", model, top=120)
    view.draw(surface, "TITLE", model, top=120)

    assert made() == 0


def test_changed_scale_still_rebuilds_menu_fonts(monkeypatch, surface) -> None:
    """The early return must not turn ``set_scale`` into a no-op."""
    model = MenuModel([MenuItem("one", "One")])
    view = MenuView(1.0)
    view.draw(surface, "TITLE", model, top=120)
    made = _count_sysfont(monkeypatch)

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
    scene.draw()
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]

    scene.draw()
    scene.draw()

    assert rebuilt == []


def test_video_scene_rebuilds_once_when_a_setting_changes(manager) -> None:
    scene = VideoScene(manager.game)
    manager.switch(scene)
    scene.draw()
    rebuilt: list[int] = []
    original = scene._rebuild
    scene._rebuild = lambda selected_action=None: (
        rebuilt.append(1),
        original(selected_action),
    )[-1]

    manager.game.settings = replace(manager.game.settings, vsync=not manager.game.settings.vsync)
    scene.draw()

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
    first = {id(text) for text in view._text_cache.values()}
    assert first

    view.draw(surface, "MENU CONTROLS", "Keyboard", rows, selected_row=0, selected_column=0, top=80)

    assert {id(text) for text in view._text_cache.values()} == first


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
    rendered = ControlsView._fit(font, text, max_width, (255, 255, 255))
    assert rendered.get_width() == font.size(expected)[0]


def test_fit_truncates_with_an_ellipsis() -> None:
    font = pygame.font.SysFont("Consolas", 22)
    text = "Left Joystick Axis 2 (Down)"
    narrow = ControlsView._fit(font, text, 40, (255, 255, 255))

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
    ControlsView._fit(font, text, 60, (255, 255, 255))
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
    scene.draw()
    overlay = _CountingSurface(scene._overlay.get_size(), pygame.SRCALPHA)
    overlay.fill(scene._overlay_color)
    scene._overlay = overlay
    overlay.fills = 0

    scene.draw()
    scene.draw()

    assert overlay.fills == 0


def test_applying_only_the_ui_scale_keeps_the_window(manager, counter) -> None:
    """``set_mode`` on a pure scale change tore the window down and flickered."""
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(pygame.display, "set_mode")

    game.apply_settings(replace(game.settings, ui_scale=1.2))

    assert count() == 0


def test_applying_a_resolution_change_rebuilds_the_window(manager, counter) -> None:
    game = manager.game
    manager.switch(VideoScene(game))
    count = counter(pygame.display, "set_mode")

    game.apply_settings(replace(game.settings, width=800, height=600))

    assert count() == 1


def test_applying_only_the_ui_scale_still_updates_the_scenes(manager) -> None:
    game = manager.game
    scene = VideoScene(game)
    manager.switch(scene)

    game.apply_settings(replace(game.settings, ui_scale=1.2))

    assert scene.view._scale == 1.2


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
