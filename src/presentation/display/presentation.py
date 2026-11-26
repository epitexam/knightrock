"""The single place where a window and a picture are reconciled.

The picture is drawn at the window's own size, so the finished frame is blitted
1:1 every frame: no ratio, no resampling, nothing that can soften a pixel. It
also owns the render target, and :meth:`Presentation.recompute` says when the
target is new so the caller can re-point the scene stack at it.
"""

import logging

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import FitPolicy, Picture, density_for, picture
from .monitors import MIN_WINDOW
from .viewport import Viewport

logger = logging.getLogger(__name__)

#: The letterbox strips: the darkest shade of the menus' background, so a
#: wide screen reads as a frame around the picture rather than a broken one.
BAR_COLOR = (10, 11, 15)

#: The density at which the smallest offered UI preference still reaches
#: ``ui.MIN_UI_SCALE``: 0.25 / 0.8. Kept here because ``core/display`` must not
#: import the interface layer; :mod:`tests.unit.test_presentation` pins the two
#: halves together so this number cannot drift from the ladders.
MIN_DENSITY_FOR_UI = 0.3125


def render_scale_is_usable(
    window: tuple[int, int], scale: float, framing: Framing = DEFAULT_FRAMING
) -> bool:
    """Whether a scale leaves the internal target dense enough for the UI.

    The window floor alone is not enough once the picture is shrunk: at
    640x480 with a 0.5 scale the target is 320x240, and the smallest UI
    preference produces a scale ``checked_ui_scale`` refuses. The game would
    die on the first view it builds.
    """
    virtual = (max(1, round(window[0] * scale)), max(1, round(window[1] * scale)))
    return density_for(picture(virtual, framing).target.size, framing) >= MIN_DENSITY_FOR_UI


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
        render_scale: float = 1.0,
    ) -> None:
        self.stage = stage
        self.framing = framing
        self.fit = fit
        self.convert = convert
        wanted = max(0.1, min(1.0, float(render_scale)))
        if not render_scale_is_usable(stage.get_size(), wanted, framing):
            # A saved scale from a larger window must not take the game down on
            # boot. The caller reads our effective scale back and corrects the
            # settings file, so the two cannot disagree after this clamp.
            logger.warning("Render scale %s is too small for this window; using 1.0", wanted)
            wanted = 1.0
        self.render_scale = wanted
        self._frame: pygame.Surface | None = None
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

    def can_use_render_scale(
        self, scale: float, window_size: tuple[int, int] | None = None
    ) -> bool:
        """Whether ``scale`` leaves a target the interface can be laid out in."""
        return render_scale_is_usable(window_size or self.window_size, scale, self.framing)

    def set_render_scale(self, scale: float) -> bool:
        """Adopt a new internal resolution; return whether the target changed."""
        wanted = max(0.1, min(1.0, float(scale)))
        if wanted == self.render_scale:
            return False
        # Keep the minimum-window rule: a scale change is not a reason to fit
        # a window in which the interface cannot be laid out.
        if self._fitted is not None and (
            self._is_too_small() or not self.can_use_render_scale(wanted)
        ):
            return False
        self.render_scale = wanted
        # Force a new target even when rounding gives the same virtual size:
        # the frame buffer itself changes with the scale, and the caller must
        # re-point the scene stack at it.
        return self.recompute(force=True)

    @property
    def surface(self) -> pygame.Surface:
        """The render target, which is also the picture."""
        return self.viewport.surface

    @property
    def density(self) -> float:
        """Target pixels per world unit, read off the target."""
        return self.viewport.density

    def recompute(self, *, force: bool = False) -> bool:
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
        window_w, window_h = self.window_size
        virtual = (
            max(1, round(window_w * self.render_scale)),
            max(1, round(window_h * self.render_scale)),
        )
        self._virtual_size = virtual
        self.picture = picture(virtual, self.framing, self.fit)
        self.rect = self.picture.dest
        if self.render_scale < 1.0:
            if self._frame is None or self._frame.get_size() != virtual:
                self._frame = pygame.Surface(virtual)
            self._painted = None
        else:
            self._frame = None
        # Placed on every call: the picture can move without changing size.
        if self.picture.target.size == self._fitted and not force:
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

    def _pointer_scale(self) -> tuple[float, float]:
        """The upscale from internal pixels to window pixels, per axis.

        Read off the actual sizes rather than the preference: a window size that
        does not divide evenly by the scale is rounded to whole internal pixels,
        so the true ratio can differ slightly from ``render_scale``. Clicks use
        the true one.
        """
        window = self.window_size
        virtual = self.picture.window
        return (
            window[0] / virtual[0] if window[0] > 0 and virtual[0] > 0 else 1.0,
            window[1] / virtual[1] if window[1] > 0 and virtual[1] > 0 else 1.0,
        )

    @property
    def window_rect(self) -> pygame.Rect:
        """The picture's rectangle in window coordinates, bars around it."""
        x_scale, y_scale = self._pointer_scale()
        rect = self.rect
        return pygame.Rect(
            round(rect.x * x_scale),
            round(rect.y * y_scale),
            round(rect.width * x_scale),
            round(rect.height * y_scale),
        )

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
        canvas = self._frame if self._frame is not None else self.stage
        if self._painted != self.rect:
            for bar in self.picture.bars:
                canvas.fill(BAR_COLOR, bar)
            # A copy, so a later change to ``rect`` cannot move it.
            self._painted = pygame.Rect(self.rect)
        # 1:1. Under zoom the crop is the *area* and the placement the *dest*
        # (``blit(source, dest, area)``); both are the same size.
        canvas.blit(self.viewport.surface, self.picture.dest, self.picture.source)
        if self._frame is not None:
            # Straight into the window: an intermediate full-size surface would
            # cost another whole-window copy on top of the scale itself.
            pygame.transform.scale(self._frame, self.stage.get_size(), self.stage)
        pygame.display.flip()

    def pointer_to_viewport(self, position: tuple[int, int]) -> tuple[int, int]:
        """A window position in target coordinates: the exact inverse of the blit.

        A position in a bar maps outside the target; see
        :meth:`pointer_in_viewport`. Under zoom the crop's origin counts too.
        """
        x_scale, y_scale = self._pointer_scale()
        x = position[0] / x_scale + self.picture.source.x - self.picture.dest.x
        y = position[1] / y_scale + self.picture.source.y - self.picture.dest.y
        return int(x), int(y)

    def viewport_to_window(self, position: tuple[int, int]) -> tuple[int, int]:
        """A render-target position in window coordinates: the inverse of :meth:`pointer_to_viewport`."""
        x_scale, y_scale = self._pointer_scale()
        return (
            round((position[0] - self.picture.source.x + self.picture.dest.x) * x_scale),
            round((position[1] - self.picture.source.y + self.picture.dest.y) * y_scale),
        )

    def pointer_in_viewport(self, position: tuple[int, int]) -> bool:
        """Whether a window position is over the picture rather than a bar."""
        return self.window_rect.collidepoint(position)
