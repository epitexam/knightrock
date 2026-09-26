"""How the game occupies the screen.

Kept free of ``pygame`` on purpose: ``settings_store`` persists this value, and
it must stay importable without a display being initialized.
"""

from enum import StrEnum


class DisplayMode(StrEnum):
    """The three ways the game can take the screen.

    ``BORDERLESS`` is the default because it is the only one that changes
    nothing on the player's system: it is a plain window at the desktop's own
    resolution, so there is no mode change to fail, no refresh-rate change, and
    nothing to redo when a hybrid-GPU laptop switches the display over to its
    integrated chip mid-session. ``FULLSCREEN`` asks the display driver for a
    real mode, which is what makes it able to blank the screen on setups that
    cannot service the request.
    """

    BORDERLESS = "borderless"
    WINDOW = "window"
    FULLSCREEN = "fullscreen"
