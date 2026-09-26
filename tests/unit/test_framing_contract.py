"""The framing contract: no level may ever be visible all at once.

The reason ``Framing`` exists is that the visible world used to be a free
variable of a video setting, and a player could see more of a level by opening
the video menu. This is the test that says so, in a form that cannot rot.

It reads ``data/levels_manifest.json`` rather than the ``.tmx`` files because
``assets/`` is git-ignored: a test that read the real files would pass in CI
without ever having looked at a level, which is the exact failure this rework
is about. ``test_levels_manifest.py`` re-derives the manifest from the real
files whenever they are present, so the two cannot drift apart unnoticed.
"""

import json
from pathlib import Path

import pytest

from src.core.display.framing import DEFAULT_FRAMING, Framing
from src.core.paths import resource_path

MANIFEST = Path(resource_path("data/levels_manifest.json"))


def _levels() -> list[dict[str, object]]:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert document["version"] == 1, "the manifest format changed; update this test"
    levels: list[dict[str, object]] = document["levels"]
    assert levels, "the manifest lists no level, so the contract below is vacuous"
    return levels


def test_the_manifest_covers_every_level_the_game_ships() -> None:
    """A manifest that lost a level would make the contract test pass by default."""
    names = {str(level["file"]) for level in _levels()}
    assert "assets/data/levels/1.tmx" in names, "the registered level must be covered"
    assert len(names) == len(_levels()), "a level is listed twice"


@pytest.mark.parametrize("level", _levels(), ids=lambda level: str(level["file"]))
def test_the_framing_never_reveals_a_whole_level(level: dict[str, object]) -> None:
    """Smaller on *both* axes, or the level is on screen anyway."""
    world = (float(level["world"][0]), float(level["world"][1]))  # type: ignore[index]
    name = str(level["file"])
    assert DEFAULT_FRAMING.width < world[0], (
        f"{name}: the framing is {DEFAULT_FRAMING.width} wide against a level {world[0]} "
        "wide, so the whole width of it is visible at once"
    )
    assert DEFAULT_FRAMING.height < world[1], (
        f"{name}: the framing is {DEFAULT_FRAMING.height} tall against a level {world[1]} "
        "tall, so the whole height of it is visible at once"
    )
    assert DEFAULT_FRAMING.is_smaller_than(world), f"{name}: not smaller on both axes"


def test_the_contract_is_expressed_as_an_api_and_not_repeated() -> None:
    """``is_smaller_than`` is the check; this guards the check itself."""
    assert DEFAULT_FRAMING.is_smaller_than((2000.0, 1000.0))
    # Taller than the level, however much narrower: still a whole level on screen.
    assert not DEFAULT_FRAMING.is_smaller_than((2000.0, 600.0))
    assert not DEFAULT_FRAMING.is_smaller_than((1000.0, 1000.0))


def test_a_framing_needs_a_positive_size() -> None:
    with pytest.raises(ValueError):
        Framing(0.0, 648.0)
    with pytest.raises(ValueError):
        Framing(1152.0, -1.0)


def test_the_viewport_is_the_framing_times_an_integer_scale() -> None:
    framing = DEFAULT_FRAMING
    assert framing.viewport_size(1) == (1152, 648)
    assert framing.viewport_size(2) == (2304, 1296)
    assert framing.viewport_size(3) == (3456, 1944)
    with pytest.raises(ValueError):
        framing.viewport_size(0)
