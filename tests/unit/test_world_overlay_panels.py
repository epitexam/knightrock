"""``world_overlay_panels``: the COMBAT readout and the clash ring.

The other layers are covered by files that build a scene and read the surface.
This one has no scene: it reports on a frame rather than drawing the world, and
what it reports is the sum of four independent conditions — the counters, the
live attack, the hit-stop and the clash. Each can be present or absent on its
own, so a test that forgets to set one leaves a line nobody has ever seen.

The clash ring is the exception, covered by pixel assertions: its whole job is
putting a mark on the world at a point."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_ui import WorldUI

SIZE = (1024, 768)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(SIZE)


@pytest.fixture()
def world_ui(monkeypatch: pytest.MonkeyPatch) -> WorldUI:
    monkeypatch.setenv("DEBUG", "1")
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill((0, 0, 0))
    return WorldUI(PanelRenderer(surface))


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(SIZE[0]), float(SIZE[1])))


def _metrics(pairs: int = 9, overlaps: int = 2, contacts: int = 1) -> SimpleNamespace:
    return SimpleNamespace(pairs_tested=pairs, overlaps=overlaps, contacts=contacts)


def _attacking(name: str = "jab") -> SimpleNamespace:
    return SimpleNamespace(
        combat=SimpleNamespace(
            state=SimpleNamespace(attack_name=name, sub_state="active", frame_counter=3)
        )
    )


def _published(world_ui: WorldUI, **kwargs) -> list[str]:
    """Drive the panel through its throttle and return the line texts."""
    for _ in range(10):
        world_ui.panels.update_metrics(_metrics())
    world_ui.panels.draw_metrics_panel(**kwargs)
    content = world_ui.panels.combat_panel()
    assert content is not None, "the panel collected nothing at all"
    return [text for text, _ in content[1]]


# -- the four conditions -----------------------------------------------------


def test_counters_reach_the_panel_through_the_metrics_argument(world_ui: WorldUI) -> None:
    """``draw_metrics_panel`` can take the counters itself.

    The game hands them over in one call; the tests had been calling
    ``update_metrics`` separately and then the panel with no argument, so the
    combined path -- the one production actually uses -- was the one path with
    no test on it.
    """
    for _ in range(10):
        world_ui.panels.draw_metrics_panel(metrics=_metrics(pairs=12, overlaps=3))
    lines = [text for text, _ in world_ui.panels.combat_panel()[1]]  # type: ignore[index]
    assert "pairs 12" in lines, lines
    assert "whiffs 9" in lines, lines


def test_a_live_attack_adds_its_own_line(world_ui: WorldUI) -> None:
    """The panel says what the player is swinging, while it is swinging.

    This is the line that answers "is my input even reaching the attack", and
    it is the only place the live attack text appears in screen space -- the
    world chip is a shape, not a sentence.
    """
    assert "atk jab active f3" in _published(world_ui, player=_attacking())


def test_an_idle_player_adds_no_attack_line(world_ui: WorldUI) -> None:
    """No attack in progress, no line: the panel is not a log."""
    idle = SimpleNamespace(
        combat=SimpleNamespace(state=SimpleNamespace(attack_name=None, sub_state=None))
    )
    assert not any(line.startswith("atk ") for line in _published(world_ui, player=idle))


def test_a_hit_stop_is_reported_in_seconds(world_ui: WorldUI) -> None:
    """Hit-stop is invisible otherwise -- the game is frozen, not broken.

    Without this line a frozen game and a crashed game look identical on
    screen, which is the single most expensive confusion a debug panel can have.
    """
    assert "hit-stop 0.08s" in _published(world_ui, hit_stop=0.08)


def test_no_hit_stop_adds_no_line(world_ui: WorldUI) -> None:
    """Zero is not a hit-stop, and neither is a missing argument."""
    assert not any(line.startswith("hit-stop") for line in _published(world_ui, hit_stop=0.0))
    assert not any(line.startswith("hit-stop") for line in _published(world_ui))


def test_a_live_clash_is_flagged_in_the_panel(world_ui: WorldUI) -> None:
    """The panel carries the clash, not only the ring in the world.

    The ring expires in a third of a second. The panel is where a clash that
    happened is still readable afterwards, and it is the only place that says
    one did.
    """
    world_ui.panels.note_clash((200.0, 200.0))
    assert "CLASH" in _published(world_ui)


def test_a_clash_that_expired_is_no_longer_flagged(world_ui: WorldUI, camera: Camera) -> None:
    """The panel reads the ring's remaining lifetime, not a sticky flag.

    A clash that is still flagged a second later is worse than no flag: it
    stops being information and becomes decoration, and the player learns to
    ignore it.
    """
    world_ui.panels.note_clash((200.0, 200.0))
    for _ in range(60):
        world_ui.panels.draw_clash_marker(camera, 0.05)
    assert not any(line == "CLASH" for line in _published(world_ui))


# -- the clash ring on the world --------------------------------------------


def test_the_stamp_paints_the_ring_without_aging_it(world_ui: WorldUI, camera: Camera) -> None:
    """Stamping is a second pass over the same ring, not a second ring.

    The health bars paint after the overlays, so a clash that happened under a
    bar would be hidden by it. The stamp draws the ring again on top -- and
    deliberately does not decay it, because the frame is not older for having
    been drawn twice.
    """
    world_ui.panels.note_clash((300.0, 300.0))
    lifetime = world_ui.panels._clash_ttl
    world_ui.panels.stamp_clash_marker(camera)
    assert world_ui.panels._clash_ttl == lifetime, "stamping consumed part of the ring's life"
    assert any(
        world_ui.surface.get_at((x, 300))[:3] == tuple(Colors.gold) for x in range(280, 321)
    ), "the stamp painted nothing where the ring should be"


def test_stamping_with_no_clash_paints_nothing(world_ui: WorldUI, camera: Camera) -> None:
    """No point, no ring -- and no draw call on an empty tuple."""
    world_ui.surface.fill((0, 0, 0))
    world_ui.panels.stamp_clash_marker(camera)
    assert world_ui.surface.get_at((300, 300))[:3] == (0, 0, 0)


def test_painting_a_ring_at_no_point_draws_nothing(world_ui: WorldUI, camera: Camera) -> None:
    """The painter guards the same condition the callers do.

    Reached by calling it directly with the lifetime set but the point cleared,
    which is the state a caller can reach by handling the two fields separately.
    """
    world_ui.surface.fill((0, 0, 0))
    world_ui.panels._clash_ttl = 0.2
    world_ui.panels.paint_clash_ring(camera)
    assert world_ui.surface.get_at((300, 300))[:3] == (0, 0, 0)
