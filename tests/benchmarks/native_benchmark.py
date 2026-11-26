"""One workload, run against interpreted and mypyc-compiled physics modules.

This is the measurement half of E2. It is deliberately small: it exercises
what actually got compiled -- the spatial hash and its query port, gravity,
friction and moving platforms -- on synthetic objects, so the two modes differ
only in the module objects behind those calls. :mod:`tools.benchmark_native`
runs this script in both trees in alternating order and compares the results.

The checksum is part of the contract: a faster mode that computes a different
world is not an optimization.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
from pygame.math import Vector2  # noqa: E402

from src.simulation.physics.gravity import apply_entity_gravity  # noqa: E402
from src.simulation.physics.platforms import update_moving_platform  # noqa: E402
from src.simulation.physics.spatial_hash import SpatialHash  # noqa: E402
from src.simulation.physics.spatial_query import make_query  # noqa: E402
from src.simulation.physics.velocity import (  # noqa: E402
    apply_slide_friction,
    apply_velocity_friction,
    lerp_velocity,
)

DT = 1.0 / 60.0


class Tile:
    __slots__ = ("rect",)

    def __init__(self, x: int, y: int) -> None:
        self.rect = pygame.Rect(x, y, 64, 64)


class Body:
    __slots__ = (
        "velocity",
        "normal_gravity",
        "fall_gravity",
        "slide_gravity",
        "max_slide_speed",
        "max_fall_speed",
        "drag_coefficient",
        "fall_drag_coefficient",
        "gravity_scale",
        "fast_fall",
    )

    def __init__(self, index: int) -> None:
        self.velocity = Vector2(float(index % 60) * 3.0, -40.0)
        self.normal_gravity = 1500.0
        self.fall_gravity = 2200.0
        self.slide_gravity = 300.0
        self.max_slide_speed = 120.0
        self.max_fall_speed = 900.0
        self.drag_coefficient = 0.5
        self.fall_drag_coefficient = 0.1
        self.gravity_scale = 1.0
        self.fast_fall = index % 3 == 0

    def is_wall_sliding(self) -> bool:
        return self.velocity.x > 170.0


class Platform:
    __slots__ = (
        "rect",
        "hitbox",
        "old_rect",
        "old_hitbox",
        "pos",
        "waypoints",
        "current_target",
        "direction",
        "speed",
    )

    def __init__(self, index: int) -> None:
        self.pos = Vector2(float(index * 40), 100.0)
        self.rect = pygame.Rect(self.pos.x, self.pos.y, 64, 16)
        self.hitbox = pygame.Rect(self.rect)
        self.old_rect = pygame.Rect(self.rect)
        self.old_hitbox = pygame.Rect(self.rect)
        self.waypoints = (Vector2(float(index * 40), 100.0), Vector2(600.0, 200.0))
        self.current_target = 1
        self.direction = 1
        self.speed = 60.0


def build():
    tiles = tuple(Tile(x, y) for y in range(0, 1920, 96) for x in range(0, 2560, 96))
    spatial_hash = SpatialHash()
    spatial_hash.add_all(tiles)
    boxes = tuple(pygame.Rect(x * 64, y * 64, 48, 48) for y in range(12) for x in range(14))
    bodies = tuple(Body(index) for index in range(256))
    platforms = tuple(Platform(index) for index in range(16))
    return make_query(spatial_hash, None), boxes, bodies, platforms


def once(query, boxes, bodies, platforms) -> float:
    candidates = 0
    for box in boxes:
        # The hash and the query port are two of the compiled modules. Without
        # feeding their result into the checksum the A/B could agree while
        # both returned nonsense.
        candidates += len(query.get_nearby(box))
    for body in bodies:
        apply_entity_gravity(body, DT)
        apply_velocity_friction(body, 8.0, DT)
        lerp_velocity(body, 100.0, 4.0, DT)
        apply_slide_friction(body, 600.0, 2.0, DT)
    for platform in platforms:
        update_moving_platform(platform, DT)
    return round(
        sum(body.velocity.y for body in bodies)
        + sum(body.velocity.x for body in bodies)
        + sum(p.pos.x for p in platforms)
        + candidates,
        3,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    pygame.init()
    query, boxes, bodies, platforms = build()
    once(query, boxes, bodies, platforms)
    checksum = once(query, boxes, bodies, platforms)

    samples: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        for _ in range(args.iterations):
            once(query, boxes, bodies, platforms)
        samples.append((time.perf_counter() - started) * 1000.0 / args.iterations)

    print(
        json.dumps(
            {
                "checksum": checksum,
                "median_ms": statistics.median(samples),
                "samples_ms": [round(sample, 4) for sample in samples],
                "module_files": [
                    sys.modules[apply_entity_gravity.__module__].__file__,
                    sys.modules[SpatialHash.__module__].__file__,
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
