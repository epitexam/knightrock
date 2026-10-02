"""Every row of the video screen, on the real runtime, across a relaunch.

The bug this file exists for is not a value that is wrong. It is a value that is
right on the screen and gone after a restart, and it survived because the tests
that covered the screen used a **fake** game: a ``SimpleNamespace`` whose
``apply_settings`` was one assignment, so "the row called apply_settings with the
new value" was the whole claim, and every step between there and the file was
unasserted.

So the assertions here are the three that actually matter, per row:

1. the value moved in ``game.settings``;
2. the payload ``SettingsStore.save`` would write carries it;
3. a *new* runtime, reading that payload back, comes up with the same value.

The relaunch is the part that was missing. A setting can be applied, written and
still not survive, if anything between the write and the next read decides
otherwise -- and three of them used to: the launch resolved ``AUTO`` and wrote
the answer back, the launch re-derived the render scale and wrote *that* back,
and a stored size was rewritten whenever it did not fit the screen it landed on.

Driven through ``Game._handle_events`` and ``Game._to_target_coordinates``, so
the pointer path is the real one: a click on the rectangle the view drew, in
window coordinates, converted by the presentation.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pygame
import pytest

from src.application.scenes.video_scene import DISPLAY_VALUES, VideoScene
from src.application.settings_store import SettingsStore, UserSettings
from src.core.display.mode import DisplayMode
from src.core.game import Game
from src.core.input.input_actions import InputAction


@pytest.fixture(autouse=True)
def _debug_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build the video menu with the overlay on, so the debug row exists.

    ``panel_scale`` is in ``VALUE_ROWS``, and the tests below walk the real screen
    looking each row up by action -- so without the flag, ``_row_index`` fails on
    it. Which is the honest failure: this file is about the rows the screen
    offers, and it should not quietly pass by not offering one.
    """
    monkeypatch.setenv("DEBUG", "1")


pytestmark = pytest.mark.usefixtures("_video_display", "_debug_on")

#: The rows that carry a value, and how to read it back out of the settings.
#: ``AUTO`` is excluded: it is resolved at launch against the machine, so what
#: persists is the player's *request* for that, which is a separate test below.
VALUE_ROWS = {
    "pixel_perfect": lambda settings: settings.pixel_perfect,
    "vsync": lambda settings: settings.vsync,
    "frame_limit": lambda settings: settings.frame_limit,
    "scale": lambda settings: settings.ui_scale,
    "panel_scale": lambda settings: settings.panel_scale,
}

#: What each row is worth cycling to from the defaults: a value that is not the
#: default, so "it persisted" cannot be confused with "it never changed".
CYCLED_TO = {
    "pixel_perfect": True,
    "vsync": True,
    "frame_limit": 120,
    "scale": 1.2,
    # The panel ladder ascends ``0.4 0.5 0.6 0.8 1.0 1.2`` and the default is
    # 1.0, so one forward click lands on 1.2. Not 0.5, which is what the
    # interface ladder's spacing would suggest -- the two ladders are unrelated
    # and the cyclicers index their own.
    "panel_scale": 1.2,
}


@pytest.fixture(scope="module", autouse=True)
def _video_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((1152, 648))


def _runtime(tmp_path: Path) -> tuple[Game, SettingsStore]:
    """A real runtime on a real settings file, built the way the game builds it."""
    store = SettingsStore(tmp_path / "settings.json")
    game = Game(save_path=tmp_path / "save.json", bindings_path=store.path)
    game._initialize()
    assert game.presentation is not None
    # Pinned: whole-pixel art needs a window with room for a whole multiple of
    # the framing, and under the dummy driver the desktop is whatever the last
    # test left behind.
    game.presentation.retarget(pygame.Surface((2304, 1296)))
    game._retarget()
    return game, store


def _row_index(scene: VideoScene, action: str) -> int:
    index = next((i for i, item in enumerate(scene.model.items) if item.action == action), None)
    assert index is not None, f"row {action!r} does not exist"
    return index


def _click(scene: VideoScene, index: int) -> None:
    """Press the row the way a pointer does: at the rectangle the view drew.

    The position is given in *window* coordinates and pushed through the game's
    own conversion, because that is the path a real click takes and it is where
    a letterbox offset would be applied twice.
    """
    game = scene.game
    assert game.presentation is not None
    centre = scene.view.item_rects[index].center
    position = (
        centre[0] + game.presentation.rect.x,
        centre[1] + game.presentation.rect.y,
    )
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
    game._handle_events()
    game.scene_manager.handle_event(game._to_target_coordinates(event))


def _rebound_bindings(game: Game):
    """Bindings that differ from the defaults, in the shape the store reads back.

    Built through the dataclasses rather than through a helper, because the
    question here is what *round-trips*: a rebind that did not survive the file
    would make the rest of this file pass for the wrong reason.
    """
    from dataclasses import replace

    from src.core.input.input_bindings import InputBindings

    gameplay = replace(game.settings.bindings.gameplay, gamepad_axes={InputAction.DASH: 3})
    return InputBindings(gameplay=gameplay, menu=game.settings.bindings.menu)


def _relaunch(store: SettingsStore, tmp_path: Path) -> UserSettings:
    """A second runtime, reading the file the first one wrote.

    ``_initialize`` and not ``load`` alone, because the launch is where three of
    the historical bugs lived: it resolved ``AUTO``, re-derived a sharpness and
    rewrote a size. Reading the file is not enough to catch those.
    """
    game = Game(save_path=tmp_path / "save2.json", bindings_path=store.path)
    game._initialize()
    return game.settings


@pytest.mark.parametrize("row", sorted(VALUE_ROWS))
def test_a_row_survives_a_relaunch(row: str, tmp_path: Path) -> None:
    """The whole claim, per row, on the runtime the player actually uses."""
    game, store = _runtime(tmp_path)
    game.apply_settings(game.settings.with_video(pixel_perfect=False, vsync=False))
    game.scene_manager.push(VideoScene(game))
    scene = game.scene_manager.current
    assert isinstance(scene, VideoScene)
    scene.draw(game.presentation.surface)
    index = _row_index(scene, row)
    assert scene.model.items[index].enabled, f"row {row!r} is not usable on this window"

    # 1. the click moves the setting
    before = VALUE_ROWS[row](game.settings)
    _click(scene, index)
    after = VALUE_ROWS[row](game.settings)
    assert after != before
    assert after == CYCLED_TO[row], f"one click must land on the next value, got {after!r}"

    # 2. the frame writes it
    game.step()
    written = json.loads(store.path.read_text(encoding="utf-8"))

    # 3. the next launch reads it back
    assert VALUE_ROWS[row](_relaunch(store, tmp_path)) == after
    assert written["version"] == 3


def test_the_display_mode_survives_a_relaunch(tmp_path: Path) -> None:
    """A mode is the one row whose value the launch used to overwrite.

    ``AUTO`` resolves against the machine every launch, which is the point of it.
    A *chosen* mode must not be re-resolved, or the row would answer once and
    then quietly go back to whatever the desktop looks like today.
    """
    game, store = _runtime(tmp_path)
    game.apply_settings(game.settings.with_video(display=DisplayMode.WINDOW))
    game.scene_manager.push(VideoScene(game))
    scene = game.scene_manager.current
    assert isinstance(scene, VideoScene)
    scene.draw(game.presentation.surface)

    # Cycle to whatever is not WINDOW, whichever end of the ladder that is.
    for _ in range(len(DISPLAY_VALUES)):
        _click(scene, _row_index(scene, "display"))
        if game.settings.display is not DisplayMode.WINDOW:
            break
    chosen = game.settings.display
    assert chosen is not DisplayMode.WINDOW
    game.step()

    assert _relaunch(store, tmp_path).display is chosen


def test_auto_is_still_auto_on_the_next_launch(tmp_path: Path) -> None:
    """The opposite contract, and it is the reason ``AUTO`` exists.

    ``AUTO`` says "decide again next time, on whatever machine I am on", so the
    file has to keep saying it. A launch that wrote the resolved mode back would
    freeze the answer on the first machine the file ever met -- which is exactly
    what a window size was, and it is why a docked laptop came back wrong.
    """
    game, store = _runtime(tmp_path)
    game.apply_settings(game.settings.with_video(display=DisplayMode.AUTO))
    game.step()

    written = json.loads(store.path.read_text(encoding="utf-8"))
    assert written["video"]["display"] == "auto"

    relaunched = _relaunch(store, tmp_path)
    assert relaunched.display.is_concrete, "the launch has to resolve it to build a window"
    assert json.loads(store.path.read_text(encoding="utf-8"))["video"]["display"] == "auto"


def test_the_reset_row_resets_the_video_settings_and_nothing_else(tmp_path: Path) -> None:
    """A reset on this screen must not cost the player their controls.

    The video screen does not own the bindings, and a reset that reached them
    would be the most expensive kind of surprise: the one thing on the screen
    that cannot be undone by walking back up the menu.
    """
    game, store = _runtime(tmp_path)
    rebound = _rebound_bindings(game)
    game.apply_bindings(rebound)
    game.apply_settings(game.settings.with_video(vsync=True, frame_limit=144, ui_scale=1.2))
    game.scene_manager.push(VideoScene(game))
    scene = game.scene_manager.current
    assert isinstance(scene, VideoScene)
    scene.draw(game.presentation.surface)

    _click(scene, _row_index(scene, "reset"))
    game.step()

    assert game.settings.vsync is UserSettings().vsync
    assert game.settings.frame_limit == UserSettings().frame_limit
    assert game.settings.ui_scale == UserSettings().ui_scale
    assert game.settings.bindings == rebound, "the bindings are not this screen's to reset"
    assert _relaunch(store, tmp_path).bindings == rebound


def test_no_setting_describes_the_window_so_none_can_go_stale(tmp_path: Path) -> None:
    """The structural version of the same claim, and the reason it now holds.

    A setting that describes the window is a claim the game cannot check, and the
    three that used to be here were all wrong in practice: the size was rewritten
    at launch whenever it did not fit, the render scale was written back once and
    then believed forever, and in borderless the window was the desktop's size
    while the menu displayed the stored one. With nothing left in the file that
    can disagree with the window, there is nothing to reconcile.
    """
    game, store = _runtime(tmp_path)

    # Nothing has been touched yet, so there is nothing to write: a first launch
    # must not leave a file behind describing a machine it has already forgotten.
    game.step()
    assert not store.path.exists()

    game.apply_settings(game.settings.with_video(vsync=True))
    game.step()

    video = json.loads(store.path.read_text(encoding="utf-8"))["video"]
    assert set(video) == {"display", "pixel_perfect", "vsync", "frame_limit"}
    assert not {"width", "height", "size_mode", "render_scale", "smoothing"} & set(video)

    # And the settings object agrees with the file, field for field.
    fresh = UserSettings.from_dict(json.loads(store.path.read_text(encoding="utf-8")))
    assert fresh == game.settings


def test_a_window_that_moves_does_not_rewrite_the_settings(tmp_path: Path) -> None:
    """A resize is not a preference, and must not be persisted as one.

    The failure this guards against is a settings file that grows a value on
    every launch because the machine it met first was not the machine it is on:
    the player's file stops describing their choices and starts describing the
    hardware, one launch at a time.
    """
    game, store = _runtime(tmp_path)
    game.apply_settings(game.settings.with_video(vsync=True, frame_limit=144))
    game.step()
    before = store.path.read_text(encoding="utf-8")

    for size in ((1920, 1080), (1280, 720), (800, 600)):
        game.presentation.retarget(pygame.Surface(size))  # type: ignore[arg-type]
        game._retarget()
        game.step()

    assert store.path.read_text(encoding="utf-8") == before
    assert game.settings.vsync is True
    assert game.settings.frame_limit == 144


def test_a_failed_read_is_reported_rather_than_swallowed(tmp_path: Path) -> None:
    """The launch must say so when it cannot trust the file.

    ``SettingsStore.load`` used to catch everything and return the defaults with
    no word, which is indistinguishable from a first launch -- and the first
    change afterwards overwrote the file that still held the player's controls.
    A missing file is silence; an unreadable one is not.
    """
    game, store = _runtime(tmp_path)
    rebound = _rebound_bindings(game)
    game.apply_bindings(rebound)
    game.step()
    store.path.write_text("{ not json", encoding="utf-8")

    with pytest.MonkeyPatch.context() as patch:
        messages: list[str] = []
        patch.setattr(
            "src.application.settings_store.logger.error",
            lambda message, *args: messages.append(message % args if args else message),
        )
        recovered = store.load()

    assert recovered == UserSettings(), "defaults are still the answer"
    assert any("settings.json" in message for message in messages), messages
    # And the file is left exactly as it was, so the controls are recoverable.
    assert store.path.read_text(encoding="utf-8") == "{ not json"
    assert game.settings.bindings == rebound, "the live runtime still holds them"


# --- the debug-only panel scale --------------------------------------------


def test_the_panel_scale_is_persisted_and_survives_a_relaunch(tmp_path: Path) -> None:
    """The default is 1.0, which makes a dropped key look correct.

    ``VALUE_ROWS`` covers the three-part claim for every row in the cycle tables;
    this one is called out because its default equals the value a missing key
    would produce, so a save that quietly omitted it would pass every assertion
    here until the player restarted -- and saw their panels at full size again
    without being told why.
    """
    game, store = _runtime(tmp_path)

    assert game.settings.panel_scale == 1.0
    game.apply_settings(game.settings.with_video(panel_scale=0.5))
    game.step()

    assert game.settings.panel_scale == 0.5
    written = json.loads(store.path.read_text())
    assert written["ui"]["panel_scale"] == 0.5

    relaunched, _ = _runtime(tmp_path)
    assert relaunched.settings.panel_scale == 0.5


def test_a_settings_file_without_the_key_keeps_the_default_size(tmp_path) -> None:
    """A file written before the key existed must not resize every panel.

    ``ui.scale`` has a default for the same reason, and the general rule is in
    ``settings_store``: unknown keys are ignored rather than rejected, because
    losing the bindings over a video key is a bad trade.
    """
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 3,
                "bindings": {},
                "video": {"display": "window", "vsync": False},
                "ui": {"scale": 1.0},
            }
        )
    )
    game, _ = _runtime(tmp_path)

    assert game.settings.panel_scale == 1.0
    assert game.settings.ui_scale == 1.0


def test_the_panel_scale_is_not_stored_under_video(tmp_path) -> None:
    """It is a size preference, and ``video`` is held to four exact keys.

    That exactness exists so no setting can describe the window and disagree with
    it. A panel scale cannot -- it says how big to draw on the window, not how big
    it is -- so it belongs beside the interface scale rather than among the keys
    that once got a stored resolution.
    """
    game, store = _runtime(tmp_path)
    game.apply_settings(game.settings.with_video(panel_scale=0.4))
    game.step()

    written = json.loads(store.path.read_text())

    assert set(written["video"]) == {"display", "pixel_perfect", "vsync", "frame_limit"}
    assert "panel_scale" in written["ui"]


def test_applying_the_panel_scale_reaches_the_panels_that_draw_them(
    tmp_path: Path,
) -> None:
    """The push, which nothing above tested.

    The persistence tests prove the value moves in ``settings``, reaches the
    file, and comes back on the next launch. None of that says the renderer ever
    hears about it -- and the setting is worthless if the panels keep drawing at
    the old size while the menu reports a new one. That gap was found by deleting
    the call from ``apply_settings`` and watching every test in this file stay
    green.

    Asserted as a ratio on the resolved ``screen_scale``, not as an absolute:
    the harness builds a 2304x1296 target, whose density is 2.0 and therefore
    already at the cap, so a fixed number here would be asserting the density as
    much as the preference. Halving the preference has to halve what is drawn.
    """
    game, _ = _runtime(tmp_path)
    overlay = game.world_overlay(game.presentation.surface)
    before = overlay.renderer.screen_scale

    game.apply_settings(game.settings.with_video(panel_scale=0.5))

    assert overlay.renderer.panel_scale == pytest.approx(0.5)
    assert overlay.renderer.screen_scale == pytest.approx(before * 0.5)


def test_applying_the_panel_scale_does_not_rebuild_the_window(tmp_path: Path) -> None:
    """It is a size preference, not a window one.

    A window change rebuilds the display and re-derives the screen scale from the
    new density, which would silently overwrite the preference -- so the two must
    stay independent. This is the same claim as
    ``test_applying_only_the_ui_scale_keeps_the_window``, for the neighbouring
    row: if this ever started calling ``set_mode``, the setting would work and
    then stop working on the next window change.
    """
    game, _ = _runtime(tmp_path)
    overlay = game.world_overlay(game.presentation.surface)

    with patch.object(pygame.display, "set_mode") as set_mode:
        game.apply_settings(game.settings.with_video(panel_scale=0.4))

    assert set_mode.call_count == 0
    assert overlay.renderer.panel_scale == pytest.approx(0.4)


def test_a_saved_panel_scale_is_the_size_drawn_on_the_first_launch(tmp_path: Path) -> None:
    """The bug this setting shipped with, as a runtime property.

    The overlay is built lazily, on the first frame that needs it -- well after
    the settings file has been read. So a preference applied only from
    ``apply_settings`` reaches an overlay that does not exist yet, and the panels
    come up at the default however the file is written: the variable right in the
    menu, the drawing wrong on screen. Everything above this test passes with
    that broken, because the value really does survive the relaunch -- it just
    never arrives.

    Asserted on the drawn size against the saved one, for every rung, because a
    partial fix -- say honouring it only for the values below 1.0 -- would show
    up as a row that passes here.
    """
    from src.application.settings_store import PANEL_SCALES

    for saved in PANEL_SCALES:
        payload = UserSettings().to_dict()
        payload["ui"] = {"scale": 1.0, "panel_scale": saved}
        (tmp_path / "settings.json").write_text(json.dumps(payload), encoding="utf-8")

        game, _ = _runtime(tmp_path)
        overlay = game.world_overlay(game.presentation.surface)

        assert game.settings.panel_scale == saved
        assert overlay.renderer.panel_scale == pytest.approx(saved), (
            f"saved {saved}, drawn {overlay.renderer.screen_scale}"
        )


def test_the_overlay_built_after_a_live_change_keeps_that_change(tmp_path: Path) -> None:
    """The other order, which is the same bug seen from the other side.

    Changing the setting while no overlay exists yet, then building one, must not
    bring the default back. It is the same defect -- a preference pushed to an
    object that did not exist -- and it is what a developer hits by changing the
    setting from the menu before ever entering a level.
    """
    game, _ = _runtime(tmp_path)
    assert game.ui is None, "the fixture is supposed to start with no overlay"

    game.apply_settings(game.settings.with_video(panel_scale=0.4))
    overlay = game.world_overlay(game.presentation.surface)

    assert overlay.renderer.panel_scale == pytest.approx(0.4)


def test_a_panel_scale_that_is_not_positive_is_refused_at_construction_too(
    tmp_path: Path,
) -> None:
    """Constructor and setter share one check, so they cannot drift.

    A value accepted when the overlay is built and refused when the player cycles
    it is a setting that works on the first run and fails on the second, which is
    harder to read than either behaviour alone.
    """
    from src.ui.panel_renderer import PanelRenderer

    with pytest.raises(ValueError, match="panel scale must be positive"):
        PanelRenderer(pygame.Surface((640, 480)), panel_scale=0.0)
    with pytest.raises(ValueError, match="panel scale must be positive"):
        PanelRenderer(pygame.Surface((640, 480)), panel_scale=-1.0)
