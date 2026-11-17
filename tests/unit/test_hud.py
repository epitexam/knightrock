"""Always-on player HUD: gauges, dash and combo, slot reels, prompt."""

import os
import random
from itertools import pairwise
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.settings import Battery as BatterySettings
from src.core.settings import Clash, Combat, Fury
from src.entities.player_kit import (
    Battery,
    Direction,
    FuryGauge,
    PromptController,
    PromptKind,
    SlotMachine,
)
from src.ui.hud import (
    HUD,
    HUD_BAR_GAP,
    HUD_BAR_HEIGHT,
    HUD_BAR_LABELS,
    HUD_BAR_WIDTH,
    HUD_BATTERY_COLOR,
    HUD_BATTERY_EMPTY_COLOR,
    HUD_DARK_COLOR,
    HUD_FURY_COLOR,
    HUD_FURY_FULL_COLOR,
    HUD_MARGIN,
    HUD_PIP_SIZE,
    HUD_TIER_COLORS,
    HUD_TRACK,
    HudLayout,
    bar_width_for,
    battery_color,
    fury_color,
    health_color,
)
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_CRIT, TEXT_OK, TEXT_WARN
from tests.fakes import game_shape
from tests.unit.helpers import make_overlay


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
    """A player with the real kit, at rest; overrides replace a field outright."""
    fields = {
        "health": 100.0,
        "max_health": 100.0,
        "battery": Battery(),
        "fury": FuryGauge(),
        "slot": SlotMachine(),
        "prompt": PromptController(),
        "dash": SimpleNamespace(charges=2, max_charges=2),
        "combat": SimpleNamespace(combo_count=0, combo_timer=0.0),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _fury(amount: float = 0.0, dark: bool = False) -> FuryGauge:
    fury = FuryGauge()
    fury.gain(Fury.MAX if dark else amount)
    if dark:
        fury.start_dark()
    return fury


def _count(surface: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> int:
    """How many pixels inside ``rect`` carry exactly ``color``."""
    return sum(
        1
        for x in range(rect.left, rect.right)
        for y in range(rect.top, rect.bottom)
        if surface.get_at((x, y))[:3] == color
    )


def test_no_player_lays_out_and_draws_nothing() -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))

    assert hud.layout(None) is None
    assert hud.draw(None) is None
    assert surface.get_at((10, 10))[:3] == Colors.black, "nothing was painted"


def test_the_three_gauges_stack_from_the_bottom_left_corner() -> None:
    layout = _hud(1024, 768).layout(_player())
    assert isinstance(layout, HudLayout)
    assert [gauge.label for gauge in layout.gauges] == list(HUD_BAR_LABELS)
    bottoms = [gauge.bar.bottom for gauge in layout.gauges]
    assert bottoms[0] == 768 - HUD_MARGIN
    assert all(a - b == HUD_BAR_HEIGHT + HUD_BAR_GAP for a, b in pairwise(bottoms))
    assert len({gauge.bar.x for gauge in layout.gauges}) == 1, "one label gutter for all"
    assert layout.gauges[0].bar.x > HUD_MARGIN


def test_the_reserved_height_covers_the_three_gauges() -> None:
    hud = _hud()
    layout = hud.layout(_player())
    top = min(gauge.bar.top for gauge in layout.gauges)

    assert 768 - hud.reserved_height() <= top - HUD_MARGIN


def test_hud_scale_changes_player_geometry() -> None:
    normal = _hud().layout(_player())
    scaled_hud = _hud()
    scaled_hud.set_scale(1.2)
    scaled = scaled_hud.layout(_player())

    assert scaled.gauge("HP").bar.height > normal.gauge("HP").bar.height


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(1.0, TEXT_OK), (0.6, TEXT_OK), (0.4, TEXT_WARN), (0.2, TEXT_CRIT), (0.0, TEXT_CRIT)],
)
def test_health_color_thresholds(ratio: float, expected: tuple[int, int, int]) -> None:
    assert health_color(ratio) == expected
    gauge = _hud().layout(_player(health=ratio * 100)).gauge("HP")
    assert gauge.color == expected
    assert gauge.fill.width == int(gauge.bar.width * ratio)


def test_the_battery_turns_red_once_empty() -> None:
    battery = Battery()
    battery.amount = BatterySettings.MAX / 4
    gauge = _hud().layout(_player(battery=battery)).gauge("BAT")
    assert gauge.color == HUD_BATTERY_COLOR == battery_color(0.25)
    assert gauge.fill.width == int(gauge.bar.width * 0.25)

    battery.amount = 0.0
    assert _hud().layout(_player(battery=battery)).gauge("BAT").color == HUD_BATTERY_EMPTY_COLOR


def test_the_fury_gauge_says_when_it_can_be_spent() -> None:
    assert fury_color(is_full=False, in_dark=False) == HUD_FURY_COLOR
    assert fury_color(is_full=True, in_dark=False) == HUD_FURY_FULL_COLOR
    assert fury_color(is_full=True, in_dark=True) == HUD_DARK_COLOR

    filling = _hud().layout(_player(fury=_fury(40.0))).gauge("FURY")
    assert filling.color == HUD_FURY_COLOR
    assert filling.fill.width == int(filling.bar.width * 0.4)
    assert _hud().layout(_player(fury=_fury(Fury.MAX))).gauge("FURY").color == HUD_FURY_FULL_COLOR
    assert _hud().layout(_player(fury=_fury(dark=True))).gauge("FURY").color == HUD_DARK_COLOR


def test_dash_pips_count_charges_and_anchor_bottom_right() -> None:
    dash = SimpleNamespace(charges=1, max_charges=3)
    layout = _hud(1024, 768).layout(_player(dash=dash))
    assert [filled for _, filled in layout.dash_pips] == [True, False, False]
    rects = [rect for rect, _ in layout.dash_pips]
    assert rects[-1].right == 1024 - HUD_MARGIN
    assert all(rect.bottom == 768 - HUD_MARGIN for rect in rects)
    assert all(rect.height == HUD_PIP_SIZE for rect in rects)
    assert all(a.right < b.left for a, b in pairwise(rects))


def test_combo_is_hidden_at_zero_and_shown_with_its_decay() -> None:
    hidden = _hud().layout(_player())
    assert hidden.combo_pos is None and hidden.combo_bar is None and hidden.combo_fill is None

    half = Combat.COMBO_WINDOW / 2
    shown = _hud().layout(_player(combat=SimpleNamespace(combo_count=4, combo_timer=half)))
    assert shown.combo_text == "x4"
    assert shown.combo_color == HUD_TIER_COLORS[0]
    assert shown.combo_fill.width == int(shown.combo_bar.width * 0.5)
    assert shown.combo_bar.right == 1024 - HUD_MARGIN
    assert shown.combo_bar.bottom < 768 - HUD_MARGIN - HUD_PIP_SIZE


def test_the_combo_counter_carries_the_fury_tier() -> None:
    """One ``!`` and one step of colour per fury tier reached."""
    for tier, (level, _speed) in enumerate(Fury.TIERS, start=1):
        combat = SimpleNamespace(combo_count=5, combo_timer=1.0)
        layout = _hud().layout(_player(combat=combat, fury=_fury(level)))
        assert layout.combo_text == "x5" + "!" * tier
        assert layout.combo_color == HUD_TIER_COLORS[tier]


def test_the_reels_show_while_a_spin_turns_and_then_stop() -> None:
    slot = SlotMachine()
    assert _hud().layout(_player(slot=slot)).reels == ()

    slot.spin(random.Random(0))
    spinning = _hud().layout(_player(slot=slot)).reels
    assert len(spinning) == 3
    rects = [rect for rect, _ in spinning]
    assert rects[1].centerx == pytest.approx(1024 // 2, abs=2)

    slot.update(10.0)
    stopped = _hud().layout(_player(slot=slot)).reels
    assert [letter for _, letter in stopped] == [
        ("stasis", "blitz", "cleave", "bell", "cherry")[symbol][0].upper() for symbol in slot.reels
    ]


def test_a_granted_power_is_named_with_its_time_left() -> None:
    slot = SlotMachine()
    rng = random.Random(0)
    while True:
        slot.reset()
        slot.spin(rng)
        if slot.update(10.0) is not None:
            break

    text = _hud().layout(_player(slot=slot)).power_text

    assert text.startswith(slot.power.value.upper())


def test_the_prompt_shows_the_direction_asked_and_the_time_left() -> None:
    prompt = PromptController()
    assert _hud().layout(_player(prompt=prompt)).prompt is None

    prompt.open(PromptKind.DEATH_BLOW, "e1", random.Random(2))
    prompt.update(prompt.window / 2)
    shown = _hud().layout(_player(prompt=prompt)).prompt

    assert shown is not None
    assert shown.direction is prompt.expected
    assert shown.timer_fill.width == pytest.approx(shown.timer_bar.width / 2, abs=1)


def test_a_blade_lock_shows_the_presses_left_and_no_arrow() -> None:
    prompt = PromptController()
    prompt.open(PromptKind.CLASH, "e1", random.Random(2))
    prompt.press()

    shown = _hud().layout(_player(prompt=prompt)).prompt

    assert shown.direction is None
    assert shown.text == str(Clash.PRESSES - 1)


@pytest.mark.parametrize("direction", list(Direction))
def test_every_arrow_is_painted(direction: Direction) -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))
    prompt = PromptController()
    prompt.open(PromptKind.DEATH_BLOW, "e1", random.Random(0))
    prompt.steps = (direction,)

    hud.draw(_player(prompt=prompt))

    box = hud.layout(_player(prompt=prompt)).prompt.box
    assert _count(surface, box.inflate(-6, -6), (255, 245, 170)) > 50


@pytest.mark.parametrize("width", [320, 800, 1280, 1440, 1920, 2560])
def test_layout_never_leaves_the_display(width: int) -> None:
    """Responsive: every gauge stays inside the screen at any width (UI-6)."""
    layout = _hud(width, 720).layout(_player())
    for gauge in layout.gauges:
        assert gauge.label_rect.left >= 0
        assert gauge.bar.right <= width
    assert max(rect.right for rect, _ in layout.dash_pips) <= width


@pytest.mark.parametrize("width", [500, 1152, 1280, 1920, 2560, 3840])
def test_the_bar_is_the_same_width_on_every_target(width: int) -> None:
    assert bar_width_for(width) == HUD_BAR_WIDTH


def test_the_bar_shrinks_rather_than_clipping_on_a_narrow_target() -> None:
    narrow = 2 * HUD_MARGIN + 10
    assert bar_width_for(narrow) < HUD_BAR_WIDTH
    assert bar_width_for(narrow) <= narrow - 2 * HUD_MARGIN


def test_draw_paints_the_gauges_where_the_layout_says() -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))
    player = _player(health=50.0, fury=_fury(30.0))

    hud.draw(player)

    layout = hud.layout(player)
    assert surface.get_at(layout.gauge("HP").fill.center)[:3] == TEXT_WARN
    assert surface.get_at(layout.gauge("BAT").fill.center)[:3] == HUD_BATTERY_COLOR
    assert surface.get_at(layout.gauge("FURY").fill.center)[:3] == HUD_FURY_COLOR
    declared = [
        *(gauge.bar for gauge in layout.gauges),
        *(gauge.label_rect for gauge in layout.gauges),
        *(rect for rect, _ in layout.dash_pips),
    ]
    strays = [
        (x, y)
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[:3] != Colors.black
        and not any(rect.collidepoint(x, y) for rect in declared)
    ]
    assert strays == [], f"{len(strays)} painted pixels fall outside the layout"


def test_gauges_shrink_without_leaving_stale_pixels() -> None:
    surface = _surface()
    surface.fill(Colors.black)
    hud = HUD(PanelRenderer(surface))
    bar = hud.layout(_player()).gauge("HP").bar
    inner = bar.inflate(-2, -2)

    hud.draw(_player(health=100.0))
    assert _count(surface, inner, TEXT_OK) == inner.width * inner.height

    surface.fill(Colors.black)
    hud.draw(_player(health=10.0))
    assert _count(surface, inner, TEXT_OK) == 0
    assert _count(surface, inner, TEXT_CRIT) > 0
    assert _count(surface, inner, HUD_TRACK) > 0


def test_gameplay_scene_draws_the_hud_even_with_debug_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UI-7: the HUD is player-facing, so it is not gated by ``DEBUG``."""
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.core.rendering.camera import Camera
    from src.core.rendering.renderer import Renderer

    monkeypatch.delenv("DEBUG", raising=False)
    surface = _surface(1024, 768)
    renderer = Renderer(
        surface, Camera(Framing(float(1024), float(768))), overlay=make_overlay(surface)
    )
    level = SimpleNamespace(
        renderer=renderer,
        player=_player(health=20.0),
        draw=lambda *args, **kwargs: None,
    )
    scene = GameplayScene(game_shape(clock=None, ui=renderer.overlay), level_id=0, level=level)

    scene.draw(pygame.display.get_surface())

    # Nothing to declare any more: the next frame erases the whole target, so
    # the only thing that matters is that the gauges reached the pixels.
    hud_layout = renderer.overlay.hud.layout(level.player)
    assert hud_layout is not None
    assert surface.get_at(hud_layout.gauge("HP").fill.center)[:3] == TEXT_CRIT


def test_gameplay_scene_hud_survives_a_level_without_a_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duck-typed levels (overlays, tests) may not expose ``player``."""
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.core.rendering.camera import Camera
    from src.core.rendering.renderer import Renderer

    monkeypatch.delenv("DEBUG", raising=False)
    renderer = Renderer(
        _surface(), Camera(Framing(float(1024), float(768))), overlay=make_overlay(_surface())
    )
    level = SimpleNamespace(renderer=renderer, draw=lambda *args, **kwargs: None, player=None)
    scene = GameplayScene(game_shape(clock=None, ui=renderer.overlay), level_id=0, level=level)

    assert scene.draw(pygame.display.get_surface()) is None
