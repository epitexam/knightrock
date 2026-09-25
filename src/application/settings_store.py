import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from src.core.input.bindings_repository import (
    bindings_from_dict,
    bindings_to_dict,
)
from src.core.input.input_bindings import InputBindings
from src.core.settings import Display

SETTINGS_FORMAT_VERSION = 1

# Bornes vidéo acceptées : elles valident ``settings.json`` pour rejeter un
# fichier corrompu ou hors limites. La fenêtre n'étant pas redimensionnable,
# les dimensions ne sont modifiées que par le menu vidéo.
MIN_WINDOW_WIDTH = 320
MIN_WINDOW_HEIGHT = 240
MAX_WINDOW_WIDTH = 7680
MAX_WINDOW_HEIGHT = 4320


@dataclass(frozen=True)
class UserSettings:
    bindings: InputBindings = field(default_factory=InputBindings)
    width: int = Display.WIDTH
    height: int = Display.HEIGHT
    fullscreen: bool = False
    vsync: bool = False
    ui_scale: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SETTINGS_FORMAT_VERSION,
            "bindings": bindings_to_dict(self.bindings),
            "video": {
                "width": self.width,
                "height": self.height,
                "fullscreen": self.fullscreen,
                "vsync": self.vsync,
            },
            "ui": {"scale": self.ui_scale},
        }

    @classmethod
    def from_dict(cls, data: object) -> UserSettings:
        if not isinstance(data, dict) or data.get("version") != SETTINGS_FORMAT_VERSION:
            raise ValueError("unsupported settings schema")
        bindings_data = data.get("bindings")
        if bindings_data is None and "gameplay" in data and "menu" in data:
            bindings_data = data
        if bindings_data is None:
            raise ValueError("settings bindings section is missing")
        bindings = bindings_from_dict(bindings_data)
        video = data.get("video", {})
        ui = data.get("ui", {})
        if not isinstance(video, dict) or not isinstance(ui, dict):
            raise ValueError("settings sections must be objects")
        width = _bounded_int(
            video.get("width", Display.WIDTH), "video.width", MIN_WINDOW_WIDTH, MAX_WINDOW_WIDTH
        )
        height = _bounded_int(
            video.get("height", Display.HEIGHT),
            "video.height",
            MIN_WINDOW_HEIGHT,
            MAX_WINDOW_HEIGHT,
        )
        fullscreen = _bounded_bool(video.get("fullscreen", False), "video.fullscreen")
        vsync = _bounded_bool(video.get("vsync", False), "video.vsync")
        scale = ui.get("scale", 1.0)
        if scale not in (0.8, 1.0, 1.2):
            raise ValueError("ui.scale must be 0.8, 1.0 or 1.2")
        return cls(bindings, width, height, fullscreen, vsync, scale)

    def with_bindings(self, bindings: InputBindings) -> UserSettings:
        return replace(self, bindings=bindings)


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
