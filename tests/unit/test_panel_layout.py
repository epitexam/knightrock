"""Responsive debug panels: column-flow layout, measure-before-draw."""

import os

import pygame
import pytest

from src.ui.panel_renderer import PanelLayout, PanelLayoutError, PanelRenderer
from src.ui.ui_manager import UIManager


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def renderer() -> PanelRenderer:
    return PanelRenderer(pygame.Surface((640, 480)))


def test_layout_stacks_panels_downward() -> None:
    layout = PanelLayout(640, 480)

    first = layout.place(200, 100)
    second = layout.place(200, 100)

    assert first == (10, 10)
    assert second[0] == 10
    assert second[1] == 10 + 100 + 8


def test_layout_wraps_to_a_new_column_on_overflow() -> None:
    layout = PanelLayout(640, 300)

    first = layout.place(200, 200)
    second = layout.place(200, 200)

    assert first == (10, 10)
    assert second[1] == 10
    assert second[0] > first[0]


def test_layout_reports_panel_too_large_for_display() -> None:
    layout = PanelLayout(100, 480)

    with pytest.raises(PanelLayoutError, match="cannot fit"):
        layout.place(200, 50)


def test_layout_reports_when_no_free_slot_exists() -> None:
    layout = PanelLayout(100, 100)
    layout.place(80, 80)

    with pytest.raises(PanelLayoutError, match="no free slot"):
        layout.place(80, 20)


def test_manual_placement_relocates_instead_of_overlapping() -> None:
    layout = PanelLayout(640, 480)
    first = layout.place_at(10, 10, 200, 100)

    second = layout.place_at(10, 10, 200, 100)

    assert isinstance(first, tuple)
    assert isinstance(second, tuple)
    assert not pygame.Rect(*first, 200, 100).colliderect(pygame.Rect(*second, 200, 100))


def test_layout_pins_top_right_inside_bounds() -> None:
    layout = PanelLayout(640, 480)

    x, y = layout.place_top_right(200, 100)

    assert (x, y) == (640 - 10 - 200, 10)

    tiny = PanelLayout(100, 480)
    with pytest.raises(PanelLayoutError, match="cannot fit"):
        tiny.place_top_right(200, 100)


def test_measure_matches_drawn_height(renderer: PanelRenderer) -> None:
    lines = ["line1", "a longer line"]
    width, height = renderer.measure_panel(lines, title="TEST")

    assert width > 0
    assert renderer.draw_panel(10, 10, lines, title="TEST") == height + 12


def test_default_line_height_comes_from_the_font(renderer: PanelRenderer) -> None:
    linesize = renderer.debug_font.get_linesize()

    _, height = renderer.measure_panel(["a", "b"])

    assert height >= 2 * linesize


def test_draw_panel_with_layout_flows_without_error(renderer: PanelRenderer) -> None:
    layout = PanelLayout(640, 480)
    lines = [f"row {i}" for i in range(10)]

    first = renderer.draw_panel(0, 0, lines, title="A", layout=layout)
    second = renderer.draw_panel(0, 0, ["short"], title="B", layout=layout)

    assert first > 0
    assert second > 0


def test_positional_calls_stay_backward_compatible(renderer: PanelRenderer) -> None:
    assert renderer.draw_panel(10, 10, ["x"], title="T") > 0


def test_debug_panels_signal_impossible_small_display_placement() -> None:
    from types import SimpleNamespace  # noqa: PLC0415 - local test double

    ui = UIManager(pygame.Surface((640, 480)))
    player = SimpleNamespace(
        state_machine=SimpleNamespace(
            current_state_name="idle", previous_state_name=None, history=[]
        ),
        velocity=pygame.math.Vector2(0, 0),
        on_surface={"floor": True, "left": False, "right": False},
        move_axis=0.0,
        jump_buffer_timer=0.0,
        coyote_timer=0.0,
        midair_jumps_left=1,
        wall_jumps_left=1,
        dash=SimpleNamespace(requested=False, duration_timer=0.0),
        combat=None,
        stagger_timer=0.0,
        invincibility_timer=0.0,
        health=100.0,
        max_health=100.0,
        guard_posture=50.0,
        guard_posture_max=100.0,
        guard_lockout_timer=0.0,
        guard_riposte_timer=0.0,
        dash_charges=2,
        max_dash_charges=2,
        dash_penalty_timer=0.0,
        dash_recharge_timer=0.0,
        speed=350.0,
        floor_control=25.0,
        air_control=12.0,
        jump_height=750.0,
        wall_jump_height=600.0,
        dash_speed=800.0,
        dash_duration=0.12,
        dash_friction=15.0,
        gravity_scale=1.0,
        otg_timer=0.0,
    )
    ui.renderer.surface = pygame.Surface((640, 480))
    from src.ui.panel_renderer import PanelLayout as Layout  # noqa: PLC0415

    layout = Layout(640, 480)
    with pytest.warns(RuntimeWarning, match="no free slot|cannot fit"):
        ui.draw_state_panel(10, 10, player, layout=layout)
        assert ui.draw_stats_panel(10, 10, player, layout=layout) == 0
        ui.draw_help_panel(10, 10, layout=layout, layers={})
