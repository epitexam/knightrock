"""The single place where a window and a picture are reconciled.

The window is whatever the platform granted and the picture is drawn at the
window's own size, so there is no scale factor left to apply: the finished frame
is blitted onto the window 1:1, pixel for pixel, every frame.

That is the whole point of this module having been reduced to a blit. It used to
compute a ratio between a fixed render target and the window and resample the
frame onto it, which cost a ``smoothscale`` per frame and could not be sharp on
any display whose size is not a whole multiple of the framing. Now there is no
second code path that could scale something differently, because there is no
scaling.

It also owns the render target, because it is the only component that knows both
sides of the reconciliation. :meth:`recompute` says whether the target changed,
which is the one fact a caller needs in order to re-point the scene stack at it.
"""

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import letterbox
from .viewport import Viewport


class Presentation:
    """Puts the picture on the window, and maps the pointer back.

    The letterbox rectangle is computed once per rebuild and used for both the
    blit and the pointer inversion. That sharing is not tidiness: if the two used
    different rectangles, a click would land on a pixel that is not where the
    player aimed, and the error would be invisible at any resolution where the
    bars are thin.
    """

    def __init__(
        self,
        stage: pygame.Surface,
        framing: Framing = DEFAULT_FRAMING,
        *,
        pixel_perfect: bool = False,
        convert: bool = False,
    ) -> None:
        self.stage = stage
        self.framing = framing
        self.pixel_perfect = pixel_perfect
        self.convert = convert
        self.rect = pygame.Rect(0, 0, 1, 1)
        self.viewport: Viewport
        self._fitted: tuple[int, int] | None = None
        self.recompute()

    def retarget(self, stage: pygame.Surface) -> bool:
        """Adopt a new window surface -- a display setting changed -- and refit.

        Separate from :meth:`recompute` because the surface is the window's and
        the window is the only thing that can replace it.
        """
        self.stage = stage
        return self.recompute()

    @property
    def surface(self) -> pygame.Surface:
        """The render target, which is also the picture."""
        return self.viewport.surface

    @property
    def density(self) -> float:
        """Target pixels per world unit, read off the target."""
        return self.viewport.density

    def recompute(self) -> bool:
        """Fit the window again, replacing the target if its size moved.

        Returns whether the target surface is new, so the caller knows if it has
        to re-point the scene stack, the camera and the interface at it. Called
        on launch, after a display setting changes, and on every window resize.
        """
        self.rect = letterbox(self.window_size, self.framing, pixel_perfect=self.pixel_perfect)
        if self.rect.size == self._fitted:
            return False
        self._fitted = self.rect.size
        self.viewport = Viewport(self.framing, self._fitted, convert=self.convert)
        return True

    @property
    def window_size(self) -> tuple[int, int]:
        """The window's granted size, read back off its surface."""
        return self.stage.get_size()

    @property
    def bars(self) -> tuple[pygame.Rect, ...]:
        """The letterbox strips, as up to four rects.

        They are painted rather than left alone because the blit only covers the
        picture: after a resize the strips still hold the previous frame's
        pixels, which is how a stretched outline of the old window ends up
        hanging off the edge of the new one.
        """
        width, height = self.window_size
        return tuple(
            bar
            for bar in (
                pygame.Rect(0, 0, self.rect.x, height),
                pygame.Rect(self.rect.right, 0, max(0, width - self.rect.right), height),
                pygame.Rect(self.rect.x, 0, self.rect.width, self.rect.y),
                pygame.Rect(
                    self.rect.x,
                    self.rect.bottom,
                    self.rect.width,
                    max(0, height - self.rect.bottom),
                ),
            )
            if bar.width > 0 and bar.height > 0
        )

    def present(self) -> None:
        """Show one finished frame. The only screen read in the whole loop."""
        for bar in self.bars:
            self.stage.fill((0, 0, 0), bar)
        # 1:1, always. No ratio, no resampling, nothing that can soften a pixel.
        self.stage.blit(self.viewport.surface, self.rect)
        pygame.display.flip()

    def pointer_to_viewport(self, position: tuple[int, int]) -> tuple[int, int]:
        """A window position in target coordinates.

        The exact inverse of the blit above, using the same rectangle, so a
        click on a menu row lands on that row's pixels. The positions that fall
        in the letterbox bars map outside the target; callers that care should
        test :meth:`pointer_in_viewport` first.
        """
        return (position[0] - self.rect.x, position[1] - self.rect.y)

    def pointer_in_viewport(self, position: tuple[int, int]) -> bool:
        """Whether a window position is over the picture rather than a bar."""
        return self.rect.collidepoint(position)
