"""The pre-split safety net for the world debug overlay.

`world_ui.py` was about to be cut into layers. This froze what the overlay
produces so the cut could be shown to be a no-op instead of asserted to be one:
bar rects, annotation rects and the padded rect of every placed card, in a
five-sprite scene chosen for the branch each sprite forces.

Geometry only, never pixels. A checksum of the surface would be a stronger
test and a worse one -- it breaks on font hinting between two SDL builds, and
once it has, everyone regenerates it without reading it. Rectangles are what the
placement code decides.

Two seams have moved since it was written, both to follow the code rather than
to keep the test stable: the sink is read through `annotation_rects`, and the
manifest check looks inside the layer classes. The recorded rectangles have not
moved with them, and that is the point."""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.ui_manager import UIManager
from src.ui.world_overlay_shared import debug_reference
from src.ui.world_ui import WorldUI

# 1024x768 at zoom 1.0. The golden asserts world-space geometry, so the render
# scale must not drift underneath it.
GOLDEN_SIZE = (1024, 768)

# The frozen geometry, keyed by entity name so the ids stay out of it.
#
# Four sprites chosen for what each one forces a different branch of the
# placement code through:
#   Ooze   -- hard against the top edge, so its health bar has to flip below
#             the entity and drag the attack annotations with it
#   Slime  -- mid-screen, mid-attack, two attack boxes plus a swept box, so it
#             contributes an attack header, badges and anchor dots
#   Ectoplasm -- attacking right on top of Slime, so two headers land on the
#             same band. They overlap on purpose: the tier stack a header dodges
#             is its own entity's bar and its own annotations, never another
#             entity's. Pinning the overlap keeps a well-meaning "fix" during
#             the split from turning two nearby fights into a staircase.
#   Goblin -- idle and close to Slime, so its card has to dodge one already
#             placed
#   Rat    -- the player, so it has no health bar and is placed first
GOLDEN_BARS = {
    "Ooze": (307, 60, 56, 6),
    "Slime": (428, 286, 60, 6),
    "Ectoplasm": (406, 286, 52, 6),
    "Goblin": (504, 316, 32, 6),
    "Rat": None,
}

GOLDEN_ANNOTATIONS = {
    "Ooze": [(300, 70, 158, 31), (344, 24, 15, 15)],
    "Slime": [(420, 251, 158, 31), (464, 314, 15, 15), (456, 348, 15, 15)],
    "Ectoplasm": [(400, 251, 158, 31), (440, 310, 15, 15)],
    "Goblin": [],
    "Rat": [],
}

# Draw order is placement priority, not scene order: the player reads first,
# then top to bottom. The Rat is last in the scene and first on screen.
GOLDEN_PLACED = [
    (680, 504, 80, 53),
    (212, 105, 247, 72),
    (310, 379, 247, 75),
    (335, 479, 247, 72),
    (468, 175, 104, 53),
]

# Every method ``WorldUI`` had before the split, and the one module each one is
# headed for. ``__init__`` is the facade's and is left out of the body below.
# The tests that read this check it is total and single-assigned, and that each
# name is on the facade or in its own module -- never both, never neither. A
# method cannot be dropped or double-claimed by a typo in here.
#
# ``_health_color`` was in this list and is not any more: it did nothing but
# call ``world_overlay_bars.health_colour``, and a card that needs an HP tint
# now calls that directly instead of paying a hop through the facade.
MANIFEST = {
    "facade": (
        "draw_debug_overlays metrics toggle surface draw_health_bars "
        "_health_bar_rect annotation_rects annotation_obstacles"
    ),
    "shared": (
        "debug_reference display_name faction hitbox_color label_color "
        "clamp_annotation dodge_annotation"
    ),
    "shapes": "draw_shape draw_shape_once draw_dashed_rect dashed_edges",
    "velocity": "draw_velocity draw_velocity_arrow is_parry_flash is_reaction_push",
    "geo": (
        "offensive_boxes offensive_shapes offensive_badges offensive_hit "
        "offensive_outline attack_header_rect attack_timeline_widths "
        "paint_attack_timeline live_attack_text timeline_progress draw_boxes "
        "draw_offensive_boxes draw_attack_geometry "
        "draw_zone_seal draw_motion_arrow draw_anchor "
        "register_annotations hurtbox_zones zone_mults zone_tags swept_boxes "
        "swept_shapes attack_anchors box_moved in_situ_dot"
    ),
    "cards": (
        "candidate_slots place_label blit_label draw_labels label_priority "
        "label_clearances label_request label_segments entity_segments "
        "zone_line attack_line status_flag_tokens reaction_flag status_flag_strings "
        "projectile_line"
    ),
    "panels": (
        "update_metrics draw_metrics_panel combat_panel note_clash draw_clash_marker "
        "stamp_clash_marker paint_clash_ring"
    ),
}

# The module each extracted group is headed for, and the class holding it.
# ``world_overlay_bars`` and ``world_overlay_shared`` are plain function
# modules; the layers that draw are classes. A group whose module does not
# exist yet is still sitting on the facade, which is the one state allowed to
# be transient.
MODULES = {
    "shared": ("src.ui.world_overlay_shared", None),
    "shapes": ("src.ui.world_overlay_shapes", "ShapeLayer"),
    "velocity": ("src.ui.world_overlay_velocity", "VelocityLayer"),
    "geo": ("src.ui.world_overlay_geo", "GeoLayer"),
    "cards": ("src.ui.world_overlay_cards", "CardLayer"),
    "panels": ("src.ui.world_overlay_panels", "PanelLayer"),
}


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(GOLDEN_SIZE)


@pytest.fixture()
def world_ui() -> WorldUI:
    surface = pygame.display.get_surface()
    assert surface is not None
    return WorldUI(UIManager(surface).renderer)


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(GOLDEN_SIZE[0]), float(GOLDEN_SIZE[1])))


def _entity(name: str, x: float, y: float, **overrides) -> SimpleNamespace:
    base = {
        "hitbox": pygame.FRect(x, y, 40, 48),
        "hurtbox": pygame.FRect(x - 2, y - 2, 44, 52),
        "hurtboxes": (pygame.FRect(x - 2, y - 2, 44, 52),),
        "hurtbox_zone_names": ("",),
        "hurtbox_mult": (1.0,),
        "hurtbox_tags": ((),),
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
    return type(name, (SimpleNamespace,), {})(**base)


def _attacker(name: str, x: float, y: float, **combat) -> SimpleNamespace:
    entity = _entity(name, x, y)
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.frame_counter = 3
    entity.combat.state.phase_index = 0
    entity.combat.current_phase = SimpleNamespace(
        startup_frames=4, active_frames=4, recovery_frames=4
    )
    for key, value in combat.items():
        setattr(entity.combat, key, value)
    return entity


def _scene() -> list[SimpleNamespace]:
    """The frozen scene. Fixed positions, fixed camera, no clock, no random."""
    return [
        _attacker(
            "Ooze",
            300.0,
            4.0,
            attack_boxes=(pygame.FRect(340, 20, 30, 20),),
            swept_attack_boxes=(pygame.FRect(336, 16, 30, 20),),
            attack_anchors=((330.0, 12.0), (348.0, 30.0)),
        ),
        _attacker(
            "Slime",
            420.0,
            300.0,
            attack_boxes=(
                pygame.FRect(460, 310, 36, 24),
                pygame.FRect(452, 344, 24, 18),
            ),
            swept_attack_boxes=(pygame.FRect(456, 306, 36, 24),),
            attack_anchors=((450.0, 306.0), (466.0, 330.0)),
        ),
        _attacker(
            "Ectoplasm",
            400.0,
            300.0,
            attack_boxes=(pygame.FRect(436, 306, 30, 22),),
            swept_attack_boxes=(pygame.FRect(432, 302, 30, 22),),
            attack_anchors=((426.0, 300.0),),
        ),
        _entity("Goblin", 500.0, 330.0),
        _entity("Rat", 700.0, 560.0, faction="player", health=40.0),
    ]


def _spy_placed(world: WorldUI, monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, ...]]:
    """Collect the padded rects the label cards actually occupied, in draw order."""
    placed: list[tuple[int, ...]] = []
    original = type(world._cards).blit_label

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
        placed.append(tuple(background_rect))
        original(self, header, rows, row_height, accent, label_rect, background_rect, screen_width)

    monkeypatch.setattr(type(world._cards), "blit_label", spy)
    return placed


def _drawn(scene: list[SimpleNamespace], world: WorldUI, camera: Camera) -> None:
    world.surface.fill((0, 0, 0))
    world.draw_debug_overlays(scene, camera)


def _inked(surface: pygame.Surface) -> bool:
    """Did anything get drawn here?

    An all-black surface and a surface with a single black pixel look the same
    to ``get_bounding_rect`` on a 32-bit target, because filling it leaves the
    whole thing opaque. The average colour does tell them apart, and it is
    exact: black everywhere averages to black, and one lit pixel moves it.
    Only the RGB is compared, since the display target carries an alpha and
    ``average_color`` reports it as a fourth channel.
    """
    return pygame.transform.average_color(surface)[:3] != (0, 0, 0)


def test_health_bar_rects_are_frozen(world_ui: WorldUI, camera: Camera) -> None:
    """Where each bar lands, including the one forced below its entity."""
    scene = _scene()
    _drawn(scene, world_ui, camera)
    actual = {}
    for entity in scene:
        anchor = camera.apply(debug_reference(entity))
        bar = world_ui._health_bar_rect(entity, anchor)
        actual[type(entity).__name__] = None if bar is None else tuple(bar)
    assert actual == GOLDEN_BARS


def test_annotation_rects_are_frozen(world_ui: WorldUI, camera: Camera) -> None:
    """The rectangles the box pass registers per sprite: headers, badges, anchors."""
    scene = _scene()
    _drawn(scene, world_ui, camera)
    actual = {
        type(entity).__name__: [
            tuple(rect) for rect in world_ui.annotation_rects.get(id(entity), ())
        ]
        for entity in scene
    }
    assert actual == GOLDEN_ANNOTATIONS


def test_placed_card_rects_are_frozen(
    world_ui: WorldUI, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every card's padded rect, in the order they were placed.

    This is the one that catches placement drift: a changed clearance, a lost
    dodge, a card that slides under a bar. All of it lands in here.
    """
    placed = _spy_placed(world_ui, monkeypatch)
    _drawn(_scene(), world_ui, camera)
    assert placed == GOLDEN_PLACED


def test_placement_is_stable_across_frames(world_ui: WorldUI, camera: Camera) -> None:
    """Drawing the same frame twice must give the same frame.

    The health bars are remembered from the previous frame so a bar that moves
    keeps its card clear of where it *was*. That memory is the one piece of
    state in this pass, and a second identical draw is the cheapest way to catch
    it being read before it is written.
    """
    scene = _scene()
    _drawn(scene, world_ui, camera)
    first = {
        type(entity).__name__: [
            tuple(rect) for rect in world_ui.annotation_rects.get(id(entity), ())
        ]
        for entity in scene
    }
    _drawn(scene, world_ui, camera)
    second = {
        type(entity).__name__: [
            tuple(rect) for rect in world_ui.annotation_rects.get(id(entity), ())
        ]
        for entity in scene
    }
    assert first == second == GOLDEN_ANNOTATIONS


def test_the_sink_is_producers_only(world_ui: WorldUI, camera: Camera) -> None:
    """The box pass writes the sink; the label pass only reads it.

    ``draw_debug_overlays`` resets the sink, the box pass fills it as it draws,
    and the label pass then consults it to know what to dodge. A label that
    also wrote to it would be claiming screen space the next entity reads as
    already taken, which is how a card ends up under a bar with nothing
    explaining it. Asserting the direction here is what keeps the split from
    quietly turning the sink into a two-way channel.
    """
    scene = _scene()
    _drawn(scene, world_ui, camera)

    registered = [tuple(rect) for rect in world_ui.annotation_obstacles]
    assert registered == [rect for rects in GOLDEN_ANNOTATIONS.values() for rect in rects]

    goblin = next(entity for entity in scene if type(entity).__name__ == "Goblin")
    request = world_ui._cards.label_request(
        goblin, camera.apply(debug_reference(goblin)), False, camera
    )
    assert request is not None
    before = len(world_ui.annotation_obstacles)
    world_ui._cards.place_label(
        request[1], request[2], request[3], [], *world_ui.surface.get_size()
    )
    assert len(world_ui.annotation_obstacles) == before, "the label pass wrote to the sink"


def test_the_sink_is_drained_every_frame(world_ui: WorldUI, camera: Camera) -> None:
    """Rectangles do not accumulate across frames.

    Without the reset, a sprite that left the scene would keep its old
    annotations registered forever and the cards of every sprite after it
    would dodge rectangles nobody draws.
    """
    scene = _scene()
    _drawn(scene, world_ui, camera)
    populated = len(world_ui.annotation_obstacles)
    _drawn([scene[3]], world_ui, camera)
    assert len(world_ui.annotation_obstacles) < populated
    _drawn(scene, world_ui, camera)
    assert len(world_ui.annotation_obstacles) == populated


def test_drawing_follows_the_surface_the_renderer_adopts(world_ui: WorldUI, camera: Camera) -> None:
    """The overlay draws into the live target, not the one it was built with.

    ``WorldUI.surface`` is derived from the renderer on purpose: it used to be
    captured at construction, and a resize path that forgot to reassign it left
    the overlay painting into an orphaned surface with no symptom until the two
    sizes disagreed. A different-sized target is used so a cached size would
    show up too.
    """
    scene = _scene()
    _drawn(scene, world_ui, camera)
    stale = world_ui.surface
    stale.fill((0, 0, 0))

    fresh = pygame.Surface((800, 600))
    fresh.fill((0, 0, 0))
    world_ui.renderer.set_surface(fresh)

    assert world_ui.surface is fresh, "the overlay kept the surface it was built with"
    world_ui.draw_debug_overlays(scene, camera)
    # The new target re-reads the density, so the overlay lands somewhere else
    # than it did on the old one. Where is not the point; that it landed is.
    assert _inked(fresh), "nothing reached the new surface"
    assert not _inked(stale), "the overlay painted the abandoned one"


def test_manifest_is_total_and_single_assigned() -> None:
    """Every method is headed somewhere, and only somewhere.

    Worth checking before the cut rather than after: the cut is the part where
    a method can be quietly left behind, and a manifest that forgot one would
    happily let it happen.
    """
    names = [name for group in MANIFEST.values() for name in group.split()]
    assert len(names) == len(set(names)), "a method is claimed by two modules"
    assert MANIFEST["facade"], "the facade cannot be empty"


def test_manifest_names_live_in_exactly_one_place() -> None:
    """Each name is on the facade or in its own module -- never both, never neither.

    This is the check that makes the split provable rather than hopeful. A
    method still sitting on ``WorldUI`` after its group was extracted shows up
    as a duplicate; a method lost on the way shows up as a hole, because the
    union across the facade and the extracted modules has to equal the manifest
    exactly.
    """
    import importlib
    import inspect

    on_facade = {
        name
        for name, member in inspect.getmembers(WorldUI)
        if inspect.isfunction(member) or isinstance(member, property)
    }

    accounted: set[str] = set()
    for group, (path, layer) in MODULES.items():
        wanted = set(MANIFEST[group].split())
        # Half of `WorldUI`'s methods are private and half are not, so "is this
        # name still on the facade" is asked of both spellings.
        pending = {name for name in wanted if name in on_facade or f"_{name}" in on_facade}
        try:
            module = importlib.import_module(path)
        except ModuleNotFoundError:
            # Not extracted yet, so every name must still be on the facade.
            # Anything else means a method went missing between two phases.
            assert pending == wanted, (
                f"{group} is neither extracted nor still on the facade: {sorted(wanted - pending)}"
            )
            accounted |= wanted
            continue
        # A group's names may sit on the layer class or beside it as plain
        # functions: a method that needs no `self` is one, which is why
        # `dashed_edges` and the two velocity predicates are module-level.
        scopes = [vars(module)]
        if layer:
            scopes.append(vars(getattr(module, layer)))
        exported = set()
        for scope in scopes:
            for name, member in scope.items():
                if name.startswith("_"):
                    continue
                # A `@staticmethod` is a descriptor on the class, not a
                # function, and several of these are built that way.
                if isinstance(member, staticmethod):
                    member = member.__func__
                if inspect.isfunction(member) or isinstance(member, property):
                    exported.add(name)
        assert wanted <= exported, f"{path} never got {sorted(wanted - exported)}"
        assert not pending, f"{sorted(pending)} stayed on WorldUI"
        accounted |= wanted

    facade = set(MANIFEST["facade"].split())
    assert facade <= on_facade, f"the facade lost {sorted(facade - on_facade)}"
    accounted |= facade
    assert accounted == {name for group in MANIFEST.values() for name in group.split()}
