"""A frame drawn between two ticks shows a fighter between its two positions."""

from __future__ import annotations

import pygame
import pytest

from src.simulation.settings import Interpolation
from tests.headless.test_combat_dynamism import DT, _arena


def _drawn_x(level, alpha: float) -> int:
    level.renderer.draw(level.groups, alpha=alpha)
    return level.renderer._drawn_rect(level.player, level.player.rect).x


def _running(level, pad) -> None:
    pad.axis = 1.0
    for _ in range(90):
        level.update(DT)


def test_a_running_fighter_is_drawn_between_the_last_two_ticks() -> None:
    level, pad, player = _arena()
    _running(level, pad)
    start = player.render_hints.previous_center[0] - player.hitbox.width / 2
    now = player.rect.x
    assert now > start, "the fighter moved during the last tick"

    assert _drawn_x(level, 1.0) == pytest.approx(now)
    assert _drawn_x(level, 0.0) == pytest.approx(player.rect.x + (start - player.hitbox.x))
    assert _drawn_x(level, 0.0) < _drawn_x(level, 0.5) < _drawn_x(level, 1.0)


def test_a_frozen_tick_draws_the_fighter_still() -> None:
    level, pad, player = _arena()
    _running(level, pad)
    level.gameplay_loop.combat_system.hit_stop_timer = 0.2
    level.update(DT)

    assert _drawn_x(level, 0.0) == _drawn_x(level, 1.0)


def test_a_teleport_is_drawn_where_it_lands() -> None:
    level, pad, player = _arena()
    _running(level, pad)
    player.render_hints.previous_center = (
        player.hitbox.centerx - Interpolation.MAX_STEP_PX - 1.0,
        player.hitbox.centery,
    )

    assert _drawn_x(level, 0.0) == pytest.approx(player.rect.x)


def test_the_health_bar_follows_the_drawn_fighter() -> None:
    level, pad, _player = _arena()
    from tests.headless.test_combat_dynamism import _foe

    foe = _foe(level, "goblin", 1300.0)
    foe.render_hints.previous_center = (foe.hitbox.centerx - 40.0, foe.hitbox.centery)
    level.renderer.draw(level.groups, alpha=0.0)
    calls: list[dict] = []
    level.renderer.overlay.draw_health_bars = (  # type: ignore[method-assign]
        lambda entities, camera, screen_rects=None: calls.append(screen_rects or {}) or []
    )

    level.renderer.draw_health_bars(level.groups.fighters)

    assert calls[0][id(foe)].x == pytest.approx(level.camera.apply(foe.hitbox).x - 40.0, abs=0.5)
    assert isinstance(calls[0][id(foe)], pygame.FRect)
