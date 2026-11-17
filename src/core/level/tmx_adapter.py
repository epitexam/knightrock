"""The one place allowed to touch PyTMX's private gid bookkeeping.

``tiledgidmap`` and ``gidmap`` are not part of PyTMX's public API: a version
upgrade may reshape or drop them. Keeping the access behind this small adapter
means a drift breaks one typed contract instead of silently stopping mirrored
tile objects from being mirrored. Everything else PyTMX exposes (``layers``,
``width``, ``TiledTileLayer``...) is public and stays where it is.
"""

from __future__ import annotations

from typing import Any


class TmxAdapter:
    """Typed view over a loaded PyTMX map, owning its private gid structures."""

    def __init__(self, tmx_map: Any) -> None:
        self._map = tmx_map

    def flips(self, gid: int | None) -> tuple[bool, bool]:
        """The (horizontal, vertical) mirror flags of a tile object's gid."""
        if not gid:
            return False, False
        tiledgidmap = getattr(self._map, "tiledgidmap", {})
        gidmap = getattr(self._map, "gidmap", {})
        tile = tiledgidmap.get(gid)
        for internal, flags in gidmap.get(tile, ()):
            if internal == gid:
                return bool(flags.flipped_horizontally), bool(flags.flipped_vertically)
        return False, False
