"""Responsive debug display: panel flow, pinned wrap, labels vs bars, edges."""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelLayout
from src.ui.styles import TEXT_MUTED
from src.ui.ui_manager import UIManager


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


@pytest.fixture()
def ui() -> UIManager:
    return UIManager(pygame.display.get_surface())


@pytest.fixture()
def camera() -> Camera:
    return Camera(1024, 768)


def _entity(x: float = 100.0, health: float = 75.0) -> SimpleNamespace:
    """Minimal labelled entity for the world overlay (like test_debug_overlay)."""
    return type("Goblin", (SimpleNamespace,), {})(
        hitbox=pygame.FRect(x, 100, 40, 48),
        velocity=Vector2(0, 0),
        faction="enemy",
        health=health,
        max_health=100.0,
        stagger_timer=0.0,
        otg_timer=0.0,
        gravity_scale=1.0,
        state_machine=SimpleNamespace(current_state_name="idle"),
    )


def _capture_labels(ui: UIManager, monkeypatch: pytest.MonkeyPatch) -> list[pygame.Rect]:
    """Spy on _blit_label and collect the padded rects actually placed."""
    placed: list[pygame.Rect] = []
    original = type(ui.world_ui)._blit_label

    def spy(
        self: object,
        header: list[pygame.Surface],
        rows: list[list[pygame.Surface]],
        row_height: int,
        accent: object,
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
        screen_width: int,
    ) -> None:
        placed.append(pygame.Rect(background_rect))
        original(self, header, rows, row_height, accent, label_rect, background_rect, screen_width)

    monkeypatch.setattr(type(ui.world_ui), "_blit_label", spy)
    return placed


def test_flowing_panels_never_cover_a_pinned_panel() -> None:
    """Pinned first, then the flow: no flowing panel covers the pinned one."""
    layout = PanelLayout(1024, 768)
    pinned_pos = layout.place_top_right(200, 300)

    placed = [layout.place(200, 250) for _ in range(4)]
    assert placed[0] == (10, 10)
    pinned = pygame.Rect(*pinned_pos, 200, 300)
    assert all(not pygame.Rect(x, y, 200, 250).colliderect(pinned) for x, y in placed), (
        f"flow panels {placed} cover the pinned panel at {pinned_pos}"
    )


def test_wrapped_column_stays_left_when_display_is_narrow() -> None:
    """No room right of the pinned panel: the new column slides left of it."""
    layout = PanelLayout(500, 768)
    layout.place_top_right(300, 100)

    x, y = layout.place(150, 400)  # overflows the bottom -> must wrap

    assert y == 10
    pinned = pygame.Rect(500 - 10 - 300, 10, 300, 100)
    assert not pygame.Rect(x, y, 150, 400).colliderect(pinned)


def test_labels_keep_clear_of_the_health_bars(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A placed label card never overlaps the bar drawn after it."""
    entity = _entity()
    placed = _capture_labels(ui, monkeypatch)

    surface = ui.world_ui.display_surface
    surface.fill((0, 0, 0))
    ui.world_ui.draw_debug_overlays([entity], camera)
    ui.draw_health_bars([entity], camera)

    assert placed, "the label card was dropped instead of dodging the bar"
    bar = ui.world_ui._health_bar_rect(entity, camera.apply(entity.hitbox))
    assert bar is not None
    assert not any(bar.colliderect(card) for card in placed)


def test_labels_dodge_bars_from_the_previous_frame(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bars seen one frame earlier remain obstacles for the next frame."""
    entity = _entity()
    _capture_labels(ui, monkeypatch)

    ui.world_ui.draw_debug_overlays([entity], camera)  # registers the bar
    bar = ui.world_ui._health_bar_rect(entity, camera.apply(entity.hitbox))
    assert bar is not None
    above_lift, _ = ui.world_ui._label_clearances(entity, camera.apply(entity.hitbox))
    placed = ui.world_ui._place_label(
        [[("Goblin idle", (255, 255, 255))], [("HP 75/100", (255, 255, 255))]],
        (255, 255, 255),
        camera.apply(entity.hitbox),
        [*ui.world_ui._previous_bar_obstacles],
        camera.width,
        camera.height,
        above_lift=above_lift,
    )
    assert placed is not None
    assert not bar.colliderect(placed)


def test_edge_labels_shift_inside_the_screen(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card near the display edge is shifted back inside, never clipped."""
    entity = _entity(x=600.0)  # near the right edge of the 1024px view
    entity.hitbox.right = 1010.0
    placed = _capture_labels(ui, monkeypatch)

    surface = ui.world_ui.display_surface
    surface.fill((0, 0, 0))
    ui.world_ui.draw_debug_overlays([entity], camera)

    assert placed, "the label card was dropped at the screen edge"
    screen = surface.get_rect()
    assert screen.contains(placed[0]), f"card {placed[0]} sticks out of the display"


def test_combat_panel_only_collects_when_debug_is_enabled(ui: UIManager) -> None:
    """DEBUG unset: draw_metrics_panel collects nothing; with DEBUG it does."""
    os.environ.pop("DEBUG", None)
    ui.world_ui.update_metrics(SimpleNamespace(pairs_tested=1, overlaps=1, contacts=1))
    ui.world_ui.draw_metrics_panel()
    assert ui.world_ui.combat_panel() is None

    os.environ["DEBUG"] = "1"
    for _ in range(10):  # metrics refresh every 10th tick, as in game
        ui.world_ui.update_metrics(SimpleNamespace(pairs_tested=2, overlaps=1, contacts=1))
    ui.world_ui.draw_metrics_panel()
    content = ui.world_ui.combat_panel()
    assert content is not None
    title, lines = content
    assert title == "COMBAT"
    assert lines[0][0] == "pairs 2"


def test_draw_combat_panel_flows_through_the_layout(ui: UIManager) -> None:
    """The COMBAT panel is drawn inside the column flow, not at a fixed spot."""
    os.environ["DEBUG"] = "1"
    surface = pygame.Surface((640, 480))
    surface.fill((0, 0, 0))
    ui.renderer.display_surface = surface
    ui.world_ui.combat_panel_lines = [("pairs 2", TEXT_MUTED)]

    layout = PanelLayout(640, 480)
    height = ui.draw_combat_panel(layout)
    assert height > 0
    # The first counter line lands inside the flow's first panel (top-left),
    # below the title block — not at the legacy fixed offset (10, 150).
    assert any(
        surface.get_at((x, y))[:3] == TEXT_MUTED for x in range(14, 110) for y in range(56, 110)
    )


def _full_player() -> SimpleNamespace:
    """Fake player feeding every debug panel (same fields as test_panel_layout)."""
    return SimpleNamespace(
        state_machine=SimpleNamespace(
            current_state_name="idle", previous_state_name=None, history=[]
        ),
        velocity=Vector2(0, 0),
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


def test_full_debug_panel_stack_never_overlaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: every debug panel lands on its own rect, none stacks."""
    from src.core.rendering.camera import Camera as _Camera
    from src.core.rendering.renderer import Renderer

    surface = pygame.Surface((1440, 900))
    renderer = Renderer(surface, _Camera(1440, 900))
    renderer.ui_manager.world_ui.combat_panel_lines = [("pairs 2", TEXT_MUTED)]

    placed: list[pygame.Rect] = []
    original_place = PanelLayout.place
    original_pin = PanelLayout.place_top_right

    def spy_place(self: PanelLayout, w: int, h: int) -> tuple[int, int]:
        pos = original_place(self, w, h)
        placed.append(pygame.Rect(*pos, w, h))
        return pos

    def spy_pin(self: PanelLayout, w: int, h: int) -> tuple[int, int]:
        pos = original_pin(self, w, h)
        placed.append(pygame.Rect(*pos, w, h))
        return pos

    monkeypatch.setattr(PanelLayout, "place", spy_place)
    monkeypatch.setattr(PanelLayout, "place_top_right", spy_pin)

    renderer.draw_debug_panels(
        player=_full_player(),
        fps=60.0,
        sprite_count=1,
        combat_count=1,
        entity_count=1,
        collision_count=1,
        hit_stop=0.0,
        spawn_cooldown=0.0,
        game=None,
        frame_time=16.0,
        cache_size=0,
    )

    # PERFORMANCE (pinned), COMBAT, PLAYER STATE, STATS, KEYS, LEGEND.
    assert len(placed) == 6
    for index, rect in enumerate(placed):
        for other in placed[index + 1 :]:
            assert not rect.colliderect(other), f"panel {rect} stacks on {other}"
    screen = surface.get_rect()
    assert all(screen.contains(rect) for rect in placed), "a panel sticks out of the display"


def test_compact_display_uses_focus_selector_without_overlap() -> None:
    from src.core.rendering.camera import Camera as _Camera
    from src.core.rendering.renderer import Renderer

    surface = pygame.Surface((640, 480))
    renderer = Renderer(surface, _Camera(640, 480))
    level = SimpleNamespace(
        deaths=0,
        groups=SimpleNamespace(
            entity_sprites=[],
            hazard_sprites=[],
            projectile_sprites=[],
        ),
    )
    game = SimpleNamespace(
        scene_manager=SimpleNamespace(
            current=SimpleNamespace(level_id=0, level=level),
        )
    )

    renderer.draw_debug_panels(
        player=_full_player(),
        fps=60.0,
        sprite_count=1,
        combat_count=0,
        entity_count=0,
        collision_count=0,
        hit_stop=0.0,
        spawn_cooldown=0.0,
        game=game,
        frame_time=16.0,
    )
    renderer.ui_manager.renderer.interaction.begin_frame()
    panels = renderer.ui_manager.renderer.interaction.panels
    screen = surface.get_rect()

    assert set(panels) == {"performance", "state"}
    assert all(screen.contains(rect) for rect in panels.values())
    assert not panels["performance"].colliderect(panels["state"])
    assert renderer.ui_manager.compact_panel_focus() == "state"
    assert renderer.ui_manager.cycle_compact_panel() == "stats"
