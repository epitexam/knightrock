"""The surface of the application runtime that scenes are allowed to use.

A scene used to be handed the concrete :class:`Game`, so any screen could reach
its private helpers and tests had to build the whole runtime. This protocol is
the explicit boundary: ``Game`` satisfies it structurally, and a test can
supply a smaller stand-in. It is intentionally the *current* surface, not an
ideal one -- narrowing it further is a later, behaviour-preserving step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pygame

if TYPE_CHECKING:
    from src.application.runtime_clock import FrameClock
    from src.application.save_game import SaveGame
    from src.application.scene_manager import SceneManager
    from src.application.settings_store import UserSettings
    from src.platform.input.event_router import EventRouter
    from src.platform.input.input_bindings import InputBindings
    from src.platform.input.input_manager import InputManager
    from src.presentation.display.letterbox import FitPolicy
    from src.presentation.display.monitors import Monitor
    from src.presentation.display.presentation import Presentation
    from src.presentation.display.stage import Stage
    from src.presentation.ui.ui_manager import UIManager
    from src.shared.events import EventBus
    from src.simulation.data.provider import GameplayData
    from src.simulation.level.level_manager import LevelManager


class SceneContext(Protocol):
    """What a scene may ask of the runtime it lives in."""

    @property
    def settings(self) -> UserSettings: ...

    @property
    def scene_manager(self) -> SceneManager: ...

    @property
    def presentation(self) -> Presentation | None: ...

    @property
    def stage(self) -> Stage | None: ...

    @property
    def ui_scale(self) -> float: ...

    @property
    def shown_area(self) -> pygame.Rect | None: ...

    @property
    def ui(self) -> UIManager | None: ...

    @property
    def save_game(self) -> SaveGame: ...

    @property
    def gameplay_data(self) -> GameplayData: ...

    @property
    def level_manager(self) -> LevelManager: ...

    @property
    def input_router(self) -> EventRouter: ...

    @property
    def input_manager(self) -> InputManager: ...

    @property
    def events(self) -> EventBus: ...

    @property
    def clock(self) -> FrameClock: ...

    @property
    def notice_lines(self) -> tuple[str, ...]: ...

    @property
    def render_target(self) -> pygame.Surface: ...

    def effective_fit(self) -> FitPolicy: ...

    def monitor(self) -> Monitor: ...

    def window_monitor(self) -> Monitor | None: ...

    def render_alpha(self) -> float: ...

    def world_overlay(self, target: pygame.Surface) -> UIManager: ...

    def notice(self, *lines: str, seconds: float = 4.0) -> None: ...

    def apply_settings(self, settings: UserSettings) -> None: ...

    def apply_bindings(self, bindings: InputBindings) -> None: ...

    def quit(self) -> None: ...
