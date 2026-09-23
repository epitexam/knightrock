from __future__ import annotations

import argparse
import os
from time import perf_counter
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer


def _player() -> SimpleNamespace:
    return SimpleNamespace(
        state_machine=SimpleNamespace(
            current_state_name="idle", previous_state_name=None, history=[]
        ),
        velocity=pygame.math.Vector2(0.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        move_axis=0.0,
        jump_buffer_timer=0.0,
        coyote_timer=0.0,
        midair_jumps_left=1,
        wall_jumps_left=1,
        dash=SimpleNamespace(requested=False, duration_timer=0.0),
        combat=None,
        stagger_timer=0.0,
        invincibility_timer=0.0,
        health=100.0,
        max_health=100.0,
        guard_posture=50.0,
        guard_posture_max=100.0,
        guard_lockout_timer=0.0,
        guard_riposte_timer=0.0,
        dash_charges=2,
        max_dash_charges=2,
        dash_penalty_timer=0.0,
        dash_recharge_timer=0.0,
        speed=350.0,
        floor_control=25.0,
        air_control=12.0,
        jump_height=750.0,
        wall_jump_height=600.0,
        dash_speed=800.0,
        dash_duration=0.12,
        dash_friction=15.0,
        gravity_scale=1.0,
        otg_timer=0.0,
    )


def _game() -> SimpleNamespace:
    level = SimpleNamespace(
        deaths=0,
        groups=SimpleNamespace(
            entity_sprites=[],
            hazard_sprites=[],
            projectile_sprites=[],
        ),
    )
    return SimpleNamespace(
        scene_manager=SimpleNamespace(
            current=SimpleNamespace(level_id=0, level=level),
        )
    )


def _percentile(samples: list[float], value: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * value))]


def run(size: tuple[int, int], iterations: int) -> dict[str, float]:
    pygame.init()
    pygame.display.set_mode(size)
    surface = pygame.Surface(size)
    renderer = Renderer(surface, Camera(*size))
    panel_samples: list[float] = []
    player = _player()
    game = _game()
    for _ in range(iterations):
        started = perf_counter()
        renderer.draw_debug_panels(
            player=player,
            fps=60.0,
            sprite_count=0,
            combat_count=0,
            entity_count=0,
            collision_count=0,
            hit_stop=0.0,
            spawn_cooldown=0.0,
            game=game,
            frame_time=16.0,
        )
        panel_samples.append((perf_counter() - started) * 1000.0)
    return {
        "p50": _percentile(panel_samples, 0.50),
        "p95": _percentile(panel_samples, 0.95),
        "p99": _percentile(panel_samples, 0.99),
        "max": max(panel_samples),
        "cache_entries": float(renderer.ui_manager.renderer.text_cache_stats["entries"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=300)
    args = parser.parse_args()
    for size in ((640, 480), (1024, 768), (1440, 900)):
        result = run(size, args.iterations)
        rendered = " ".join(f"{key}={value:.3f}" for key, value in result.items())
        print(f"{size[0]}x{size[1]} {rendered}")


if __name__ == "__main__":
    main()
