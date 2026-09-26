"""Always-on player HUD (UI-7): anchoring, scaling, gauges and dirty rects."""

import os
from itertools import pairwise
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import Colors
from src.core.display.framing import Framing
from src.ui.hud import (
    HUD,
    HUD_BAR_GAP,
    HUD_BAR_HEIGHT,
    HUD_BAR_WIDTH,
    HUD_MARGIN,
    HUD_PIP_SIZE,
    HUD_TRACK,
    HudLayout,
    bar_width_for,
    health_color,
    posture_color,
)
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_CRIT, TEXT_OK, TEXT_WARN


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


def _surface(width: int = 1024, height: int = 768) -> pygame.Surface:
    return pygame.Surface((width, height))


def _hud(width: int = 1024, height: int = 768) -> HUD:
    return HUD(PanelRenderer(_surface(width, height)))


def _player(**overrides) -> SimpleNamespace:
    """Fake player with the stats the HUD reads (thresholds exercised below)."""
    base = {
        "health": 100.0,
        "max_health": 100.0,
        "guard_posture": 100.0,
        "guard_posture_max": 100.0,
        "guard_lockout_timer": 0.0,
        "dash_charges": 2,
        "max_dash_charges": 2,
        "combat": SimpleNamespace(combo_count=0, combo_timer=0.0),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _count(surface: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> int:
    """How many pixels inside ``rect`` carry exactly ``color``."""
    return sum(
        1
        for x in range(rect.left, rect.right)
        for y in range(rect.top, rect.bottom)
        if surface.get_at((x, y))[:3] == color
    )


def test_no_player_lays_out_and_draws_nothing() -> None:
    hud = _hud()
    assert hud.layout(None) is None
    assert hud.draw(None) == []


def test_player_disappearing_hands_its_last_frame_back_once() -> None:
    """A vanished gauges' area is refreshed once, then no longer reported."""
    hud = _hud()
    first = hud.draw(_player())
    assert first, "the HUD painted its gauges"

    stale = hud.draw(None)
    assert stale == first, "the gauges' last frame must be presented once more"
    assert hud.draw(None) == []


def test_health_and_posture_anchor_to_the_bottom_left_corner() -> None:
    layout = _hud(1024, 768).layout(_player())
    assert isinstance(layout, HudLayout)
    assert layout.health_bar.bottom == 768 - HUD_MARGIN
    assert layout.posture_bar.bottom == 768 - HUD_MARGIN - HUD_BAR_HEIGHT - HUD_BAR_GAP
    assert layout.health_bar.height == HUD_BAR_HEIGHT
    # Both gauges share the label gutter, right of the left margin.
    assert layout.health_bar.x == layout.posture_bar.x
    assert layout.health_bar.x > HUD_MARGIN


def test_hud_scale_changes_player_geometry() -> None:
    normal = _hud().layout(_player())
    scaled_hud = _hud()
    scaled_hud.set_scale(1.2)
    scaled = scaled_hud.layout(_player())

    assert isinstance(normal, HudLayout)
    assert isinstance(scaled, HudLayout)
    assert scaled.health_bar.height > normal.health_bar.height


def test_full_health_fills_the_whole_bar() -> None:
    layout = _hud().layout(_player())
    assert layout.health_fill == layout.health_bar
    assert layout.health_color == TEXT_OK


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(1.0, TEXT_OK), (0.6, TEXT_OK), (0.4, TEXT_WARN), (0.2, TEXT_CRIT), (0.0, TEXT_CRIT)],
)
def test_health_color_thresholds(ratio: float, expected: tuple[int, int, int]) -> None:
    assert health_color(ratio) == expected
    layout = _hud().layout(_player(health=ratio * 100))
    assert layout.health_color == expected
    assert layout.health_fill.width == int(layout.health_bar.width * ratio)


def test_guard_lockout_paints_the_posture_gauge_red() -> None:
    assert posture_color(1.0, 0.0) == TEXT_OK
    assert posture_color(0.3, 0.0) == TEXT_WARN
    assert posture_color(1.0, 0.2) == TEXT_CRIT
    layout = _hud().layout(_player(guard_posture=40.0, guard_lockout_timer=0.3))
    assert layout.posture_color == TEXT_CRIT
    assert layout.posture_fill.width == int(layout.posture_bar.width * 0.4)


def test_dash_pips_count_charges_and_anchor_bottom_right() -> None:
    layout = _hud(1024, 768).layout(_player(dash_charges=1, max_dash_charges=3))
    assert len(layout.dash_pips) == 3
    assert [filled for _, filled in layout.dash_pips] == [True, False, False]
    rects = [rect for rect, _ in layout.dash_pips]
    assert rects[-1].right == 1024 - HUD_MARGIN
    assert all(rect.bottom == 768 - HUD_MARGIN for rect in rects)
    assert all(rect.height == HUD_PIP_SIZE for rect in rects)
    # No overlap, and the row reads left-to-right in charge order.
    assert all(a.right < b.left for a, b in pairwise(rects))


def test_combo_is_hidden_at_zero_and_shown_with_its_decay() -> None:
    hidden = _hud().layout(_player())
    assert hidden.combo_pos is None and hidden.combo_bar is None and hidden.combo_fill is None

    shown = _hud().layout(_player(combat=SimpleNamespace(combo_count=4, combo_timer=0.25)))
    assert shown.combo_text == "x4"
    assert shown.combo_pos is not None and shown.combo_bar is not None
    assert shown.combo_fill is not None
    # Combat.COMBO_WINDOW is 0.5 s: a quarter of a second left halves the bar.
    assert shown.combo_fill.width == int(shown.combo_bar.width * 0.5)
    # Stacked above the dash row, right-aligned, still on screen.
    assert shown.combo_bar.right == 1024 - HUD_MARGIN
    assert shown.combo_bar.bottom < 768 - HUD_MARGIN - HUD_PIP_SIZE
    assert shown.combo_pos[0] >= 0 and shown.combo_pos[1] >= 0


@pytest.mark.parametrize("width", [320, 800, 1280, 1440, 1920, 2560])
def test_layout_never_leaves_the_display(width: int) -> None:
    """Responsive: every gauge stays inside the screen at any width (UI-6)."""
    layout = _hud(width, 720).layout(_player(dash_charges=2, max_dash_charges=2))
    assert layout is not None
    assert layout.health_bar.left - HUD_MARGIN >= 0, "the HP label must stay on screen"
    assert layout.health_bar.right <= width
    assert layout.posture_bar.right <= width
    assert max(rect.right for rect, _ in layout.dash_pips) <= width


@pytest.mark.parametrize("width", [500, 1152, 1280, 1920, 2560, 3840])
def test_the_bar_is_the_same_width_on_every_target(width: int) -> None:
    """It used to be 22% of the display, so the HUD was a different size
    depending on a video setting. The target is a constant, so the bar is too."""
    assert bar_width_for(width) == HUD_BAR_WIDTH


def test_the_bar_shrinks_rather_than_clipping_on_a_narrow_target() -> None:
    narrow = 2 * HUD_MARGIN + 10
    assert bar_width_for(narrow) < HUD_BAR_WIDTH
    assert bar_width_for(narrow) <= narrow - 2 * HUD_MARGIN


def test_draw_paints_the_gauges_and_returns_their_rects() -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))

    rects = hud.draw(_player(health=50.0))

    layout = hud.layout(_player(health=50.0))
    assert layout is not None
    # The dirty rects cover the labels too, so they contain the bare bars.
    assert any(rect.contains(layout.health_bar) for rect in rects)
    assert any(rect.left < layout.health_bar.left for rect in rects)
    assert surface.get_at(layout.health_fill.center)[:3] == TEXT_WARN
    assert any(
        surface.get_at(rect.center)[:3] == Colors.sky_blue
        for rect, filled in layout.dash_pips
        if filled
    )


def test_draw_represents_last_frame_so_an_expired_combo_disappears() -> None:
    """The HUD hands both frames' rects over: the loop presents dirty rects only."""
    hud = _hud()
    combo = SimpleNamespace(combo_count=3, combo_timer=0.4)
    with_combo = hud.draw(_player(combat=combo))
    combo_bar = hud.layout(_player(combat=combo)).combo_bar
    assert combo_bar is not None
    assert any(rect.contains(combo_bar) for rect in with_combo)

    without_combo = hud.draw(_player())
    assert any(rect.contains(combo_bar) for rect in without_combo), (
        "the stale combo area must be presented"
    )


def test_gauges_shrink_without_leaving_stale_pixels() -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))
    bar = hud.layout(_player()).health_bar
    inner = bar.inflate(-2, -2)  # inside the 1 px border

    hud.draw(_player(health=100.0))
    assert _count(surface, inner, TEXT_OK) == inner.width * inner.height

    surface.fill(Colors.black)
    hud.draw(_player(health=10.0))
    assert _count(surface, inner, TEXT_OK) == 0, "the full-health bar must be erased"
    assert _count(surface, inner, TEXT_CRIT) > 0
    assert _count(surface, inner, HUD_TRACK) > 0, "the emptied part shows the track"


def test_gameplay_scene_draws_the_hud_even_with_debug_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UI-7: the HUD is player-facing, so it is not gated by ``DEBUG``."""
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.core.rendering.camera import Camera
    from src.core.rendering.renderer import Renderer

    monkeypatch.delenv("DEBUG", raising=False)
    surface = _surface(1024, 768)
    renderer = Renderer(surface, Camera(Framing(float(1024), float(768))))
    level = SimpleNamespace(
        renderer=renderer,
        player=_player(health=20.0),
        draw=lambda *args, **kwargs: None,
    )
    scene = GameplayScene(SimpleNamespace(clock=None), level_id=0, level=level)

    scene.draw(pygame.display.get_surface())

    # Nothing to declare any more: the next frame erases the whole target, so
    # the only thing that matters is that the gauges reached the pixels.
    hud_layout = renderer.ui_manager.hud.layout(level.player)
    assert hud_layout is not None
    assert surface.get_at(hud_layout.health_fill.center)[:3] == TEXT_CRIT


def test_gameplay_scene_hud_survives_a_level_without_a_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duck-typed levels (overlays, tests) may not expose ``player``."""
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.core.rendering.camera import Camera
    from src.core.rendering.renderer import Renderer

    monkeypatch.delenv("DEBUG", raising=False)
    renderer = Renderer(_surface(), Camera(Framing(float(1024), float(768))))
    level = SimpleNamespace(renderer=renderer, draw=lambda *args, **kwargs: None)
    scene = GameplayScene(SimpleNamespace(clock=None), level_id=0, level=level)

    assert scene.draw(pygame.display.get_surface()) is None
