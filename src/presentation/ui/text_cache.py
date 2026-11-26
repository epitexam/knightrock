"""One bounded, LRU cache of rendered text surfaces for every UI view.

The views used to hand-roll three caches with three eviction policies (clear-all
at 512, clear-all at 256, LRU at 256) and two different key shapes. A rendered
surface is a pure function of its key, so unifying the policy cannot change a
pixel; it just stops a fix in one cache from missing the other two.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable

import pygame


def _plain_render(
    font: pygame.font.Font, text: str, color: tuple[int, int, int], max_width: int
) -> pygame.Surface:
    del max_width
    # No antialiasing: a pixel font blurred at its edges is not one.
    return font.render(text, False, color)


def fit_prefix(
    font: pygame.font.Font,
    text: str,
    max_width: int,
    marker: str = "…",
    empty_if_no_prefix: bool = False,
) -> str:
    """The longest prefix of ``text`` that fits with ``marker`` appended.

    The marker is part of the measurement, so the result never overhangs. Both
    menu views used to run this binary search themselves; ``empty_if_no_prefix``
    keeps the grid's honest empty cell when not even the marker fits, while the
    menu keeps its marker-only fallback.
    """
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if font.size(text[:middle] + marker)[0] <= max_width:
            low = middle
        else:
            high = middle - 1
    if low == 0 and empty_if_no_prefix:
        return ""
    return f"{text[:low].rstrip()}{marker}"


class TextCache:
    """Memoise ``font.render`` output keyed by font identity and text style.

    ``max_width`` is part of the key because the grid truncates text before
    rendering; callers that do not truncate pass the default 0.
    """

    def __init__(
        self,
        capacity: int = 256,
        render: Callable[[pygame.font.Font, str, tuple[int, int, int], int], pygame.Surface]
        | None = None,
    ) -> None:
        if capacity < 0:
            raise ValueError("text cache capacity must be non-negative")
        self.capacity = capacity
        self._render = render or _plain_render
        self._entries: OrderedDict[tuple[int, str, tuple[int, int, int], int], pygame.Surface] = (
            OrderedDict()
        )
        self.hits = 0
        self.misses = 0

    def render(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        max_width: int = 0,
    ) -> pygame.Surface:
        key = (id(font), text, color, max_width)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            self.hits += 1
            return cached
        self.misses += 1
        rendered = self._render(font, text, color, max_width)
        if self.capacity:
            self._entries[key] = rendered
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
        return rendered

    def values(self) -> object:
        """The cached surfaces, for the layout tests that check reuse."""
        return self._entries.values()

    def clear(self) -> None:
        self._entries.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)
