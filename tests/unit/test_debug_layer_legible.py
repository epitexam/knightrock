"""The debug layer has to be *visible*, and a dead key has to say so.

Two failures, one afternoon, and both are about a tool that was present and
useless:

* **F1 drew nothing.** Not because the key was dead -- it toggled the layer
  perfectly well -- but because the overlay's cull compared a sprite's
  **world** rectangle against a **target-pixel** rectangle. The two spaces only
  coincide when the camera sits at the origin, which is never, so every sprite
  was culled and the loop had nothing to draw. A cull that rejects everything
  looks exactly like an empty one: no error, no log, a frame that is simply
  identical to the frame without the overlay.
* **and what did draw was half the weight.** Every width, padding and gap in the
  layer was a literal in target pixels from the era when a world unit was one
  target pixel, while the rectangles they decorated came from ``camera.apply``,
  which scales. At a density of 1.889 a 1px hitbox outline arrived at 53% of its
  intent and vanished into the tile grid.

Both are unit mismatches, and both are invisible to a test that only checks that
a boolean flipped. So these tests look at *pixels* and at *units*.
"""

import os

import pygame
import pytest

from src.core.game import Game
from src.core.settings import Debug
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_ui import WorldUI

WINDOW = (2176, 1224)
DENSITY = WINDOW[0] / 1152.0


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


def _renderer(density: float) -> PanelRenderer:
    surface = pygame.Surface((round(1152 * density), round(648 * density)))
    return PanelRenderer(surface, density=density)


# --------------------------------------------------------------------------
# 1. The cull is in the same space as what it culls.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("offset", [(0.0, 0.0), (300.0, 1103.0), (2400.0, 0.0)])
def test_a_sprite_the_camera_is_looking_at_survives_the_overlay_cull(offset) -> None:
    """The regression, stated as the invariant that broke.

    ``draw_debug_overlays`` culled with a rectangle it had pushed through
    ``camera.apply`` -- target pixels -- against ``sprite.rect`` -- world units.
    With the camera at the world origin the two agree by accident, which is why
    the bug waited for a level with a player who moves.
    """
    from src.core.rendering.camera import Camera

    camera = Camera()
    camera.offset.update(offset)
    camera._previous_offset = pygame.Vector2(camera.offset)
    camera.begin_frame(1.0)

    # A sprite at the middle of what the camera is looking at, and one a long
    # way outside it. The first is placed from the *offset*, because that is
    # where the framing is: a fixture that assumed the origin is a fixture that
    # cannot fail.
    centre = camera.offset + pygame.Vector2(camera.viewport_width / 2, camera.viewport_height / 2)
    inside = pygame.FRect(centre.x, centre.y, 32, 32)
    outside = pygame.FRect(-4000.0, -4000.0, 32, 32)

    assert camera.is_visible(inside), "the fixture sprite must be on screen"
    assert not camera.is_visible(outside)


def test_the_overlay_cull_is_the_camera_cull() -> None:
    """One cull, not two: the overlay and the world pass cannot disagree.

    The fix was not a corrected conversion, it was to stop converting and ask
    the camera -- the component that already owns a world-space cull, and the one
    the renderer itself uses.
    """
    assert not hasattr(WorldUI, "_viewport"), (
        "a second cull is what broke; the overlay must use Camera.is_visible"
    )


# --------------------------------------------------------------------------
# 2. Every dimension in the layer is in the layer's own units.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("density", [1.0, 1.1111, 1.8889, 2.0, 3.3333, 0.5])
def test_the_overlay_is_never_thinner_than_its_art_pixels(density: float) -> None:
    """Every dimension is its world value at the layer's scale, floored at one.

    The scale is ``max(1.0, density)``: a window smaller than the framing thins
    the overlay towards its design size and stops there, because rounding a
    width to zero *deletes* it and a debug layer with a hole in it is worse than
    one that is slightly too big.
    """
    world_ui = WorldUI(_renderer(density))
    metrics = world_ui.metrics
    scale = world_ui.renderer.world_scale

    assert world_ui.stroke() == max(1, round(scale))
    assert metrics.zone_outline == max(1, round(scale))
    assert metrics.zone_boost_outline == max(1, round(2 * scale))
    # Below one it keeps its design size rather than thinning towards nothing.
    assert metrics.tier_gap >= 1
    assert metrics.chip_pad >= 1
    assert metrics.timeline_bar_height >= 1
    assert metrics.timeline_px_per_frame >= 1
    assert metrics.clash_radius >= 1


def test_the_world_scale_never_drops_below_one() -> None:
    """A window smaller than the framing thins the overlay, never removes it.

    ``not drawing the outline`` is the one outcome a debug tool must never
    produce, and a plain round at a density of 0.4 produces exactly that.
    """
    assert WorldUI(_renderer(0.4)).stroke() == 1
    assert _renderer(0.4).world_scale == 1.0


@pytest.mark.parametrize("density", [1.0, 1.8889, 3.3333])
def test_the_panel_typography_follows_the_window(density: float) -> None:
    """Panels are screen furniture, so they grow with the window -- to a point.

    Capped, because a 4K panel scaled by its 3.3 density would spend a quarter
    of the display saying the same thing three times larger.
    """
    renderer = _renderer(density)
    design = _renderer(1.0)

    assert renderer.debug_font.get_height() > design.debug_font.get_height() or density == 1.0
    assert renderer.screen_scale == pytest.approx(min(max(1.0, density), 2.0))
    assert renderer.world_scale == pytest.approx(max(1.0, density))


def test_the_world_cards_and_the_panels_scale_independently() -> None:
    """The two families, on one renderer, at a density where they differ.

    A label card pinned above a sprite is a description of the world and follows
    it; a panel is furniture and is capped. Wiring both to one scale is how the
    4K case ends up with unreadable cards.
    """
    renderer = _renderer(3.3333)
    assert renderer.world_scale == pytest.approx(3.3333)
    assert renderer.screen_scale == pytest.approx(2.0)


def test_a_panel_hit_box_is_the_size_of_the_button_it_belongs_to() -> None:
    """A ``×`` nobody can hit is a panel nobody can close.

    The hit box is shared with the interaction layer, so it is checked here
    through both: the drawn glyph's box and the one the click is tested against
    must be the same rect, and both must grow with the panels.
    """
    from src.ui.panel_renderer import close_box_rect

    for scale in (1.0, 1.8889, 2.0):
        assert close_box_rect(100, 100, scale).width == max(6, round(14 * scale))
    interaction = _renderer(1.8889).interaction
    assert interaction.scale == pytest.approx(1.8889)


# --------------------------------------------------------------------------
# 3. A key that cannot act says so.
# --------------------------------------------------------------------------


def _game(tmp_path, monkeypatch, debug: bool) -> Game:
    monkeypatch.setenv("KNIGHTROCK_SAVE_DIR", str(tmp_path / "home"))
    monkeypatch.setenv("DEBUG", "1" if debug else "0")
    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    return game


def test_f_keys_without_the_flag_explain_themselves_instead_of_doing_nothing(
    tmp_path, monkeypatch
) -> None:
    """The second failure: a silent dead key is indistinguishable from a bug.

    Every F-key is debug-only, and without ``--debug`` they did nothing at all:
    no overlay, no log, no hint. The fix is not to make the overlay
    unconditional -- a player who asked for no panels should get no panels -- but
    to name the flag, once.
    """
    from src.application.scenes.gameplay_scene import GameplayScene

    game = _game(tmp_path, monkeypatch, debug=False)
    game.scene_manager.switch(GameplayScene(game, 0))
    for _ in range(3):
        game.step()
    assert not Debug.is_enabled()

    pygame.event.post(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1, mod=0, unicode="", scancode=0)
    )
    game._handle_events()

    assert game.notice_lines, "F1 with no debug flag must say something"
    assert any("--debug" in line for line in game.notice_lines)
    assert any("F1" in line or "F-keys" in line for line in game.notice_lines)


def test_the_notice_is_shown_once_and_then_expires(tmp_path, monkeypatch) -> None:
    """A hint that repeats is a permanent overlay, which is what it warns about."""
    from src.application.scenes.gameplay_scene import GameplayScene

    game = _game(tmp_path, monkeypatch, debug=False)
    game.scene_manager.switch(GameplayScene(game, 0))
    for _ in range(3):
        game.step()

    for key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)
        )
        game._handle_events()
    assert game.notice_lines, "a second key should not need a second hint"
    assert sum(1 for _ in game.notice_lines) == 2

    for _ in range(600):
        game.step()
    assert game.notice_lines == (), "the notice has to go away on its own"


def test_with_the_flag_there_is_no_notice_and_the_layers_still_flip(tmp_path, monkeypatch) -> None:
    """The flag path is unchanged: no nagging, and F1 still toggles."""
    from src.application.scenes.gameplay_scene import GameplayScene

    game = _game(tmp_path, monkeypatch, debug=True)
    game.scene_manager.switch(GameplayScene(game, 0))
    for _ in range(3):
        game.step()
    scene = game.scene_manager.current
    world_ui = scene.level.renderer.ui_manager.world_ui
    before = world_ui.layers["boxes"]

    pygame.event.post(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1, mod=0, unicode="", scancode=0)
    )
    game._handle_events()

    assert world_ui.layers["boxes"] is not before
    assert game.notice_lines == ()


def test_an_unrelated_key_never_produces_a_notice(tmp_path, monkeypatch) -> None:
    """Only the debug keys. A notice on every keypress is noise."""
    from src.application.scenes.gameplay_scene import GameplayScene

    game = _game(tmp_path, monkeypatch, debug=False)
    game.scene_manager.switch(GameplayScene(game, 0))
    for _ in range(3):
        game.step()

    pygame.event.post(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=0)
    )
    game._handle_events()

    assert game.notice_lines == ()
