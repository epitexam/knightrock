"""The video settings, their file format, and how a v1 file is read.

Schema v2 replaced "fullscreen: bool" with a real display mode, and turned the
window size into something the machine gets a say in. Both changes exist for
the same reason: a setting that describes the player's screen is a claim the
game cannot check, and the v1 catalogue of absolute resolutions made that claim
seven times over -- offering 2560x1440 to a 1366x768 laptop.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.core.display.mode import DisplayMode
from src.core.display.size_mode import SizeMode
from src.core.display.viewport import DEFAULT_RENDER_SCALE, RENDER_SCALES
from src.core.input.bindings_repository import (
    bindings_from_dict,
    bindings_to_dict,
)
from src.core.input.input_bindings import InputBindings
from src.core.settings import Display

#: v1 had a boolean; v2 has a mode. Both are read.
SETTINGS_FORMAT_VERSION = 2
LEGACY_FORMAT_VERSION = 1

# Bornes vidéo acceptées : elles valident ``settings.json`` pour rejeter un
# fichier corrompu ou hors limites. La fenêtre est redimensionnable, donc ces
# bornes ne servent plus qu'à écarter un fichier absurde, et la taille est
# recalculée au lancement quand le mode est « auto ».
MIN_WINDOW_WIDTH = 320
MIN_WINDOW_HEIGHT = 240
MAX_WINDOW_WIDTH = 7680
MAX_WINDOW_HEIGHT = 4320

#: Frame limits offered. 20, 30 and 60 divide the 60Hz tick rate, so each is a
#: whole number of simulation ticks per presented frame; 144 covers a 144Hz
#: display without the player having to guess, and None means uncapped.
FRAME_LIMITS: tuple[int | None, ...] = (None, 20, 30, 60, 120, 144, 240)
DEFAULT_FRAME_LIMIT: int | None = 60
MIN_FRAME_LIMIT = 20
MAX_FRAME_LIMIT = 500

#: The frame limit below which the fixed-step accumulator starts losing time:
#: ``Simulation.MAX_FRAME_TIME`` truncates a frame at 100ms, so anything under
#: 10fps runs the game in slow motion rather than dropping ticks. 20 leaves a
#: factor of two.
MIN_SAFE_FRAME_LIMIT = 20


@dataclass(frozen=True)
class UserSettings:
    bindings: InputBindings = field(default_factory=InputBindings)
    display: DisplayMode = DisplayMode.AUTO
    width: int = Display.WIDTH
    height: int = Display.HEIGHT
    size_mode: SizeMode = SizeMode.AUTO
    render_scale: int = DEFAULT_RENDER_SCALE
    smoothing: bool = True
    vsync: bool = False
    frame_limit: int | None = DEFAULT_FRAME_LIMIT
    ui_scale: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SETTINGS_FORMAT_VERSION,
            "bindings": bindings_to_dict(self.bindings),
            "video": {
                "display": self.display.value,
                "width": self.width,
                "height": self.height,
                "size_mode": self.size_mode.value,
                "render_scale": self.render_scale,
                "smoothing": self.smoothing,
                "vsync": self.vsync,
                "frame_limit": self.frame_limit,
            },
            "ui": {"scale": self.ui_scale},
        }

    @classmethod
    def from_dict(cls, data: object) -> UserSettings:
        """Read a v2 file, or a v1 one through the migration below."""
        if not isinstance(data, dict):
            raise ValueError("settings must be an object")
        version = data.get("version")
        if version == LEGACY_FORMAT_VERSION:
            return cls._from_v1(data)
        if version != SETTINGS_FORMAT_VERSION:
            raise ValueError("unsupported settings schema")
        return cls._from_v2(data)

    @classmethod
    def _bindings(cls, data: dict[str, Any]) -> InputBindings:
        bindings_data = data.get("bindings")
        if bindings_data is None and "gameplay" in data and "menu" in data:
            bindings_data = data
        if bindings_data is None:
            raise ValueError("settings bindings section is missing")
        return bindings_from_dict(bindings_data)

    @classmethod
    def _from_v2(cls, data: dict[str, Any]) -> UserSettings:
        bindings = cls._bindings(data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")

        scale = ui.get("scale", 1.0)
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("ui.scale must be 0.8, 1.0 or 1.2")

        render_scale = _bounded_int(
            video.get("render_scale", DEFAULT_RENDER_SCALE),
            "video.render_scale",
            min(RENDER_SCALES),
            max(RENDER_SCALES),
        )
        if render_scale not in RENDER_SCALES:
            raise ValueError(f"video.render_scale must be one of {RENDER_SCALES}")

        frame_limit = video.get("frame_limit", DEFAULT_FRAME_LIMIT)
        if frame_limit is not None:
            frame_limit = _bounded_int(
                frame_limit, "video.frame_limit", MIN_FRAME_LIMIT, MAX_FRAME_LIMIT
            )

        return cls(
            bindings=bindings,
            display=_enum(DisplayMode, video.get("display", DisplayMode.BORDERLESS), "display"),
            width=_bounded_int(
                video.get("width", Display.WIDTH),
                "video.width",
                MIN_WINDOW_WIDTH,
                MAX_WINDOW_WIDTH,
            ),
            height=_bounded_int(
                video.get("height", Display.HEIGHT),
                "video.height",
                MIN_WINDOW_HEIGHT,
                MAX_WINDOW_HEIGHT,
            ),
            size_mode=_enum(SizeMode, video.get("size_mode", SizeMode.AUTO), "size_mode"),
            render_scale=render_scale,
            smoothing=_bounded_bool(video.get("smoothing", True), "video.smoothing"),
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            frame_limit=frame_limit,
            ui_scale=scale,
        )

    @classmethod
    def _from_v1(cls, data: dict[str, Any]) -> UserSettings:
        """Read a v1 file.

        Two mappings, both deliberate rather than mechanical:

        ``fullscreen: true`` becomes **borderless**, not exclusive fullscreen.
        A v1 player who asked for fullscreen asked not to have a window, and
        borderless is the way to give them that without asking the driver for a
        mode change -- which is what makes v1 fullscreen the thing that blacks
        out a hybrid-GPU laptop.

        The size becomes ``MANUAL``, because a v1 size is a number the player
        picked off a fixed list, and honouring that intent exactly is the
        honest reading. The runtime still refuses to open a window that does not
        fit the current screen, and says so in the menu.
        """
        bindings = cls._bindings(data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")
        fullscreen = _bounded_bool(video.get("fullscreen", False), "video.fullscreen")
        scale = ui.get("scale", 1.0)
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("ui.scale must be 0.8, 1.0 or 1.2")
        return cls(
            bindings=bindings,
            display=DisplayMode.BORDERLESS if fullscreen else DisplayMode.WINDOW,
            width=_bounded_int(
                video.get("width", Display.WIDTH),
                "video.width",
                MIN_WINDOW_WIDTH,
                MAX_WINDOW_WIDTH,
            ),
            height=_bounded_int(
                video.get("height", Display.HEIGHT),
                "video.height",
                MIN_WINDOW_HEIGHT,
                MAX_WINDOW_HEIGHT,
            ),
            size_mode=SizeMode.MANUAL,
            vsync=_bounded_bool(video.get("vsync", False), "video.vsync"),
            ui_scale=scale,
        )

    def with_bindings(self, bindings: InputBindings) -> UserSettings:
        return replace(self, bindings=bindings)

    def with_video(self, **changes: object) -> UserSettings:
        """A copy with some video fields replaced, for the menu's cycling."""
        return replace(self, **changes)  # type: ignore[arg-type]

    @property
    def frame_rate(self) -> int:
        """The target the loop paces to, given vsync may override it."""
        if self.frame_limit is None:
            return Display.FPS
        return self.frame_limit

    @property
    def is_windowed(self) -> bool:
        return self.display is DisplayMode.WINDOW


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


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> UserSettings:
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
            return UserSettings.from_dict(data)
        except OSError, ValueError, TypeError, KeyError, json.JSONDecodeError:
            return UserSettings()

    def save(self, settings: UserSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing: object = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError, TypeError, json.JSONDecodeError:
            existing = {}
        payload = dict(existing) if isinstance(existing, dict) else {}
        payload.update(settings.to_dict())
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as temporary:
            json.dump(payload, temporary, indent=2)
            temporary_path = Path(temporary.name)
        temporary_path.replace(self.path)


def default_settings_path() -> Path:
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "settings.json"
