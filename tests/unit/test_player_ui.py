"""Tests for PlayerUI (ui/player_ui)."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.entities.player_config import PlayerConfig
from src.entities.player_controllers import DashController
from src.ui.panel_renderer import PanelRenderer
from src.ui.player_ui import PlayerUI


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def player_ui() -> PlayerUI:
    return PlayerUI(PanelRenderer(pygame.display.get_surface()))


def _mock_state():
    return SimpleNamespace(enter=lambda *a, **kw: None, tags=[])


def _make_player(**overrides) -> SimpleNamespace:
    """Build a SimpleNamespace with all attributes PlayerUI draws."""
    from src.states.state_machine import StateMachine

    sm = StateMachine(SimpleNamespace())
    sm.add_state("idle", _mock_state())
    sm.set_initial_state("idle")

    defaults = dict(
        state_machine=sm,
        velocity=pygame.Vector2(10.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        move_axis=0.0,
        jump_buffer_timer=0.0,
        coyote_timer=0.0,
        midair_jumps_left=1,
        wall_jumps_left=2,
        dash=DashController(PlayerConfig()),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_full_player(**overrides) -> SimpleNamespace:
    """Player with all stats attributes for draw_stats_panel."""
    base = dict(
        health=100.0,
        max_health=100.0,
        block_stamina=0.5,
        max_block_stamina=0.75,
        block_cooldown_timer=0.0,
        dash_charges=2,
        max_dash_charges=2,
        dash_penalty_timer=0.0,
        dash_recharge_timer=0.0,
        speed=450,
        floor_control=25.0,
        air_control=12.0,
        jump_height=750.0,
        wall_jump_height=612.0,
        dash_speed=1500,
        dash_duration=0.12,
        dash_friction=15.0,
    )
    base.update(overrides)
    return _make_player(**base)


def test_draw_state_panel_none_player(player_ui: PlayerUI) -> None:
    assert player_ui.draw_state_panel(0, 0, None) == 0


def test_draw_state_panel_no_state_machine(player_ui: PlayerUI) -> None:
    player = _make_player(state_machine=None)
    assert player_ui.draw_state_panel(0, 0, player) == 0


def test_draw_state_panel_draws(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_state_panel_with_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        combat=SimpleNamespace(
            state=SimpleNamespace(
                attack_name="slash",
                phase_index=0,
                current_attack_def=SimpleNamespace(phases=[]),
            ),
            hurt_timer=0.0,
            is_hurt=False,
            charging=None,
            cooldowns={},
            combo_count=0,
            combo_timer=0.0,
        ),
    )
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_state_panel_is_hurt_shows_line(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        combat=SimpleNamespace(
            state=SimpleNamespace(
                attack_name="-", phase_index=0, current_attack_def=None
            ),
            hurt_timer=0.2,
            is_hurt=True,
            charging=None,
            cooldowns={},
            combo_count=1,
            combo_timer=0.3,
        ),
    )
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_none_player(player_ui: PlayerUI) -> None:
    assert player_ui.draw_stats_panel(0, 0, None) == 0


def test_draw_stats_panel_draws(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_low_health(player_ui: PlayerUI) -> None:
    player = _make_full_player(health=10.0, max_health=100.0, combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_with_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        health=80.0,
        combat=SimpleNamespace(combo_count=3, combo_timer=0.5),
    )
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_without_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0