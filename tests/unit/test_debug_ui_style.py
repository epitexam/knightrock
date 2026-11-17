"""The debug panels speak the menus' language: the pixel font, and the way around
said on the panel being looked at."""

from __future__ import annotations

import pygame
import pytest

from src.core.settings import Debug
from src.ui import panel_renderer
from src.ui.fonts import menu_font, menu_font_size
from src.ui.panel_renderer import PanelLayout, PanelRenderer
from src.ui.styles import SELECTION_BG
from src.ui.ui_manager import PANEL_KEYS, PANEL_PERFORMANCE, UIManager


@pytest.fixture(autouse=True)
def _display() -> None:
    pygame.init()
    pygame.display.set_mode((64, 64))


def _ui(size: tuple[int, int] = (1152, 648)) -> UIManager:
    return UIManager(pygame.Surface(size))


def test_the_panels_draw_with_the_menu_font() -> None:
    renderer = PanelRenderer(pygame.Surface((1152, 648)))
    assert renderer.debug_font is menu_font(menu_font_size(Debug.FONT_SIZE, 1.0))


def test_the_close_box_lights_where_the_pointer_is_in_the_picture() -> None:
    """Hover is read from the events the panels get, in target coordinates.

    It used to read ``pygame.mouse.get_pos()``, the window's coordinates, so
    with letterbox bars or a zoom the box lit up somewhere the pointer was not.
    """
    ui = _ui()
    renderer = ui.renderer
    renderer.draw_panel(10, 10, ["line"], title="T", panel_id="probe")
    renderer.interaction.begin_frame()  # the next frame hit-tests what was drawn
    close = renderer.interaction.close_rect("probe")
    assert close is not None
    ui.handle_panel_event(
        pygame.event.Event(pygame.MOUSEMOTION, pos=close.center, rel=(1, 1), buttons=(0, 0, 0))
    )
    renderer.surface.fill((0, 0, 0))
    renderer.draw_panel(10, 10, ["line"], title="T", panel_id="probe")
    assert renderer.surface.get_at(close.topleft)[:3] == SELECTION_BG


def test_the_keys_panel_says_the_state_of_every_layer() -> None:
    ui = _ui()
    layers = {"boxes": True, "labels": False, "velocities": True, "statics": False, "panels": True}
    captured: list[list[str]] = []
    original = ui.renderer.draw_panel

    def spy(x, y, lines, *args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("panel_id") == PANEL_KEYS:
            captured.append(list(lines))
        return original(x, y, lines, *args, **kwargs)

    ui.renderer.draw_panel = spy  # type: ignore[method-assign]
    ui.draw_help_panel(10, 10, layers=layers)
    text = " ".join(captured[0])
    for shown in ("F1 boxes on", "F2 labels off", "F3 speed on", "F4 statics off", "F5 panels on"):
        assert shown in text


def test_the_compact_layout_says_how_to_move_on_the_panel_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(panel_renderer, "_compact_panels", True)
    ui = _ui()
    focus = ui.compact_panel_focus()
    footers = ui._panel_footers()
    assert list(footers) == [focus]
    position = ui.COMPACT_ORDER.index(focus) + 1
    assert footers[focus] == f"F10 next {position}/{len(ui.COMPACT_ORDER)} · F11 all"

    captured: dict[str, list[str]] = {}
    original = ui.renderer.draw_panel

    def spy(x, y, lines, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured[kwargs.get("panel_id") or ""] = list(lines)
        return original(x, y, lines, *args, **kwargs)

    ui.renderer.draw_panel = spy  # type: ignore[method-assign]
    ui.draw_performance_panel(
        fps=60.0,
        sprite_count=1,
        combat_count=1,
        entity_count=1,
        collision_count=1,
        hit_stop=0.0,
        spawn_cooldown=0.0,
        layout=PanelLayout(1152, 648),
    )
    assert not any("F10" in line for line in captured[PANEL_PERFORMANCE])


def test_with_every_panel_shown_the_way_back_is_said_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(panel_renderer, "_compact_panels", False)
    assert _ui()._panel_footers() == {PANEL_PERFORMANCE: "F11 one at a time"}
