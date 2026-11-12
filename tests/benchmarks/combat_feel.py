"""How the combat plays, in numbers: a duel in a flat arena with a scripted pad.

Not a timing benchmark. The simulation is deterministic, so every figure here
is a property of the tuning in ``data/gameplay/*.json`` and ``settings.py``:
how often the player can swing, how many swings land, how long each enemy
takes to kill, how much warning an enemy attack gives, how much a passive
player loses. Run it before and after a tuning change and compare.

    uv run python tests/benchmarks/combat_feel.py
    uv run python tests/benchmarks/combat_feel.py --seconds 10 --json

The player keeps within reach of the enemy (``KEEP_PX``) and presses a button
on every other tick: the best a human masher can do. No art is needed.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from src.combat.refusal import Refusal  # noqa: E402
from src.core.input.input_actions import InputAction  # noqa: E402
from src.core.input.input_manager import InputManager  # noqa: E402
from src.core.input.input_provider import InputProvider  # noqa: E402
from src.core.input.input_state import InputState  # noqa: E402
from src.core.level.level import Level  # noqa: E402
from src.core.level.level_data import (  # noqa: E402
    LevelConfig,
    LevelData,
    ObjectData,
    ObjectLayerData,
)
from src.core.sprites import Sprite  # noqa: E402
from src.data.provider import shipped_gameplay_data  # noqa: E402
from src.entities.enemies.enemy import Enemy  # noqa: E402
from src.entities.enemies.factory import create_enemy  # noqa: E402
from src.entities.player import Player  # noqa: E402

DT = 1 / 60
#: How close the scripted player stays to its enemy, edge to edge.
KEEP_PX = 8.0
#: The enemies a level places (the dummy is a test target, not a fight).
FIGHTERS = ("goblin", "slime", "tooth", "shell")

Script = Callable[[int], frozenset[InputAction]]


class _Pad(InputProvider):
    def __init__(self) -> None:
        self.held: frozenset[InputAction] = frozenset()
        self.axis = 0.0

    def poll(self) -> InputState:
        return InputState(move_axis=self.axis, held_actions=self.held)


def _arena(enemy: str, ai: bool = True, health: float | None = None):
    pad = _Pad()
    data = shipped_gameplay_data()
    spawn = ObjectData(
        name="player",
        x=1000.0,
        y=300.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )
    level_data = LevelData(
        width=80,
        height=12,
        tile_size=64,
        object_layers={"Entities": ObjectLayerData(name="Entities", objects=[spawn])},
        config=LevelConfig(),
    )
    level = Level(pygame.Surface((1152, 648)), level_data, InputManager(pad), gameplay_data=data)
    floor = Sprite(
        (0.0, 400.0), surf=pygame.Surface((5000, 64)), groups=(level.groups.collision_sprites,)
    )
    level.spatial_hash.add(floor)
    player = level.player
    player.animator = None
    config = data.enemies[enemy]
    if not ai:
        config = replace(config, has_ai=False)
    if health is not None:
        config = replace(config, health=health, max_health=health)
    foe = create_enemy(
        enemy,
        (1060.0, 340.0),
        (level.groups.all_sprites,),
        level.groups.collision_sprites,
        player,
        config=config,
        spatial_hash=level.spatial_hash,
    )
    foe.animator = None
    level.groups.add_fighter(foe)
    for _ in range(60):
        level.update(DT)
    return level, pad, player, foe


def _duel(
    script: Script, seconds: float, enemy: str, ai: bool = True, health: float | None = None
) -> dict[str, float | None]:
    level, pad, player, foe = _arena(enemy, ai, health)
    started = _count_starts(player)
    landed = frozen = 0
    taken = 0.0
    foe_health, player_health = foe.health, player.health
    ticks = int(seconds * 60)
    killed_at: float | None = None
    for tick in range(ticks):
        pad.held = script(tick)
        pad.axis = _follow(player, foe)
        frozen += level.gameplay_loop.combat_system.in_hit_stop
        level.update(DT)
        landed += foe.health < foe_health
        foe_health = foe.health
        taken += max(0.0, player_health - player.health)
        player_health = player.health
        if foe.is_dead:
            killed_at = (tick + 1) / 60
            ticks = tick + 1
            break
    elapsed = ticks / 60
    swings = started[0]
    return {
        "swings_per_s": round(swings / elapsed, 2),
        "hits_per_s": round(landed / elapsed, 2),
        "landed_ratio": round(landed / swings, 2) if swings else 0.0,
        "kill_s": round(killed_at, 2) if killed_at is not None else None,
        "hp_lost": round(taken, 1),
        "hit_stop_share": round(frozen / ticks, 2),
    }


def _count_starts(player: Player) -> list[int]:
    """Count every attack the player actually starts, chained ones included.

    Watching ``is_attacking`` rise misses a move cancelled into itself: the
    fighter never stops attacking between the two.
    """
    count = [0]
    start = player.combat.start_attack

    def counted(*args: object, **kwargs: object) -> object:
        refusal = start(*args, **kwargs)  # type: ignore[arg-type]
        count[0] += refusal is Refusal.NONE
        return refusal

    player.combat.start_attack = counted  # type: ignore[method-assign]
    return count


def _follow(player: Player, foe: Enemy) -> float:
    dx = foe.hitbox.centerx - player.hitbox.centerx
    gap = abs(dx) - (foe.hitbox.w + player.hitbox.w) / 2
    return (1.0 if dx > 0 else -1.0) if gap > KEEP_PX else 0.0


def _mash(button: InputAction) -> Script:
    return lambda tick: frozenset({button}) if tick % 2 == 0 else frozenset()


def _idle(_tick: int) -> frozenset[InputAction]:
    return frozenset()


def measure(seconds: float) -> dict[str, object]:
    """Every figure of the report, keyed by what it measures."""
    report: dict[str, object] = {}
    for name, button in (
        ("light", InputAction.ATTACK_1),
        ("heavy", InputAction.ATTACK_2),
    ):
        report[f"mash_{name}_vs_target"] = _duel(
            _mash(button), seconds, "goblin", ai=False, health=1e6
        )
    for enemy in FIGHTERS:
        report[f"mash_light_vs_{enemy}"] = _duel(_mash(InputAction.ATTACK_1), 3 * seconds, enemy)
    report["idle_vs_goblin"] = _duel(_idle, seconds, "goblin")
    attacks = shipped_gameplay_data().attack_sets
    report["enemy_warning_ms"] = {
        owner: round(next(iter(table.values())).phases[0].startup_frames / 60 * 1000)
        for owner, table in attacks.items()
        if owner != "player"
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=10.0, help="length of each duel")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args()
    pygame.init()
    pygame.display.set_mode((64, 64))
    report = measure(args.seconds)
    if args.json:
        print(json.dumps(report, indent=1))
        return
    for key, value in report.items():
        print(f"{key:24} {value}")


if __name__ == "__main__":
    main()
