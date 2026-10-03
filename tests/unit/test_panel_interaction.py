"""Debug panels interactivity: ``×`` close buttons, drag & drop, F5 reset."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.gameplay_scene import GameplayScene
from src.combat.frame_data import Stance
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.ui import ui_manager as ui_ids
from src.ui.panel_renderer import (
    PANEL_CLOSE_BOX,
    PANEL_CLOSE_GAP,
    PANEL_CLOSE_INSET,
    PANEL_MARGIN,
    PanelInteraction,
    PanelLayout,
    PanelRenderer,
    _close_glyph,
    close_box_rect,
)
from src.ui.styles import PANEL_BORDER, TEXT_MUTED, TEXT_TITLE
from src.ui.ui_manager import UIManager
from tests.unit.helpers import make_overlay


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


def _frame(ui: UIManager) -> None:
    """Promote the rects just drawn, exactly as the next frame's pass does."""
    ui.renderer.interaction.begin_frame()


def _mousedown(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)


def _mouseup(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos)


def _motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0))


def _draw_help(ui: UIManager, size: tuple[int, int], *, with_player: bool = False) -> PanelLayout:
    """Draw the DEBUG KEYS panel through the flow and settle the frame.

    ``with_player`` adds the live attack-button block, which is what a real frame
    draws -- ``draw_debug_panels`` always passes the player -- so the geometry
    these tests measure is the geometry the game produces. Without it the panel
    is a different size and a drag test would be asserting against a shape no
    frame ever had.
    """
    layout = PanelLayout(*size)
    player = _player() if with_player else None
    ui.draw_help_panel(10, 10, layout=layout, layers={}, player=player)
    _frame(ui)
    return layout


def test_measure_reserves_room_for_the_close_button() -> None:
    """A closable panel is widened so the header never runs under the ``×``."""
    renderer = PanelRenderer(pygame.Surface((640, 480)))
    lines = ["FPS       60.0"]
    title = "PERFORMANCE"

    plain_w, plain_h = renderer.measure_panel(lines, title=title, padding=12)
    reserved_w, reserved_h = renderer.measure_panel(
        lines, title=title, padding=12, reserve_close=True
    )

    title_w = renderer.render_text(title, renderer.title_font, TEXT_TITLE).get_width()
    assert reserved_h == plain_h, "the ``×`` is drawn in the header, not below it"
    assert reserved_w == max(
        plain_w, title_w + PANEL_CLOSE_GAP + PANEL_CLOSE_BOX + PANEL_CLOSE_INSET + 12
    )
    assert 12 + title_w <= close_box_rect(reserved_w, 0).left, "title runs under the ``×``"


def test_close_button_is_drawn_inside_the_top_right_corner() -> None:
    surface = pygame.Surface((320, 160))
    surface.fill((0, 0, 0))
    renderer = PanelRenderer(surface)

    rect = renderer.draw_close_button(0, 0, 200)

    assert rect == close_box_rect(200, 0)
    assert rect.right == 200 - PANEL_CLOSE_INSET
    assert surface.get_at(rect.topleft)[:3] == PANEL_BORDER


def test_the_close_cross_is_the_same_thing_at_every_panel_scale() -> None:
    """The ``×`` has to be *drawn* at the scales the panels are shrunk to.

    This is the pixel test the feature was missing. Its hit box is sized from
    ``panel_scale`` and a test already pinned the box, so the one thing nothing
    checked was what lands inside it: the insets were the pixels 3 and 4, and a
    7px box has no room for a 4px inset. At 0.5 the two endpoints met and the cross
    was a single pixel, and at 0.4 the second landed *before* the first, so it was
    drawn diagonally out of its own box. Both rungs are the ones a player reaches
    for precisely because the panels did not fit the window.

    So the invariant is that the stroke spans a real run of pixels at every rung
    rather than a collapsed or reversed line, checked on the surface, because that
    is what the player sees. The rung where the cross is exact is pinned too, so a
    fix that moved the 1.0 glyph while fixing the small ones would be caught.
    """
    for panel_scale in (1.2, 1.0, 0.8, 0.6, 0.5, 0.4):
        surface = pygame.Surface((320, 160))
        surface.fill((0, 0, 0))
        renderer = PanelRenderer(surface, panel_scale=panel_scale)

        rect = renderer.draw_close_button(0, 0, 200)

        lit = [
            (px, py)
            for px in range(rect.width)
            for py in range(rect.height)
            if surface.get_at((rect.left + px, rect.top + py))[:3] == TEXT_MUTED
        ]
        xs = {px for px, _ in lit}
        ys = {py for _, py in lit}

        assert len(lit) >= 2, f"the × is missing at {panel_scale}: {len(lit)}px lit"
        assert max(xs) - min(xs) >= 1, f"the × collapsed to a line at {panel_scale}"
        assert max(ys) - min(ys) >= 1, f"the × collapsed to a line at {panel_scale}"
        assert min(xs) >= 1 and max(xs) <= rect.width - 2, "the × escaped its box"
        assert min(ys) >= 1 and max(ys) <= rect.height - 2, "the × escaped its box"

        # Two strokes, not one. A single diagonal spans both axes too, so the
        # bounds above cannot tell a cross from one line -- but only a cross lights
        # all four inner corners.
        near, far, _ = _close_glyph(rect)
        corners = [near, (far[0], near[1]), (near[0], far[1]), far]
        unlit = [c for c in corners if surface.get_at(c)[:3] != TEXT_MUTED]
        assert not unlit, f"at {panel_scale} only one stroke was drawn, not a ×: {unlit}"

    exact = pygame.Surface((320, 160))
    exact.fill((0, 0, 0))
    box = PanelRenderer(exact).draw_close_button(0, 0, 200)
    assert exact.get_at((box.left + 3, box.top + 3))[:3] == TEXT_MUTED, "the 1.0 × moved"

    # The share of the box the inset takes is what keeps the two ends apart, so
    # the invariant is pinned across every box size, reachable or not -- raising
    # 22% to 30% inverts a 6px box again. It starts at 4px because a 2px or 3px
    # box cannot hold a diagonal at any inset: there is no room between the ends.
    for edge in range(4, 18):
        near, far, _ = _close_glyph(pygame.Rect(0, 0, edge, edge))
        assert far[0] > near[0] and far[1] > near[1], f"inverted at a {edge}px box"

    # The stroke is part of the contract too, and the pixel bounds above cannot
    # see it: a 1px cross satisfies all of them and looks like an ant's hair.
    assert _close_glyph(close_box_rect(200, 0, 1.0))[2] == 2, "the 1.0 × got thinner"
    assert _close_glyph(close_box_rect(200, 0, 0.4))[2] == 1, "the 0.4 × got thicker"


def test_close_click_uses_topmost_panel() -> None:
    interaction = PanelInteraction()
    interaction.panels = {
        "under": pygame.Rect(0, 0, 300, 100),
        "top": pygame.Rect(10, 0, 100, 100),
    }
    close = interaction.close_rect("top")
    assert close is not None

    assert interaction.handle_event(_mousedown(close.center)) is True
    assert interaction.is_closed("top")
    assert not interaction.is_closed("under")


def test_close_click_hides_one_panel_until_f5() -> None:
    """A click on the ``×`` skips that panel only; F5 brings it back."""
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    _draw_help(ui, size)

    close = ui.renderer.interaction.close_rect(ui_ids.PANEL_KEYS)
    assert close is not None

    assert ui.handle_panel_event(_mousedown(close.center)) is True
    assert ui.renderer.interaction.is_closed(ui_ids.PANEL_KEYS)

    layout = PanelLayout(*size)
    assert ui.draw_help_panel(10, 10, layout=layout, layers={}) == 0
    assert ui.draw_legend_panel(10, 10, layout=layout) > 0, "the rest of the stack survives"

    ui.reset_debug_panels()
    assert not ui.renderer.interaction.is_closed(ui_ids.PANEL_KEYS)
    assert ui.draw_help_panel(10, 10, layout=PanelLayout(*size), layers={}) > 0


def test_closed_panel_stops_swallowing_clicks() -> None:
    """The ghost of a closed panel must not keep eating mouse input."""
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    layout = _draw_help(ui, size)
    rect = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]

    close = ui.renderer.interaction.close_rect(ui_ids.PANEL_KEYS)
    assert close is not None
    assert ui.handle_panel_event(_mousedown(close.center)) is True
    # No ghost frame: the rect leaves the registry with the click.
    assert ui_ids.PANEL_KEYS not in ui.renderer.interaction.panels
    assert ui.handle_panel_event(_mousedown(rect.center)) is False

    # Next frame: the panel is skipped, so the registry stays clean.
    ui.draw_help_panel(10, 10, layout=layout, layers={})
    _frame(ui)
    assert ui_ids.PANEL_KEYS not in ui.renderer.interaction.panels
    assert ui.handle_panel_event(_mousedown(rect.center)) is False


def test_only_left_click_and_panel_hits_are_consumed() -> None:
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    _draw_help(ui, size)
    rect = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]

    assert ui.handle_panel_event(_mousedown(rect.center, button=3)) is False
    assert ui.renderer.interaction.drag_id is None
    assert ui.handle_panel_event(_mousedown((1, 1))) is False
    assert ui.renderer.interaction.drag_id is None
    assert ui.handle_panel_event(_mousedown(rect.center)) is True
    assert ui.renderer.interaction.drag_id == ui_ids.PANEL_KEYS


def test_focus_loss_cancels_drag_without_persisting_target() -> None:
    interaction = PanelInteraction()
    interaction.panels["panel"] = pygame.Rect(20, 30, 100, 80)
    interaction.positions["panel"] = (20, 30)
    interaction.start_drag("panel", (25, 35))
    interaction.move_drag((500, 500))

    consumed = interaction.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))

    assert consumed is True
    assert interaction.drag_id is None
    assert interaction.positions["panel"] == (20, 30)
    assert interaction.handle_event(_motion((600, 600))) is False


def test_explicit_cancel_discards_drag_and_closing_panel_clears_it() -> None:
    interaction = PanelInteraction()
    interaction.panels["first"] = pygame.Rect(10, 10, 100, 80)
    interaction.panels["second"] = pygame.Rect(200, 10, 100, 80)
    interaction.start_drag("first", (15, 15))
    interaction.move_drag((300, 300))

    interaction.cancel_drag()
    assert interaction.drag_id is None
    assert "first" not in interaction.positions

    interaction.start_drag("second", (205, 15))
    interaction.set_closed("second")
    assert interaction.drag_id is None
    assert "second" not in interaction.positions


def test_drag_and_drop_moves_a_panel_out_of_the_flow() -> None:
    """Dropping a panel stores its position; it is redrawn exactly there."""
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    _draw_help(ui, size, with_player=True)
    rect = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]

    start = rect.topleft
    assert ui.handle_panel_event(_mousedown(start)) is True
    # Inside the display *for the panel as drawn*. The drop is clamped to the
    # surface, so a fixed x=640 stopped being where it was asked to go once the
    # live attack block made the panel wider than the space to the right edge --
    # the clamp was working, and the test was asserting a pre-clamp position.
    target = (size[0] - rect.width - 20, 300)
    assert target[0] + rect.width <= size[0], "the target does not fit the surface"
    assert ui.handle_panel_event(_motion(target)) is True
    assert ui.handle_panel_event(_mouseup(target)) is True
    assert ui.renderer.interaction.drag_id is None
    assert ui.renderer.interaction.positions[ui_ids.PANEL_KEYS] == target

    _draw_help(ui, size)
    moved = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]
    assert moved.topleft == target


def test_flow_packs_around_a_dropped_panel() -> None:
    """Panels drawn after a drop still dodge it: responsive after a drag."""
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    layout = PanelLayout(*size)

    ui.draw_legend_panel(10, 10, layout=layout)
    ui.renderer.interaction.positions[ui_ids.PANEL_KEYS] = (PANEL_MARGIN, PANEL_MARGIN)
    ui.draw_help_panel(10, 10, layout=layout, layers={})
    ui.draw_stats_panel(10, 10, _player(), layout=layout)
    _frame(ui)

    keys = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]
    legend = ui.renderer.interaction.panels[ui_ids.PANEL_LEGEND]
    stats = ui.renderer.interaction.panels[ui_ids.PANEL_STATS]

    assert not keys.colliderect(legend)
    assert not stats.colliderect(keys)
    assert not stats.colliderect(legend)
    assert ui.renderer.interaction.positions[ui_ids.PANEL_KEYS] == keys.topleft


def test_dragged_panel_is_clamped_inside_the_display() -> None:
    size = (640, 480)
    ui = UIManager(pygame.Surface(size))
    _draw_help(ui, size)
    rect = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]

    assert ui.handle_panel_event(_mousedown(rect.topleft)) is True
    assert ui.handle_panel_event(_motion((5000, 5000))) is True
    assert ui.handle_panel_event(_mouseup((5000, 5000))) is True

    _draw_help(ui, size)
    moved = ui.renderer.interaction.panels[ui_ids.PANEL_KEYS]
    assert pygame.Rect(0, 0, *size).contains(moved)
    assert moved.right <= size[0] - PANEL_MARGIN
    assert moved.bottom <= size[1] - PANEL_MARGIN


def test_dropped_position_is_normalized_after_surface_reduction() -> None:
    renderer = PanelRenderer(pygame.Surface((1024, 768)))
    renderer.interaction.positions["panel"] = (900, 700)
    renderer.surface = pygame.Surface((640, 480))
    layout = PanelLayout(640, 480)

    renderer.draw_panel(0, 0, ["line"], panel_id="panel", layout=layout)
    renderer.interaction.begin_frame()

    position = renderer.interaction.positions["panel"]
    rect = renderer.interaction.panels["panel"]
    assert position == rect.topleft
    assert position[0] <= 640 - PANEL_MARGIN
    assert position[1] <= 480 - PANEL_MARGIN


def test_f5_reset_reopens_panels_and_clears_drops() -> None:
    size = (1024, 768)
    ui = UIManager(pygame.Surface(size))
    _draw_help(ui, size)

    close = ui.renderer.interaction.close_rect(ui_ids.PANEL_KEYS)
    assert close is not None
    ui.handle_panel_event(_mousedown(close.center))
    ui.renderer.interaction.positions[ui_ids.PANEL_LEGEND] = (500, 500)

    ui.reset_debug_panels()

    assert ui.renderer.interaction.closed == set()
    assert ui.renderer.interaction.positions == {}
    assert ui.renderer.interaction.drag_id is None


def test_gameplay_scene_routes_panel_clicks_and_resets_on_f5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the scene gives the mouse to the panels, F5 wipes the state."""
    monkeypatch.setenv("DEBUG", "1")
    surface = pygame.Surface((1024, 768))
    renderer = Renderer(
        surface, Camera(Framing(float(1024), float(768))), overlay=make_overlay(surface)
    )
    scene = GameplayScene(
        SimpleNamespace(ui=renderer.overlay), level_id=0, level=SimpleNamespace(renderer=renderer)
    )
    ui = renderer.overlay

    ui.draw_help_panel(10, 10, layout=PanelLayout(1024, 768), layers={})
    _frame(ui)
    close = ui.renderer.interaction.close_rect(ui_ids.PANEL_KEYS)
    assert close is not None

    scene.handle_event(_mousedown(close.center))
    assert ui.renderer.interaction.is_closed(ui_ids.PANEL_KEYS)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
    assert not ui.renderer.interaction.is_closed(ui_ids.PANEL_KEYS)
    assert ui.world_ui.layers["panels"] is False, "F5 still toggles the layer"


def test_gameplay_scene_ignores_panels_while_the_layer_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invisible panel must not grab the cursor."""
    monkeypatch.setenv("DEBUG", "1")
    surface = pygame.Surface((1024, 768))
    renderer = Renderer(
        surface, Camera(Framing(float(1024), float(768))), overlay=make_overlay(surface)
    )
    scene = GameplayScene(
        SimpleNamespace(ui=renderer.overlay), level_id=0, level=SimpleNamespace(renderer=renderer)
    )
    ui = renderer.overlay

    ui.draw_help_panel(10, 10, layout=PanelLayout(1024, 768), layers={})
    _frame(ui)

    ui.world_ui.toggle("panels")  # off
    scene.handle_event(_mousedown(ui.renderer.interaction.panels[ui_ids.PANEL_KEYS].center))
    assert ui.renderer.interaction.drag_id is None

    ui.world_ui.toggle("panels")  # back on
    scene.handle_event(_mousedown(ui.renderer.interaction.panels[ui_ids.PANEL_KEYS].center))
    assert ui.renderer.interaction.drag_id == ui_ids.PANEL_KEYS


def test_panel_mouse_routing_is_skipped_without_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    surface = pygame.Surface((1024, 768))
    renderer = Renderer(
        surface, Camera(Framing(float(1024), float(768))), overlay=make_overlay(surface)
    )
    scene = GameplayScene(
        SimpleNamespace(ui=renderer.overlay), level_id=0, level=SimpleNamespace(renderer=renderer)
    )
    ui = renderer.overlay

    # Even with a stale rect registered, no debug panel eats the click.
    ui.renderer.interaction.register(ui_ids.PANEL_KEYS, pygame.Rect(0, 0, 200, 200))
    _frame(ui)
    scene.handle_event(_mousedown((50, 50)))
    assert ui.renderer.interaction.drag_id is None


def _player() -> SimpleNamespace:
    """Minimal player for the STATS panel (the fields it reads)."""
    return SimpleNamespace(
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
        stagger_timer=0.0,
        invincibility_timer=0.0,
        otg_timer=0.0,
        # The DEBUG KEYS panel reads both when a player is passed to it. Absent
        # before, its live block was simply never exercised here and the panel
        # under test was three rows smaller than any frame the game draws.
        stance=Stance.GROUND,
        combat=SimpleNamespace(cooldowns={}),
    )
