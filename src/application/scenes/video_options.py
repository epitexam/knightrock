"""The lists a settings screen opens, and what each entry says about itself.

Each function returns :class:`~src.application.scenes.option_screen.Option`
entries with a note on the consequence, testable without a display.
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

#: Text keys of the notes, where a note says something the value does not.
_FRAME_LIMIT_NOTES: dict[int | None, str] = {
    None: "limit.note.uncapped",
    30: "limit.note.30",
    60: "limit.note.60",
    120: "limit.note.120",
}

_PANEL_SCALE_NOTES: dict[float, str] = {0.4: "panel.note.small"}


def _note(key: str | None) -> str:
    return t(key) if key else ""


def fit_options(window: tuple[int, int]) -> tuple[Option, ...]:
    """The fit policies, each with what it does to the picture.

    ``integer`` is disabled, with its reason, where it would change nothing: a
    window too small for a whole multiple, or one that already is one.
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
    """The largest window offered: :func:`opening_size`, clamped to the usable area.

    The clamp only matters when the panel's report was bad enough to answer
    ``FALLBACK_WINDOW``.
    """
    opening = opening_size(monitor)
    usable = monitor.usable_size
    return (min(opening[0], usable[0]), min(opening[1], usable[1]))


def window_size_options(
    monitor: Monitor,
    current: tuple[int, int] | None,
    granted: tuple[int, int],
) -> tuple[Option, ...]:
    """Sizes worth offering a window on this panel, largest first.

    - "free size" (``None``): the window keeps what it is dragged to;
    - the largest window that fits with its title bar (the opening size);
    - up to four sizes under it: the framing's whole multiples and the usual
      16:9 sizes.

    ``current``, if not in the list, is added: choosable when it fits, disabled
    and explained when it does not.
    """
    usable = monitor.usable_size
    widest = _largest_fitting(monitor)
    options: list[Option] = [
        Option(t("size.free"), None, t("size.free.note")),
    ]
    offered: list[tuple[int, int]] = []

    def offer(size: tuple[int, int], note: str) -> None:
        if size in offered or size[0] > widest[0] or size[1] > widest[1]:
            return
        if size[0] < MIN_WINDOW[0] or size[1] < MIN_WINDOW[1]:
            return
        offered.append(size)
        if size == tuple(granted):
            note = t("size.current_after", note=note) if note else t("size.current")
        options.append(Option(t("value.size", width=size[0], height=size[1]), size, note))

    # The largest window that fits with its frame: the size the game opens at.
    offer(widest, t("size.largest"))
    # Then the few sizes below it worth choosing: whole multiples of the
    # framing first -- the only sizes where the integer fit fills the window --
    # and the usual 16:9 sizes. Nothing above ``widest``: the window manager
    # would shrink it, and the row would describe a size nobody gets.
    candidates = [(size, t("size.whole")) for size in _whole_multiples()] + [
        (size, "") for size in STANDARD_SIZES
    ]
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
                t("value.size", width=current[0], height=current[1]),
                current,
                t("size.too_large", width=usable[0], height=usable[1])
                if too_large
                else t("size.earlier"),
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
    """The frame-limit ladder. Under VSync every entry says it is ignored,
    since the present paces and the limit never bites.
    """
    return tuple(
        Option(
            t("limit.uncapped") if value is None else str(value),
            value,
            t("limit.note.vsync") if vsync else _note(_FRAME_LIMIT_NOTES.get(value)),
        )
        for value in FRAME_LIMITS
    )


def ui_scale_options(current: float, density: float) -> tuple[Option, ...]:
    """The interface scale, each with the text scale it gives on this screen
    (the preference times the window's density).
    """
    options = []
    for value in UI_SCALES:
        effective = value * density
        note = t("scale.note", effective=effective) if density > 0 else ""
        options.append(Option(f"{value:.1f}x", value, note))
    return tuple(options)


def panel_scale_options() -> tuple[Option, ...]:
    return tuple(
        Option(f"{value:g}x", value, _note(_PANEL_SCALE_NOTES.get(value))) for value in PANEL_SCALES
    )
