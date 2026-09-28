"""``world_overlay_cards``: the card's content, and the rows nothing else carries.

The golden pins *where* a card lands; this pins *what is written on it*, for the
rows the golden's plain-entity scene never produces: an attack's phase and hit
count, the status flags, and the per-zone guards. The flags matter most -- the
world boxes carry no text at all, so a card is the only place "dizzy", "ledge"
or "armor" is ever said."""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_ui import WorldUI
from tests.unit.helpers import card_rows

SIZE = (1024, 768)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(SIZE)


@pytest.fixture()
def world_ui() -> WorldUI:
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill((0, 0, 0))
    return WorldUI(PanelRenderer(surface))


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(SIZE[0]), float(SIZE[1])))


def _entity(name: str = "Goblin", **overrides) -> SimpleNamespace:
    base = {
        "hitbox": pygame.FRect(100, 100, 40, 48),
        "hurtbox": pygame.FRect(98, 98, 44, 52),
        "hurtboxes": (pygame.FRect(98, 98, 44, 52),),
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


def _attacking(name: str = "Slime", **state) -> SimpleNamespace:
    entity = _entity(
        name, state_machine=SimpleNamespace(current_state_name=state.get("state_name", "idle"))
    )
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.phase_index = state.get("phase_index", 1)
    entity.combat.state.frame_counter = state.get("frame_counter", 7)
    entity.combat.targets_hit = state.get("targets_hit", {1, 2})
    return entity


# -- the attack row ----------------------------------------------------------


def test_an_attack_gets_a_row_with_its_phase_and_hits(world_ui) -> None:
    """The card is the only place a swing's numbers are written down.

    The world overlay draws the attack box and the header chip, and both of
    those are geometry. "Which phase, which frame, how many things has it
    already hit" has no geometric expression at all, so this row is the only
    place it exists -- and it is the row that answers "why did my attack do
    nothing", which is the question a debug overlay is usually being asked.
    """

    row = card_rows(world_ui._cards, _attacking(state_name="run"))
    attack = next(line for line in row if "claw_swipe" in line)
    assert "p1" in attack, attack
    assert "active:7" in attack, attack
    assert "hits:2" in attack, attack


def test_an_idle_sprite_gets_no_attack_row(world_ui) -> None:
    """No name, no row: a card is not a place to print a null."""

    row = card_rows(world_ui._cards, _entity())
    assert not any("p0" in line for line in row), row


# -- status flags ------------------------------------------------------------


def _flags(sprite: SimpleNamespace) -> list[str]:
    from src.ui.world_overlay_cards import CardLayer

    return [text for text, _ in CardLayer.status_flag_tokens(sprite)]


def _flag_colours(sprite: SimpleNamespace) -> dict[str, object]:
    from src.ui.world_overlay_cards import CardLayer

    return dict(CardLayer.status_flag_tokens(sprite))


def test_a_dizzy_sprite_is_flagged_with_its_remaining_stagger() -> None:
    """Dizzy is a state, but the number that matters is how long it lasts.

    "DIZZY" on its own says the entity is stunned; "DIZZY 0.40s" says whether to
    wait or to leave. The stagger timer is the same number the STAG row shows,
    printed twice on purpose -- the rows are read independently.
    """
    sprite = _entity(
        "Dazed",
        state_machine=SimpleNamespace(current_state_name="dizzy"),
        stagger_timer=0.4,
    )
    assert "DIZZY 0.40s" in _flags(sprite)


def test_a_dizzy_flag_is_gold_while_stagger_is_orange() -> None:
    """Two rows, two colours, so they are not read as one thing.

    The tokens are built from the flag *names*, so this asserts that the two
    names are actually distinct entries in the colour table rather than one
    string written twice.
    """
    from src.core.colors import Colors

    sprite = _entity(
        "Dazed",
        state_machine=SimpleNamespace(current_state_name="dizzy"),
        stagger_timer=0.4,
    )
    colours = _flag_colours(sprite)
    assert colours["DIZZY 0.40s"] == Colors.gold
    assert colours["STAG 0.40s"] == Colors.orange
    assert colours["DIZZY 0.40s"] != colours["STAG 0.40s"]


def test_a_dizzy_sprite_with_no_stagger_timer_still_says_dizzy() -> None:
    """The state is the flag; the timer only qualifies it.

    A stun that outlives its timer still has the player locked out of control,
    and printing "DIZZY 0.00s" for it is the honest reading.
    """
    sprite = _entity("Dazed", state_machine=SimpleNamespace(current_state_name="dizzy"))
    assert "DIZZY 0.00s" in _flags(sprite)


def test_a_ledge_is_flagged_only_while_the_probe_says_so() -> None:
    """The probe is a method, not a value, so it is asked at draw time.

    Standing on a ledge is a per-frame fact and a cached boolean would go stale
    the moment the entity walked off -- which is the frame you care about.
    """
    from src.core.colors import Colors

    on_ledge = _entity("Watcher", is_at_ledge=lambda: True)
    assert _flag_colours(on_ledge)["LEDGE"] == Colors.yellow
    assert "LEDGE" in _flags(on_ledge)

    off_ledge = _entity("Watcher", is_at_ledge=lambda: False)
    assert "LEDGE" not in _flags(off_ledge)


def test_a_non_callable_ledge_attribute_is_not_a_ledge() -> None:
    """``is_at_ledge = True`` is a field on some other entity, not a probe."""
    assert "LEDGE" not in _flags(_entity("Watcher", is_at_ledge=True))


# -- the zone roster row -----------------------------------------------------


def test_a_zone_row_names_its_zone_and_its_guards(world_ui: WorldUI) -> None:
    """The world draws zone outlines; the roster that explains them is here.

    A guarded zone gets a dashed seal on screen, and the seal says nothing
    about *which* tag. This row is where "armor" and "immune" are written, and
    the only reason a player can act on what the seal told them.
    """

    sprite = _entity(
        "Ooze",
        hurtboxes=(pygame.FRect(100, 100, 40, 48), pygame.FRect(100, 100, 20, 48)),
        hurtbox_zone_names=("", "guard"),
        hurtbox_mult=(1.0, 2.0),
        hurtbox_tags=((), ("armor", "immune")),
    )
    row = world_ui._cards.zone_line(sprite)
    assert row is not None
    text = "".join(part for part, _ in row)
    assert "guard" in text, text
    assert "x2" in text, text
    assert "armor,immune" in text, text


def test_an_untagged_single_neutral_zone_gets_no_row(world_ui: WorldUI) -> None:
    """One zone, no name, no multiplier, no guard: there is nothing to say."""

    assert world_ui._cards.zone_line(_entity()) is None


def test_a_guarded_zone_with_no_name_still_gets_a_row(world_ui: WorldUI) -> None:
    """The guard alone is worth a row even when the zone is anonymous.

    A sealed zone on screen with no roster entry would be a mark the player
    cannot act on, which is the whole thing the seal is for.
    """

    sprite = _entity(
        "Ooze",
        hurtboxes=(pygame.FRect(100, 100, 40, 48), pygame.FRect(100, 100, 20, 48)),
        hurtbox_zone_names=("", ""),
        hurtbox_mult=(1.0, 1.0),
        hurtbox_tags=((), ("armor",)),
    )
    row = world_ui._cards.zone_line(sprite)
    assert row is not None
    assert "armor" in "".join(part for part, _ in row)


# -- placements that are supposed to fail -----------------------------------


def test_a_card_taller_than_the_display_is_dropped_not_squeezed(
    world_ui: WorldUI, camera: Camera
) -> None:
    """A card with no fully visible position is not drawn at all.

    Compressing the rows to fit would mean guessing at line heights, and a
    card with a mis-spaced row is harder to read than no card. Dropped beats
    illegible, which is the rule the rest of the placement follows.
    """
    card = world_ui._cards
    tall = [[(f"row {index}", (255, 255, 255))] for index in range(400)]
    placed = card.place_label(
        tall,  # type: ignore[arg-type]
        (255, 255, 255),
        camera.apply(pygame.FRect(300, 300, 40, 48)),
        [],
        *world_ui.surface.get_size(),
    )
    assert placed is None, "a card taller than the screen was drawn anyway"


def test_a_sprite_with_no_label_gets_no_request(world_ui: WorldUI, camera: Camera) -> None:
    """A request needs segments; with none, the card pass is not asked.

    A sprite whose label is ``None`` is one the card layer deliberately has
    nothing to say about, and inventing a request for it would push an empty
    card into the placement and shift every other card around it.
    """
    hazard = _entity("Hazard", state_machine=None, hitbox=None, rect=pygame.FRect(10, 10, 8, 8))
    request = world_ui._cards.label_request(
        hazard, camera.apply(pygame.FRect(10, 10, 8, 8)), True, camera
    )
    assert request is None


def test_the_labels_layer_off_means_no_request(world_ui: WorldUI, camera: Camera) -> None:
    """The toggle is read per request, so F4 takes effect on the next sprite."""
    entity = _entity()
    world_ui.toggle("labels")
    try:
        request = world_ui._cards.label_request(entity, camera.apply(entity.hitbox), False, camera)
        assert request is None, "a card was requested with the labels layer off"
    finally:
        world_ui.toggle("labels")


def test_a_sprite_with_neither_a_body_nor_a_state_gets_no_request(
    world_ui: WorldUI, camera: Camera
) -> None:
    """The last refusal: nothing to describe, and nothing to describe it with.

    A projectile has no state machine and still gets a card, from its velocity
    and its faction. A sprite with no state machine *and* no hitbox has neither
    that nor a body, so ``label_segments`` answers ``None``.

    Through ``draw_debug_overlays`` this is unreachable -- a sprite with no
    hitbox is static, and the static check refuses it first. It is reachable
    from a caller that contradicts itself, which is precisely what the guard is
    for: a second refusal, so the request is never built from a missing row.
    """
    ghost = _entity("Ghost", state_machine=None)
    del ghost.hitbox
    ghost.rect = None
    request = world_ui._cards.label_request(ghost, pygame.FRect(0, 0, 1, 1), False, camera)
    assert request is None, "a request was built for a sprite with no segments"
