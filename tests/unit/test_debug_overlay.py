"""World-space debug overlay UX: culling, faction colors, toggles, hierarchy."""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.entities.components.reaction import ReactionKind, ReactionStatus
from src.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN
from src.ui.ui_manager import UIManager
from src.ui.world_ui import (
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_LABEL_GAP,
    LABEL_ANCHOR_GAP,
    LABEL_DIVIDER_BOTTOM,
    LABEL_DIVIDER_TOP,
    LABEL_LINE_GAP,
    LABEL_NUDGE_PX,
    LABEL_PAD_X,
    LABEL_PAD_Y,
    VELOCITY_MIN_LENGTH,
    VELOCITY_OUTLINE,
    WorldUI,
    arrow_outline,
)


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


def test_idle_entity_gets_header_and_hp_rows(world_ui: WorldUI) -> None:
    segments = world_ui._label_segments(_entity())
    assert segments is not None
    assert segments[0] == [("Goblin ", Colors.light_red), ("idle", Colors.off_white)]
    assert segments[1][0] == ("HP ", TEXT_MUTED)
    assert segments[1][1][0] == "75/100"
    assert world_ui._label_lines(_entity()) == ["Goblin idle", "HP 75/100"]


def test_attack_and_flags_get_their_own_rows(world_ui: WorldUI) -> None:
    entity = _entity(stagger_timer=0.2, otg_timer=0.4, gravity_scale=0.5)
    entity.on_surface["floor"] = False
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.frame_counter = 3
    segments = world_ui._label_segments(entity)
    lines = world_ui._label_lines(entity)
    assert segments is not None and lines is not None
    assert segments[0] == [("Goblin ", Colors.light_red), ("idle", Colors.off_white)]
    assert segments[1][0] == ("HP ", TEXT_MUTED)
    assert segments[2][0] == ("ATK ", TEXT_MUTED)
    assert segments[2][1] == ("claw_swipe ", Colors.gold)
    assert segments[3][0] == ("STAG 0.20s", Colors.orange)
    assert lines[0] == "Goblin idle"
    assert lines[1] == "HP 75/100"
    assert "claw_swipe" in lines[2]
    assert "p0 active:3" in lines[2]
    assert lines[3] == "STAG 0.20s | OTG 0.40s | GRAV x0.5 | AIR"


def test_segments_color_each_token_with_the_faction_accent(world_ui: WorldUI) -> None:
    """Header name takes the faction color; detail values keep their own."""
    segments = world_ui._label_segments(_entity())
    assert segments is not None
    assert segments[0] == [("Goblin ", Colors.light_red), ("idle", Colors.off_white)]
    assert segments[1] == [("HP ", TEXT_MUTED), ("75/100", TEXT_OK)]


def test_hp_row_tints_by_remaining_ratio(world_ui: WorldUI) -> None:
    warn = world_ui._label_segments(_entity(health=40.0, max_health=100.0))
    crit = world_ui._label_segments(_entity(health=20.0, max_health=100.0))
    assert warn is not None and crit is not None
    assert warn[1] == [("HP ", TEXT_MUTED), ("40/100", TEXT_WARN)]
    assert crit[1] == [("HP ", TEXT_MUTED), ("20/100", TEXT_CRIT)]


def test_attack_row_splits_name_from_phase_stats(world_ui: WorldUI) -> None:
    entity = _entity()
    entity.combat.state.attack_name = "claw_swipe"
    segments = world_ui._label_segments(entity)
    assert segments is not None
    assert segments[1][0] == ("HP ", TEXT_MUTED)
    assert segments[2] == [
        ("ATK ", TEXT_MUTED),
        ("claw_swipe ", Colors.gold),
        ("p0 None:0 hits:0", Colors.light_grey),
    ]


def test_status_flags_are_pipe_separated(world_ui: WorldUI) -> None:
    entity = _entity(stagger_timer=0.2, otg_timer=0.4)
    lines = world_ui._label_lines(entity)
    assert lines is not None
    assert lines[-1] == "STAG 0.20s | OTG 0.40s"


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


def test_arrow_outline_is_a_tapered_shaft_with_a_flared_head() -> None:
    """Seven points, mirrored about the axis: tail, neck, barb, tip."""
    points = arrow_outline(Vector2(0, 0), Vector2(1, 0), 40.0, 10.0, 6.0)
    assert points == [(0, 1), (30, 2), (30, 6), (40, 0), (30, -6), (30, -2), (0, -1)]


def test_arrow_outline_follows_the_direction() -> None:
    """A vertical push points up: tip above the pivot, barbs behind the neck."""
    points = arrow_outline(Vector2(0, 0), Vector2(0, -1), 40.0, 10.0, 6.0)
    assert points == [(1, 0), (2, -30), (6, -30), (0, -40), (-6, -30), (-2, -30), (-1, 0)]


def test_velocity_vector_is_a_filled_arrowhead_not_a_hairline(
    world_ui: WorldUI, camera: Camera
) -> None:
    """A 2 px line + tip dot covered ~190 px; the filled head adds ~200 more."""
    surface = world_ui.display_surface
    surface.fill(Colors.sky_blue)
    world_ui.draw_debug_overlays([_entity(velocity=Vector2(600, 0))], camera)
    covered = sum(
        1
        for x in range(120, 215)
        for y in range(110, 140)
        if surface.get_at((x, y))[:3] == Colors.debug_velocity
    )
    assert covered >= 300
    # Off-axis points next to the tip are only reachable by a flared head.
    assert surface.get_at((196, 117))[:3] == Colors.debug_velocity
    assert surface.get_at((196, 131))[:3] == Colors.debug_velocity


def test_velocity_arrow_keeps_a_dark_rim_over_a_bright_background(
    world_ui: WorldUI, camera: Camera
) -> None:
    """The rim separates the fill from the sky: the silhouette stays readable."""
    surface = world_ui.display_surface
    surface.fill(Colors.sky_blue)
    world_ui.draw_debug_overlays([_entity(velocity=Vector2(600, 0))], camera)
    rim = sum(
        1
        for x in range(120, 215)
        for y in range(110, 140)
        if surface.get_at((x, y))[:3] == VELOCITY_OUTLINE
    )
    assert rim > 0


def test_slow_vector_is_stretched_to_the_minimum_arrow_length(
    world_ui: WorldUI, camera: Camera
) -> None:
    """65 px/s previews 9.75 px: the arrow floors to VELOCITY_MIN_LENGTH."""
    surface = world_ui.display_surface
    surface.fill(Colors.sky_blue)
    world_ui.draw_debug_overlays([_entity(velocity=Vector2(65, 0))], camera)
    tip_x = 120 + int(VELOCITY_MIN_LENGTH)
    assert surface.get_at((tip_x, 124))[:3] == Colors.debug_velocity
    assert surface.get_at((tip_x + 4, 124))[:3] == Colors.sky_blue


def test_velocity_arrow_pivot_marks_the_entity_center(world_ui: WorldUI, camera: Camera) -> None:
    """The vector visibly departs the entity: pivot dot, fill only ahead."""
    surface = world_ui.display_surface
    surface.fill(Colors.sky_blue)
    world_ui.draw_debug_overlays([_entity(velocity=Vector2(-600, 0))], camera)
    assert surface.get_at((120, 124))[:3] == Colors.debug_velocity  # pivot dot
    assert surface.get_at((60, 124))[:3] == Colors.debug_velocity  # shaft + head
    assert surface.get_at((180, 124))[:3] == Colors.sky_blue  # nothing behind


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


def test_guarded_push_status_colors_the_vector_red(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.GUARDED, magnitude=90.0, direction=1.0
    )
    entity.reaction_age = 0.4
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.red


def test_parried_status_colors_the_vector_gold(world_ui: WorldUI, camera: Camera) -> None:
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(kind=ReactionKind.PARRIED, magnitude=0.0, direction=1.0)
    entity.reaction_age = 0.4
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.gold


def test_expired_reaction_status_keeps_the_locomotion_color(
    world_ui: WorldUI, camera: Camera
) -> None:
    """Stale cause *and* the state machine left knockback: locomotion again."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(kind=ReactionKind.PUSH, magnitude=300.0, direction=1.0)
    entity.reaction_age = 0.0
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_knockback_state_keeps_the_vector_red_after_the_freshness_window(
    world_ui: WorldUI, camera: Camera
) -> None:
    """A launch outlives ReactionMark.DURATION: the state still carries it.

    Measured in flight, a (400, -600) launch stays in ``knockback`` for
    ~1.15 s while ``reaction_age`` runs out after 0.4 s — the vector is still
    the knockback, so it stays red (this was the "sometimes yellow" report).
    """
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.LAUNCH, magnitude=500.0, direction=1.0
    )
    entity.reaction_age = 0.0  # freshness expired, still being launched
    entity.state_machine = SimpleNamespace(current_state_name="knockback")
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.red


def test_resolved_knockback_falls_back_to_the_locomotion_color(
    world_ui: WorldUI, camera: Camera
) -> None:
    """Once the state machine leaves knockback, a stale cause is locomotion."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.LAUNCH, magnitude=500.0, direction=1.0
    )
    entity.reaction_age = 0.0
    entity.state_machine = SimpleNamespace(current_state_name="chase")
    world_ui.draw_debug_overlays([entity], camera)
    assert surface.get_at((200, 124))[:3] == Colors.debug_velocity


def test_stale_stagger_never_turns_the_vector_red(world_ui: WorldUI, camera: Camera) -> None:
    """The kind gate still rules: a stagger carries no impulse, state or not."""
    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    entity = _entity(velocity=Vector2(600, 0))
    entity.reaction_status = ReactionStatus(kind=ReactionKind.STAGGER, magnitude=0.0, direction=0.0)
    entity.reaction_age = 0.0
    entity.state_machine = SimpleNamespace(current_state_name="knockback")
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


def test_fresh_reaction_status_shows_the_hit_flag(world_ui: WorldUI) -> None:
    entity = _entity()
    entity.reaction_status = ReactionStatus(
        kind=ReactionKind.LAUNCH, magnitude=500.0, direction=1.0
    )
    entity.reaction_age = 0.2
    segments = world_ui._label_segments(entity)
    lines = world_ui._label_lines(entity)
    assert segments is not None and lines is not None
    assert segments[-1] == [("HIT launch 0.20s", Colors.red)]
    assert lines[-1] == "HIT launch 0.20s"


def test_stale_reaction_status_shows_the_expired_marker(world_ui: WorldUI) -> None:
    entity = _entity()
    entity.reaction_status = ReactionStatus(kind=ReactionKind.PUSH, magnitude=300.0, direction=1.0)
    entity.reaction_age = 0.0
    segments = world_ui._label_segments(entity)
    lines = world_ui._label_lines(entity)
    assert segments is not None and lines is not None
    assert segments[-1] == [("HIT push (old)", Colors.dark_red)]
    assert lines[-1] == "HIT push (old)"


def test_entity_without_reaction_has_no_hit_flag(world_ui: WorldUI) -> None:
    lines = world_ui._label_lines(_entity())
    assert lines is not None
    assert all("HIT" not in line for line in lines)


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
        header: list[pygame.Surface],
        rows: list[list[pygame.Surface]],
        row_height: int,
        accent: Color,
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
        screen_width: int,
    ) -> None:
        placed.append(pygame.Rect(background_rect))
        original(self, header, rows, row_height, accent, label_rect, background_rect, screen_width)

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
    """The player is placed first: its card sits closest to the entity."""
    player = _entity(faction="player", health=100.0, max_health=100.0)
    enemy = _entity(faction="enemy", health=90.0, max_health=100.0)
    placed = _place_crowd(monkeypatch, world_ui, [enemy, player], camera)

    assert len(placed) == 2
    ordered = sorted(placed, key=lambda rect: rect.top)
    anchor = camera.apply(pygame.FRect(100, 100, 40, 48))
    # Priority order held: the player (sorted first) claimed the upper slot and
    # the enemy dodged below it — no overlap, each card clear of the other.
    assert not ordered[0].colliderect(ordered[1])
    assert ordered[1].top - ordered[0].bottom >= 4
    # Sanity: both cards sit near the entity, above and below it.
    assert ordered[0].bottom <= anchor.top
    assert ordered[1].top >= anchor.bottom


def test_labels_beyond_all_slots_are_dropped(
    monkeypatch: pytest.MonkeyPatch, world_ui: WorldUI, camera: Camera
) -> None:
    """More labels than dodge room: extras vanish instead of overdrawing."""
    placed = _place_crowd(monkeypatch, world_ui, _crowd(12), camera)

    # Compact world fonts: cards are ~53 px tall with padding at the
    # default anchor, so more dodge slots fit than with the old panel-sized
    # fonts — exactly 5 cards, all apart, the rest dropped.
    assert len(placed) == 5
    assert all(not placed[i].colliderect(placed[j]) for i in range(5) for j in range(i + 1, 5))


def test_label_card_renders_header_divider_and_accent_edge(
    world_ui: WorldUI, camera: Camera
) -> None:
    """Visual pin: the card body fill reads (14,16,19) on a black surface."""
    entity = _entity()
    segments = world_ui._label_segments(entity)
    assert segments is not None
    header_width = sum(world_ui.renderer.world_title_font.size(text)[0] for text, _ in segments[0])
    row_width = sum(world_ui.renderer.world_label_font.size(text)[0] for text, _ in segments[1])
    card_w = max(header_width, row_width)
    row_h = max(
        world_ui.renderer.world_title_font.get_height(),
        world_ui.renderer.world_label_font.get_height(),
    )
    card_h = row_h * 2 + LABEL_LINE_GAP + (LABEL_DIVIDER_TOP + 1 + LABEL_DIVIDER_BOTTOM)
    anchor = camera.apply(pygame.FRect(100, 100, 40, 48))
    # Stack order: entity -> health bar -> card. The card's content box sits
    # LABEL_ANCHOR_GAP plus the bar + gap above the anchor.
    above_lift, _ = world_ui._label_clearances(entity, anchor)
    assert above_lift == HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + LABEL_PAD_Y
    content_left = int(anchor.centerx - card_w // 2)
    content_top = int(anchor.top - LABEL_ANCHOR_GAP - above_lift - card_h)
    body_y = content_top + row_h + LABEL_DIVIDER_TOP + 1 + LABEL_DIVIDER_BOTTOM

    surface = world_ui.display_surface
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([entity], camera)
    world_ui.draw_health_bars([entity], camera)

    # The health bar sits between the entity and the card: background track
    # visible at its left edge, never covered by the card above it.
    bar = world_ui._health_bar_rect(entity, anchor)
    assert bar is not None
    card_bg_bottom = content_top + card_h + LABEL_PAD_Y
    assert card_bg_bottom + HEALTH_BAR_LABEL_GAP <= bar.top
    assert bar.bottom + LABEL_ANCHOR_GAP == int(anchor.top)
    assert surface.get_at((bar.x + 1, bar.y + 2))[:3] != (0, 0, 0)

    # Inside the HP row (below the divider rule): the dark fill shows through
    # in the padding, away from the glyphs.
    assert surface.get_at((content_left + LABEL_PAD_X + 4, body_y + 2))[:3] == (14, 16, 19)
    # Top accent edge (faction red for enemies): 2 px just inside the top
    # border, spanning the card width.
    bg_left = content_left - LABEL_PAD_X
    bg_top = content_top - LABEL_PAD_Y
    assert surface.get_at((bg_left + 3, bg_top + 2))[:3] == (Colors.light_red)
    # No full-height side stripe anymore: the left padding shows card fill.
    assert surface.get_at((bg_left + 3, body_y + 2))[:3] == (14, 16, 19)


def test_health_bar_never_hides_inside_the_label_card(world_ui: WorldUI, camera: Camera) -> None:
    """The gap between card and bar stays empty: no overlap, in any row count."""
    for kwargs in ({}, {"stagger_timer": 0.2, "otg_timer": 0.4, "gravity_scale": 0.5}):
        entity = _entity(**kwargs)
        anchor = camera.apply(pygame.FRect(100, 100, 40, 48))
        bar = world_ui._health_bar_rect(entity, anchor)
        assert bar is not None
        assert bar.bottom + LABEL_ANCHOR_GAP == int(anchor.top)

        surface = world_ui.display_surface
        surface.fill((0, 0, 0))
        world_ui.draw_debug_overlays([entity], camera)
        world_ui.draw_health_bars([entity], camera)
        # Mid-gap pixel: below every placed card, above the bar -> untouched.
        gap_y = bar.top - HEALTH_BAR_LABEL_GAP // 2 - 1
        assert surface.get_at((int(anchor.centerx), gap_y))[:3] == (0, 0, 0)


def test_health_bar_flips_below_entity_at_top_of_screen(world_ui: WorldUI, camera: Camera) -> None:
    """No room above: the bar goes under the entity, the card keeps the top."""
    entity = _entity(hitbox=pygame.FRect(100, 2, 40, 48))
    anchor = camera.apply(pygame.FRect(100, 2, 40, 48))
    bar = world_ui._health_bar_rect(entity, anchor)
    assert bar is not None
    assert bar.top >= anchor.bottom  # flipped below
    above_lift, below_drop = world_ui._label_clearances(entity, anchor)
    assert (above_lift, below_drop) == (0, HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + LABEL_PAD_Y)


def test_health_bar_width_is_responsive_and_clamped(world_ui: WorldUI, camera: Camera) -> None:
    """Bar width follows the on-screen sprite width within [30, 60] px."""
    wide = world_ui._health_bar_rect(
        _entity(hitbox=pygame.FRect(100, 100, 200, 48)),
        camera.apply(pygame.FRect(100, 100, 200, 48)),
    )
    narrow = world_ui._health_bar_rect(
        _entity(hitbox=pygame.FRect(100, 100, 10, 48)),
        camera.apply(pygame.FRect(100, 100, 10, 48)),
    )
    assert wide is not None and narrow is not None
    assert wide.width == 60
    assert narrow.width == 30
    # Clamped to the viewport: never spills off the left edge.
    edge = world_ui._health_bar_rect(
        _entity(hitbox=pygame.FRect(-30, 100, 40, 48)),
        camera.apply(pygame.FRect(-30, 100, 40, 48)),
    )
    assert edge is not None
    assert edge.left >= 0


def test_dead_entity_draws_no_health_bar(world_ui: WorldUI, camera: Camera) -> None:
    entity = _entity(is_dead=True)
    anchor = camera.apply(pygame.FRect(100, 100, 40, 48))
    assert world_ui._health_bar_rect(entity, anchor) is None
    assert world_ui._label_clearances(entity, anchor) == (0, 0)


def test_world_cards_use_compact_fonts(world_ui: WorldUI) -> None:
    """Regression pin: entity cards stay smaller than the side debug panels."""
    assert (
        world_ui.renderer.world_title_font.get_height() < world_ui.renderer.title_font.get_height()
    )
    assert (
        world_ui.renderer.world_label_font.get_height() <= world_ui.renderer.label_font.get_height()
    )


def test_enemy_header_shows_the_registry_type(world_ui: WorldUI) -> None:
    """Foes share one class: the header shows ``enemy_type``, not ``Enemy``."""
    entity = _entity(enemy_type="goblin")
    segments = world_ui._label_segments(entity)
    lines = world_ui._label_lines(entity)
    assert segments is not None and lines is not None
    assert segments[0] == [("goblin ", Colors.light_red), ("idle", Colors.off_white)]
    assert lines[0] == "goblin idle"


def test_enemy_without_type_falls_back_to_class_name(world_ui: WorldUI) -> None:
    assert world_ui._display_name(_entity()) == "Goblin"


def test_player_header_ignores_enemy_type(world_ui: WorldUI) -> None:
    """Only foes read ``enemy_type``: the player keeps its class name."""
    entity = _entity(faction="player", enemy_type="goblin")
    segments = world_ui._label_segments(entity)
    assert segments is not None
    assert segments[0] == [("Goblin ", Colors.light_green), ("idle", Colors.off_white)]


def test_factory_enemy_label_shows_its_type(world_ui: WorldUI) -> None:
    """End to end: a factory-built slime labels itself ``slime``."""
    from pygame.sprite import Group

    from src.entities.enemies.factory import create_enemy

    enemy = create_enemy(
        name="slime",
        pos=(100, 100),
        groups=Group(),
        collision_sprites=Group(),
        player_reference=None,
    )
    assert enemy.enemy_type == "slime"
    segments = world_ui._label_segments(enemy)
    assert segments is not None
    assert segments[0][0] == ("slime ", Colors.light_red)


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


def test_freeze_key_toggles_only_in_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """F6 flips the freeze switch in debug mode, ignored otherwise."""
    from src.application.scenes.gameplay_scene import GameplayScene

    scene = GameplayScene(SimpleNamespace(), level_id=0, level=SimpleNamespace())

    monkeypatch.setenv("DEBUG", "1")
    assert scene.frozen is False
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    assert scene.frozen is True
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    assert scene.frozen is False

    monkeypatch.setenv("DEBUG", "0")
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    assert scene.frozen is False


def test_frozen_scene_holds_the_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frozen: input still polls, level.update never runs until unfreeze."""
    from src.application.scenes.gameplay_scene import GameplayScene

    monkeypatch.setenv("DEBUG", "1")
    calls = {"input": 0, "level": 0}
    game = SimpleNamespace(
        input_manager=SimpleNamespace(update=lambda: calls.__setitem__("input", calls["input"] + 1))
    )
    level = SimpleNamespace(
        update=lambda dt: calls.__setitem__("level", calls["level"] + 1),
        completed=False,
        deaths=0,
    )
    scene = GameplayScene(game, level_id=0, level=level)

    scene.update(1 / 60)
    assert calls == {"input": 1, "level": 1}

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    scene.update(1 / 60)
    assert calls == {"input": 2, "level": 1}

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    scene.update(1 / 60)
    assert calls == {"input": 3, "level": 2}


def test_step_key_advances_one_tick_while_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """F7 while frozen runs exactly one tick, then holds again."""
    from src.application.scenes.gameplay_scene import GameplayScene

    monkeypatch.setenv("DEBUG", "1")
    calls = {"level": 0}
    game = SimpleNamespace(input_manager=SimpleNamespace(update=lambda: None))
    level = SimpleNamespace(
        update=lambda dt: calls.__setitem__("level", calls["level"] + 1),
        completed=False,
        deaths=0,
    )
    scene = GameplayScene(game, level_id=0, level=level)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))  # freeze
    scene.update(1 / 60)
    assert calls["level"] == 0

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F7))  # step
    scene.update(1 / 60)
    assert calls["level"] == 1

    scene.update(1 / 60)  # pending step consumed: hold again
    assert calls["level"] == 1

    # F7 ignored while unfrozen (step is freeze-only).
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))  # unfreeze
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F7))
    scene.update(1 / 60)
    assert calls["level"] == 2  # normal unfrozen update, not a double-step


def test_frozen_scene_paints_a_marker(monkeypatch: pytest.MonkeyPatch, camera: Camera) -> None:
    """The FROZEN tag reads red on black while the sim is held."""
    from src.application.scenes.gameplay_scene import GameplayScene
    from src.core.rendering.renderer import Renderer

    monkeypatch.setenv("DEBUG", "1")
    surface = pygame.display.get_surface()
    assert surface is not None
    renderer = Renderer(surface, camera)
    game = SimpleNamespace(input_manager=SimpleNamespace(update=lambda: None), clock=None)
    level = SimpleNamespace(renderer=renderer, draw=lambda *args, **kwargs: None)
    scene = GameplayScene(game, level_id=0, level=level)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
    surface.fill((0, 0, 0))
    assert scene.draw() is None
    assert any(
        surface.get_at((x, y))[:3] == Colors.red for x in range(400, 624) for y in range(10, 34)
    )


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
