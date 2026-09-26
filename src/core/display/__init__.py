"""The display subsystem: framing, letterbox, window and presentation.

Four objects with four jobs, kept apart on purpose:

``Framing``
    How much of the world is visible. Fixed, in world units. The only display
    quantity the simulation may read.
``Viewport``
    The surface everything is drawn into, at the window's own size.
``Stage``
    The OS window. Mode, position, DPI, vsync. It has no opinion about size.
``Presentation``
    Window and target, and the pointer back. The only place that reconciles
    them, and it does not scale: the picture is blitted 1:1.
"""

from .detection import (
    auto_display_mode,
    desktop_refresh_rates,
    desktop_size,
    desktop_sizes,
    initial_window_size,
)
from .framing import DEFAULT_FRAMING, Framing
from .letterbox import density_for, fits_whole_pixel, letterbox
from .mode import DisplayMode
from .presentation import Presentation
from .stage import Stage, WindowSpec
from .viewport import Viewport

__all__ = [
    "DEFAULT_FRAMING",
    "DisplayMode",
    "Framing",
    "Presentation",
    "Stage",
    "Viewport",
    "WindowSpec",
    "auto_display_mode",
    "desktop_refresh_rates",
    "desktop_size",
    "desktop_sizes",
    "density_for",
    "fits_whole_pixel",
    "initial_window_size",
    "letterbox",
]
