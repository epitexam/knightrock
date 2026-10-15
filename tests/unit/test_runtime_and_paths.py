"""Tests for resource lookup and the top-level game runtime boundary."""

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import Mock, patch

import pygame
import pytest

from src.application.settings_store import UserSettings
from src.core.display import detection
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import letterbox
from src.core.display.mode import DisplayMode
from src.core.display.monitors import centre_on, fit_size, opening_size
from src.core.display.stage import PLACE_ATTEMPTS, TITLE_BAR_KEEP, Stage, WindowSpec
from src.core.display.viewport import Viewport
from src.core.game import Game
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

    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW, vsync=True))

    assert game.surface is not None
    assert game.surface.get_size() == game.stage.size
    assert game.settings.vsync is True


def test_a_windowed_window_is_resizable_and_borderless_asks_for_no_mode_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The two modes, by what they ask the driver for.

    Windowed is resizable, and the drag is the point: the window is the render
    target, so a resize is a first-class case rather than something to protect
    the picture from. Borderless asks for FULLSCREEN *at the desktop's own size*
    rather than a mode change, which is what keeps it safe on a hybrid-GPU
    laptop.

    ``pygame.SCALED`` is deliberately absent. It was doing the letterboxing,
    which the render target now does itself, and pygame's documentation calls it
    an experimental API.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    set_mode = Mock(wraps=pygame.display.set_mode)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)

    # From a mode that is definitely not the one under test: the dummy driver
    # reports a desktop whose shape depends on whichever test ran last, so
    # AUTO may already have resolved to WINDOW here.
    game.apply_settings(replace(game.settings, display=DisplayMode.BORDERLESS))
    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW))

    windowed_flags = set_mode.call_args.args[1]
    assert windowed_flags & pygame.RESIZABLE
    assert not windowed_flags & pygame.FULLSCREEN
    assert not windowed_flags & pygame.SCALED
    # No size of our own: the desktop decides how big a window to open, and the
    # player drags it from there.
    requested = set_mode.call_args.args[0]
    monitor = detection.topology().resolve(game.settings.monitor).monitor
    assert requested == opening_size(monitor)

    game.apply_settings(replace(game.settings, display=DisplayMode.BORDERLESS))

    fullscreen_flags = set_mode.call_args.args[1]
    assert fullscreen_flags & pygame.FULLSCREEN
    assert not fullscreen_flags & pygame.RESIZABLE
    assert not fullscreen_flags & pygame.SCALED
    assert set_mode.call_args.args[0] == monitor.usable_size


def _panel(width: int, height: int):
    """A monitor whose usable area is the whole panel, for stage arithmetic."""
    from src.core.display.monitors import Monitor

    return Monitor(index=0, name="", bounds=(0, 0, width, height), usable=(0, 0, width, height))


class _RecordingWindow:
    """A window that goes where it is told, and remembers being asked to.

    Stands in for the ``pygame.Window`` handle in the placement tests, because
    what those are about is the *request*: which modes make one, and what it says.
    A real handle cannot be steered, and what happens when one refuses is the
    next test, which is why the setter is the seam rather than a ``Mock``: the
    stage sets ``position`` and nothing else on the handle it places.
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
    """The first ``set_mode`` after a flag change is dropped; the second is not.

    Measured on the development machine: switching from borderless to windowed and
    picking a size left the window the size of the player's desktop, with
    ``Requested window size: (1600, 900) / New window size: (2560, 1440)`` on
    stderr and nothing else. The stage read the granted size back -- it had always
    done that -- and then believed it.

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

    stage = Stage(WindowSpec(mode=DisplayMode.WINDOW), monitor)

    assert len(asked) >= 2, "a refused size was accepted as if it had been honoured"
    assert stage.size == opening_size(monitor)


def test_a_borderless_window_is_placed_and_not_only_a_windowed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Borderless is a window, so a change of screen has to move it.

    ``set_mode``'s display index does not move a window that already exists --
    measured, twice in a row, the window stayed on the other display -- and the
    stage only ever placed a *windowed* one. So picking another screen from the
    video menu changed the label, changed the settings file, and left the game on
    the panel the player had just said no to: a row that answers and does nothing.

    ``FULLSCREEN | NOFRAME`` is the case this is about: measured at 1600x900 it is
    still a real, positioned, draggable window. Exclusive fullscreen is left alone
    and the test says so too -- a request SDL refuses on purpose is not a
    placement the game should keep re-issuing.
    """
    monitor = _panel(1920, 1080)

    for mode in (DisplayMode.WINDOW, DisplayMode.BORDERLESS):
        window = _RecordingWindow()
        monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda handle=window: handle))
        monkeypatch.setattr(pygame.display, "get_window_position", lambda: (0, 0))

        stage = Stage(WindowSpec(mode=mode), monitor)

        assert window.asked, f"{mode.value} is left to the WM, so a screen change cannot move it"
        assert window.asked[0] == centre_on(monitor, stage.size), (
            "the window is asked for the middle of the panel it opens on"
        )

    exclusive = _RecordingWindow()
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: exclusive))
    Stage(WindowSpec(mode=DisplayMode.FULLSCREEN), monitor)
    assert exclusive.asked == [], "a real fullscreen window is placed by SDL, not by us"


def test_a_remembered_window_position_is_honoured_and_clamped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where the player left the window is where it goes, as long as it can be reached.

    A remembered position is clamped into the usable area rather than dropped: a
    window on a screen that is no longer attached cannot be dragged back, and the
    player would be left with a game they cannot get to. The clamp is the
    difference between a window that reopens where it was and one that reopens
    off the desktop entirely.
    """
    from src.core.display.monitors import fit_position

    monitor = _panel(1920, 1080)
    window = _RecordingWindow()
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: window))
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (0, 0))

    remembered = (-500, 4000)
    stage = Stage(WindowSpec(mode=DisplayMode.WINDOW, position=remembered), monitor)

    assert window.asked[0] == fit_position(remembered, stage.size, monitor)
    assert Stage.on_monitor(monitor, window.asked[0]), (
        "a remembered position is brought back onto the panel it cannot leave"
    )


def test_a_window_that_will_not_move_is_not_fought(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused placement costs the same number of requests, whatever it costs.

    Measured against a window manager that keeps every window inside one panel: the
    game asked for another, got the same position back three times, and the window
    stayed where it was. The stage stops after a fixed number of asks -- the player
    is not waiting on a window manager -- and the runtime says so on screen, which
    is the other half of the claim and the half the player needs.
    """
    monitor = _panel(1920, 1080)

    class _StubbornWindow(_RecordingWindow):
        def __setattr__(self, name: str, value: object) -> None:
            if name == "position" and "asked" in self.__dict__:
                self.asked.append(value)  # type: ignore[arg-type]
                return  # the platform refuses to move the window
            object.__setattr__(self, name, value)

    window = _StubbornWindow()
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: window))
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (-9000, -9000))

    Stage(WindowSpec(mode=DisplayMode.WINDOW), monitor)

    assert len(window.asked) == PLACE_ATTEMPTS, "the retries must be bounded"


def test_the_window_is_on_the_monitor_it_was_asked_for() -> None:
    """``on_monitor`` is what both the placement and the notice are made of.

    A pure function of bounds and a coordinate, so the window manager's frame --
    which shifts every position it reports by its own decoration -- is what the
    slack is for. Without it, a window that had arrived exactly on the origin of a
    panel would be asked for three times and then reported as having failed.
    """
    from src.core.display.monitors import Monitor

    monitor = Monitor(
        index=1,
        name="DP-2",
        bounds=(1920, 0, 2560, 1440),
        usable=(1920, 0, 2560, 1400),
    )

    assert Stage.on_monitor(monitor, (1920, 0))
    assert Stage.on_monitor(monitor, (4000, 1400)), "the far corner is still on the panel"
    assert Stage.on_monitor(monitor, (1920 - TITLE_BAR_KEEP[0], -TITLE_BAR_KEEP[1])), (
        "a window manager's frame offsets the position it reports"
    )
    assert not Stage.on_monitor(monitor, (0, 0)), "the other monitor is not this one"
    assert not Stage.on_monitor(monitor, (1920, 1440)), "below the panel is not on it"


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
    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW, window_size=(1200, 800)))

    game.step()

    assert game.settings.window_size == (1200, 800), "the rebuild's own size undid the setting"


def test_a_window_that_will_not_move_is_told_so_and_then_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The player is told when the window did not go where they asked, and when it does.

    Measured on a two-display desk: a window asked for the panel it was not on
    stays there while ``set_mode`` reports success and the settings file keeps the
    screen the player chose. Silent, the menu says one thing and the desktop shows
    another -- which is the failure this whole rework is about.

    The message is withdrawn on the first rebuild that does land, because a warning
    about a failure that has stopped being true is a lie about the present one.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=Path(tmp_path / "settings.json"),
    )
    game._initialize()
    monitor = game.stage.monitor  # type: ignore[union-attr]

    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (-9000, -9000))
    game._say_where_the_window_landed()
    told = game.notice_lines
    assert told, "a window left on the wrong screen is silent about it"

    monkeypatch.setattr(pygame.display, "get_window_position", lambda: monitor.bounds[:2])
    game._say_where_the_window_landed()
    assert not game.notice_lines, "the warning outlived the failure it described"


def test_a_window_notice_does_not_clear_someone_elses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The notice channel is shared; a placement that succeeds owns nothing to clear.

    ``notice`` also carries "a display was plugged in" and the dead-key warning, so
    withdrawing this module's own message has to be able to tell the two apart.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=Path(tmp_path / "settings.json"),
    )
    game._initialize()
    monitor = game.stage.monitor  # type: ignore[union-attr]
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: monitor.bounds[:2])

    game.notice("That screen is no longer connected.")

    game._say_where_the_window_landed()
    assert game.notice_lines == ("That screen is no longer connected.",)


def test_a_window_rebuilt_reports_the_pointer_where_it_is_not_a_gesture() -> None:
    """The focus must not jump to whatever the mouse happens to be over.

    A window rebuilt -- which is what every display setting does -- makes SDL emit
    a ``MOUSEMOTION`` with no relative movement: the pointer did not move, the
    window under it did. Routed as a gesture it takes the menu's selection with
    it, because a list reads its focused row from the row under the pointer.
    Measured: the focus sat on "Display mode", the player changed the display
    mode, and the focus came back as "Back" -- the next press closed the menu, and
    one row further down it was "Reset video settings".
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


def test_borderless_and_fullscreen_are_not_the_same_request(tmp_path: Path) -> None:
    """The bug this file's own flag assertions used to agree with.

    Both modes passed ``pygame.FULLSCREEN`` and nothing else, so the three names
    in ``DisplayMode`` described two requests. The ``mode`` enum's docstring said
    borderless "changes nothing on the player's system: no mode change to fail, no
    refresh-rate change, nothing to redo when a hybrid-GPU laptop switches the
    display over to its integrated chip mid-session" -- and the flags never
    delivered that, so the shipped default was the risky one.

    The difference is ``NOFRAME``: a borderless window covers the panel with no
    decoration and at the panel's own resolution, so no mode is changed. This
    asserts the requests differ rather than restating what each should be, since
    the two assertions above already pin what each one is.
    """
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()
    # Read the request rather than wrapping set_mode: the second mode in the loop
    # rebuilds the window, and patching the call the rebuild itself makes would
    # record the rebuild rather than the setting.
    requested: dict[DisplayMode, tuple[tuple[int, int], int]] = {}
    real_set_mode = pygame.display.set_mode

    def record(size, flags=0, depth=0, display=0, vsync=0):
        requested[mode] = (size, flags)
        return real_set_mode(size, flags, depth, display, vsync)

    for mode in (DisplayMode.BORDERLESS, DisplayMode.FULLSCREEN):
        # From windowed, because applying the mode the game is already in does
        # not rebuild -- the signature is unchanged and nothing asks for a new
        # window. That skipping is correct behaviour and not what this test is
        # about.
        game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW))
        with patch.object(pygame.display, "set_mode", record):
            game.apply_settings(replace(game.settings, display=mode))

    borderless_size, borderless_flags = requested[DisplayMode.BORDERLESS]
    fullscreen_size, fullscreen_flags = requested[DisplayMode.FULLSCREEN]

    assert borderless_flags != fullscreen_flags, "the two modes are the same request"
    assert borderless_flags & pygame.NOFRAME, "borderless needs no decoration"
    assert not fullscreen_flags & pygame.NOFRAME, "fullscreen keeps the platform's own chrome"
    assert borderless_size != fullscreen_size, (
        "borderless fills the usable area, fullscreen defers to the display's mode"
    )


def test_fullscreen_asks_sdl_for_the_displays_own_mode(tmp_path: Path) -> None:
    """``(0, 0)`` is how SDL is told to use the current mode.

    The alternative is asking for a resolution, which is the claim this whole
    rework removed: a mode change to a size the game picked, on a panel it never
    measured.
    """
    spec = WindowSpec(mode=DisplayMode.FULLSCREEN)
    assert Stage._window_size(spec, _panel(2560, 1440)) == (0, 0)


def test_no_setting_survives_that_would_describe_the_window(tmp_path: Path) -> None:
    """The regression, restated against what is allowed to describe one.

    A stored size used to *be* the window: the player set a resolution and the
    window was rebuilt from it, so the menu and the screen disagreed whenever the
    two could not both be true -- in borderless the window is the panel's size
    whatever the file says, and nothing wrote the difference back.

    Two window fields are back, and each is a different kind of claim:

    - ``monitor`` names a screen, and the game resolves it against the live
      topology and reports the outcome rather than overwriting the file;
    - ``window_size``/``window_position`` are a *request* the stage clamps to
      the monitor it opens on, never written back.

    Neither can silently disagree with the window, because neither is asserted
    about it. The genuinely uncheckable claims -- the fixed render scale and the
    per-frame smoothing flag, both describing machinery that no longer exists --
    stay gone, which is what this asserts.
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
        "display",
        "monitor",
        "pixel_perfect",
        "fit",
        "vsync",
        "frame_limit",
        "ui_scale",
        "panel_scale",
        "fullscreen_mode",
        "window_size",
        "window_position",
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
    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW))

    from src.core.display.monitors import fit_size

    oversized = (7680, 4320)
    game.apply_settings(replace(game.settings, window_size=oversized))
    monitor = detection.topology().resolve(game.settings.monitor).monitor

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
    game.apply_settings(replace(game.settings, display=DisplayMode.WINDOW, window_size=window_size))
    assert game.presentation is not None
    window = FakeWindow(window_size)
    game.presentation.stage = window  # type: ignore[assignment]
    game.presentation.recompute()
    game._built_window_size = window.get_size()
    return game


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
