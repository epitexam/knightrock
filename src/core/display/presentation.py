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
        #: The letterbox strips, fitted alongside ``rect``. Computed here rather
        #: than per frame because ``present`` needs them every frame and they
        #: only move when the window does.
        self._bars: tuple[pygame.Rect, ...] = ()
        #: The ``rect`` the strips were last painted for, or ``None`` while the
        #: window holds pixels nobody has accounted for. See :meth:`present`.
        self._painted: pygame.Rect | None = None
        self.recompute()

    def retarget(self, stage: pygame.Surface) -> bool:
        """Adopt a new window surface -- a display setting changed -- and refit.

        Separate from :meth:`recompute` because the surface is the window's and
        the window is the only thing that can replace it.
        """
        self.stage = stage
        # A new surface has nothing painted on it, whatever size it turns out
        # to be -- and ``recompute`` below may well decide the fitted rectangle
        # has not moved, which would otherwise leave this looking painted.
        self._painted = None
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
        # Refitted on every call, before the early return below: the strips are a
        # function of where ``rect`` *sits*, and a window can change shape in a
        # way that moves it without changing its size (a 16:9 window made taller
        # keeps its fitted width and gains a strip above and below). Keying this
        # on size, as the target below is, would miss exactly that.
        self._bars = self._fit_bars()
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

        Fitted in :meth:`recompute` rather than worked out here, because
        :meth:`present` reads them every frame and they only change when the
        window does.
        """
        return self._bars

    def _fit_bars(self) -> tuple[pygame.Rect, ...]:
        """The window, less the rectangle the picture occupies."""
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
        """Show one finished frame. The only screen read in the whole loop.

        The strips are painted only when they have moved. They were painted on
        every frame, which is a second full pass over them for nothing: this is
        the only place anything writes to the window surface, so outside the
        picture the window holds whatever was last put there, and that is black
        from the first frame onward. On a 3440x1440 window the strips are 1.27
        million pixels and the pass costs 0.69 ms a frame, 38 % of the present
        and 4 % of the frame budget, to write black over black. A 16:9 window
        has no strips at all, so this only ever pays off on a window of another
        shape -- and there it is the largest single cost of presenting a frame.

        What it rests on is that a painted window pixel stays painted until
        something writes over it. :meth:`present` paints the strips and then
        blits the picture over the same surface before a single flip, so the
        picture already depends on this: if ``flip`` handed back a different
        buffer than the one just drawn into, the frame itself would not survive
        its own present. The strips are simply the part of that assumption that
        is not rewritten every frame.

        That holds while the window is a software surface, which is all this
        game can ask for -- :meth:`Stage._flags` requests ``FULLSCREEN`` or
        ``RESIZABLE`` and never ``OPENGL``, so ``flip`` is an update rather than
        a buffer exchange. An accelerated path would have to paint every frame
        again, because each buffer would then arrive holding the other's
        contents.
        """
        if self._painted != self.rect:
            for bar in self._bars:
                self.stage.fill((0, 0, 0), bar)
            # A copy, not the rect itself: the window being resized must not be
            # able to move the one this comparison is made against.
            self._painted = pygame.Rect(self.rect)
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
