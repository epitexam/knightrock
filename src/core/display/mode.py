"""How the game occupies the screen.

Kept free of ``pygame`` on purpose: ``settings_store`` persists this value, and
it must stay importable without a display being initialized.
"""

from enum import StrEnum


class DisplayMode(StrEnum):
    """The ways the game can take the screen.

    ``BORDERLESS`` is the safest concrete mode because it changes nothing on the
    player's system: a window at the desktop's own resolution, so there is no
    mode change to fail, no refresh-rate change, and nothing to redo when a
    hybrid-GPU laptop switches the display over to its integrated chip
    mid-session. ``FULLSCREEN`` asks the driver for a real mode, which is what
    makes it able to blank the screen on setups that cannot service the request.

    ``AUTO`` is not a fourth way to fill the screen; it is the absence of a
    decision, re-evaluated on every launch. It resolves to borderless when the
    desktop already has the shape of the framing, so the letterbox collapses to
    nothing, and to a window otherwise -- where the player can *see* the bars
    and the desktop around them, which reads as deliberate rather than broken.
    """

    AUTO = "auto"
    BORDERLESS = "borderless"
    WINDOW = "window"
    FULLSCREEN = "fullscreen"

    @property
    def is_concrete(self) -> bool:
        """Whether this names a mode rather than deferring to the machine."""
        return self is not DisplayMode.AUTO
