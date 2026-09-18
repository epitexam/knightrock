"""World-space debug overlay UX: culling, faction colors, toggles, hierarchy."""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.core.colors import Colors
from src.core.rendering.camera import Camera
from src.entities.components.reaction import ReactionKind, ReactionStatus
from src.ui.ui_manager import UIManager
from src.ui.world_ui import LABEL_NUDGE_PX, WorldUI


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


@pytest.fixture()
def world_ui() -> WorldUI:
    return WorldUI(UIManager(pygame.display.get_surface()).renderer)


@pytest.fixture()
def camera() -> Camera:
    return Camera(1024, 768)


def _named(name: str, **attrs) -> SimpleNamespace:
    """SimpleNamespace with a readable class name for overlay labels."""
    return type(name, (SimpleNamespace,), {})(**attrs)


def _entity(**overrides) -> SimpleNamespace:
    base = {
        "hitbox": pygame.FRect(100, 100, 40, 48),
        "hurtbox": pygame.FRect(98, 98, 44, 52),
        "velocity": Vector2(0, 0),
        "faction": "enemy",
        "health": 75.0,
        "max_health": 100.0,
        "stagger_timer": 0.0,
        "otg_timer": 0.0,
        "gravity_scale": 1.0,
        "on_surface": {"floor": True, "left": False, "right": False},
        "state_machine": SimpleNamespace(current_state_name="idle"),
        "combat": SimpleNamespace(
            state=SimpleNamespace(attack_name=None, sub_state=None, phase_index=0, frame_counter=0),
            targets_hit=set(),
        ),
    }
    base.update(overrides)
    return _named("Goblin", **base)


def test_idle_entity_gets_single_line_label(world_ui: WorldUI) -> None:
    assert world_ui._label_lines(_entity()) == ["Goblin idle 75/100"]


def test_attack_and_flags_add_detail_line(world_ui: WorldUI) -> None:
    entity = _entity(stagger_timer=0.2, otg_timer=0.4, gravity_scale=0.5)
    entity.on_surface["floor"] = False
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.frame_counter = 3
    lines = world_ui._label_lines(entity)
    assert lines is not None
    assert lines[0] == "Goblin idle 75/100"
    assert "claw_swipe" in lines[1]
    assert lines[2] == "STAG 0.20 OTG 0.40 JGx0.50 AIR"


def test_hitbox_color_follows_faction(world_ui: WorldUI) -> None:
    assert world_ui._hitbox_color(_entity(faction="enemy")) == Colors.red
    assert world_ui._hitbox_color(_entity(faction="player")) == Colors.debug_hitbox
    assert world_ui._hitbox_color(_entity(faction="neutral")) == Colors.light_grey


def test_projectile_label_shows_flight_data(world_ui: WorldUI) -> None:
    shot = _named(
        "Projectile",
        hitbox=pygame.FRect(0, 0, 12, 12),
        velocity=Vector2(700, -50),
        life=1.9,
        faction="player",
        config=SimpleNamespace(pierce=True),
        targets_hit={"e1"},
    )
    lines = world_ui._label_lines(shot)
    assert lines == ["Projectile player (700,-50) 1.9s pierce hits:1"]


def test_static_sprite_has_no_label(world_ui: WorldUI) -> None:
    hazard = _named("SpanHazard", rect=pygame.Rect(10, 10, 64, 16))
    assert world_ui._label_lines(hazard) is None


def test_bare_sprite_has_no_label(world_ui: WorldUI) -> None:
    assert world_ui._label_lines(SimpleNamespace()) is None


def test_offscreen_sprites_draw_nothing(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    far = _entity(
        hitbox=pygame.FRect(5000, 5000, 40, 48),
        hurtbox=pygame.FRect(4998, 4998, 44, 52),
        velocity=Vector2(600, 0),
    )
    world_ui.draw_debug_overlays([far], camera)
    assert surface.get_at((100, 100))[:3] == (0, 0, 0)
    assert surface.get_at((512, 384))[:3] == (0, 0, 0)


def test_overlay_paints_faction_hitbox(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([pygame.sprite.Sprite(), _entity()], camera)
    assert surface.get_at((100, 100))[:3] == Colors.red
    assert surface.get_at((98, 98))[:3] == Colors.debug_hurtbox


def test_overlay_marks_otg_guard(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([_entity(otg_timer=0.4)], camera)
    assert surface.get_at((100, 100))[:3] == Colors.debug_otg


def test_overlay_marks_juggle_gravity(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([_entity(gravity_scale=0.5)], camera)
    assert surface.get_at((100, 100))[:3] == Colors.debug_juggle


def test_stationary_sprites_draw_no_velocity_vector(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([_entity()], camera)
    # 0.15 s preview of a null velocity would land on the center: stays black.
    assert surface.get_at((120, 124))[:3] == (0, 0, 0)


def test_locomotion_vector_is_yellow(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([_entity(velocity=Vector2(600, 0))], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_knockback_vector_is_red(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.LAUNCH, magnitude=500.0, direction=1.0
    )
    entity.reaction_age = 0.2
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.red


def test_state_name_alone_no_longer_colors_the_vector_red(
    world_ui: WorldUI, camera: Camera
) -> None:
    """The overlay reads the typed cause, never a state-machine name."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.state_machine = SimpleNamespace(current_state_name="knockback")
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_blocked_push_status_colors_the_vector_red(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.BLOCKED, magnitude=90.0, direction=1.0
    )
    entity.reaction_age = 0.4
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.red


def test_expired_reaction_status_keeps_the_locomotion_color(
    world_ui: WorldUI, camera: Camera
) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(kind=ReactionKind.PUSH, magnitude=300.0, direction=1.0)
    entity.reaction_age = 0.0
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_stagger_status_keeps_the_locomotion_color(world_ui: WorldUI, camera: Camera) -> None:
    """Stagger carries no impulse: the vector keeps its locomotion color."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(kind=ReactionKind.STAGGER, magnitude=0.0, direction=0.0)
    entity.reaction_age = 0.2
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_fresh_reaction_status_shows_the_rx_flag(world_ui: WorldUI) -> None:
    entity = _entity()
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.LAUNCH, magnitude=500.0, direction=1.0
    )
    entity.reaction_age = 0.2
    lines = world_ui._label_lines(entity)
    assert lines is not None
    assert lines[-1] == "RX launch 0.20"


def test_stale_reaction_status_shows_the_expired_marker(world_ui: WorldUI) -> None:
    entity = _entity()
    entity.reaction_status = ReactionStatus(kind=ReactionKind.PUSH, magnitude=300.0, direction=1.0)
    entity.reaction_age = 0.0
    lines = world_ui._label_lines(entity)
    assert lines is not None
    assert lines[-1] == "RX~ push"


def test_entity_without_reaction_has_no_rx_flag(world_ui: WorldUI) -> None:
    lines = world_ui._label_lines(_entity())
    assert lines is not None
    assert all("RX" not in line for line in lines)


def _crowd(count: int) -> list[SimpleNamespace]:
    """Stacked enemies sharing one anchor spot (distinct healths for unique text)."""
    return [_entity(faction="enemy", health=100.0 + i, max_health=200.0) for i in range(count)]


def _place_crowd(
    monkeypatch: pytest.MonkeyPatch,
    world_ui: WorldUI,
    sprites: list[SimpleNamespace],
    camera: Camera,
) -> list[pygame.Rect]:
    """Draw the crowd and return the padded rects of every label actually placed."""
    placed: list[pygame.Rect] = []
    original = WorldUI._blit_label

    def spy(
        self: WorldUI,
        rendered: list[pygame.Surface],
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
    ) -> None:
        placed.append(pygame.Rect(background_rect))
        original(self, rendered, label_rect, background_rect)

    monkeypatch.setattr(WorldUI, "_blit_label", spy)
    world_ui.draw_debug_overlays(sprites, camera)
    return placed


def test_overlapping_entities_get_non_overlapping_labels(
    monkeypatch: pytest.MonkeyPatch, world_ui: WorldUI, camera: Camera
) -> None:
    """Two entities at the same spot: the second label dodges instead of stacking."""
    placed = _place_crowd(monkeypatch, world_ui, _crowd(2), camera)

    assert len(placed) == 2
    first, second = sorted(placed, key=lambda rect: rect.top)
    assert not first.colliderect(second)
    assert second.top - first.bottom >= -1


def test_label_cascade_walks_upward_until_a_slot_is_free(
    monkeypatch: pytest.MonkeyPatch, world_ui: WorldUI, camera: Camera
) -> None:
    """Stacked entities: labels line up as a column, no two panels overlap."""
    crowd = _crowd(4)
    placed = _place_crowd(monkeypatch, world_ui, [crowd[2], crowd[1], crowd[3], crowd[0]], camera)

    assert len(placed) == 4
    ordered = sorted(placed, key=lambda rect: rect.top)
    assert all(not ordered[i].colliderect(ordered[i + 1]) for i in range(3))
    span = ordered[-1].top - ordered[0].top
    assert span >= 3 * LABEL_NUDGE_PX


def test_player_label_wins_the_default_slot(
    monkeypatch: pytest.MonkeyPatch, world_ui: WorldUI, camera: Camera
) -> None:
    """The player is placed first: its label hugs its entity, the enemy dodges up."""
    player = _entity(faction="player", health=100.0, max_health=100.0)
    enemy = _entity(faction="enemy", health=90.0, max_health=100.0)
    placed = _place_crowd(monkeypatch, world_ui, [enemy, player], camera)

    assert len(placed) == 2
    ordered = sorted(placed, key=lambda rect: rect.top)
    anchor_top = float(camera.apply(pygame.FRect(100, 100, 40, 48)).top)
    # The lowest panel hugs the entity's top edge: that is the player's label.
    assert abs(ordered[-1].bottom - (anchor_top - 5)) <= 3
    # The enemy label dodged a full step above, leaving a visible gap.
    assert ordered[-1].top - ordered[0].bottom >= 4


def test_labels_beyond_all_slots_are_dropped(
    monkeypatch: pytest.MonkeyPatch, world_ui: WorldUI, camera: Camera
) -> None:
    """More labels than dodge room: extras vanish instead of overdrawing."""
    placed = _place_crowd(monkeypatch, world_ui, _crowd(12), camera)

    # Deterministic slot budget at the default anchor: 3 upward slots before
    # the screen edge, then 7 below the entity — exactly 10 panels, all apart.
    assert len(placed) == 10
    assert all(not placed[i].colliderect(placed[j]) for i in range(10) for j in range(i + 1, 10))


def test_single_label_panel_is_visible_at_the_expected_color(
    world_ui: WorldUI, camera: Camera
) -> None:
    """Visual pin: the panel fill (18,20,24 @ alpha 210) reads (14,16,19) on black."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays(_crowd(1), camera)

    anchor = camera.apply(pygame.FRect(100, 100, 40, 48))
    probe_y = anchor.top - 18  # inside the single-line panel above the entity
    assert surface.get_at((95, probe_y))[:3] == (14, 16, 19)


def test_toggle_flips_layer_and_rejects_unknown(world_ui: WorldUI) -> None:
    assert world_ui.toggle("labels") is False
    assert world_ui.toggle("labels") is True
    with pytest.raises(KeyError):
        world_ui.toggle("nope")


def test_disabled_labels_layer_draws_boxes_only(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.toggle("labels")
    world_ui.draw_debug_overlays([_entity()], camera)
    assert surface.get_at((100, 100))[:3] == Colors.red


def test_help_panel_lists_debug_keys() -> None:
    from src.ui.ui_manager import UIManager as _UIManager

    manager = _UIManager(pygame.display.get_surface())
    assert manager.draw_help_panel(10, 10) > 0


def test_gameplay_scene_function_keys_toggle_overlay_layers() -> None:
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.ui.panel_renderer import PanelRenderer

    world_ui = WorldUI(PanelRenderer(pygame.display.get_surface()))
    level = SimpleNamespace(renderer=SimpleNamespace(ui_manager=SimpleNamespace(world_ui=world_ui)))
    scene = GameplayScene(SimpleNamespace(), level_id=0, level=level)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
    assert world_ui.layers["labels"] is False
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
    assert world_ui.layers["labels"] is True
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
    assert world_ui.layers["boxes"] is False
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
    assert world_ui.layers["panels"] is False


def test_debug_panels_can_be_hidden() -> None:
    from src.core.rendering.camera import Camera as _Camera
    from src.core.rendering.renderer import Renderer

    camera = _Camera(1024, 768)
    renderer = Renderer(pygame.display.get_surface(), camera)
    surface = pygame.display.get_surface()
    assert surface is not None

    renderer.draw_debug_panels(None, 60.0, 1, 1, 1, 1, 0.0, 0.0)
    assert surface.get_at((20, 60))[:3] != (0, 0, 0)

    surface.fill((0, 0, 0))
    renderer.ui_manager.world_ui.toggle("panels")
    renderer.draw_debug_panels(None, 60.0, 1, 1, 1, 1, 0.0, 0.0)
    assert surface.get_at((20, 60))[:3] == (0, 0, 0)
