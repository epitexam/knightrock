"""The process environment, read once at startup into an immutable config.

Tests still drive ``DEBUG`` and the ``KNIGHTROCK_*`` path overrides through
``os.environ`` (their fixtures set those variables directly), so the leaf
helpers that read them keep doing so for now. This config owns the values the
application layer itself uses -- SDL hints and the default user files -- so
``Game`` no longer reaches into the environment as it is constructed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

#: SDL reads these when the video subsystem comes up, so they must be set
#: before pygame.init(). pygame-ce 2.5.7 has no HIDPI flag, so the hint is the
#: whole mechanism.
SDL_HINTS: Mapping[str, str] = {
    "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
    "SDL_VIDEO_HIDPI": "1",
}


@dataclass(frozen=True)
class RuntimeConfig:
    """The environment as the application saw it at startup."""

    debug: bool = False
    combat_dump: bool = False
    data_dir: Path | None = None
    save_dir: Path = field(default_factory=Path.home)
    export_dir: Path = field(default_factory=lambda: Path.home() / ".knightrock" / "exports")
    sdl_hints: Mapping[str, str] = field(default_factory=lambda: dict(SDL_HINTS))

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> RuntimeConfig:
        env = os.environ if environ is None else environ
        data_dir = env.get("KNIGHTROCK_DATA_DIR")
        return cls(
            debug=env.get("DEBUG", "0") == "1",
            combat_dump=env.get("DEBUG_COMBAT_DUMP", "0") == "1",
            data_dir=Path(data_dir) if data_dir else None,
            save_dir=Path(env.get("KNIGHTROCK_SAVE_DIR", str(Path.home()))),
            export_dir=Path(
                env.get("KNIGHTROCK_EXPORT_DIR", str(Path.home() / ".knightrock" / "exports"))
            ),
        )

    @property
    def save_path(self) -> Path:
        return self.save_dir / ".knightrock" / "savegame.json"

    @property
    def settings_path(self) -> Path:
        return self.save_dir / ".knightrock" / "settings.json"

    def apply_sdl_hints(self) -> None:
        """Set the hints SDL needs before the display is opened."""
        for name, value in self.sdl_hints.items():
            os.environ[name] = value
