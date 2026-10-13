"""The video settings, their file format, and how an old file is read.

What a setting is allowed to be
-------------------------------
A choice the player can make and the game can honour, or nothing. That rule is
what this file is down to, and it is why there is no window size here any more.

The size used to be here, with a ``size_mode`` to say whether it was the
player's or the machine's, and a ``render_scale`` on top to say how sharply to
draw a fixed target. All three were claims about the player's screen, and the
game could check none of them: it could not tell whether a remembered size still
fit, and in borderless the window is the desktop's size whatever the file says,
so the menu displayed a number the game was not using. A player who set a
resolution watched the menu disagree with the screen and the number change on
the next launch.

The window is now the only source of truth (:mod:`src.core.display.letterbox`),
and the picture is derived from it, so the settings that survive are the ones
that were never about the screen: a display mode, whole-pixel art, vsync, a
frame limit, an interface scale, and the bindings.

Schema v3 dropped the window keys. A v2 or v1 file still loads: unknown keys
are ignored rather than rejected, because the bindings are the expensive half
to rebuild and must not be lost over a video key that no longer means anything.
"""

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.core.display.letterbox import FitPolicy
from src.core.display.mode import DisplayMode
from src.core.input.bindings_repository import (
    bindings_from_dict,
    bindings_to_dict,
)
from src.core.input.input_bindings import InputBindings

logger = logging.getLogger(__name__)

#: v1 had a boolean, v2 a window and a render scale, v3 only choices, v4 adds
#: the monitor the player picked and the window they left it at. All are read.
SETTINGS_FORMAT_VERSION = 4
LEGACY_FORMAT_VERSIONS = (1, 2)

#: Interface scale, as the player chooses it. The scale the views are handed is
#: this multiplied by the target's pixel density, so it is a preference about
#: legibility and not a claim about the screen.
UI_SCALES: tuple[float, ...] = (0.8, 1.0, 1.2)

#: Debug-panel scale, offered down to 0.4. Its own ladder and not a slice of
#: ``UI_SCALES``, because the panels are at the far end of the problem: they are
#: ``Debug.FONT_SIZE = 24`` over a design frame, and at 1.0 only one of the five
#: placeable panels finds a slot on a 640x480 window. 0.5 is where the full stack
#: fits there, and 0.4 is the margin below it.
#:
#: A multiplier on the window's density rather than a replacement for it, so a
#: high-resolution display still gets panels larger than the design size.
PANEL_SCALES: tuple[float, ...] = (0.4, 0.5, 0.6, 0.8, 1.0, 1.2)


#: Frame limits offered. 20, 30 and 60 divide the 60Hz tick rate, so each is a
#: whole number of simulation ticks per presented frame; above that the render
#: blend takes over, which is why the higher values do not divide anything.
#: None means uncapped.
#:
#: 180 is in the list because a 180Hz panel exists and did not: the first real
#: session this ran on was one, and the ladder topped out at 144, so the one
#: rate the player was actually looking at was the one they could not select.
#: The video menu also shows the screen's own reported rate, so the ladder and
#: the hardware do not have to agree -- but when they can, they should.
FRAME_LIMITS: tuple[int | None, ...] = (None, 20, 30, 60, 120, 144, 180, 240)
DEFAULT_FRAME_LIMIT: int | None = 60

#: The floor, and the reason for it: this is where the fixed-step accumulator
#: starts losing time. ``Simulation.MAX_FRAME_TIME`` truncates a frame at 100ms,
#: so anything under 10fps runs the game in slow motion rather than dropping
#: ticks, and 20 leaves a factor of two. It used to be a second constant,
#: ``MIN_SAFE_FRAME_LIMIT``, that nothing referenced -- the same number under a
#: name that explained itself, next to the one that was actually enforced.
MIN_FRAME_LIMIT = 20
MAX_FRAME_LIMIT = 500


@dataclass(frozen=True)
class UserSettings:
    """Everything the player is allowed to have an opinion about.

    Notice what is not here: a window size, a "size mode", a render scale or a
    smoothing flag. Every one of them was a claim about the player's screen
    that the game could not check, and the two that mattered most were also
    wrong in practice -- the window is either the desktop's size (borderless) or
    whatever the player dragged it to, while the file and the menu carried a
    third number that nobody wrote back. The picture is derived from the window
    instead, so there is nothing to store and nothing to get wrong.

    What is left is a list of choices, and each one is really a choice:

    - **display**: how to occupy the screen. ``AUTO`` is re-evaluated every
      launch, which is the honest answer for "I have never seen this machine".
    - **pixel_perfect**: give up filling the window to get whole-pixel art.
    - **vsync**, **frame_limit**: how often to present.
    - **ui_scale**: the interface's own size, independent of the density.
    - **panel_scale**: the debug panels' size, down to 0.4 so the full stack fits
      a small window. Offered in the video menu only when the game is running
      with the debug overlay on, since there is nothing for it to size otherwise.
    - **bindings**: what the buttons do.
    """

    bindings: InputBindings = field(default_factory=InputBindings)
    display: DisplayMode = DisplayMode.AUTO
    #: The monitor the player picked, by the name the platform gives it.
    #:
    #: A name and not an index, and that is the whole reason this can be stored
    #: at all. An index is a claim about a machine that cannot be checked: the
    #: platform's enumeration order is not stable across boots, so "1" from a
    #: three-monitor desk can be a different panel afterwards. A name is
    #: resolved against the topology on every launch and, when it is not found,
    #: the game says so on the menu and uses the primary rather than silently
    #: landing somewhere else. ``None`` means "whatever the primary is", which is
    #: a first launch and a reset rather than a preference anyone expressed.
    monitor: str | None = None
    pixel_perfect: bool = False
    #: How the picture meets the window: bars, whole-pixel blocks, or zoom to
    #: fill with the overflow cropped. All three show *at most* the framing, so
    #: none of them can turn a video setting into a gameplay advantage.
    fit: FitPolicy = FitPolicy.BARS
    vsync: bool = False
    frame_limit: int | None = DEFAULT_FRAME_LIMIT
    ui_scale: float = 1.0
    panel_scale: float = 1.0
    #: The window geometry to restore, in window mode only. Remembered from what
    #: the player dragged the window to, and clamped to the monitor it opens on
    #: rather than overwritten -- see :func:`src.core.display.monitors.fit_size`.
    window_size: tuple[int, int] | None = None
    window_position: tuple[int, int] | None = None
    #: The mode to ask the driver for in *exclusive* fullscreen, as a pair.
    #:
    #: Only meaningful in that one mode, and only honoured when the driver still
    #: reports it -- a mode list is what the platform says this panel supports
    #: today, so a mode that disappeared with a cable change cannot be asked for.
    #: ``None`` means "whatever the display is already running", which is the
    #: safe default and the one a first launch gets.
    fullscreen_mode: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SETTINGS_FORMAT_VERSION,
            "bindings": bindings_to_dict(self.bindings),
            "video": {
                "display": self.display.value,
                "monitor": self.monitor,
                "pixel_perfect": self.pixel_perfect,
                "fit": self.fit.value,
                "vsync": self.vsync,
                "frame_limit": self.frame_limit,
                "fullscreen_mode": (list(self.fullscreen_mode) if self.fullscreen_mode else None),
            },
            "window": {
                "size": list(self.window_size) if self.window_size else None,
                "position": list(self.window_position) if self.window_position else None,
            },
            # Under ``ui`` and not ``video``: this is about the size of text on
            # screen, like the scale above it, and the ``video`` section is held
            # to exactly the four keys above by tests that exist to keep window
            # data out of it. A panel scale is not a claim about the window.
            "ui": {"scale": self.ui_scale, "panel_scale": self.panel_scale},
        }

    @classmethod
    def from_dict(cls, data: object) -> UserSettings:
        """Read a v3 file, or an older one through the migration below."""
        if not isinstance(data, dict):
            raise ValueError("settings must be an object")
        version = data.get("version")
        if version in LEGACY_FORMAT_VERSIONS:
            return cls._from_v1(data) if version == 1 else cls._from_v2(data)
        if version == 3:
            return cls._from_v3(data)
        if version != SETTINGS_FORMAT_VERSION:
            raise ValueError("unsupported settings schema")
        return cls._from_v4(data)

    @classmethod
    def _bindings(cls, data: dict[str, Any]) -> InputBindings:
        bindings_data = data.get("bindings")
        if bindings_data is None and "gameplay" in data and "menu" in data:
            bindings_data = data
        if bindings_data is None:
            raise ValueError("settings bindings section is missing")
        return bindings_from_dict(bindings_data)

    @classmethod
    def _from_v3(cls, data: dict[str, Any]) -> UserSettings:
        """Read a v3 file: choices, and nothing about the screen."""
        bindings = cls._bindings(data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")

        scale = ui.get("scale", 1.0)
        if scale not in UI_SCALES:
            raise ValueError(f"ui.scale must be one of {UI_SCALES}")

        panel_scale = ui.get("panel_scale", 1.0)
        if panel_scale not in PANEL_SCALES:
            raise ValueError(f"ui.panel_scale must be one of {PANEL_SCALES}")

        frame_limit = video.get("frame_limit", DEFAULT_FRAME_LIMIT)
        if frame_limit is not None:
            frame_limit = _bounded_int(
                frame_limit, "video.frame_limit", MIN_FRAME_LIMIT, MAX_FRAME_LIMIT
            )

        return cls(
            bindings=bindings,
            display=_enum(DisplayMode, video.get("display", DisplayMode.AUTO), "display"),
            pixel_perfect=_bounded_bool(video.get("pixel_perfect", False), "video.pixel_perfect"),
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            frame_limit=frame_limit,
            ui_scale=scale,
            panel_scale=panel_scale,
        )

    @classmethod
    def _from_v4(cls, data: dict[str, Any]) -> UserSettings:
        """Read a v4 file: a chosen screen and a chosen window, plus v3's choices.

        The window keys are read as *requests*. Nothing here decides whether they
        can be honoured -- that needs the topology, which is not known until the
        window is opened -- so they are carried through and clamped by
        :mod:`src.core.display.monitors` at launch. What is decided here is only
        whether the file is well formed, because a settings file that fails to
        parse takes the player's bindings down with it.

        A v3 file loads through this too: the keys it lacks are simply absent, so
        ``monitor``, ``fit`` and the window geometry all take their defaults and
        the player keeps their controls and their choices.
        """
        bindings = cls._bindings(data)
        video = data.get("video", {})
        window = data.get("window", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")
        if not isinstance(window, dict):
            raise ValueError("settings window section must be an object")

        scale = ui.get("scale", 1.0)
        if scale not in UI_SCALES:
            raise ValueError(f"ui.scale must be one of {UI_SCALES}")

        panel_scale = ui.get("panel_scale", 1.0)
        if panel_scale not in PANEL_SCALES:
            raise ValueError(f"ui.panel_scale must be one of {PANEL_SCALES}")

        frame_limit = video.get("frame_limit", DEFAULT_FRAME_LIMIT)
        if frame_limit is not None:
            frame_limit = _bounded_int(
                frame_limit, "video.frame_limit", MIN_FRAME_LIMIT, MAX_FRAME_LIMIT
            )

        monitor = video.get("monitor")
        if monitor is not None and not isinstance(monitor, str):
            raise ValueError("video.monitor must be a string or null")

        return cls(
            bindings=bindings,
            display=_enum(DisplayMode, video.get("display", DisplayMode.AUTO), "display"),
            monitor=monitor or None,
            pixel_perfect=_bounded_bool(video.get("pixel_perfect", False), "video.pixel_perfect"),
            fit=_enum(FitPolicy, video.get("fit", FitPolicy.BARS), "fit"),
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            frame_limit=frame_limit,
            ui_scale=scale,
            panel_scale=panel_scale,
            window_size=_placement(window, "size"),
            window_position=_placement(window, "position"),
            fullscreen_mode=_placement(video, "fullscreen_mode"),
        )

    @classmethod
    def _from_v2(cls, data: dict[str, Any]) -> UserSettings:
        """Read a v2 file.

        Everything but the bindings and the choices is dropped on the floor:
        ``width``, ``height``, ``size_mode``, ``render_scale`` and
        ``smoothing`` are all window claims, and the window is now the only
        source of truth. They are ignored rather than rejected, so a v2 player
        keeps their controls -- the expensive half to rebuild -- instead of
        landing on the defaults because of a video key that no longer means
        anything.
        """
        bindings = cls._bindings(data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")

        scale = ui.get("scale", 1.0)
        if scale not in UI_SCALES:
            raise ValueError(f"ui.scale must be one of {UI_SCALES}")
        panel_scale = ui.get("panel_scale", 1.0)
        if panel_scale not in PANEL_SCALES:
            raise ValueError(f"ui.panel_scale must be one of {PANEL_SCALES}")

        frame_counter = video.get("frame_counter", True)
        if not isinstance(frame_counter, bool):
            raise ValueError("video.frame_counter must be boolean")

        frame_limit = video.get("frame_limit", DEFAULT_FRAME_LIMIT)
        if frame_limit is not None:
            frame_limit = _bounded_int(
                frame_limit, "video.frame_limit", MIN_FRAME_LIMIT, MAX_FRAME_LIMIT
            )

        return cls(
            bindings=bindings,
            # v2 defaulted a missing mode to borderless, having just invented
            # the mode; v3 defaults it to auto, which is the honest answer for a
            # file that never expressed a preference.
            display=_enum(DisplayMode, video.get("display", DisplayMode.AUTO), "display"),
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            frame_limit=frame_limit,
            panel_scale=panel_scale,
            ui_scale=scale,
        )

    @classmethod
    def _from_v1(cls, data: dict[str, Any]) -> UserSettings:
        """Read a v1 file.

        One mapping, and it is a mode rather than a size: ``fullscreen: true``
        becomes **borderless**, not exclusive fullscreen. A v1 player who asked
        for fullscreen asked not to have a window, and borderless is the way to
        give them that without asking the driver for a mode change -- which is
        what makes v1 fullscreen the thing that blacks out a hybrid-GPU laptop.

        The size v1 stored is dropped rather than honoured. It came off a fixed
        catalogue, so it was a guess about the player's monitor, and honouring
        it would mean being the only component left that believes in a window
        size.
        """
        bindings = cls._bindings(data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")
        fullscreen = _bounded_bool(video.get("fullscreen", False), "video.fullscreen")
        scale = ui.get("scale", 1.0)
        if scale not in UI_SCALES:
            raise ValueError(f"ui.scale must be one of {UI_SCALES}")
        # A v1 file predates the key; 1.0 is what an absent preference has to
        # mean, or migrating a file would resize every panel on the first launch
        # after the upgrade.
        panel_scale = ui.get("panel_scale", 1.0)
        if panel_scale not in PANEL_SCALES:
            raise ValueError(f"ui.panel_scale must be one of {PANEL_SCALES}")
        return cls(
            bindings=bindings,
            display=DisplayMode.BORDERLESS if fullscreen else DisplayMode.WINDOW,
            panel_scale=panel_scale,
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            ui_scale=scale,
        )

    def with_bindings(self, bindings: InputBindings) -> UserSettings:
        return replace(self, bindings=bindings)

    def with_video(self, **changes: object) -> UserSettings:
        """A copy with some video fields replaced, for the menu's cycling.

        The name is now the least accurate thing here: the interface and panel
        scales are edited through it too. Renamed for clarity the moment it is
        cheaper than the grep this comment is standing in for.

        The enum fields are coerced rather than trusted. This is the only way a
        setting changes once the file has been read, so it is the only place a
        raw ``"zoom"`` can enter -- from a caller cycling a row with the value
        rather than the enum. A ``str`` that reached the dataclass unconverted
        would sit there looking fine and then raise at ``to_dict``, on the frame
        the game tries to write its settings on, which is the worst moment
        available to find out.
        """
        coerced = dict(changes)
        if isinstance(coerced.get("fit"), str):
            coerced["fit"] = FitPolicy(str(coerced["fit"]))
        if isinstance(coerced.get("display"), str):
            coerced["display"] = DisplayMode(str(coerced["display"]))
        return replace(self, **coerced)  # type: ignore[arg-type]


def _enum[E: StrEnum](enum_type: type[E], value: object, name: str) -> E:
    """Read one of a fixed set, so a typo in the file is a clean rejection."""
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            pass
    raise ValueError(f"video.{name} is not a known value")


def _bounded_int(value: object, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field_name} is out of range")
    return value


def _bounded_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean")
    return value


def _placement(window: dict[str, Any], key: str) -> tuple[int, int] | None:
    """A remembered window coordinate pair, or ``None`` for no preference.

    Read strictly -- two numbers in range -- because the alternative is a
    coordinate the stage would have to defend against, and a stage that
    sanitises its own settings cannot be tested on its own arithmetic. The
    values are still *clamped* rather than rejected at launch, because "this
    window is larger than this laptop's screen" is a normal thing to open on
    another machine and not a malformed file.
    """
    value = window.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"window.{key} must be a pair of numbers or null")
    first, second = value
    for number in (first, second):
        if not isinstance(number, int) or isinstance(number, bool):
            raise ValueError(f"window.{key} must be a pair of numbers or null")
    # A negative coordinate is legitimate: a monitor to the left of the primary
    # sits at a negative origin, and that is where a window belongs. A wildly
    # large one is not a coordinate, it is a corrupted number, and it is capped
    # rather than refused so the file still loads and the player keeps their
    # bindings.
    return (
        max(-_COORDINATE_LIMIT, min(_COORDINATE_LIMIT, first)),
        max(-_COORDINATE_LIMIT, min(_COORDINATE_LIMIT, second)),
    )


#: Bound on a remembered coordinate. Beyond it the number cannot describe a
#: position on any desktop the game will meet, and clamping it lets the rest of
#: the file survive a corrupted value.
_COORDINATE_LIMIT = 65535


class SettingsStore:
    """Reads and writes one file, and says so when it cannot.

    The failure mode this class used to have is worth stating, because it is the
    worst kind of bug: :meth:`load` caught every error and returned the
    defaults, silently. A schema that stopped matching, a truncated write, a
    file someone edited by hand -- and the player came back to a game that had
    forgotten every setting, with nothing in the log to say why, and the first
    change they made then overwrote the file that still held their bindings.

    So a read that fails is an error in the log, with the path and the reason,
    and the file is kept: :meth:`save` copies what it is about to replace to
    ``settings.json.bak`` first, which is the difference between "my controls
    are gone" and "my controls are one file away".
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> UserSettings:
        """The stored settings, or the defaults with the reason on the record."""
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
            return UserSettings.from_dict(data)
        except FileNotFoundError:
            # A first launch. Not a problem, and not worth a line.
            return UserSettings()
        except (OSError, ValueError, TypeError, KeyError) as error:
            logger.error(
                "Unable to read the settings at %s (%s: %s); starting from the defaults. "
                "The file is left untouched -- move it aside to see it, or delete it to "
                "stop seeing this.",
                self.path,
                type(error).__name__,
                error,
            )
            return UserSettings()

    def save(self, settings: UserSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._keep_backup()
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as temporary:
            json.dump(settings.to_dict(), temporary, indent=2)
            temporary_path = Path(temporary.name)
        temporary_path.replace(self.path)

    def _keep_backup(self) -> None:
        """Copy the file about to be replaced next to it, best effort.

        Best effort on purpose: a backup that can fail the write is a worse
        outcome than no backup, and the case it exists for -- a valid file being
        replaced by a valid file -- is not the case that needed saving anyway.
        """
        try:
            if self.path.is_file():
                shutil.copy2(self.path, self.path.with_suffix(".json.bak"))
        except OSError as error:
            logger.warning("Could not keep a backup of %s: %s", self.path, error)


def default_settings_path() -> Path:
    """Where settings live when nothing overrides it."""
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
