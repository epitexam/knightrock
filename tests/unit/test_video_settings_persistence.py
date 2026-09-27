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

import pygame
import pytest

from src.application.scenes.video_scene import DISPLAY_VALUES, VideoScene
from src.application.settings_store import SettingsStore, UserSettings
from src.core.display.mode import DisplayMode
from src.core.game import Game
from src.core.input.input_actions import InputAction

pytestmark = pytest.mark.usefixtures("_video_display")

#: The rows that carry a value, and how to read it back out of the settings.
#: ``AUTO`` is excluded: it is resolved at launch against the machine, so what
#: persists is the player's *request* for that, which is a separate test below.
VALUE_ROWS = {
    "pixel_perfect": lambda settings: settings.pixel_perfect,
    "vsync": lambda settings: settings.vsync,
    "frame_limit": lambda settings: settings.frame_limit,
    "scale": lambda settings: settings.ui_scale,
}

#: What each row is worth cycling to from the defaults: a value that is not the
#: default, so "it persisted" cannot be confused with "it never changed".
CYCLED_TO = {
    "pixel_perfect": True,
    "vsync": True,
    "frame_limit": 120,
    "scale": 1.2,
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
