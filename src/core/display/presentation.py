"""The single place where a window and a picture are reconciled.

The picture is drawn at the window's own size, so the finished frame is blitted
1:1 every frame: no ratio, no resampling, nothing that can soften a pixel. It
also owns the render target, and :meth:`Presentation.recompute` says when the
target is new so the caller can re-point the scene stack at it.
"""

import logging

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import FitPolicy, Picture, picture
from .monitors import MIN_WINDOW
from .viewport import Viewport

logger = logging.getLogger(__name__)

#: The letterbox strips: the darkest shade of the menus' background, so a
#: wide screen reads as a frame around the picture rather than a broken one.
BAR_COLOR = (10, 11, 15)


class Presentation:
    """Puts the picture on the window, and maps the pointer back.

    The blit and the pointer inversion share one placement, so a click lands
    on the pixel the player aimed at.
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
        """The older name for ``fit is FitPolicy.INTEGER``."""
        return self.fit is FitPolicy.INTEGER

    @pixel_perfect.setter
    def pixel_perfect(self, value: bool) -> None:
        self.fit = FitPolicy.INTEGER if value else FitPolicy.BARS

    def retarget(self, stage: pygame.Surface) -> bool:
        """Adopt a new window surface and refit."""
        self.stage = stage
        # A new surface has no strips painted on it, even at the same size.
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
        """Fit the window again; return whether the target surface is new.

        A window under :data:`~src.core.display.monitors.MIN_WINDOW` is refused
        and the last target kept: below it the interface scale is one
        :func:`~src.ui.scale.checked_ui_scale` rejects, so a window dragged that
        small is clipped for the drag rather than crashing. The first fit has
        nothing to keep and fits anyway.
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
        # Placed on every call: the picture can move without changing size.
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

        Painted, because after a resize they still hold the old frame's pixels.
        """
        return self.picture.bars

    def present(self) -> None:
        """Show one finished frame.

        The strips are painted only when they moved (on an ultrawide window
        they were 0.7 ms a frame of black over black). That relies on the
        window surface keeping its pixels between flips, which holds for the
        stage's ``RESIZABLE`` window with or without vsync; an ``OPENGL``
        window would need them painted every frame.
        """
        if self._painted != self.rect:
            for bar in self.picture.bars:
                self.stage.fill(BAR_COLOR, bar)
            # A copy, so a later change to ``rect`` cannot move it.
            self._painted = pygame.Rect(self.rect)
        # 1:1. Under zoom the crop is the *area* and the placement the *dest*
        # (``blit(source, dest, area)``); both are the same size.
        self.stage.blit(self.viewport.surface, self.picture.dest, self.picture.source)
        pygame.display.flip()

    def pointer_to_viewport(self, position: tuple[int, int]) -> tuple[int, int]:
        """A window position in target coordinates: the exact inverse of the blit.

        A position in a bar maps outside the target; see
        :meth:`pointer_in_viewport`. Under zoom the crop's origin counts too.
        """
        return (
            position[0] + self.picture.source.x - self.picture.dest.x,
            position[1] + self.picture.source.y - self.picture.dest.y,
        )

    def pointer_in_viewport(self, position: tuple[int, int]) -> bool:
        """Whether a window position is over the picture rather than a bar."""
        return self.rect.collidepoint(position)
