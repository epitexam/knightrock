"""The frame readout: a frame rate alone cannot tell a slow game from a paced one.

"100 fps" reads as a problem and is the answer when the limit is 100. So the
readout carries the pacer next to the timings, prices the four terms that
actually happen, and takes medians rather than instantaneous values -- a number
that describes one frame of sixty is a number about nothing.

The measurement is unconditional and the painting is a setting, and both halves
are asserted here, because the split is the design: a number only collected
while something watches it cannot be compared with the run where it was off.
"""


import pytest

from src.core.game import Game
from src.ui.frame_counter import SAMPLE_WINDOW, FrameCounter


def test_a_fresh_counter_reports_nothing_rather_than_zero() -> None:
    """A readout that starts at 0 fps is a readout nobody trusts for ten frames.

    ``0.0`` is the honest answer -- nothing has been measured -- and it is
    distinguishable from a measured zero because the sample window is empty.
    """
    counter = FrameCounter()

    assert counter.fps() == 0.0
    assert counter.frame_ms == 0.0
    assert counter.median("world") == 0.0
    assert len(counter.frame_samples) == 0


def test_one_hitch_does_not_move_the_median() -> None:
    """The frame the player sees is not the one that is typical.

    Fifty-nine good frames and one 40ms stall is a smooth game with a hiccup;
    the mean would report a quarter of the budget gone, and the fix that follows
    from that number is usually wrong.
    """
    counter = FrameCounter()
    for _ in range(SAMPLE_WINDOW - 1):
        counter.sample(frame_ms=16.0, tick_ms=1.0, world_ms=2.0, ui_ms=0.5, present_ms=0.5)
    counter.sample(frame_ms=40.0, tick_ms=1.0, world_ms=2.0, ui_ms=0.5, present_ms=0.5)

    assert counter.frame_ms == 16.0
    assert counter.fps() == pytest.approx(62.5, abs=0.1)


def test_the_window_is_bounded_so_a_long_session_cannot_grow_it() -> None:
    counter = FrameCounter()

    for _ in range(SAMPLE_WINDOW * 3):
        counter.sample(frame_ms=16.0, tick_ms=1.0, world_ms=2.0, ui_ms=0.5, present_ms=0.5)

    assert len(counter.frame_samples) == SAMPLE_WINDOW
    assert all(len(values) == SAMPLE_WINDOW for values in counter.samples.values())


def test_the_readout_has_an_answer_and_its_evidence() -> None:
    """Two lines: the number, then the four terms that make it up.

    Everything else about a frame budget is a guess until you can see which term
    is large, so the terms are not decoration -- they are the whole point, and
    the test says so by checking each one appears.
    """
    counter = FrameCounter()
    for _ in range(SAMPLE_WINDOW):
        counter.sample(frame_ms=10.0, tick_ms=1.0, world_ms=4.0, ui_ms=1.0, present_ms=1.0)
    counter.pacer = "limite 60"

    first, second = counter.lines()

    assert "100.0 fps" in first
    assert "10.00 ms" in first
    assert "limite 60" in first, "the pacer is what makes the number mean something"
    for term in ("sim", "monde", "ui", "pres"):
        assert term in second, f"{term} is missing from the evidence line"


def test_the_pacer_names_what_is_holding_the_frame_rate(tmp_path, monkeypatch) -> None:
    """The three answers, and the word for each.

    A capped game and a slow game report the same number; this is the line that
    tells them apart, so each state has to say which one it is.
    """
    monkeypatch.setenv("KNIGHTROCK_SAVE_DIR", str(tmp_path / "home"))
    monkeypatch.setenv("DEBUG", "0")
    game = Game(save_path=tmp_path / "s.json", bindings_path=tmp_path / "settings.json")
    game._initialize()

    game.settings = game.settings.with_video(vsync=False, frame_limit=144)
    assert game._pacer_label() == "limite 144"
    game.settings = game.settings.with_video(frame_limit=None)
    assert game._pacer_label() == "libre"
    game.settings = game.settings.with_video(vsync=True, frame_limit=None)
    assert game._pacer_label() == "vsync"


class _InstantClock:
    """A clock that never sleeps, so a test does not take five frames of 16ms."""

    def tick(self, fps: int = 0) -> int:
        return 0

    def get_fps(self) -> float:
        return 0.0

    def get_time(self) -> int:
        return 0
