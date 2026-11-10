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
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import (
    FitPolicy,
    already_a_whole_multiple,
    fits_whole_pixel,
)
from src.core.display.monitors import (
    MIN_WINDOW,
    Monitor,
    opening_size,
)
from src.ui.text import t

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


def fit_options(window: tuple[int, int]) -> tuple[Option, ...]:
    """The three fit policies, each saying what it does to the picture.

    Whole-pixel art used to be a separate row on the parent screen, and it was
    the *same setting* as the integer policy here. With zoom selected it was a
    dead row: the label flipped, the stored flag changed, and the picture was
    byte-identical. Folding it in here removes the contradiction instead of
    labelling it -- and the note on ``integer`` is where a player actually reads
    what "whole-pixel" means.

    ``integer`` is offered **disabled** when it would change nothing, and there
    are two classes of window where it does not. A window too small to hold a
    whole multiple has nothing to snap to. A window *already* sized to a whole
    multiple is a subtler case: bars and integer hand back the same rectangle,
    so selecting it is a press that moves nothing -- and a row that flips its
    label while the screen sits still is indistinguishable from a dead one,
    which is the failure this screen has produced twice. Both are refused with
    their reason, which is the difference between an unavailable choice and one
    that quietly does nothing.
    """
    options = []
    for policy in (FitPolicy.AUTO, FitPolicy.BARS, FitPolicy.INTEGER, FitPolicy.ZOOM):
        note = t(f"fit.note.{policy.value}")
        enabled = True
        if policy is FitPolicy.INTEGER:
            if not fits_whole_pixel(window):
                note = t("fit.note.integer.small")
                enabled = False
            elif already_a_whole_multiple(window):
                note = t("fit.note.integer.same")
                enabled = False
        options.append(Option(t(f"fit.{policy.value}"), policy, note, enabled=enabled))
    return tuple(options)


def _largest_fitting(monitor: Monitor) -> tuple[int, int]:
    """The largest window that fits: what "as large as fits" has to mean here.

    :func:`opening_size` is the game's own answer, and it is normally *below*
    the usable area by the title bar -- that margin is the entire reason it
    exists. It can also overshoot: on a panel below the interface floor whose
    report the guard refuses, it answers ``FALLBACK_WINDOW``, a size chosen for
    use on a panel that gave nothing to derive from -- bigger than the panel,
    and unbeholdable as a list entry. Clamping per axis here is what keeps the
    head of the ladder honest on any panel: on a normal desk the margin decides
    (the clamps do not bite), and on a report bad enough to answer a fallback,
    the ladder tops out at the panel rather than at the fiction.
    """
    opening = opening_size(monitor)
    usable = monitor.usable_size
    return (min(opening[0], usable[0]), min(opening[1], usable[1]))


def window_size_options(
    monitor: Monitor,
    current: tuple[int, int] | None,
    granted: tuple[int, int],
) -> tuple[Option, ...]:
    """Sizes worth offering a window, on this panel. Five at most, largest first.

    Not the driver's mode list: a window is not driven at a mode, and that list
    ran to 26 entries down to 320x240. Offered instead:

    - "free size" (``None``): no stored size, the window keeps what it is dragged to;
    - the largest window that fits with its title bar -- :func:`opening_size`,
      the size the game opens at. The usable area itself is not offered: the
      window manager grants it short by the frame;
    - up to four sizes under it: the framing's whole multiples (the only sizes
      the integer fit fills) and the usual 16:9 sizes.

    ``current`` is the remembered preference. If it is not in the list it is
    added: choosable when the panel can hold it, disabled and explained when it
    cannot (a 4K window arriving at a laptop).
    """
    usable = monitor.usable_size
    widest = _largest_fitting(monitor)
    options: list[Option] = [
        Option(
            "free size",
            None,
            "no stored size: the window keeps whatever size you drag it to",
        ),
    ]
    offered: list[tuple[int, int]] = []

    def offer(size: tuple[int, int], note: str) -> None:
        if size in offered or size[0] > widest[0] or size[1] > widest[1]:
            return
        if size[0] < MIN_WINDOW[0] or size[1] < MIN_WINDOW[1]:
            return
        offered.append(size)
        if size == tuple(granted):
            note = f"{note} · current" if note else "current"
        options.append(Option(f"{size[0]} x {size[1]}", size, note))

    # The largest window that fits with its frame: the size the game opens at.
    offer(widest, "as large as fits, title bar included")
    # Then the few sizes below it worth choosing: whole multiples of the
    # framing first -- the only sizes where the integer fit fills the window --
    # and the usual 16:9 sizes. Nothing above ``widest``: the window manager
    # would shrink it, and the row would describe a size nobody gets.
    candidates = [
        (size, "whole multiple: sharpest with the integer fit") for size in _whole_multiples()
    ] + [(size, "") for size in STANDARD_SIZES]
    fitting = sorted(
        (c for c in candidates if c[0][0] <= widest[0] and c[0][1] <= widest[1]),
        key=lambda c: (-c[0][0] * c[0][1], -c[0][0]),
    )
    for size, note in fitting:
        if len(offered) > LADDER_RUNGS:
            break
        offer(size, note)
    entries = sorted(
        options[1:], key=lambda option: (-option.value[0] * option.value[1], -option.value[0])
    )
    if current is not None and tuple(current) not in offered:
        too_large = current[0] > usable[0] or current[1] > usable[1]
        entries.append(
            Option(
                f"{current[0]} x {current[1]}",
                current,
                f"too large for this screen ({usable[0]}x{usable[1]})"
                if too_large
                else "the size you chose earlier",
                enabled=not too_large,
            )
        )
    return (options[0], *entries)


#: How many sizes are offered under the largest one.
LADDER_RUNGS = 4

#: The usual 16:9 window sizes, offered when they fit.
STANDARD_SIZES: tuple[tuple[int, int], ...] = (
    (960, 540),
    (1024, 576),
    (1280, 720),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3200, 1800),
    (3840, 2160),
)


def _whole_multiples() -> tuple[tuple[int, int], ...]:
    """The framing at x1, x2, x3: the window sizes integer scaling fills."""
    return tuple(
        (round(DEFAULT_FRAMING.width * k), round(DEFAULT_FRAMING.height * k)) for k in (1, 2, 3)
    )


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
