"""The lists a settings screen opens: what they list, and what they say about it.

Each function here answers one question -- *what are the choices for this
setting, and what does each one mean?* -- and hands back a list of
:class:`~src.application.scenes.option_screen.Option`. Keeping them apart from
both the screen and the picker is what lets the same option list be drawn, tested
and reasoned about without a display attached, and it is why adding a setting is
one function rather than a screen.

Every entry carries a consequence, not a name. "Zoom" on its own is a word; "Zoom
-- fills the window, cropping the edges" tells a player what will happen before
it happens, which is the difference between picking on purpose and picking
whatever came first.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.scenes.option_screen import Option
from src.application.settings_store import FRAME_LIMITS, PANEL_SCALES, UI_SCALES
from src.core.display.letterbox import FitPolicy, fits_whole_pixel
from src.core.display.mode import DisplayMode
from src.core.display.monitors import (
    Monitor,
    Resolution,
    ResolutionReason,
    Topology,
    opening_size,
)

#: Why the borderless mode is the one most players should be on. Said here rather
#: than in a comment, because a player deciding between three modes is exactly the
#: reader who needs it.
_BORDERLESS_NOTE = "covers the whole screen, no mode change, nothing to restore"
_WINDOW_NOTE = "a normal window; drag it, and its size is remembered"
_FULLSCREEN_NOTE = "a true fullscreen mode; the resolution below is honoured"

_FIT_NOTES: dict[FitPolicy, str] = {
    FitPolicy.BARS: "shows the whole picture; black bars on the sides",
    FitPolicy.INTEGER: "sharpest: every art pixel is an exact square block",
    FitPolicy.ZOOM: "fills the window, cropping the edges of the picture",
}

#: Every ladder value gets a note where one is useful, and a bare value where one
#: is not. An entry whose description is only restating its own label ("uncapped"
#: -> "no limit") is noise: it makes every list longer and says nothing.
_FRAME_LIMIT_NOTES: dict[int | None, str] = {
    None: "as fast as the machine draws",
    30: "saves power, and a lot of it",
    60: "one frame per simulation tick",
    120: "smoother, if the machine can hold it",
    144: "",
    180: "",
    240: "",
}

_PANEL_SCALE_NOTES: dict[float, str] = {
    0.4: "small enough for the whole stack on a small window",
    0.5: "",
    0.6: "",
    0.8: "",
    1.0: "",
    1.2: "",
}


def _hz(value: int) -> str:
    return f"{value} Hz" if value > 0 else ""


def screen_options(topology: Topology, resolution: Resolution) -> tuple[Option, ...]:
    """Every display this machine has, with enough to tell them apart.

    The old row said ``Screen 2``. On a desk with two identical 27-inch panels
    that is a coin toss presented as a menu, so each entry carries the connector
    name, the resolution and refresh, and where the panel sits on the desktop.
    The position is what actually disambiguates a pair of twins, and it is the
    one fact a player can check against their own desk.

    The entry in force is *not* simply the stored one: when the stored name no
    longer matches anything, the entry in force is the primary and says why.
    Showing the reason here as well as on the parent row is deliberate -- a player
    who opened the list to find out what happened should not have to go back to
    read it.
    """
    options: list[Option] = []
    for monitor in topology.monitors:
        detail = monitor.detail
        origin_x, origin_y = monitor.origin
        detail = f"{detail} at ({origin_x}, {origin_y})"
        if monitor.index == 0:
            detail = f"{detail} (primary)"
        if topology.label_for(monitor) != monitor.name:
            # Duplicates already get an index suffix; say which one this is so
            # the position is not the only thing distinguishing them.
            detail = f"#{monitor.index} · {detail}"
        options.append(Option(topology.label_for(monitor), monitor.name, detail))
    if not resolution.honoured and resolution.reason is not ResolutionReason.NONE_CHOSEN:
        options.append(
            Option(
                f"note:{resolution.reason.value}",
                "",
                f"The saved screen is not connected ({resolution.reason}). "
                f"It will be used again if it comes back.",
                enabled=False,
            )
        )
    return tuple(options)


def fit_options(window: tuple[int, int], current: FitPolicy) -> tuple[Option, ...]:
    """The three fit policies, each saying what it does to the picture.

    Whole-pixel art used to be a separate row on the parent screen, and it was
    the *same setting* as the integer policy here. With zoom selected it was a
    dead row: the label flipped, the stored flag changed, and the picture was
    byte-identical. Folding it in here removes the contradiction instead of
    labelling it -- and the note on ``integer`` is where a player actually reads
    what "whole-pixel" means.
    """
    options = []
    for policy in (FitPolicy.BARS, FitPolicy.INTEGER, FitPolicy.ZOOM):
        note = _FIT_NOTES[policy]
        if policy is FitPolicy.INTEGER and not fits_whole_pixel(window):
            note = "not on this window: too small to hold a whole block"
        options.append(Option(policy.value, policy, note))
    return tuple(options)


def display_options(current: DisplayMode | None = None) -> tuple[Option, ...]:
    """The three ways to occupy a screen, with what each costs.

    ``auto`` is listed first because it is the shipped default and the one a
    player should never have to think about, and the note says so rather than
    leaving them to discover that it re-decides on every launch.

    ``current`` is accepted so this has the same shape as every other list here,
    and is unused: the mark is drawn by comparing the option to the selection the
    picker was given, so a list does not need to know which one is in force.
    """
    return (
        Option(
            "auto",
            DisplayMode.AUTO,
            "decides on every launch: borderless if the screen's shape fits",
        ),
        Option("borderless", DisplayMode.BORDERLESS, _BORDERLESS_NOTE),
        Option("window", DisplayMode.WINDOW, _WINDOW_NOTE),
        Option("fullscreen", DisplayMode.FULLSCREEN, _FULLSCREEN_NOTE),
    )


def fullscreen_mode_options(
    modes: Sequence[tuple[int, int]],
    monitor: Monitor,
    current: tuple[int, int] | None,
) -> tuple[Option, ...]:
    """Every mode the driver reports that this panel can actually show.

    Filtered, and that is the whole point. The driver happily reports a 2560x1440
    mode on a 1080p panel -- it is a mode of *some* configuration -- and offering
    it is the resolution catalogue this menu used to have, rebuilt from a source
    that happens to sound authoritative. A mode larger than the panel is not one
    this machine can display at its own resolution.

    ``(0, 0)`` leads the list as "the display's own mode", because that is the
    correct answer for most players and it is not a specific resolution at all.
    """
    panel = monitor.size
    options: list[Option] = [
        Option(
            "the display's own mode",
            None,
            "uses whatever the screen is already running",
        )
    ]
    usable = [mode for mode in modes if mode[0] <= panel[0] and mode[1] <= panel[1]]
    usable.sort(key=lambda mode: (mode[0] * mode[1], mode), reverse=True)
    for width, height in usable:
        note = "native" if (width, height) == panel else ""
        options.append(Option(f"{width} x {height}", (width, height), note))
    if current is not None and current not in usable:
        # The saved mode is one the panel cannot show, which is what happens when
        # a settings file travels to a smaller screen. It is still shown, and
        # disabled, because silently dropping it would leave the player unable
        # to see that something they chose is no longer available.
        options.append(
            Option(
                f"{current[0]} x {current[1]}",
                current,
                f"not available on this screen ({panel[0]}x{panel[1]})",
                enabled=False,
            )
        )
    return tuple(options)


def window_size_options(
    modes: Sequence[tuple[int, int]],
    monitor: Monitor,
    current: tuple[int, int] | None,
    granted: tuple[int, int],
) -> tuple[Option, ...]:
    """Sizes the window can actually take, on this panel.

    The same shape as the fullscreen list and for the same reason: every entry
    is derived from the panel the window is on, and filtered to sizes that fit
    inside it. A catalogue written down in this file would be a claim about the
    player's monitor the game cannot check, which is the resolution picker that
    was deleted for exactly that reason.

    What differs from fullscreen is that the window has a frame, so the sizes
    here are not simply the panel's modes. Measured on the development machine:
    requesting the usable area exactly -- 1920x1048 -- comes back as 1920x1011,
    because the window manager subtracts the title bar and the borders, and only
    the request that touches the edge is corrected. Everything smaller is granted
    as asked. So the top entry is deliberately a margin below the usable area, and
    it is the one the game already opens at.

    ``modes`` is the driver's own list, the same source as the fullscreen
    options. A window is not obliged to match a display mode, but every number
    offered here is one this panel can actually show at this panel's own
    resolution, which is the property that makes the row honest. Writing a list
    of common window sizes into this file instead would be the catalogue the
    resolution picker used to be.

    ``current`` is the remembered preference, which may be a size this panel
    cannot take -- a 4K window arriving at a laptop. It is listed and disabled
    rather than dropped, because silently forgetting it would leave the player
    unable to see that something they chose is not available here.
    """
    usable = monitor.usable_size
    widest = opening_size(monitor)
    options: list[Option] = [
        Option(
            "the size I dragged it to",
            None,
            "follow the window wherever you put it",
        ),
        Option(f"{widest[0]} x {widest[1]}", widest, "as large as the screen allows"),
    ]
    offered: list[tuple[int, int]] = [widest]
    for size in sorted(set(modes), key=lambda m: (m[0] * m[1], m), reverse=True):
        if size[0] > usable[0] or size[1] > usable[1] or size in offered:
            continue
        offered.append(size)
        options.append(Option(f"{size[0]} x {size[1]}", size))
    if current is not None and current not in offered:
        options.append(
            Option(
                f"{current[0]} x {current[1]}",
                current,
                f"too large for this screen ({usable[0]}x{usable[1]})",
                enabled=False,
            )
        )
    return tuple(options)


def frame_limit_options() -> tuple[Option, ...]:
    return tuple(
        Option(
            "uncapped" if value is None else str(value),
            value,
            _FRAME_LIMIT_NOTES.get(value, ""),
        )
        for value in FRAME_LIMITS
    )


def ui_scale_options(current: float, density: float) -> tuple[Option, ...]:
    """The interface scale, in the units it actually ends up at.

    The row on the parent screen read ``1.0x``, which is the *preference*. The
    player looks at text, and what they see is the preference multiplied by the
    window's own pixel density -- 1.667 at 1920x1080 on this panel, so a "1.0x"
    row is describing something the player never sees. Both numbers are shown,
    because one is the choice and the other is the consequence.
    """
    options = []
    for value in UI_SCALES:
        effective = value * density
        note = f"text at {effective:.2f}x on this screen" if density > 0 else ""
        options.append(Option(f"{value:.1f}x", value, note))
    return tuple(options)


def panel_scale_options() -> tuple[Option, ...]:
    return tuple(
        Option(f"{value:g}x", value, _PANEL_SCALE_NOTES.get(value, "")) for value in PANEL_SCALES
    )
