"""The asset-free fatal screen, for crashes before the UI can be built."""

from __future__ import annotations

from itertools import chain, cycle, repeat
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from src.application import fatal_screen as screen
from src.application.fatal_screen import (
    ERROR_FILE,
    State,
    _clamp,
    _copy_error,
    _handle_event,
    _layout,
    _summary,
    _thumb,
    _window_geometry,
    show_fatal_error,
)
from src.presentation.display.monitors import Monitor, Topology, centre_on


def _events(monkeypatch, batches) -> None:
    calls = cycle(batches)
    monkeypatch.setattr(pygame.event, "get", lambda: next(calls))


def _past_grace(monkeypatch) -> None:
    times = chain([0.0], repeat(1.0))
    monkeypatch.setattr("src.application.fatal_screen.time.monotonic", lambda: next(times))


def _surface(monkeypatch) -> pygame.Surface:
    surface = pygame.Surface((900, 600))
    monkeypatch.setattr(pygame.display, "set_mode", lambda *a, **k: surface)
    monkeypatch.setattr(pygame.display, "get_surface", lambda: surface)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return surface


def test_a_window_close_quits(monkeypatch) -> None:
    _past_grace(monkeypatch)
    _events(monkeypatch, [[pygame.event.Event(pygame.QUIT)]])
    assert show_fatal_error(RuntimeError("boom")) == "quit"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (pygame.K_q, "quit"),
        (pygame.K_ESCAPE, "quit"),
        (pygame.K_r, "retry"),
        (pygame.K_RETURN, "retry"),
    ],
)
def test_keys_then_choose_after_the_grace(monkeypatch, key, expected) -> None:
    _past_grace(monkeypatch)
    _events(monkeypatch, [[pygame.event.Event(pygame.KEYDOWN, key=key)]])
    assert show_fatal_error(RuntimeError("boom")) == expected


def test_the_three_buttons_are_clickable(monkeypatch) -> None:
    _past_grace(monkeypatch)
    surface = _surface(monkeypatch)
    panel = _layout(surface)
    _events(
        monkeypatch,
        [
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=panel.copy.center)],
            [],
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=panel.quit.center)],
            [],
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=panel.menu.center)],
        ],
    )
    copy = Mock(return_value="Copied")
    monkeypatch.setattr(screen, "_copy_error", copy)

    assert show_fatal_error(RuntimeError("boom")) == "quit"
    copy.assert_called_once()

    _past_grace(monkeypatch)  # a fresh clock for the second screen
    _events(
        monkeypatch, [[pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=panel.menu.center)]]
    )
    assert show_fatal_error(RuntimeError("boom")) == "retry"


def test_the_copy_key_saves_the_whole_traceback(monkeypatch, tmp_path: Path) -> None:
    _past_grace(monkeypatch)
    monkeypatch.setattr(screen.tempfile, "gettempdir", lambda: str(tmp_path))
    notice = _copy_error("Traceback\nRuntimeError: boom\n")
    saved = tmp_path / ERROR_FILE

    assert saved.read_text(encoding="utf-8") == "Traceback\nRuntimeError: boom\n"
    assert str(saved) in notice

    copy = Mock(return_value="Done")
    monkeypatch.setattr(screen, "_copy_error", copy)
    _events(
        monkeypatch,
        [
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c)],
            [],
            [pygame.event.Event(pygame.QUIT)],
        ],
    )
    assert show_fatal_error(RuntimeError("boom")) == "quit"
    copy.assert_called_once()


def test_the_scrollbar_jumps_and_drags() -> None:
    panel = _layout(pygame.Surface((900, 600)))
    maximum = 500
    state = State()
    thumb = _thumb(panel, 0, maximum)

    # Clicking the rail below the thumb jumps there and starts a drag.
    below = (panel.rail.centerx, panel.rail.bottom - 4)
    assert (
        _handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=below),
            panel,
            state,
            maximum,
            grace=False,
        )
        is None
    )
    assert state.scroll > 0
    assert state.dragging is True

    # Dragging to the top goes back to the beginning.
    top = (panel.rail.centerx, panel.rail.y + 4)
    _handle_event(
        pygame.event.Event(pygame.MOUSEMOTION, pos=top, buttons=(1, 0, 0)),
        panel,
        state,
        maximum,
        grace=False,
    )
    assert state.scroll == 0
    _handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=top),
        panel,
        state,
        maximum,
        grace=False,
    )
    assert state.dragging is False

    # The thumb itself stays draggable without jumping first.
    assert thumb.height >= 18


def test_the_scroll_is_clamped_and_the_summary_is_the_exception() -> None:
    assert _clamp(-20, 100) == 0
    assert _clamp(200, 100) == 100
    assert _summary("Traceback:\n  line 1\nRuntimeError: boom\n") == "RuntimeError: boom"


def test_the_window_is_medium_and_centred_on_the_games_monitor(monkeypatch) -> None:
    monitor = Monitor(
        index=0,
        name="",
        bounds=(100, 50, 1920, 1080),
        usable=(100, 90, 1920, 1040),
    )
    monkeypatch.setattr(
        "src.application.fatal_screen.topology", lambda: Topology((monitor,), named=True)
    )
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (500, 300))

    size, position = _window_geometry()

    assert 640 <= size[0] <= 960
    assert 480 <= size[1] <= 640
    assert position == centre_on(monitor, size)
