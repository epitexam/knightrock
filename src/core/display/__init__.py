"""The display subsystem: framing, viewport, window and presentation.

Four objects with four jobs, kept apart on purpose:

``Framing``
    How much of the world is visible. Fixed, in world units. The only display
    quantity the simulation may read.
``Viewport``
    The fixed-size surface everything is drawn into.
``Stage``
    The OS window. Mode, size, position, DPI, vsync.
``Presentation``
    Viewport onto window, and the pointer back. The only place that scales.
"""

from .detection import (
    auto_display_mode,
    auto_settings,
    centered_on_primary,
    desktop_refresh_rates,
    desktop_size,
    desktop_sizes,
    fits_on_desktop,
    largest_window_size,
    window_size_choices,
)
from .framing import DEFAULT_FRAMING, Framing
from .mode import DisplayMode
from .presentation import Presentation
from .stage import Stage, WindowSpec
from .viewport import DEFAULT_RENDER_SCALE, RENDER_SCALES, Viewport

__all__ = [
    "DEFAULT_FRAMING",
    "DEFAULT_RENDER_SCALE",
    "RENDER_SCALES",
    "DisplayMode",
    "Framing",
    "Presentation",
    "Stage",
    "Viewport",
    "WindowSpec",
    "auto_display_mode",
    "auto_settings",
    "centered_on_primary",
    "desktop_refresh_rates",
    "desktop_size",
    "desktop_sizes",
    "fits_on_desktop",
    "largest_window_size",
    "window_size_choices",
]
