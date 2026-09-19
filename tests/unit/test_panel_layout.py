"""Responsive debug panels: column-flow layout, measure-before-draw."""

import os

import pygame
import pytest

from src.ui.panel_renderer import PanelLayout, PanelRenderer
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


def test_layout_clamps_panels_inside_narrow_displays() -> None:
    layout = PanelLayout(100, 480)

    x, y = layout.place(200, 50)

    assert x == 10
    assert y == 10


def test_layout_pins_top_right_inside_bounds() -> None:
    layout = PanelLayout(640, 480)

    x, y = layout.place_top_right(200, 100)

    assert (x, y) == (640 - 10 - 200, 10)

    tiny = PanelLayout(100, 480)
    x, _ = tiny.place_top_right(200, 100)
    assert x == 10


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
    layout = PanelLayout(640, 200)
    lines = [f"row {i}" for i in range(20)]

    first = renderer.draw_panel(0, 0, lines, title="A", layout=layout)
    second = renderer.draw_panel(0, 0, ["short"], title="B", layout=layout)

    assert first > 0
    assert second > 0


def test_positional_calls_stay_backward_compatible(renderer: PanelRenderer) -> None:
    assert renderer.draw_panel(10, 10, ["x"], title="T") > 0


def test_debug_panels_fit_a_small_display() -> None:
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
    ui.renderer.display_surface = pygame.Surface((640, 480))
    from src.ui.panel_renderer import PanelLayout as Layout  # noqa: PLC0415

    layout = Layout(640, 480)
    ui.draw_state_panel(10, 10, player, layout=layout)
    ui.draw_stats_panel(10, 10, player, layout=layout)
    ui.draw_help_panel(10, 10, layout=layout)
    ui.draw_performance_panel(
        fps=60.0,
        sprite_count=1,
        combat_count=1,
        entity_count=1,
        collision_count=1,
        hit_stop=0.0,
        spawn_cooldown=0.0,
        layout=layout,
    )
