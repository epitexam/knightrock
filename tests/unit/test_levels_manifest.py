"""The manifest must describe the levels that actually exist.

``test_framing_contract.py`` trusts ``data/levels_manifest.json`` because
``assets/`` is git-ignored and CI never sees the real ``.tmx`` files. That trust
is only sound while the manifest is true, so this test re-derives it from the
files and fails on any drift. It is skipped when the assets are absent, which
is the CI case and the only case where the manifest has nothing to be checked
against.
"""

import json
import re
from pathlib import Path

import pytest

from src.core.paths import PROJECT_ROOT, resource_path

MANIFEST = Path(resource_path("data/levels_manifest.json"))
LEVELS_DIR = PROJECT_ROOT / "assets" / "data"

#: The map header is the first line of a TMX file; reading it with a pattern
#: keeps this test independent of pytmx, of the display, and of anything the
#: loader might one day do differently.
_MAP_ATTRIBUTES = {
    "width": re.compile(r'\bwidth="(\d+)"'),
    "height": re.compile(r'\bheight="(\d+)"'),
    "tilewidth": re.compile(r'\btilewidth="(\d+)"'),
    "tileheight": re.compile(r'\btileheight="(\d+)"'),
}

pytestmark = pytest.mark.skipif(
    not LEVELS_DIR.is_dir(),
    reason="assets/ is git-ignored and absent in CI; the manifest is checked there by "
    "test_framing_contract.py instead",
)


def _tmx_files() -> list[Path]:
    files = sorted(LEVELS_DIR.glob("levels/*.tmx")) + sorted(LEVELS_DIR.glob("overworld/*.tmx"))
    assert files, f"no .tmx found under {LEVELS_DIR}; the assets are not where we expect"
    return files


def _read_manifest() -> dict[str, tuple[int, int]]:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {str(level["file"]): tuple(level["world"]) for level in document["levels"]}  # type: ignore[misc]


def test_every_level_on_disk_is_in_the_manifest() -> None:
    """A level added without a manifest entry is a level nothing checks."""
    manifest = _read_manifest()
    on_disk = {str(path.relative_to(PROJECT_ROOT)) for path in _tmx_files()}
    assert on_disk == set(manifest), (
        f"the manifest and the level folder disagree: "
        f"only on disk {sorted(on_disk - set(manifest))}, only in the manifest "
        f"{sorted(set(manifest) - on_disk)}"
    )


@pytest.mark.parametrize("path", _tmx_files(), ids=lambda p: p.name)
def test_the_recorded_size_is_the_real_one(path: Path) -> None:
    header = path.read_text(encoding="utf-8")[:512]
    values = {
        name: int(pattern.search(header).group(1)) for name, pattern in _MAP_ATTRIBUTES.items()
    }  # type: ignore[union-attr]
    recorded = _read_manifest()[str(path.relative_to(PROJECT_ROOT))]
    assert recorded == (
        values["width"] * values["tilewidth"],
        values["height"] * values["tileheight"],
    ), (
        f"{path.name} is {values['width']}x{values['height']} tiles of "
        f"{values['tilewidth']}x{values['tileheight']}, so its world size is not the one "
        "the manifest records; update data/levels_manifest.json"
    )
