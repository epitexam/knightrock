"""The window rules, from tables: no window and no display needed."""

from src.core.display.monitors import Monitor, Topology
from src.core.display.window_watch import DisplayChange, WindowWatch, monitor_at

LEFT = Monitor(0, "DP-1", (0, 0, 2560, 1440), (0, 0, 2560, 1400), 180)
RIGHT = Monitor(1, "DP-2", (2560, 0, 1920, 1080), (2560, 0, 1920, 1040), 60)
DESK = Topology(monitors=(LEFT, RIGHT), named=True)


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _watch(topologies: list[Topology] | None = None) -> tuple[WindowWatch, _Clock]:
    clock = _Clock()
    lists = list(topologies or [DESK])
    return WindowWatch(
        read_topology=lambda: lists.pop(0) if len(lists) > 1 else lists[0], clock=clock
    ), clock


def test_the_window_it_just_built_is_no_resize() -> None:
    watch, _ = _watch()
    watch.built((1600, 900))

    assert watch.resized((1600, 900)) is None


def test_a_size_change_right_after_a_build_is_the_window_manager() -> None:
    watch, clock = _watch()
    watch.built((1600, 900))
    clock.now += 0.2

    resize = watch.resized((1580, 870))

    assert resize is not None and not resize.by_player


def test_a_size_change_later_is_the_player() -> None:
    watch, clock = _watch()
    watch.built((1600, 900))
    clock.now += WindowWatch.RESIZE_GRACE_SECONDS + 0.1

    resize = watch.resized((1200, 800))

    assert resize is not None and resize.by_player
    assert watch.resized((1200, 800)) is None, "the same size twice is one resize"


def test_nothing_is_read_before_the_poll_is_due() -> None:
    reads = []
    watch = WindowWatch(read_topology=lambda: reads.append(1) or DESK)
    watch.topology()

    assert watch.poll(WindowWatch.DISPLAY_POLL_SECONDS / 2, lambda: LEFT) is None
    assert len(reads) == 1


def test_losing_the_screen_holding_the_window_asks_for_a_rebuild() -> None:
    watch, _ = _watch([DESK, Topology(monitors=(LEFT,), named=True)])
    watch.topology()

    change = watch.poll(WindowWatch.DISPLAY_POLL_SECONDS, lambda: RIGHT)

    assert change is DisplayChange.WINDOW_SCREEN_GONE


def test_losing_another_screen_is_only_news() -> None:
    watch, _ = _watch([DESK, Topology(monitors=(LEFT,), named=True)])
    watch.topology()

    change = watch.poll(WindowWatch.DISPLAY_POLL_SECONDS, lambda: LEFT)

    assert change is DisplayChange.SCREEN_COUNT_CHANGED


def test_a_renumbered_screen_is_still_the_same_screen() -> None:
    renumbered = Monitor(0, RIGHT.name, RIGHT.bounds, RIGHT.usable, RIGHT.refresh_rate)
    watch, _ = _watch([DESK, Topology(monitors=(renumbered,), named=True)])
    watch.topology()

    change = watch.poll(WindowWatch.DISPLAY_POLL_SECONDS, lambda: RIGHT)

    assert change is DisplayChange.SCREEN_COUNT_CHANGED


def test_a_taskbar_moving_is_no_news() -> None:
    moved = Monitor(0, LEFT.name, LEFT.bounds, (0, 40, 2560, 1400), LEFT.refresh_rate)
    watch, _ = _watch([DESK, Topology(monitors=(moved, RIGHT), named=True)])
    watch.topology()

    assert watch.poll(WindowWatch.DISPLAY_POLL_SECONDS, lambda: RIGHT) is None


def test_the_window_is_on_the_screen_holding_its_centre() -> None:
    # The corner is on the left panel; most of the window is on the right one.
    assert monitor_at(DESK, (2400, 100), (1280, 720)) is RIGHT
    assert monitor_at(DESK, (10, 10), (1280, 720)) is LEFT


def test_no_geometry_names_no_screen() -> None:
    assert monitor_at(Topology(), (0, 0), (800, 600)) is None
