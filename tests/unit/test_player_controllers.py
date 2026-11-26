"""Unit tests for the player's jump and dash controllers."""

import pygame
import pytest

from src.simulation.entities.player_config import PlayerConfig
from src.simulation.entities.player_controllers import DashController, JumpController


@pytest.fixture
def config() -> PlayerConfig:
    return PlayerConfig(
        max_midair_jumps=1,
        max_wall_jumps=2,
        coyote_duration=0.1,
        jump_buffer_duration=0.2,
        max_dash_charges=3,
        dash_recharge_time=1.0,
        dash_penalty_duration=2.0,
    )


class TestJumpController:
    def test_update_refills_coyote_while_on_floor(self, config) -> None:
        jump = JumpController(config)

        jump.update(0.016, on_floor=True)

        assert jump.coyote_timer == pytest.approx(0.1)

    def test_update_decays_coyote_in_the_air(self, config) -> None:
        jump = JumpController(config)
        jump.update(0.016, on_floor=True)

        jump.update(0.04, on_floor=False)

        assert jump.coyote_timer == pytest.approx(0.06)

    def test_buffer_press_arms_buffer_then_decays(self, config) -> None:
        jump = JumpController(config)

        jump.buffer_press()
        assert jump.has_buffered_jump()

        jump.update(0.2, on_floor=False)
        assert not jump.has_buffered_jump()

    def test_restore_ground_jumps_refills_all_stocks(self, config) -> None:
        jump = JumpController(config)
        jump.midair_jumps_left = 0
        jump.wall_jumps_left = 0

        jump.restore_ground_jumps()

        assert jump.midair_jumps_left == 1
        assert jump.wall_jumps_left == 2

    def test_restore_midair_jumps_keeps_wall_stocks(self, config) -> None:
        jump = JumpController(config)
        jump.midair_jumps_left = 0
        jump.wall_jumps_left = 1

        jump.restore_midair_jumps()

        assert jump.midair_jumps_left == 1
        assert jump.wall_jumps_left == 1

    def test_reset_restores_timers_and_stocks(self, config) -> None:
        jump = JumpController(config)
        jump.buffer_press()
        jump.update(0.016, on_floor=True)
        jump.midair_jumps_left = 0
        jump.wall_jumps_left = 0

        jump.reset()

        assert jump.jump_buffer_timer == 0.0
        assert jump.coyote_timer == 0.0
        assert jump.midair_jumps_left == 1
        assert jump.wall_jumps_left == 2


class TestDashController:
    def test_request_gated_by_charges_and_penalty(self, config) -> None:
        dash = DashController(config)
        dash.request()
        assert dash.can_use()

        dash.charges = 0
        dash.request()
        assert not dash.can_use()

        dash.charges = 1
        dash.penalty_timer = 0.5
        dash.request()
        assert not dash.requested

    def test_consume_charge_arms_recharge_then_penalty(self, config) -> None:
        dash = DashController(config)

        dash.consume_charge()
        assert dash.charges == 2
        assert dash.recharge_timer == pytest.approx(1.0)
        assert dash.penalty_timer == 0.0

        dash.charges = 1
        dash.consume_charge()
        assert dash.charges == 0
        assert dash.penalty_timer == pytest.approx(2.0)

    def test_update_recharges_one_charge_per_window(self, config) -> None:
        dash = DashController(config)
        dash.charges = 2
        dash.consume_charge()

        dash.update(0.6)
        assert dash.charges == 1

        dash.update(0.4)
        assert dash.charges == 2
        assert dash.recharge_timer == pytest.approx(1.0)

    def test_update_waits_for_penalty_before_recharging(self, config) -> None:
        dash = DashController(config)
        dash.charges = 1
        dash.consume_charge()

        dash.update(2.0)
        assert dash.charges == 0

        dash.update(1.0)
        assert dash.charges == 1
        assert dash.penalty_timer <= 0

    def test_squish_and_restore_hitbox_keeps_center(self, config) -> None:
        dash = DashController(config, original_hitbox_width=50.0)
        hitbox = pygame.FRect(100.0, 0.0, 50.0, 60.0)

        dash.apply_squish(hitbox)
        assert hitbox.width == pytest.approx(30.0)
        assert hitbox.centerx == pytest.approx(125.0)

        assert dash.restore_hitbox(hitbox)
        assert hitbox.width == pytest.approx(50.0)
        assert hitbox.centerx == pytest.approx(125.0)
        assert not dash.restore_hitbox(hitbox)

    def test_reset_refills_charges_and_clears_request(self, config) -> None:
        dash = DashController(config)
        dash.charges = 0
        dash.penalty_timer = 1.0
        dash.recharge_timer = 0.5
        dash.requested = True

        dash.reset()

        assert dash.charges == 3
        assert dash.penalty_timer == 0.0
        assert dash.recharge_timer == 0.0
        assert not dash.requested
