"""The simulation must not be able to see the window.

This is the invariant the whole display rework rests on, stated as tests. The
simulation reads the framing and nothing else, so the same input log has to
produce the same world whatever size the window happens to be.

Worth being precise about what went wrong, because "the resolution is a video
setting" sounds harmless. The camera was built from the window's pixel size, so
the slice of world the player could see was decided in the video menu: two
players on the same level saw different amounts of it, reaction times differed,
and a large enough window put a whole level on screen at once.

The tests divide into two groups, and it is worth knowing which catches what.
Re-coupling the **camera** to the window moves both the framing and the camera
offset, and the checksum tests see it. Re-coupling the **render target** to the
window changes the target's size without touching the world at all -- and that
is the regression the world-state tests cannot see, because the world state
genuinely does not depend on it. ``test_the_render_target_size_does_not_depend
_on_the_window`` is the one that catches that, and it is the reason the video
menu can offer a setup-aware size list without the layout code having to know.
"""

import os

import pygame
import pytest

from src.core.display.detection import desktop_size
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.settings import Simulation
from tests.headless.conftest import make_programmatic_level_data

pytestmark = pytest.mark.usefixtures("_independence_display")

#: Deliberately spans a 16:9 panel, a 16:10 one and a small window, and both
#: render scales: none of them may reach the world.
WINDOWS = [(640, 480), (1280, 720), (1440, 900), (1920, 1080), (2560, 1440)]
SCALES = (1, 2, 3)

#: A window even smaller than the smallest preset: the case the old
#: fixed-catalogue picker got wrong by offering sizes it could not show.
TINY_WINDOW = (800, 450)


@pytest.fixture(scope="module", autouse=True)
def _independence_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def _world_checksum(level: Level) -> str:
    """A stable fingerprint of everything the simulation owns.

    The camera offset is in it deliberately, and it is the part that gives this
    test its teeth. Entity positions alone would have been identical under the
    old camera: the world state genuinely did not depend on the window, only
    how much of it was *visible*. The offset is where that showed up, because
    ``follow`` aims at ``centre - viewport / 2`` and the clamp is
    ``world - viewport``, so a window-derived viewport moved the camera.
    """
    parts: list[str] = []
    parts.append(f"tick={level.tick}")
    parts.append(f"camera={round(level.camera.offset.x, 2)},{round(level.camera.offset.y, 2)}")
    for sprite in sorted(
        level.groups.all_sprites, key=lambda s: (round(s.rect.x), round(s.rect.y))
    ):
        parts.append(
            f"{type(sprite).__name__}:{round(sprite.rect.x, 2)},{round(sprite.rect.y, 2)},"
            f"{round(sprite.rect.width, 2)},{round(sprite.rect.height, 2)}"
        )
    if level.player is not None:
        parts.append(f"player_state={level.player.state_machine.current_state_name}")
        parts.append(f"health={level.player.health:.2f}")
        parts.append(f"posture={level.player.guard_posture:.2f}")
        parts.append(f"charges={level.player.dash_charges}")
    return "|".join(parts)


def _run(window: tuple[int, int], scale: int, ticks: int = 90) -> str:
    """Run a fixed input log at one window size and one render scale."""
    pygame.display.set_mode(window)
    viewport = Viewport(DEFAULT_FRAMING, scale)
    viewport.surface.fill((0, 0, 0))
    level = Level(viewport.surface, make_programmatic_level_data(), InputManager())
    for _ in range(ticks):
        level.update(Simulation.TIMESTEP)
    return _world_checksum(level)


def test_the_same_input_gives_the_same_world_at_every_window_size() -> None:
    reference = _run(WINDOWS[0], 1)
    assert reference, "the checksum must not be empty, or this test proves nothing"

    for window in WINDOWS[1:]:
        assert _run(window, 1) == reference, f"the world moved at {window}"


def test_the_render_scale_cannot_reach_the_world_either() -> None:
    """The scale decides how big the picture is, and nothing else.

    Worth separating from the window: it is the one display setting that is
    *meant* to change how much detail is drawn, so it is the one most likely to
    leak into a coordinate somewhere.
    """
    reference = _run(WINDOWS[0], 1)

    for scale in SCALES[1:]:
        assert _run(WINDOWS[0], scale) == reference, f"the world moved at scale {scale}"


def test_a_window_too_small_to_show_a_whole_level_changes_nothing() -> None:
    assert _run(TINY_WINDOW, 1) == _run(WINDOWS[0], 1)


def test_the_camera_viewport_is_the_framing_at_every_window_size() -> None:
    """The other half: not only is the state unchanged, so is what is visible."""
    seen = set()
    for window in WINDOWS:
        pygame.display.set_mode(window)
        viewport = Viewport(DEFAULT_FRAMING, 2)
        level = Level(viewport.surface, make_programmatic_level_data(), InputManager())
        seen.add((level.camera.viewport_width, level.camera.viewport_height))
    assert seen == {DEFAULT_FRAMING.size}


def test_the_render_target_size_does_not_depend_on_the_window() -> None:
    """Which is the property that makes the layout code above unnecessary."""
    sizes = set()
    for window in WINDOWS:
        pygame.display.set_mode(window)
        sizes.add(Viewport(DEFAULT_FRAMING, 2).size)
    assert sizes == {DEFAULT_FRAMING.viewport_size(2)}


def test_a_desktop_smaller_than_the_framing_still_opens_a_window() -> None:
    """The "launch on any setup" case, headless.

    A window narrower than the framing used to be impossible to centre: the
    arithmetic goes negative and the title bar lands under the task bar. It is
    bounded now, and the framing does not care.
    """
    from src.core.display.detection import centered_on_primary

    x, y = centered_on_primary((2000, 1200), (1024, 600))

    assert (x, y) == (0, 0)
    assert pygame.display.get_surface() is not None
    assert desktop_size()[0] > 0
