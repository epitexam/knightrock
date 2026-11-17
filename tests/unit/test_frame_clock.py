"""The frame pacer is injectable, so a frame can be driven without sleeping."""

from pathlib import Path

from src.application.game import Game
from src.application.runtime_clock import ManualFrameClock, PygameFrameClock


def test_game_uses_the_injected_clock(tmp_path: Path) -> None:
    clock = ManualFrameClock(delta=1 / 240)

    game = Game(
        save_path=tmp_path / "save.json",
        bindings_path=tmp_path / "settings.json",
        frame_clock=clock,
    )

    assert game.clock is clock


def test_frame_delta_is_the_injected_delta_without_sleeping(tmp_path: Path) -> None:
    clock = ManualFrameClock(delta=0.004)
    game = Game(
        save_path=tmp_path / "save.json",
        bindings_path=tmp_path / "settings.json",
        frame_clock=clock,
    )
    game.settings = game.settings.with_video(vsync=False)

    assert game._frame_delta() == 0.004  # noqa: SLF001 - the port under test
    assert clock.ticks == 1


def test_manual_clock_reports_stats_for_the_debug_overlay() -> None:
    clock = ManualFrameClock(delta=1 / 60)

    assert clock.get_fps() == 0.0
    assert clock.get_time() == 16


def test_pygame_clock_is_the_default() -> None:
    assert isinstance(Game().clock, PygameFrameClock)
