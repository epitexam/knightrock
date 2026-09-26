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
from src.core.display.letterbox import letterbox
from src.core.display.viewport import Viewport
from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.settings import Simulation
from tests.headless.conftest import make_programmatic_level_data

pytestmark = pytest.mark.usefixtures("_independence_display")

#: Deliberately spans a 16:9 panel, a 16:10 one and a small window, and both
#: render scales: none of them may reach the world.
WINDOWS = [(640, 480), (1280, 720), (1440, 900), (1920, 1080), (2560, 1440)]

#: Densities worth walking: below one (a window smaller than the framing), whole
#: numbers, and the awkward fractions real displays produce.
DENSITIES = (0.5, 1.0, 1.25, 2176 / 1152, 2.0)

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


def _run(window: tuple[int, int], density: float = 1.0, ticks: int = 90) -> str:
    """Run a fixed input log at one window size and one pixel density."""
    pygame.display.set_mode(window)
    viewport = Viewport(DEFAULT_FRAMING, _target(density))
    viewport.surface.fill((0, 0, 0))
    level = Level(viewport.surface, make_programmatic_level_data(), InputManager())
    for _ in range(ticks):
        level.update(Simulation.TIMESTEP)
    return _world_checksum(level)


def _target(density: float) -> tuple[int, int]:
    """A target of that density, the way a window of some size would produce."""
    return (
        round(DEFAULT_FRAMING.width * density),
        round(DEFAULT_FRAMING.height * density),
    )


def test_the_same_input_gives_the_same_world_at_every_window_size() -> None:
    reference = _run(WINDOWS[0])
    assert reference, "the checksum must not be empty, or this test proves nothing"

    for window in WINDOWS[1:]:
        assert _run(window) == reference, f"the world moved at {window}"


def test_the_pixel_density_cannot_reach_the_world_either() -> None:
    """The density decides how big the picture is, and nothing else.

    Worth separating from the window: it is the one display quantity that is
    *meant* to change how much detail is drawn, so it is the one most likely to
    leak into a coordinate somewhere. It is also a fraction now, which is a new
    way for a rounding to turn into a physics difference.
    """
    reference = _run(WINDOWS[0], 1.0)

    for density in DENSITIES:
        assert _run(WINDOWS[0], density) == reference, f"the world moved at {density}"


def test_a_window_too_small_to_show_a_whole_level_changes_nothing() -> None:
    assert _run(TINY_WINDOW) == _run(WINDOWS[0])


def test_the_camera_viewport_is_the_framing_at_every_density() -> None:
    """The other half: not only is the state unchanged, so is what is visible.

    The density is the only display quantity the draw path has, and it decides
    how large the world is *drawn*. What the player sees is the framing, whatever
    that density turns out to be.
    """
    seen = set()
    for density in DENSITIES:
        viewport = Viewport(DEFAULT_FRAMING, _target(density))
        level = Level(viewport.surface, make_programmatic_level_data(), InputManager())
        seen.add((level.camera.viewport_width, level.camera.viewport_height))
    assert seen == {DEFAULT_FRAMING.size}


def test_the_render_target_follows_the_window_and_nothing_else() -> None:
    """The inverse of the property this file used to assert, and it is the point.

    It used to say the target's size did not depend on the window -- true, and
    the reason a fixed target had to be resampled onto the window afterwards, at
    a cost of 4.24ms a frame at 2176x1224 and with a softness no setting could
    remove. The target is the window now, so it follows it exactly, and what
    still does *not* follow it is the world: the checksum tests above are the
    other half, and neither half is optional.
    """
    seen = set()
    for window in WINDOWS:
        pygame.display.set_mode(window)
        seen.add(Viewport(DEFAULT_FRAMING, letterbox(window, DEFAULT_FRAMING).size).size)
    assert seen == {letterbox(window, DEFAULT_FRAMING).size for window in WINDOWS}, (
        "the target must be each window's own letterbox rectangle"
    )
    assert len(seen) > 1, "a target that ignores the window is the regression"


def test_a_desktop_smaller_than_the_framing_still_gets_a_target() -> None:
    """The "launch on any setup" case, headless.

    A window narrower than the framing used to be impossible to place: the
    arithmetic went negative and the title bar landed under the task bar. The
    placement now belongs to SDL, so the question is only whether a target is
    produced whatever the desktop claims.
    """
    assert desktop_size()[0] > 0
    for window in ((800, 600), (640, 360), (500, 400), (100, 80)):
        target = Viewport(DEFAULT_FRAMING, letterbox(window, DEFAULT_FRAMING).size)
        assert target.size[0] > 0 and target.size[1] > 0
        assert target.density > 0.0
