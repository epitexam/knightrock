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

import logging

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import FitPolicy, Picture, picture
from .monitors import MIN_WINDOW
from .viewport import Viewport

logger = logging.getLogger(__name__)


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
        fit: FitPolicy = FitPolicy.BARS,
        convert: bool = False,
    ) -> None:
        self.stage = stage
        self.framing = framing
        self.fit = fit
        self.convert = convert
        self.rect = pygame.Rect(0, 0, 1, 1)
        self.viewport: Viewport
        #: The whole placement -- target, source and destination -- rather than
        #: a rect, because zoom's destination is the window and its source is a
        #: crop of a target larger than the window.
        self.picture: Picture
        self._fitted: tuple[int, int] | None = None
        #: The ``dest`` the strips were last painted for, or ``None`` while the
        #: window holds pixels nobody has accounted for. See :meth:`present`.
        self._painted: pygame.Rect | None = None
        self.recompute()

    @property
    def pixel_perfect(self) -> bool:
        """Whether the picture is snapped to whole pixels.

        Kept as the older name for ``fit is FitPolicy.INTEGER``. Both the settings
        menu and the persistence tests speak in whole-pixel art, and zoom is not
        an integer policy, so this cannot simply be aliased to ``fit``.
        """
        return self.fit is FitPolicy.INTEGER

    @pixel_perfect.setter
    def pixel_perfect(self, value: bool) -> None:
        self.fit = FitPolicy.INTEGER if value else FitPolicy.BARS

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
        on launch, after a display setting changes, and on every frame the window
        is found to have changed size.

        **A window too small to draw in is refused, not fitted.** The interface
        has a floor of its own -- a scale below which its text stops being text --
        and a window narrower than
        :data:`~src.core.display.monitors.MIN_WINDOW` puts the density under it:
        measured, a 240x180 window asks the interface to draw at 0.21, which
        :func:`~src.ui.scale.checked_ui_scale` refuses, and that refusal is an
        exception rather than a smaller font. The last target that was drawable
        is kept instead, so a window dragged below the floor is clipped for the
        duration of the drag rather than taking the game down with it.

        "Last target that was drawable" rather than "no target": the *first* fit
        has nothing to keep, so a runtime that opens on a window this small --
        a headless caller, a platform that refused the minimum outright -- still
        gets a surface it can draw on. That is what a degenerate window has always
        meant here, and it is not the case this is refusing.

        The floor is the same number the stage asks the platform for, and the two
        are pinned together by a test: a platform that refuses the request is a
        platform that will hand us a window under it, which is what this is for.
        """
        if self._fitted is not None and self._is_too_small():
            logger.debug(
                "A %sx%s window is below the %s floor; keeping the current target",
                *self.window_size,
                MIN_WINDOW,
            )
            return False
        self.picture = picture(self.window_size, self.framing, self.fit)
        self.rect = self.picture.dest
        # Refitted on every call, before the early return below: the strips are a
        # function of where the picture *sits*, and a window can change shape in
        # a way that moves it without changing its size (a 16:9 window made
        # taller keeps its fitted width and gains a strip above and below).
        # Keying this on size, as the target below is, would miss exactly that.
        if self.picture.target.size == self._fitted:
            return False
        self._fitted = self.picture.target.size
        self.viewport = Viewport(self.framing, self._fitted, convert=self.convert)
        return True

    def _is_too_small(self) -> bool:
        """Whether the window is under the size the interface can be laid out in."""
        width, height = self.window_size
        return width < MIN_WINDOW[0] or height < MIN_WINDOW[1]

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

        Fitted alongside ``picture`` rather than worked out here, because
        :meth:`present` reads them every frame and they only change when the
        window does.
        """
        return self.picture.bars

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
            for bar in self.picture.bars:
                self.stage.fill((0, 0, 0), bar)
            # A copy, not the rect itself: the window being resized must not be
            # able to move the one this comparison is made against.
            self._painted = pygame.Rect(self.rect)
        # 1:1, always. No ratio, no resampling, nothing that can soften a pixel.
        # Under zoom the source is a crop and the destination is the window; the
        # two rects are the same size, so this is still one pixel per pixel.
        # Argument order matters: pygame's signature is ``blit(source, dest,
        # area)``, so the crop is the *area* and the placement is the *dest*.
        # Swapped, it reads as a destination covering a region the source does
        # not have -- an area of (0, 0, 800, 450) on a 800x450 source clips the
        # blit to nothing past the picture's own height and leaves the window
        # half-painted.
        self.stage.blit(self.viewport.surface, self.picture.dest, self.picture.source)
        pygame.display.flip()

    def pointer_to_viewport(self, position: tuple[int, int]) -> tuple[int, int]:
        """A window position in target coordinates.

        The exact inverse of the blit above, using the same rectangles, so a
        click on a menu row lands on that row's pixels. A position that falls in a
        letterbox bar maps outside the target; callers that care should test
        :meth:`pointer_in_viewport` first.

        Under zoom the window shows a crop of a larger target, so this is not
        simply "minus the picture's offset" -- the offset is the crop's own
        origin, which is why it reads ``source`` and not ``target``.
        """
        return (
            position[0] + self.picture.source.x - self.picture.dest.x,
            position[1] + self.picture.source.y - self.picture.dest.y,
        )

    def pointer_in_viewport(self, position: tuple[int, int]) -> bool:
        """Whether a window position is over the picture rather than a bar."""
        return self.rect.collidepoint(position)
