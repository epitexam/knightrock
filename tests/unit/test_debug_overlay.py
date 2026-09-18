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
from src.ui.world_ui import WorldUI


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
