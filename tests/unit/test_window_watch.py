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


# -- the platform's own report of the window's display -------------------------


def test_nothing_is_reported_until_the_platform_speaks() -> None:
    watch, _ = _watch()

    assert watch.reported_monitor() is None


def test_the_reported_display_is_the_window_s_screen() -> None:
    watch, _ = _watch()

    watch.moved_to_display(1)

    assert watch.reported_monitor() == RIGHT


def test_a_report_naming_no_known_display_is_no_answer() -> None:
    watch, _ = _watch()

    watch.moved_to_display(7)

    assert watch.reported_monitor() is None


def test_a_hotplug_forgets_the_reported_index() -> None:
    """SDL renumbers on a hotplug: index 1 of the old desk may be another panel now."""
    watch, _ = _watch([DESK, Topology(monitors=(RIGHT,), named=True)])
    watch.topology()
    watch.moved_to_display(1)

    watch.poll(WindowWatch.DISPLAY_POLL_SECONDS, lambda: RIGHT)

    assert watch.display_index is None
    assert watch.reported_monitor() is None


def test_the_report_wins_over_the_window_s_position(monkeypatch) -> None:
    """And it answers where a position cannot be read at all."""
    import pygame

    from src.application.screen import Screen

    screen = Screen()
    screen.window = _watch()[0]
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (100, 100))
    assert screen.window_monitor() == LEFT

    screen.window.moved_to_display(1)

    assert screen.window_monitor() == RIGHT


def test_the_game_hands_the_display_event_to_the_watch(tmp_path, monkeypatch) -> None:
    import pygame

    from src.application.game import Game

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.display.set_mode((320, 240))
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.WINDOWDISPLAYCHANGED, display_index=1))

    game._handle_events()

    assert game.screen.window.display_index == 1


# -- the focus the game's own rebuild takes away -------------------------------


def test_the_window_is_settling_right_after_a_build_and_not_later() -> None:
    watch, clock = _watch()
    assert not watch.settling

    watch.built((1600, 900))
    assert watch.settling

    clock.now += WindowWatch.RESIZE_GRACE_SECONDS + 0.1
    assert not watch.settling


def test_a_focus_lost_while_the_window_settles_never_reaches_the_scenes(
    tmp_path, monkeypatch
) -> None:
    """Toggling fullscreen can take the focus and hand it back: not the player leaving."""
    import pygame

    from src.application.game import Game

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.display.set_mode((320, 240))
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    seen: list[int] = []
    monkeypatch.setattr(game.scene_manager, "handle_event", lambda event: seen.append(event.type))

    game.screen.window.built((320, 240))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    game._handle_events()
    assert pygame.WINDOWFOCUSLOST not in seen

    game.screen.window.grace_until = 0.0
    pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    game._handle_events()
    assert pygame.WINDOWFOCUSLOST in seen


# -- the screen the last session closed on -------------------------------------


def test_a_screen_is_found_by_its_name() -> None:
    assert DESK.called("DP-2") == RIGHT
    assert DESK.called("HDMI-9") is None
    assert DESK.called(None) is None
    assert DESK.called("") is None


def test_a_desk_known_by_size_alone_has_no_names_to_match() -> None:
    from src.core.display.monitors import degraded

    assert degraded(((1920, 1080), (1280, 720))).called("") is None


def _opened_on(monkeypatch, screen_name: str | None) -> int:
    """Open a Screen over ``DESK`` and return the display index asked of ``set_mode``."""
    import pygame

    from src.application.screen import Screen
    from src.core.display.letterbox import FitPolicy
    from src.core.display.stage import Stage, WindowSpec

    asked: list[int] = []

    def set_mode(size, flags=0, depth=0, display=0, vsync=0):
        asked.append(display)
        return pygame.Surface(size)

    def no_position():
        raise pygame.error("no window yet")

    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    monkeypatch.setattr(pygame.display, "get_window_position", no_position)
    monkeypatch.setattr(Stage, "_window_handle", staticmethod(lambda: None))
    screen = Screen()
    screen.window = _watch()[0]
    screen.open(WindowSpec(size=(1280, 720)), FitPolicy.BARS, screen_name)
    return asked[-1]


def test_the_window_opens_on_the_screen_the_last_session_closed_on(monkeypatch) -> None:
    assert _opened_on(monkeypatch, "DP-2") == RIGHT.index


def test_a_remembered_screen_that_is_gone_opens_on_the_primary(monkeypatch) -> None:
    """The file from another machine, or the screen unplugged since: no crash, no guess."""
    assert _opened_on(monkeypatch, "HDMI-9") == DESK.primary.index


def test_no_remembered_screen_opens_on_the_primary(monkeypatch) -> None:
    assert _opened_on(monkeypatch, None) == DESK.primary.index


def test_the_screen_name_is_only_given_when_the_platform_names_screens(monkeypatch) -> None:
    import pygame

    from src.application.screen import Screen
    from src.core.display.monitors import degraded

    monkeypatch.setattr(pygame.display, "get_window_position", lambda: (3000, 100))
    screen = Screen()
    screen.window = _watch()[0]
    assert screen.screen_name() == "DP-2"

    screen.window = _watch([degraded(((1920, 1080),))])[0]
    assert screen.screen_name() is None
