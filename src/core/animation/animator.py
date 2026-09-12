"""Per-state frame animation driven by :class:`AssetLibrary` (Phase 2 #1).

The shipped art lives under ``assets/graphics/`` as directories of numbered
PNG frames (``idle/0.png``, ``idle/1.png``, ...).  The :class:`Animator`
turns such a directory into a looping or one-shot animation, flips frames
for left-facing sprites, and resizes them to the entity's sprite rect so
the physics rect stays authoritative (audit F2.2: hitbox owns geometry).
"""

from collections.abc import Mapping
from dataclasses import dataclass

import pygame

from src.core.asset_library import AssetLibrary


@dataclass(frozen=True)
class AnimationSpec:
    """Definition of one named animation.

    Parameters
    ----------
    name : str
        Animation key used by :meth:`Animator.play` (usually a state name).
    directory : str
        Asset directory of numbered PNG frames, relative to the project
        root, e.g. ``"assets/graphics/player/idle"``.
    frame_duration : float
        Seconds each frame is displayed.
    loop : bool
        Restart from frame 0 after the last frame (False: hold last frame).
    """

    name: str
    directory: str
    frame_duration: float = 0.1
    loop: bool = True


class Animator:
    """Frame sequencer serving display-ready surfaces for one entity.

    The animator owns *which* frame is shown; the entity owns *when* it is
    blitted (the renderer still blits ``sprite.image`` at ``sprite.rect``).
    Display surfaces (scaled to the sprite rect and mirrored per facing)
    are cached, so the expensive ``smoothscale`` runs once per
    (animation, frame, facing, size) combination.
    """

    def __init__(
        self,
        library: AssetLibrary,
        specs: Mapping[str, AnimationSpec],
        default: str = "",
    ) -> None:
        """Create the animator.

        Parameters
        ----------
        library : AssetLibrary
            Shared loader providing converted frame surfaces.
        specs : Mapping[str, AnimationSpec]
            Available animations, keyed by name.
        default : str
            Animation started at construction; defaults to the first spec.
        """
        if not specs:
            raise ValueError("Animator requires at least one AnimationSpec")
        self._library = library
        self._specs: dict[str, AnimationSpec] = dict(specs)
        self._default = default if default in self._specs else next(iter(self._specs))
        self._current = self._default
        self._timer = 0.0
        self._frame = 0
        self._finished = False
        self._display_cache: dict[tuple[str, int, bool, tuple[int, int]], pygame.Surface] = {}

    @property
    def current(self) -> str:
        """Name of the animation currently playing."""
        return self._current

    @property
    def frame_index(self) -> int:
        """Index of the frame currently displayed."""
        return self._frame

    @property
    def finished(self) -> bool:
        """True once a non-looping animation reached its last frame."""
        return self._finished

    def play(self, name: str) -> bool:
        """Switch to ``name``; return True when the animation changed.

        Switching restarts the new animation at frame 0.  Requesting an
        unknown name or the already-current animation is a no-op so callers
        can simply pass the state-derived name every tick.
        """
        if name not in self._specs or name == self._current:
            return False
        self._current = name
        self._timer = 0.0
        self._frame = 0
        self._finished = False
        return True

    def update(self, delta_time: float) -> None:
        """Advance the frame clock by ``delta_time`` seconds."""
        spec = self._specs[self._current]
        self._timer += delta_time
        while self._timer >= spec.frame_duration:
            self._timer -= spec.frame_duration
            last = len(self._library.frames(spec.directory)) - 1
            if self._frame < last:
                self._frame += 1
            elif spec.loop:
                self._frame = 0
            else:
                self._frame = last
                self._finished = True
                self._timer = 0.0
                return

    def surface(self, size: tuple[int, int], facing_right: bool) -> pygame.Surface | None:
        """Return the current frame ready for blitting, or None for 0 size.

        The frame is scaled to ``size`` (the sprite rect) and mirrored when
        ``facing_right`` is False.  Results are cached per
        (animation, frame, facing, size).
        """
        if size[0] <= 0 or size[1] <= 0:
            return None
        spec = self._specs[self._current]
        key = (spec.name, self._frame, facing_right, size)
        cached = self._display_cache.get(key)
        if cached is not None:
            return cached

        frames = self._library.frames(spec.directory)
        scaled = pygame.transform.smoothscale(frames[self._frame], size)
        if not facing_right:
            scaled = pygame.transform.flip(scaled, True, False)
        self._display_cache[key] = scaled
        return scaled
