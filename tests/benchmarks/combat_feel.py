"""How the combat plays, in numbers: a duel in a flat arena with a scripted pad.

Not a timing benchmark. The simulation is deterministic, so every figure here
is a property of the tuning in ``data/gameplay/*.json`` and ``settings.py``:
how often the player can swing, how many swings land, how long each enemy
takes to kill, how much warning an enemy attack gives, how much a passive
player loses. Run it before and after a tuning change and compare.

    uv run python tests/benchmarks/combat_feel.py
    uv run python tests/benchmarks/combat_feel.py --seconds 10 --json

The player keeps within reach of the enemy (``KEEP_PX``) and presses a button
on every other tick: the best a human masher can do. A prompt -- the death
blow, a throw, a blade lock -- is answered as soon as it shows. No art is
needed.

``mash_slash_vs_<enemy>`` kills with the blade and the death blow;
``mash_beat_vs_<enemy>`` stuns with the body and throws. ``perfect_dodge_ticks``
is how many ticks before a blow lands a dash still slows the world.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from src.combat.frame_data import PhaseState  # noqa: E402
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
from src.entities.player_kit import Direction  # noqa: E402

DT = 1 / 60
#: Every fighter's RNG is seeded before the warm-up, so two processes produce
#: the same report. Without this, ``Entity`` builds an unseeded ``Random`` and
#: the duels with AI differ run to run (guard height, move choice, prompts).
SEED = 20260913
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
        id_factory=level.id_factory,
    )
    foe.animator = None
    level.groups.add_fighter(foe)
    # Seed before the settling ticks: the constructor has already drawn the
    # patrol direction, so that one has to be redrawn from the seeded stream.
    player.rng = random.Random(SEED)
    foe.rng = random.Random(SEED + 1)
    if config.reverse is None:
        foe.patrol_direction = 1 if foe.rng.random() > 0.5 else -1
    for _ in range(60):
        level.update(DT)
    return level, pad, player, foe


@dataclass
class _Span:
    """One started attack, from its first active frame to its cancel or end."""

    name: str
    start: int
    hits: int = 0
    blocks: int = 0
    recovery: int = 0


class _FeelTrace:
    """Collect the feel figures the basic duel counters cannot see.

    ``start_attack`` is wrapped because a chained move never leaves ATTACK, so
    watching that state rise misses it; ``record_contact`` and
    ``guards_against`` are wrapped because the guard events are drained by the
    feedback stage before the caller can read them.
    """

    def __init__(self, player: Player, foe: Enemy) -> None:
        self.player = player
        self.foe = foe
        self.tick = 0
        self.spans: list[_Span] = []
        self.current: _Span | None = None
        self.attempts = 0
        self.cancels = 0
        self.contact_at = -1
        self.guard_at = -1
        self.hitstop: dict[str, list[float]] = defaultdict(list)
        self.advantage: dict[str, list[int]] = defaultdict(list)
        self.combo_peaks: list[int] = []
        self._peak = 0
        self._start = player.combat.start_attack
        self._contact = player.combat.record_contact
        self._guard = foe.guards_against
        player.combat.start_attack = self.on_start  # type: ignore[method-assign]
        player.combat.record_contact = self.on_contact  # type: ignore[method-assign]
        foe.guards_against = self.on_guard  # type: ignore[method-assign]

    def on_start(self, name: object, *args: object, **kwargs: object) -> object:
        busy = self.player.combat.state.is_attacking
        refusal = self._start(name, *args, **kwargs)  # type: ignore[arg-type]
        if busy:
            self.attempts += 1
            if refusal is Refusal.NONE:
                self.cancels += 1
        if refusal is Refusal.NONE:
            self.current = _Span(str(name), self.tick)
            self.spans.append(self.current)
        return refusal

    def on_contact(self, target_id: str) -> None:
        self.contact_at = self.tick
        self._contact(target_id)

    def on_guard(self, height: object, unblockable: object, source_x: object) -> bool:
        stopped = self._guard(height, unblockable, source_x)  # type: ignore[arg-type]
        if stopped:
            self.guard_at = self.tick
        return bool(stopped)

    def after_tick(self, level: Level, name_before: str | None, sub_before: object) -> None:
        state = self.player.combat.state
        if sub_before is PhaseState.RECOVERY and self.current is not None:
            self.current.recovery += 1
        self._peak = max(self._peak, self.player.combat.combo_count)
        if self.contact_at != self.tick and self.guard_at != self.tick:
            return
        kind = "block" if self.guard_at == self.tick else "hit"
        if self.current is not None:
            if kind == "hit":
                self.current.hits += 1
            else:
                self.current.blocks += 1
        key = name_before or "?"
        self.hitstop[key].append(round(level.gameplay_loop.combat_system.hit_stop_timer, 4))
        phase = state.current_phase_def
        if phase is None or (phase.cancel_on_hit and self.player.combat.targets_hit):
            attacker_left = 0
        elif state.sub_state is PhaseState.RECOVERY:
            attacker_left = max(0, phase.recovery_frames - state.frame_counter)
        elif state.sub_state is PhaseState.ACTIVE:
            attacker_left = (phase.active_frames - state.frame_counter) + phase.recovery_frames
        else:
            attacker_left = 0
        defender_left = math.ceil(max(self.foe.combat.hurt_timer, self.foe.stagger_timer) / DT)
        self.advantage[kind].append(defender_left - attacker_left)
        self.contact_at = self.guard_at = -1


def _duel(
    script: Script, seconds: float, enemy: str, ai: bool = True, health: float | None = None
) -> dict[str, object]:
    level, pad, player, foe = _arena(enemy, ai, health)
    started = _count_starts(player)
    trace = _FeelTrace(player, foe)
    landed = frozen = stunned_at = 0
    taken = 0.0
    foe_health, player_health = foe.health, player.health
    ticks = int(seconds * 60)
    killed_at: float | None = None
    for tick in range(ticks):
        pad.held = script(tick)
        pad.axis = _follow(player, foe)
        if player.prompt.active:
            pad.axis, pad.held = _answer(player, tick)
        frozen += level.gameplay_loop.combat_system.in_hit_stop
        trace.tick = tick
        state = player.combat.state
        name_before = str(state.attack_name) if state.attack_name is not None else None
        sub_before = state.sub_state
        level.update(DT)
        trace.after_tick(level, name_before, sub_before)
        landed += foe.health < foe_health
        foe_health = foe.health
        if not stunned_at and foe.is_stunned:
            stunned_at = tick + 1
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
        "stun_s": round(stunned_at / 60, 2) if stunned_at else None,
        "hp_lost": round(taken, 1),
        "hit_stop_share": round(frozen / ticks, 2),
        "cancel_success_ratio": (
            round(trace.cancels / trace.attempts, 3) if trace.attempts else 0.0
        ),
        "hitstop_by_move": {
            name: round(sum(values) / len(values), 4)
            for name, values in sorted(trace.hitstop.items())
        },
        "frame_advantage": {
            kind: round(sum(values) / len(values))
            for kind, values in sorted(trace.advantage.items())
        },
        "combo_peak": max(trace._peak, player.combat.combo_count),
        "recovery_after_whiff": (
            round(
                sum(span.recovery for span in trace.spans if not span.hits and not span.blocks)
                / max(1, sum(1 for span in trace.spans if not span.hits and not span.blocks)),
                2,
            )
        ),
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


#: The stick and the buttons that give each direction a prompt asks for.
_DIRECTIONS: dict[Direction, tuple[float, frozenset[InputAction]]] = {
    Direction.LEFT: (-1.0, frozenset()),
    Direction.RIGHT: (1.0, frozenset()),
    Direction.UP: (0.0, frozenset({InputAction.JUMP})),
    Direction.DOWN: (0.0, frozenset({InputAction.MOVE_DOWN})),
}


def _answer(player: Player, tick: int) -> tuple[float, frozenset[InputAction]]:
    """The answer to the prompt up: its direction every other tick, or the slash mashed."""
    if tick % 2 == 0:
        return 0.0, frozenset()
    expected = player.prompt.expected
    if expected is None:
        return 0.0, frozenset({InputAction.ATTACK_1})
    return _DIRECTIONS[expected]


def _follow(player: Player, foe: Enemy) -> float:
    dx = foe.hitbox.centerx - player.hitbox.centerx
    gap = abs(dx) - (foe.hitbox.w + player.hitbox.w) / 2
    return (1.0 if dx > 0 else -1.0) if gap > KEEP_PX else 0.0


def _mash(button: InputAction) -> Script:
    return lambda tick: frozenset({button}) if tick % 2 == 0 else frozenset()


def _idle(_tick: int) -> frozenset[InputAction]:
    return frozenset()


def _dodges_perfectly(lead: int) -> bool:
    """Whether a dash thrown ``lead`` ticks before a goblin's blow lands slows the world."""
    level, pad, player, foe = _arena("goblin")
    for _ in range(600):
        state = foe.combat.state
        phase = state.current_phase_def
        if (
            phase is not None
            and state.sub_state is PhaseState.STARTUP
            and phase.startup_frames - state.frame_counter == lead + 1
        ):
            break
        level.update(DT)
    else:
        return False
    pad.axis = -1.0 if foe.hitbox.centerx > player.hitbox.centerx else 1.0
    pad.held = frozenset({InputAction.DASH})
    level.update(DT)
    pad.held = frozenset()
    pad.axis = 0.0
    for _ in range(lead + 10):
        level.update(DT)
        if player.rush_timer > 0.0:
            return True
    return False


def _perfect_dodge_ticks() -> int:
    """The longest lead, in ticks, at which a dash away is still a perfect dodge."""
    lead = 0
    while lead < 60 and _dodges_perfectly(lead):
        lead += 1
    return lead


def measure(seconds: float) -> dict[str, object]:
    """Every figure of the report, keyed by what it measures."""
    report: dict[str, object] = {}
    for name, button in (
        ("slash", InputAction.ATTACK_1),
        ("beat", InputAction.ATTACK_2),
    ):
        report[f"mash_{name}_vs_target"] = _duel(
            _mash(button), seconds, "goblin", ai=False, health=1e6
        )
    for enemy in FIGHTERS:
        report[f"mash_slash_vs_{enemy}"] = _duel(_mash(InputAction.ATTACK_1), 3 * seconds, enemy)
    for enemy in FIGHTERS:
        report[f"mash_beat_vs_{enemy}"] = _duel(_mash(InputAction.ATTACK_2), 3 * seconds, enemy)
    report["idle_vs_goblin"] = _duel(_idle, seconds, "goblin")
    report["perfect_dodge_ticks"] = _perfect_dodge_ticks()
    attacks = shipped_gameplay_data().attack_sets
    report["enemy_warning_ms"] = {
        f"{owner}.{name}": round(attack.phases[0].startup_frames / 60 * 1000)
        for owner, table in attacks.items()
        if owner != "player"
        for name, attack in table.items()
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
