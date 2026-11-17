"""One owner for the caches whose surfaces depend on the display format.

A resize changes the pixel format every cached surface was converted against.
Clearing only the asset library used to leave the FX frames, the level's
converted tiles and the renderer's sheared surfaces stale. This coordinator is
the single method that invalidates all of them together; adding a new derived
cache means adding one line here, not finding a new call site in ``Game``.
"""

from __future__ import annotations

from collections.abc import Callable

#: Each cache exposes its own invalidation verb; the coordinator only needs a
#: no-argument callable, so neither LevelManager nor the fx module has to change.
Invalidate = Callable[[], None]


class ResourceCoordinator:
    """Invalidates every display-format-derived cache in one place."""

    def __init__(
        self,
        assets: Invalidate,
        levels: Invalidate,
        fx: Invalidate | None = None,
        renderer: Invalidate | None = None,
    ) -> None:
        self._assets = assets
        self._levels = levels
        self._fx = fx
        self._renderer = renderer

    def invalidate_display_format(self) -> None:
        """Drop every surface derived from the old display format."""
        self._assets()
        self._levels()
        if self._fx is not None:
            self._fx()
        if self._renderer is not None:
            self._renderer()
