"""Tests for resource lookup and the top-level game runtime boundary."""

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pygame
import pytest

from src.application.scenes.menu_scene import MenuScene
from src.application.settings_store import UserSettings
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy, letterbox
from src.core.display.monitors import centre_on, fit_size, opening_size
from src.core.display.stage import Stage, WindowSpec
from src.core.display.viewport import Viewport
from src.core.game import Game
from src.core.input.input_actions import InputAction
from src.core.level.level_manager import LevelManager, UnknownLevelError
from src.core.paths import PROJECT_ROOT, resource_path


def test_resource_path_is_independent_from_current_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert (
        Path(resource_path("assets/data/levels/1.tmx"))
        == (PROJECT_ROOT / "assets/data/levels/1.tmx").resolve()
    )


def test_resource_path_uses_pyinstaller_bundle_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert Path(resource_path("assets/example.dat")) == (tmp_path / "assets/example.dat").resolve()


def test_level_manager_raises_clear_error_for_missing_level() -> None:
    manager = LevelManager()
    manager.register(99, "assets/data/levels/does_not_exist.tmx")

    with pytest.raises(FileNotFoundError) as exc_info:
        manager.get(99)

    assert "Level file not found" in str(exc_info.value)


def test_an_unregistered_level_id_is_not_a_bare_key_error() -> None:
    """A stale id from an old save must say so, not raise ``KeyError: 7``.

    The bare-KeyError version of this failure was a crash at launch with no
    message at all, on the path that resolves a save file's ``last_level_id``.
    """
    manager = LevelManager({0: "assets/data/levels/1.tmx", 3: "assets/data/levels/4.tmx"})

    with pytest.raises(UnknownLevelError) as exc_info:
        manager.get(7)

    message = str(exc_info.value)
    assert "7" in message
    assert "0, 3" in message, "the message must name the ids that do exist"


def test_the_two_level_failures_are_distinguishable() -> None:
    """Unregistered id and missing file are different problems, not one."""
    manager = LevelManager()
    manager.register(99, "assets/data/levels/does_not_exist.tmx")

    with pytest.raises(LookupError):
        manager.get(98)
    with pytest.raises(FileNotFoundError):
        manager.get(99)


def test_an_empty_registry_still_produces_a_readable_message() -> None:
    """``known: none`` beats an empty parenthesis nobody can act on."""
    with pytest.raises(UnknownLevelError) as exc_info:
        LevelManager().get(0)

    assert "none" in str(exc_info.value)


def test_run_handles_initialization_errors_and_always_quits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    error = RuntimeError("initialization failed")
    initialize = Mock(side_effect=error)
    handle_fatal_error = Mock()
    quit_pygame = Mock()
    monkeypatch.setattr(game, "_initialize", initialize)
    monkeypatch.setattr(game, "_handle_fatal_error", handle_fatal_error)
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit) as exit_info:
        game.run()

    assert exit_info.value.code == 1
    handle_fatal_error.assert_called_once_with(error)
    quit_pygame.assert_called_once_with()


def test_run_handles_loop_errors_and_always_quits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    error = RuntimeError("loop failed")
    initialize = Mock()
    run_loop = Mock(side_effect=error)
    handle_fatal_error = Mock()
    quit_pygame = Mock()
    monkeypatch.setattr(game, "_initialize", initialize)
    monkeypatch.setattr(game, "_run_loop", run_loop)
    monkeypatch.setattr(game, "_handle_fatal_error", handle_fatal_error)
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit) as exit_info:
        game.run()

    assert exit_info.value.code == 1
    initialize.assert_called_once_with()
    handle_fatal_error.assert_called_once_with(error)
    quit_pygame.assert_called_once_with()


def test_run_quits_when_the_event_loop_requests_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    monkeypatch.setattr(game, "_initialize", Mock())
    monkeypatch.setattr(game, "_run_loop", Mock(side_effect=SystemExit))
    quit_pygame = Mock()
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit):
        game.run()

    quit_pygame.assert_called_once_with()


def test_first_added_joystick_is_assigned_without_private_state_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    joystick = Mock()
    joystick.get_instance_id.return_value = 7
    joystick.get_name.return_value = "Test controller"
    connect_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "connect_joystick", connect_joystick)
    event = pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0)
    monkeypatch.setattr(pygame.event, "get", lambda: [event])
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _index: joystick)

    game._handle_events()

    assert game.joysticks == {7: joystick}
    connect_joystick.assert_called_once_with(joystick)


def test_second_joystick_is_not_assigned_while_first_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    active = Mock()
    active.get_instance_id.return_value = 7
    second = Mock()
    second.get_instance_id.return_value = 8
    connect_joystick = Mock()
    game.joysticks = {7: active}
    game.input_provider.connect_joystick(active)  # type: ignore[arg-type]
    monkeypatch.setattr(game.input_provider, "connect_joystick", connect_joystick)
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _index: second)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEADDED, device_index=1)],
    )

    game._handle_events()

    assert game.joysticks == {7: active, 8: second}
    connect_joystick.assert_not_called()


def test_removed_joystick_is_reassigned_to_remaining_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    removed = Mock()
    removed.get_instance_id.return_value = 7
    removed.get_name.return_value = "Removed controller"
    replacement = Mock()
    replacement.get_instance_id.return_value = 8
    game.joysticks = {7: removed, 8: replacement}
    game.input_provider.connect_joystick(removed)  # type: ignore[arg-type]
    disconnect_joystick = Mock()
    reassign_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "disconnect_joystick", disconnect_joystick)
    monkeypatch.setattr(game.input_provider, "reassign_joystick", reassign_joystick)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=7)],
    )

    game._handle_events()

    assert game.joysticks == {8: replacement}
    disconnect_joystick.assert_called_once_with(7)
    reassign_joystick.assert_called_once_with({8: replacement})


def test_removing_inactive_joystick_keeps_active_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    active = Mock()
    active.get_instance_id.return_value = 7
    removed = Mock()
    removed.get_instance_id.return_value = 8
    removed.get_name.return_value = "Inactive controller"
    game.joysticks = {7: active, 8: removed}
    game.input_provider.connect_joystick(active)  # type: ignore[arg-type]
    reassign_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "reassign_joystick", reassign_joystick)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=8)],
    )

    game._handle_events()

    assert game.joysticks == {7: active}
    reassign_joystick.assert_called_once_with({7: active})


def test_game_applies_persisted_video_settings(tmp_path: Path) -> None:
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()

    game.apply_settings(replace(game.settings, vsync=True))

    assert game.surface is not None
    assert game.surface.get_size() == game.stage.size
    assert game.settings.vsync is True


def test_the_window_is_resizable_and_never_asks_for_a_mode_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One window, and it never asks the driver for a mode.

    The window is resizable and the drag is the point: the window is the render
    target, so a resize is a first-class case rather than something to protect
    the picture from. ``FULLSCREEN`` is never asked for -- the three ways to
    occupy a screen dressed up two flags, and the one that asked the driver for
    a mode change was the shipped default. ``pygame.SCALED`` is deliberately
    absent too: it was doing the letterboxing, which the render target does
    itself, and pygame's own documentation calls it an experimental API.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    set_mode = Mock(wraps=pygame.display.set_mode)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)

    game.apply_settings(replace(game.settings, vsync=not game.settings.vsync))

    windowed_flags = set_mode.call_args.args[1]
    assert windowed_flags & pygame.RESIZABLE
    assert not windowed_flags & pygame.FULLSCREEN
    assert not windowed_flags & pygame.SCALED
    # No size of our own: the desktop decides how big a window to open, and the
    # player drags it from there.
    requested = set_mode.call_args.args[0]
    monitor = game.topology().primary
    assert requested == opening_size(monitor)

    # And the size the player did choose survives the same request.
    game.apply_settings(replace(game.settings, window_size=(1400, 900)))
    assert set_mode.call_args.args[0] == fit_size((1400, 900), monitor)


def _panel(width: int, height: int):
    """A monitor whose usable area is the whole panel, for stage arithmetic."""
    from src.core.display.monitors import Monitor

    return Monitor(index=0, name="", bounds=(0, 0, width, height), usable=(0, 0, width, height))


class _RecordingWindow:
    """A window that goes where it is told, and remembers being asked to.

    Stands in for the ``pygame.Window`` handle in the placement tests, because
    what those are about is the *request*: where the window is asked to sit, and
    what the handle records. A real handle cannot be steered, which is why the
    setter is the seam rather than a ``Mock``: the stage sets ``position`` and
    nothing else on the handle it places.
    """

    def __init__(self) -> None:
        # ``asked`` is created last, so the initial position is set directly and
        # only the stage's requests are recorded.
        self.position: tuple[int, int] = (0, 0)
        self.minimum_size: tuple[int, int] | None = None
        self.asked: list[tuple[int, int]] = []

    def __setattr__(self, name: str, value: object) -> None:
        if name == "position" and "asked" in self.__dict__:
            self.asked.append(value)  # type: ignore[arg-type]
        object.__setattr__(self, name, value)


def test_a_refused_window_size_is_asked_for_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first ``set_mode`` after a window rebuild is dropped; the second is not.

    Measured on the development machine: after a rebuild that picked a size, the
    window came back the size of the player's desktop, with ``Requested window
    size: (1600, 900) / New window size: (2560, 1440)`` on stderr and nothing
    else. The stage read the granted size back -- it had always done that -- and
    then believed it.

    So the platform is simulated here as the one measured: the first request comes
    back at a different size than the one asked for and only the second is
    honoured. A stage that asks once ends up on the wrong size, and the assertion
    is on ``stage.size`` because that is the size the player would have had.
    """
    monitor = _panel(1920, 1080)
    asked: list[tuple[int, int]] = []

    def refuses_the_first_request(size, flags=0, depth=0, display=0, vsync=0):
        # A plain surface rather than a real window: the dummy video driver in CI
        # has an opinion of its own about sizes -- it hands back the desktop's
        # whatever is asked -- and a test about the game re-asking must not be
        # able to pass or fail on that.
        asked.append(size)
        granted = (1280, 1024) if len(asked) == 1 else size
        return pygame.Surface(granted)

    monkeypatch.setattr(pygame.display, "set_mode", refuses_the_first_request)
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (0, 0))
    window = _RecordingWindow()
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: window))

    stage = Stage(WindowSpec(), monitor)

    assert len(asked) >= 2, "a refused size was accepted as if it had been honoured"
    assert stage.size == opening_size(monitor)


def test_the_window_is_centred_on_the_panel_it_opens_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window opens in the middle of the panel it was built for.

    One request and no verification. The retry loop and the ``on_monitor``
    check existed because the menu could ask for a *specific* screen and the
    window manager sometimes refused; there is no such request any more, so a
    refusal has nothing to be wrong about and nothing to retry for.

    The setter is the seam, because that is the whole of what the stage does to
    the window it places: it sets ``position`` and nothing else.
    """
    monitor = _panel(1920, 1080)
    window = _RecordingWindow()
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: window))
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (0, 0))

    stage = Stage(WindowSpec(), monitor)

    assert window.asked == [centre_on(monitor, stage.size)]


def test_a_resize_no_longer_undoes_the_players_own_drag(tmp_path: Path) -> None:
    """A drag is the player's last word, and a settings change must not overrule it.

    Measured: pick 1600x900 from the video menu, drag the window to 1200x800, then
    toggle VSync -- and the window snapped back to 1600x900. The menu promised "a
    normal window; drag it, and its size is remembered" while nothing ever wrote
    the geometry a drag produced, so an earlier preference overruled the player on
    the next rebuild.

    What is forgotten is the *choice*, not the measurement: the stored size goes
    back to ``None``, which now means "follow the window". The file therefore says
    the player stopped choosing a size, rather than carrying a number that
    describes their panel -- which is the rule
    :func:`test_a_window_that_moves_does_not_rewrite_the_settings` is about.

    The window is a :class:`FakeWindow` rather than the live one, because the
    dummy video driver in CI has an opinion of its own about sizes and a test
    about the game's reaction must not be able to pass or fail on that.
    """
    game = _game_in_a_window(tmp_path, window_size=(1600, 900))
    dragged = (1200, 800)

    _resize(game, dragged)
    game.step()

    assert game.settings.window_size is None, "the drag is the player choosing to follow the window"

    with _recording_requests() as requested:
        game.apply_settings(replace(game.settings, vsync=not game.settings.vsync))
    # Asked for as the player left it, and clamped to the panel it opens on --
    # which is the whole contract of ``fit_size``, and the reason the assertion is
    # written against the request rather than the window.
    assert requested[-1] == fit_size(dragged, game.stage.monitor), (  # type: ignore[union-attr]
        "a display setting undid the player's drag"
    )


def test_a_click_after_a_resize_hits_the_row_it_was_aimed_at(tmp_path: Path) -> None:
    """A click is measured against the geometry it is drawn on, not a former one.

    The conversion and the hit-test read two different things: the pointer goes
    through the picture in force *now*, while the rows are the ones the last draw
    produced. After a resize those disagree, and the gap is large -- measured, the
    last row of the video menu was 244px from where it had been drawn, so a click
    landed on a neighbour, on nothing, or on the disabled read-out. That is the
    "the clickable space has moved" report, and it is a wrong row rather than a
    dead one, which is the worst of the two.

    So the frame in which the window moves lays the scenes out before the input is
    read. The assertion is that the rows a click is measured against are the rows
    the frame goes on to draw -- the pointer is aimed nowhere in particular,
    because the point is not where it lands but that both geometries agree.
    """
    game = _game_in_a_window(tmp_path, window_size=(2560, 1440))
    video = _video_scene(game)
    frames(game, 2)
    before = [tuple(rect) for rect in video.view.item_rects]

    # What a pointer event is measured against, at the moment it is dispatched.
    # Captured there rather than after the frame, which would compare the layout
    # with itself and pass either way.
    seen: list[list[pygame.Rect]] = []
    dispatch = video.handle_routed
    video.handle_routed = lambda routed: (  # type: ignore[method-assign]
        seen.append(list(video.view.item_rects)),
        dispatch(routed),
    )[1]

    # The window changes under the game and the pointer arrives on the very next
    # frame. No draw in between: that is the whole point of the ordering.
    #
    # A *move*, not a click, and the reason is this test's own reliability: a
    # click that lands on a value row changes a setting, and a setting like the
    # scale rebuilds the window -- so the frame would end with a *third*
    # geometry and the assertion would be about which row the click happened to
    # find. A move is measured against the very same rectangles and changes
    # nothing, which leaves the geometry as the only variable. ``rel`` is given
    # because a move without a delta is the platform re-reporting a pointer that
    # did not move, and the runtime drops those on purpose.
    _resize(game, (1920, 1080))
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEMOTION, pos=(960, 540), rel=(4, 0), buttons=(0, 0, 0))
    )
    game.step()

    assert seen, "the pointer never reached the scene"
    assert before != [tuple(rect) for rect in video.view.item_rects], (
        "the resize did not move the layout, so this proves nothing"
    )
    assert seen[-1] == list(video.view.item_rects), (
        "the rows a click is measured against are not the rows the frame drew: the "
        f"hit-test used {seen[-1][0]} and the frame drew {video.view.item_rects[0]}"
    )


def test_a_snap_is_a_drag_and_forgets_the_chosen_size_the_same_way(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A keyboard snap is a player gesture, so it lands on the same rule.

    Super+Left/Right halves or quarters the window, and it used to arrive as
    something the game was not listening to at all -- so the size chosen in the
    menu survived it and the picture did not move. Read off the window instead,
    it is a drag: the stored size goes back to ``None``, and the next display
    setting asks for the size the player left rather than the one they replaced.
    """
    game = _game_in_a_window(tmp_path, window_size=(1400, 900))
    snapped = (1280, 720)

    _resize(game, snapped)
    game.step()

    assert game.settings.window_size is None, "a snap is the player choosing to follow the window"
    assert game.presentation.window_size == snapped, "and the picture is the window"
    assert game.presentation.surface.get_size() == letterbox(snapped, DEFAULT_FRAMING).size

    with _recording_requests() as requested:
        game.apply_settings(replace(game.settings, vsync=not game.settings.vsync))
    assert requested[-1] == fit_size(snapped, game.stage.monitor), (  # type: ignore[union-attr]
        "the next rebuild asks for the snapped size"
    )


def test_the_own_resize_of_a_rebuild_is_not_read_as_a_drag(tmp_path: Path) -> None:
    """The window the game just built is not the player moving it.

    Read as a drag, the preference the menu had just set would be cleared one
    frame after being applied, so choosing a size from the list would be undone
    by the window opening at it. A rebuild records the size it was built at, and
    the poll compares against that.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=Path(tmp_path / "settings.json"),
    )
    game._initialize()
    game.apply_settings(replace(game.settings, window_size=(1200, 800)))

    game.step()

    assert game.settings.window_size == (1200, 800), "the rebuild's own size undid the setting"


def test_a_window_rebuilt_reports_the_pointer_where_it_is_not_a_gesture() -> None:
    """The focus must not jump to whatever the mouse happens to be over.

    A window rebuilt -- which is what every display setting does -- makes SDL emit
    a ``MOUSEMOTION`` with no relative movement: the pointer did not move, the
    window under it did. Routed as a gesture it takes the menu's selection with
    it, because a list reads its focused row from the row under the pointer.
    Measured: the focus sat on "Window size", the player changed it, and the focus
    came back as "Back" -- the next press closed the menu, and one row further
    down it was "Reset video settings".
    """
    stationary = pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 20), rel=(0, 0))
    moved = pygame.event.Event(pygame.MOUSEMOTION, pos=(30, 40), rel=(20, 20))
    clicked = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(10, 20), button=1)

    assert not Game._is_a_real_pointer_move(stationary), (
        "a window moving under the pointer is not the player moving it"
    )
    assert Game._is_a_real_pointer_move(moved)
    assert Game._is_a_real_pointer_move(clicked), (
        "a press is a gesture whatever its relative motion"
    )


def test_no_setting_survives_that_would_describe_the_window(tmp_path: Path) -> None:
    """The regression, restated against what is allowed to describe one.

    A stored size used to *be* the window: the player set a resolution and the
    window was rebuilt from it, so the menu and the screen disagreed whenever the
    two could not both be true -- in borderless the window is the panel's size
    whatever the file says, and nothing wrote the difference back.

    One window field is back, and it is a *request* the stage clamps to the
    monitor it opens on and never writes back, so it cannot silently disagree
    with the window either. The genuinely uncheckable claims stay gone: the fixed
    render scale, the per-frame smoothing flag, the screen picker and the display
    mode. The screen and the mode are there because the game cannot keep them --
    a window manager can refuse a move, and a mode asks the driver for something
    the driver can blank out on.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()

    names = {field.name for field in fields(UserSettings)}
    assert not names & {"width", "height", "size_mode", "render_scale", "smoothing"}
    assert names == {
        "bindings",
        "pixel_perfect",
        "fit",
        "vsync",
        "frame_limit",
        "ui_scale",
        "panel_scale",
        "window_size",
    }


def test_a_remembered_window_size_is_clamped_and_not_rewritten(tmp_path: Path) -> None:
    """A 4K window arriving at a laptop is honoured as far as it can be.

    The two halves are the point and they are not the same half. The window is
    opened at a size that fits the panel it opened on, so the player is not left
    with a window they cannot move -- and the file keeps the size they chose, so
    the next launch on a desk that has the room uses it again. Writing the
    clamped size back is what the old ``width``/``height`` keys did, and it is
    why a size could never survive a change of machine.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()

    from src.core.display.monitors import fit_size

    oversized = (7680, 4320)
    game.apply_settings(replace(game.settings, window_size=oversized))
    monitor = game.topology().primary

    assert game.stage is not None
    granted = fit_size(oversized, monitor)
    # The window manager gets the last word on the granted size -- it subtracts
    # the frame from the request, so a request for the panel's full height comes
    # back short. That is why the stage measures the surface rather than
    # trusting the request, and why the assertion is a containment rather than an
    # equality: what matters is that the window fits the panel and is not the
    # 8K the player asked for.
    assert game.stage.size[0] <= granted[0]
    assert game.stage.size[1] <= granted[1]
    assert game.stage.size[0] > 0 and game.stage.size[1] > 0
    assert game.settings.window_size == oversized, "the player's choice must survive"


def test_the_game_and_the_settings_agree_about_the_fit_in_force(
    tmp_path: Path,
) -> None:
    """One reader rule, at the runtime level, on the file the migration writes.

    The settings file can reach this runtime in exactly the shape where two
    readers of ``fit`` diverge: migrated from v3, which carries the whole-pixel
    flag and no fit key of its own. ``settings.fit`` then answers *bars* while
    the render draws at whole pixels, and the video menu -- which reads
    ``Game.effective_fit`` now, as the render does -- described a target size
    nothing was drawn at.

    The Game method is the assertion that the pure rule in ``letterbox`` is the
    one the runtime actually hands to the presentation, rather than a definition
    only the tests believe. A file that *has* chosen a policy keeps it, so the
    mixed case is also asserted: the same flag must not reach back out of the
    file and override ``zoom``.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()

    # The v3 migration shape, written the way the reader writes it: flag on,
    # policy untouched.
    game.settings = game.settings.with_video(pixel_perfect=True)
    assert game.settings.fit is FitPolicy.BARS, "the file's policy is the default"
    assert game.effective_fit() is FitPolicy.INTEGER, "and the flag promotes it"

    # A player who chose a policy keeps it, flag or no flag -- and only zoom and
    # integer are distinguishable from the migration artefact, because a file
    # saying ``fit: bars`` plus the flag *is* the migration shape; the row itself
    # never writes that pair (it stores the pair coherently), so bars plus a live
    # flag has exactly one honest reading.
    for chosen in (FitPolicy.INTEGER, FitPolicy.ZOOM):
        game.settings = game.settings.with_video(fit=chosen, pixel_perfect=True)
        assert game.effective_fit() is chosen, f"{chosen.value} must keep its choice"


class FakeWindow:
    """A window that changes size in place, the way SDL's surface does.

    ``pygame`` gives back one surface object and a resize changes its size, so
    ``Presentation`` must be able to notice without being handed a new object.
    A plain ``pygame.Surface`` cannot do that -- it has no resize -- which is
    why this exists rather than a mock of ``Presentation`` itself: the method
    under test is ``recompute``, and a mock of it would prove nothing.
    """

    def __init__(self, size: tuple[int, int]) -> None:
        self._size = size
        self.surface = pygame.Surface(size)

    def get_size(self) -> tuple[int, int]:
        return self._size

    def resize(self, size: tuple[int, int]) -> None:
        self._size = size
        self.surface = pygame.Surface(size)

    def fill(self, *args: object, **kwargs: object) -> None:
        self.surface.fill(*args, **kwargs)  # type: ignore[arg-type]

    def blit(self, *args: object, **kwargs: object) -> None:
        self.surface.blit(*args, **kwargs)  # type: ignore[arg-type]


def _video_scene(game: Game) -> Any:
    """The video screen on top of a running game, laid out.

    Driven through the real scene rather than a stub, because the claim is about
    what a click hits on the screen the player is looking at, and a stub's rows are
    the test's own invention. The menu's own rows are found by name, because the
    main menu has a different number of entries depending on whether a save
    exists -- and pinning two presses would land on "Level select" on one machine
    and "Options" on another.
    """
    from src.application.scenes.options_scene import OptionsScene
    from src.application.scenes.video_scene import VideoScene

    menu = game.scene_manager.current
    assert isinstance(menu, MenuScene), f"expected the main menu, got {type(menu).__name__}"
    for _ in range(len(menu.model.items)):
        if menu.model.current_item is not None and menu.model.current_item.action == "options":
            break
        press_key(game, InputAction.UI_DOWN)
        game.step()
    else:
        pytest.fail("the main menu has no Options row to reach")

    press_key(game, InputAction.UI_CONFIRM)
    game.step()
    assert isinstance(game.scene_manager.current, OptionsScene)
    press_key(game, InputAction.UI_CONFIRM)
    game.step()
    video = game.scene_manager.current
    assert isinstance(video, VideoScene), type(video).__name__
    return video


def press_key(game: Game, action: InputAction) -> None:
    """A key press through the real event queue, the way a player's reaches it."""
    bound = game.settings.bindings.menu.keyboard[action]
    key = bound[0] if isinstance(bound, tuple) else bound
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))
    game._handle_events()


def _game_in_a_window(tmp_path: Path, *, window_size: tuple[int, int]) -> Game:
    """A running game whose window is a :class:`FakeWindow`, windowed at ``window_size``.

    The setting is applied first -- that is the game's own rebuild, and it does not
    matter what size the platform grants -- and the window the presentation draws
    onto is replaced afterwards. The dummy video driver in CI refuses whatever
    size it is asked for and hands back the desktop's, so a test about what the
    game does with a resize has to own a window it can resize.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=Path(tmp_path / "settings.json"),
    )
    game._initialize()
    game.apply_settings(replace(game.settings, window_size=window_size))
    assert game.presentation is not None
    window = FakeWindow(window_size)
    game.presentation.stage = window  # type: ignore[assignment]
    game.presentation.recompute()
    game._built_window_size = window.get_size()
    return game


def test_the_game_can_name_the_screen_its_window_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``window_monitor`` is what the VSync row reads, so it has to be the truth.

    Not the primary, which is where the game opens: on a two-screen desk the two
    differ as soon as the player drags the window across, so reading the rate off
    the primary is how a window on a 60Hz panel came to be described as a 180Hz
    one. The window's own top-left corner is the fact, mapped through the
    desktop, with ``nearest`` so a window whose corner falls in the gap between
    two panels still resolves to one of them.

    Patched rather than asked of the machine, since a position the test does not
    control would make the answer a property of the desk it ran on.
    """
    game = _game_in_a_window(tmp_path, window_size=(1280, 720))
    from src.core.display.monitors import Monitor, Topology

    desk = Topology(
        monitors=(
            Monitor(0, 'DP-1 27"', (0, 0, 2560, 1440), (0, 0, 2560, 1400), 180),
            Monitor(1, 'DP-2 24"', (2560, 0, 1920, 1080), (2560, 0, 1920, 1040), 60),
        ),
        named=True,
    )
    monkeypatch.setattr(game, "topology", lambda: desk)

    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (2700, 100))
    on_the_second = game.window_monitor()
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (10, 10))
    on_the_first = game.window_monitor()

    assert on_the_second is not None and on_the_second.refresh_rate == 60, (
        "the window is at x=2700, which is inside DP-2 and nowhere else"
    )
    assert on_the_first is not None and on_the_first.refresh_rate == 180, (
        "the window is at the origin, which is inside DP-1"
    )


def frames(game: Game, count: int = 2) -> None:
    """Run whole frames, so a draw happens the way it does in the loop."""
    for _ in range(count):
        game.step()


def _resize(game: Game, size: tuple[int, int]) -> None:
    """The window changed size, by whatever gesture -- and no event is posted."""
    assert game.presentation is not None
    window = game.presentation.stage
    assert isinstance(window, FakeWindow), "this test drives a window it can resize"
    window.resize(size)


@contextmanager
def _recording_requests() -> Iterator[list[tuple[int, int]]]:
    """The sizes the game asks the platform for, in order.

    The request is the half of the window the game owns; what the platform then
    grants is its own business, and under the dummy driver it is a business with
    a fixed answer. Asserting on the request is therefore both the stronger claim
    and the only one that survives CI.
    """
    requested: list[tuple[int, int]] = []
    real = pygame.display.set_mode

    def record(size, flags=0, depth=0, display=0, vsync=0):
        requested.append(size)
        return real(size, flags, depth, display, vsync)

    with patch.object(pygame.display, "set_mode", record):
        yield requested


def test_the_target_is_the_window_so_a_resize_reaches_the_views(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A resize is read off the window, and no event has to arrive for it.

    This used to be driven by a posted ``VIDEORESIZE``, which is how it stayed
    green while the feature was broken: *which* event a resize arrives as is the
    platform's business, and measured on the development machine a keyboard snap
    delivered only ``WINDOWSIZECHANGED`` -- so the picture kept the size it had,
    and a 1000x562 frame was clipped at the right and the bottom of a 640x500
    window.

    So nothing is posted here at all. The window is resized and a frame runs; the
    target, the density, the interface scale and every view follow.
    """
    from src.core.display.letterbox import letterbox

    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    assert game.presentation is not None
    # Pinned rather than taken from the runtime: under the dummy driver the
    # desktop is whatever the last test left behind, so the window the game
    # opened is not the same from one run to the next.
    window = FakeWindow((1600, 900))
    game.presentation.stage = window  # type: ignore[assignment]
    game.presentation.recompute()
    game._built_window_size = window.get_size()
    notified = Mock()
    game.scene_manager.set_surface = notified  # type: ignore[method-assign]
    start = game.presentation.surface.get_size()

    for size in ((1920, 1080), (1024, 768), (800, 600)):
        assert letterbox(size, DEFAULT_FRAMING).size != start
        window.resize(size)

        game.step()

        assert game.presentation.surface.get_size() == letterbox(size, DEFAULT_FRAMING).size
        assert game.presentation.density == pytest.approx(
            letterbox(size, DEFAULT_FRAMING).width / DEFAULT_FRAMING.width
        )
        assert game.ui_scale == pytest.approx(game.settings.ui_scale * game.presentation.density)

    # Once per new picture, and every surface handed over is the one that is
    # about to be drawn into.
    assert notified.call_count == 3, "the views were never told about the new target"
    handed = [call.args[0] for call in notified.call_args_list]
    assert handed == [
        Viewport(DEFAULT_FRAMING, letterbox(size, DEFAULT_FRAMING).size).surface
        for size in ((1920, 1080), (1024, 768), (800, 600))
    ] or all(
        surface.get_size() == letterbox(size, DEFAULT_FRAMING).size
        for surface, size in zip(handed, ((1920, 1080), (1024, 768), (800, 600)), strict=True)
    )


def test_a_resize_that_changes_nothing_does_not_rebuild_the_target(tmp_path: Path) -> None:
    """SDL announces a resize during its own ``set_mode``; that has to be a no-op.

    Otherwise every display change rebuilds the target twice, and a drag of the
    window rebuilds it once per event whether or not the size moved.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    assert game.presentation is not None
    before = game.presentation.surface
    assert game.presentation.recompute() is False
    assert game.presentation.surface is before


# -- the fatal error path -----------------------------------------------------
#
# This runs when something has already gone wrong, so every part of it has to
# be safe: the log is the artifact worth keeping, the screen is a courtesy, and
# neither may replace a reportable crash with an unreportable one.


def test_a_fatal_error_is_logged_with_its_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The log, not the screen, is what a player sends you.

    It used to be `logger.error(f"FATAL ERROR: {error}")` -- the message and
    nothing else, so a crash whose exception had an empty message logged an
    empty line, and the frame that raised it was recorded nowhere.
    """
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()

    with caplog.at_level(logging.CRITICAL):
        game._handle_fatal_error(RuntimeError("the level would not build"))

    record = caplog.records[-1]
    assert record.levelno == logging.CRITICAL
    assert record.exc_info is not None, "the traceback is the point"
    assert "the level would not build" in caplog.text


def test_the_fatal_screen_goes_on_the_render_target_and_is_presented(
    tmp_path: Path,
) -> None:
    """Not on the window, and not until something presents it.

    Drawing straight to the window put the message at 1:1 whatever the
    letterbox and density were, and the next present would have wiped it.
    """
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    presented = Mock()
    monkey = Mock(wraps=game.presentation)
    game.presentation = monkey
    monkey.present = presented

    game._handle_fatal_error(RuntimeError("boom"))

    presented.assert_called_once_with()
    # Something was painted into the target, not only the window.
    assert any(
        game.presentation.surface.get_at((x, y))[:3] != (0, 0, 0)
        for x in range(0, 200, 7)
        for y in range(0, 120, 7)
    )


def test_a_crash_before_the_display_falls_back_to_the_window(
    tmp_path: Path,
) -> None:
    """No presentation yet is the normal case for an initialization failure."""
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    game.presentation = None  # as if the crash happened before it was built
    window = pygame.display.get_surface()

    game._handle_fatal_error(RuntimeError("no display"))

    assert window is not None
    assert game.surface is window
    assert any(
        window.get_at((x, y))[:3] != (0, 0, 0) for x in range(0, 400, 5) for y in range(0, 40, 5)
    ), "the message reached the window"


def test_the_fatal_handler_never_raises(tmp_path: Path) -> None:
    """A display that has gone away must not turn a crash into a hang."""
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()

    def exploding(*args, **kwargs):
        raise pygame.error("the display driver has gone")

    game.presentation = exploding

    game._handle_fatal_error(RuntimeError("boom"))  # must not raise


def test_a_crash_with_an_empty_message_still_says_something(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()

    with caplog.at_level(logging.CRITICAL):
        game._handle_fatal_error(RuntimeError())

    assert "RuntimeError" in caplog.text
