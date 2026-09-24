"""Gameplay scene: one level, its deaths, its transitions (Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.colors import Colors
from src.core.level.level import Level
from src.core.settings import Debug, Gameplay

if TYPE_CHECKING:
    from src.core.game import Game


#: Debug overlay layers toggled by function keys (F1-F5).
_OVERLAY_TOGGLES = {
    pygame.K_F1: "boxes",
    pygame.K_F2: "labels",
    pygame.K_F3: "velocities",
    pygame.K_F4: "statics",
    pygame.K_F5: "panels",
}

#: Debug-only freeze key (F6): holds the simulation still so floating
#: label cards can be read, while rendering keeps running.
_FREEZE_KEY = pygame.K_F6

#: Debug-only single-step key (F7): while frozen, advance exactly one tick
#: so sweep ghosts and attack phases stay readable at full speed otherwise.
_STEP_KEY = pygame.K_F7

#: Debug-only attack-replay key (F8): loops the last (or first) showcase
#: attack while the player is idle, for overlay/timeline inspection.
_REPLAY_KEY = pygame.K_F8
_EXPORT_KEY = pygame.K_F9
_PANEL_FOCUS_KEY = pygame.K_F10

#: Mouse events the debug panels may consume (``×`` clicks and drag & drop);
#: anything else reaches the level untouched.
_PANEL_MOUSE_EVENTS = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)


class GameplayScene(Scene):
    """Run a ``Level`` and trigger the end transitions.

    Transitions:
    - exit flag reached → next level (or menu if last level);
    - ``Gameplay.MAX_DEATHS`` deaths → Game Over scene;
    - ESC → pause (the scene is frozen on the stack).
    - F6 (debug only) → freeze the simulation in place to inspect the
      debug label cards; rendering keeps running.
    - F7 (debug only, while frozen) → advance exactly one simulation tick.
    - F8 (debug only) → toggle looping the last showcase attack.

    Mouse events are offered to the debug panels first (debug only): a click
    on their ``×`` hides that panel and a drag moves it, until F5 resets the
    whole set.
    """

    def __init__(self, game: Game, level_id: int = 0, level: Level | None = None) -> None:
        """``level`` allows injecting a Level in tests (no TMX)."""
        super().__init__(game)
        self.level_id = level_id
        self.level: Level | None = level
        self.frozen = False
        self._step_pending = False

    def enter(self) -> None:
        if self.level is None:
            self._load_level()

    def _load_level(self) -> None:
        if self.game.display_surface is None:
            raise RuntimeError("The game display is not initialized")
        level_data = self.game.level_manager.get(self.level_id)
        self.level = Level(
            self.game.display_surface,
            level_data,
            self.game.input_manager,
            level_id=self.level_id,
            events=self.game.events,
            gameplay_data=self.game.gameplay_data,
        )

    def update(self, delta_time: float) -> None:
        if self.level is None:
            raise RuntimeError("GameplayScene has no level loaded")
        self.game.input_manager.update()
        if self.frozen and Debug.is_enabled():
            if not self._step_pending:
                return  # debug freeze: the frame still renders, the sim holds still
            self._step_pending = False
        self.level.update(delta_time)

        if self.level.completed:
            self._advance_level()
        elif self.level.deaths >= Gameplay.MAX_DEATHS:
            # Local import: Menu/GameOver/Gameplay reference each other.
            from src.application.scenes.gameover_scene import GameOverScene

            self.game.scene_manager.push(GameOverScene(self.game, self.level_id))

    def _advance_level(self) -> None:
        from src.application.scenes.gameplay_scene import GameplayScene
        from src.application.scenes.menu_scene import MenuScene

        next_id = self.game.level_manager.next_id(self.level_id)
        if next_id is None:
            self.game.scene_manager.switch(MenuScene(self.game))
        else:
            self.game.scene_manager.switch(GameplayScene(self.game, next_id))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from src.application.scenes.pause_scene import PauseScene

            self.game.scene_manager.push(PauseScene(self.game, self.level_id))
            return
        if self._route_to_panels(event):
            return
        if event.type == pygame.KEYDOWN and self.level is not None:
            self._handle_gameplay_key(event.key)

    def _handle_panel_tools_key(self, key: int) -> bool:
        if self.level is None:
            return False
        if key == _EXPORT_KEY:
            from src.application.attack_authoring import export_attack

            spawn = getattr(self.level, "spawn_system", None)
            selected = getattr(spawn, "selected_attack", None)
            if callable(selected) and selected():
                export_attack(self.game.gameplay_data.attack_sets, selected())
            return True
        if key == _PANEL_FOCUS_KEY:
            self.level.renderer.ui_manager.cycle_compact_panel()
            return True
        return False

    def _handle_gameplay_key(self, key: int) -> None:
        if self.level is None or not Debug.is_enabled():
            return
        if key == _FREEZE_KEY:
            self.frozen = not self.frozen
            self._step_pending = False
            return
        if key == _STEP_KEY and self.frozen:
            self._step_pending = True
            return
        if key == _REPLAY_KEY:
            spawn = getattr(self.level, "spawn_system", None)
            toggle = getattr(spawn, "toggle_attack_replay", None)
            if callable(toggle):
                toggle()
            return
        if self._handle_panel_tools_key(key):
            return
        toggle = _OVERLAY_TOGGLES.get(key)
        if toggle is not None:
            ui_manager = self.level.renderer.ui_manager
            ui_manager.world_ui.toggle(toggle)
            if toggle == "panels":
                ui_manager.reset_debug_panels()

    def _route_to_panels(self, event: pygame.event.Event) -> bool:
        """Let the debug panels swallow a mouse event (``×``, drag & drop).

        Only while the panels are actually painted: their registered rects
        outlive the frame that drew them, so routing clicks while the layer
        is off would let an invisible panel eat gameplay input. Non-mouse
        events return at once, before the level is even touched.
        """
        if event.type not in _PANEL_MOUSE_EVENTS:
            return False
        if self.level is None or not Debug.is_enabled():
            return False
        # Duck-typed levels (tests) may not carry a renderer at all.
        renderer = getattr(self.level, "renderer", None)
        if renderer is None:
            return False
        ui_manager = renderer.ui_manager
        if not ui_manager.world_ui.layers.get("panels", True):
            return False
        return bool(ui_manager.handle_panel_event(event))

    def draw(self) -> list[pygame.Rect] | None:
        if self.level is None:
            raise RuntimeError("GameplayScene has no level loaded")
        clock = self.game.clock
        fps = clock.get_fps() if clock else 0.0
        frame_time = clock.get_time() if clock else 0.0
        rects = self.level.draw(fps, game=self.game, frame_time=frame_time)
        # Always-on player gauges (UI-7): drawn last so the HUD stays on top of
        # the world and of the debug panels, and never hidden by F5. Its rects
        # join the dirty set, since a non-debug frame presents those only.
        ui_manager = self.level.renderer.ui_manager
        hud_rects = ui_manager.draw_hud(getattr(self.level, "player", None))
        if rects is not None:
            rects.extend(hud_rects)
        if self.frozen:
            self._draw_frozen_tag()
        return rects

    def _draw_frozen_tag(self) -> None:
        """Paint a red FROZEN marker, top-center, while the sim is held."""
        assert self.level is not None  # draw() already guarantees a level
        ui_manager = self.level.renderer.ui_manager
        surface = ui_manager.renderer.display_surface
        tag = ui_manager.renderer.render_text("FROZEN", ui_manager.renderer.title_font, Colors.red)
        surface.blit(tag, (surface.get_width() // 2 - tag.get_width() // 2, 10))
