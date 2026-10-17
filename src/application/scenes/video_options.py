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

from src.application.scenes.option_screen import Option
from src.application.settings_store import FRAME_LIMITS, PANEL_SCALES, UI_SCALES
from src.core.display.letterbox import FitPolicy, fits_whole_pixel
from src.core.display.monitors import (
    MIN_WINDOW,
    Monitor,
    opening_size,
)

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


def window_size_options(
    monitor: Monitor,
    current: tuple[int, int] | None,
    granted: tuple[int, int],
) -> tuple[Option, ...]:
    """Sizes worth offering a window, on this panel.

    **Not the driver's mode list**, and the difference is the point. A *mode* is
    a resolution the panel is driven at, and the whole of them was the right
    answer only for exclusive fullscreen -- which is gone. If you are taking the
    panel over, it is being run at one of these or nothing else.

    A *window* is not driven at anything. It floats on the panel, it can be any
    size the player drags it to, and the driver has no opinion. Feeding it the
    mode list produced 26 entries on this machine -- down to 320x240 -- which is
    not a list of choices, it is a list to scroll through, and offering somebody
    a 320x240 window as a deliberate option is an insult to the screen it is on.

    So the sizes are the useful ones, filtered to what this panel can hold: the
    largest the frame allows, the panel's own resolution, and a ladder that
    shrinks. Every one is checkable -- they are all either derived from the
    monitor or refused if it cannot take them -- which is what keeps this from
    being the catalogue the resolution picker used to be.

    The frame matters and is measured, not assumed: requesting the usable area
    exactly comes back short, because the window manager subtracts the title bar.
    The largest entry is therefore :func:`opening_size`, which leaves that room,
    and it is the size the game already opens at.

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
    ]
    offered: list[tuple[int, int]] = []

    def offer(size: tuple[int, int], note: str = "") -> None:
        if size in offered or size[0] > usable[0] or size[1] > usable[1]:
            return
        if size[0] < MIN_WINDOW[0] or size[1] < MIN_WINDOW[1]:
            return
        offered.append(size)
        if size == tuple(granted):
            note = f"{note} · current" if note else "current"
        options.append(Option(f"{size[0]} x {size[1]}", size, note))

    offer(widest, "as large as the screen allows")
    offer((monitor.size[0], monitor.size[1]), "the screen's own resolution")
    # A ladder rather than everything the panel supports, and it only goes
    # downwards: `widest` is already as large as the frame allows, so a
    # "three quarters" rung would land above it and be filtered out as too big.
    # These are derived from the panel rather than written down, so a 4K desk
    # gets a 4K ladder and a laptop gets a laptop's.
    for denominator, note in ((2, "half the screen"), (3, "a third of the screen")):
        offer(
            (
                max(MIN_WINDOW[0], widest[0] // denominator),
                max(MIN_WINDOW[1], widest[1] // denominator),
            ),
            note,
        )
    # Largest first, so the list reads as a scale rather than as an accident of
    # the order the sizes were thought up in. On a 1366x768 laptop the panel's
    # own resolution is *bigger* than the widest window that fits under its
    # taskbar, and offering the smaller one first read as backwards.
    entries = sorted(options[1:], key=lambda option: (-option.value[0] * option.value[1], option))
    if current is not None and tuple(current) not in offered:
        entries.append(
            Option(
                f"{current[0]} x {current[1]}",
                current,
                f"too large for this screen ({usable[0]}x{usable[1]})"
                if current[0] > usable[0] or current[1] > usable[1]
                else "not one of the sizes offered here",
                enabled=False,
            )
        )
    return (options[0], *entries)


def frame_limit_options(vsync: bool) -> tuple[Option, ...]:
    """The frame-limit ladder, with what it is worth under the current pacing.

    With vsync active the present is the pacer and the clock never bites -- the
    ceiling it is ticked against is above every value here, by construction, so
    the whole ladder is inert. Repeating "saves power" under vsync would be the
    promise that made the row read as broken, so the note says the one thing that
    is true about every entry in that state.
    """
    note = "ignored while VSync is on" if vsync else ""
    return tuple(
        Option(
            "uncapped" if value is None else str(value),
            value,
            note if vsync else _FRAME_LIMIT_NOTES.get(value, ""),
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
