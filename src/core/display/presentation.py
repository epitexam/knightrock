"""The single place where anything is scaled.

The viewport is a fixed size and the window is not, so exactly one component
has to reconcile the two. Keeping that in one file is what makes the guarantee
checkable: there is no second code path that could scale something differently.
"""

import pygame

from .stage import Stage
from .viewport import Viewport


class Presentation:
    """Puts the viewport on the window, and maps the pointer back.

    The letterbox rectangle is computed once per rebuild and reused for both
    the blit and the pointer inversion. That sharing is not tidiness: if the
    two used different rectangles, a click would land on a pixel that is not
    where the player aimed, and the error would be invisible at any resolution
    where the bars are thin.
    """

    def __init__(
        self,
        stage: Stage,
        viewport: Viewport,
        smoothing: bool = True,
    ) -> None:
        self.stage = stage
        self.viewport = viewport
        self.smoothing = smoothing
        self.scale = 1.0
        self.rect = pygame.Rect(0, 0, stage.size[0], stage.size[1])
        self._destination = pygame.Surface(self.viewport.size)
        self.recompute()

    def recompute(self) -> None:
        """Recompute the letterbox rectangle after a window or viewport change."""
        window = self.stage.size
        viewport = self.viewport.size
        if window[0] <= 0 or window[1] <= 0:
            self.scale = 1.0
            self.rect = pygame.Rect(0, 0, max(1, window[0]), max(1, window[1]))
            self._destination = pygame.Surface((1, 1))
            return

        if window == viewport:
            # No bars, nothing to scale. Worth its own branch: smoothscale
            # measures 2.19ms at 1:1, so scaling when there is no ratio to
            # apply is 2.19ms of nothing, every frame.
            self.scale = 1.0
            self.rect = pygame.Rect((0, 0), window)
            self._destination = pygame.Surface(viewport)
            return

        self.scale = min(window[0] / viewport[0], window[1] / viewport[1])
        width = max(1, round(viewport[0] * self.scale))
        height = max(1, round(viewport[1] * self.scale))
        self.rect = pygame.Rect(
            (window[0] - width) // 2,
            (window[1] - height) // 2,
            width,
            height,
        )
        self._destination = pygame.Surface((width, height))

    @property
    def bars(self) -> tuple[pygame.Rect, ...]:
        """The letterbox strips, as up to four rects.

        They are painted rather than left alone because the blit only covers the
        viewport: after a resize the strips still hold the previous frame's
        pixels, which is how a stretched outline of the old window ends up
        hanging off the edge of the new one.
        """
        window = self.stage.size
        left = pygame.Rect(0, 0, self.rect.x, window[1])
        right = pygame.Rect(self.rect.right, 0, max(0, window[0] - self.rect.right), window[1])
        top = pygame.Rect(self.rect.x, 0, self.rect.width, self.rect.y)
        bottom = pygame.Rect(
            self.rect.x, self.rect.bottom, self.rect.width, max(0, window[1] - self.rect.bottom)
        )
        return tuple(bar for bar in (left, right, top, bottom) if bar.width > 0 and bar.height > 0)

    def present(self) -> None:
        """Show one finished frame. The only screen read in the whole loop."""
        window = self.stage.surface
        for bar in self.bars:
            window.fill((0, 0, 0), bar)
        if self.scale == 1.0:
            window.blit(self.viewport.surface, self.rect)
        else:
            self._rescale()
            window.blit(self._destination, self.rect)
        pygame.display.flip()

    def _rescale(self) -> None:
        target = (self.rect.width, self.rect.height)
        if self._destination.get_size() != target:
            self._destination = pygame.Surface(target)
        if self.smoothing:
            pygame.transform.smoothscale(self.viewport.surface, target, self._destination)
        else:
            pygame.transform.scale(self.viewport.surface, target, self._destination)

    def pointer_to_viewport(self, position: tuple[int, int]) -> tuple[float, float]:
        """A window position in viewport coordinates.

        The exact inverse of the blit above, using the same rectangle, so a
        click on a menu row lands on that row's pixels. The positions that
        fall in the letterbox bars map outside the viewport; callers that care
        should test ``pointer_in_viewport`` first.
        """
        return (
            (position[0] - self.rect.x) / self.scale,
            (position[1] - self.rect.y) / self.scale,
        )

    def pointer_in_viewport(self, position: tuple[int, int]) -> bool:
        """Whether a window position is over the image rather than a bar."""
        return self.rect.collidepoint(position)
