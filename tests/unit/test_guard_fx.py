"""Guard feedback: spark FX, guard events, parry hit-stop, overlay cues."""

from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core import fx
from src.core.fx import (
    SparkParticle,
    spawn_break_burst,
    spawn_guard_spark,
    spawn_parry_burst,
)
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.settings import Guard as GuardSettings
from src.entities.player import Player
from tests.unit.helpers import InputStub, make_active_attacker


def _entity() -> SimpleNamespace:
    return SimpleNamespace(hitbox=pygame.FRect(100, 100, 40, 48))


def test_spark_fades_and_reaps_itself() -> None:
    group = Group()
    spark = SparkParticle((10.0, 10.0), (100.0, -50.0), (255, 255, 255))
    group.add(spark)

    spark.update(fx.SPARK_TTL / 2.0)

    assert spark.alive()
    assert 0 <= (spark.image.get_alpha() if spark.image else 255) < 255
    spark.update(fx.SPARK_TTL)

    assert not spark.alive()
    assert len(group) == 0


def test_guard_spawners_emit_expected_counts() -> None:
    entity = _entity()

    assert len(spawn_guard_spark(Group(), entity)) == fx.GUARD_SPARK_COUNT
    assert len(spawn_parry_burst(Group(), entity)) == fx.PARRY_SPARK_COUNT
    assert len(spawn_break_burst(Group(), entity)) == fx.BREAK_SPARK_COUNT


def test_guard_spawners_respect_budget_and_missing_hitbox() -> None:
    full = Group()
    for _ in range(fx.MAX_FX_SPRITES):
        full.add(SparkParticle((0.0, 0.0), (0.0, 0.0), (255, 255, 255)))

    assert spawn_guard_spark(full, _entity()) == []
    assert spawn_parry_burst(Group(), SimpleNamespace()) == []
    assert spawn_break_burst(Group(), SimpleNamespace()) == []


def test_parry_burst_kicks_upward() -> None:
    entity = _entity()

    for spark in spawn_parry_burst(Group(), entity):
        assert spark.velocity.y < 0.0


def _guard_player(posture: float = 100.0, parry: bool = False) -> Player:
    player = Player(
        pos=(0.0, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.state_machine.current_state_name = "guard"
    player.facing_right = False
    player.guard.posture = posture
    if parry:
        player.guard.press()
    return player


def test_combat_system_records_guard_event() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert len(system.guard_events) == 1
    assert system.guard_events[0].kind == "guard"
    assert system.guard_events[0].target is player


def test_combat_system_records_parry_event_with_bonus_hitstop() -> None:
    player = _guard_player(parry=True)
    attacker = make_active_attacker(player)
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert [event.kind for event in system.guard_events] == ["parry"]
    assert system.hit_stop_timer >= GuardSettings.PARRY_HITSTOP


def test_combat_system_records_break_event() -> None:
    player = _guard_player(posture=5.0)
    attacker = make_active_attacker(player)
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert [event.kind for event in system.guard_events] == ["break"]


def test_guard_events_clear_each_tick() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    system = CombatSystem()
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert len(system.guard_events) == 1

    system.process_attacks([])

    assert system.guard_events == []


def _loop_with_camera() -> tuple[GameplayLoop, SimpleNamespace]:
    camera = SimpleNamespace(traumas=[], add_trauma=lambda amount: camera.traumas.append(amount))
    loop = GameplayLoop(camera_system=camera)  # type: ignore[arg-type]
    return loop, camera


def test_game_loop_drains_guard_events_into_fx_and_trauma() -> None:
    player = _guard_player(parry=True)
    attacker = make_active_attacker(player)
    loop, camera = _loop_with_camera()
    loop.combat_system.process_attacks([attacker, player])  # type: ignore[list-item]
    groups = SimpleNamespace(fx_sprites=Group())

    loop._emit_guard_fx(groups, loop.camera_system)

    assert len(groups.fx_sprites) == fx.PARRY_SPARK_COUNT
    assert camera.traumas == [pytest.approx(GuardSettings.PARRY_TRAUMA)]
    assert loop.combat_system.guard_events == []


def test_game_loop_guard_trauma_uses_strongest_event() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    loop, camera = _loop_with_camera()
    loop.combat_system.process_attacks([attacker, player])  # type: ignore[list-item]
    groups = SimpleNamespace(fx_sprites=Group())

    loop._emit_guard_fx(groups, loop.camera_system)

    assert len(groups.fx_sprites) == fx.GUARD_SPARK_COUNT
    assert camera.traumas == [pytest.approx(GuardSettings.GUARD_TRAUMA)]


def test_game_loop_skips_fx_without_events() -> None:
    loop, camera = _loop_with_camera()
    groups = SimpleNamespace(fx_sprites=Group())

    loop._emit_guard_fx(groups, loop.camera_system)

    assert len(groups.fx_sprites) == 0
    assert camera.traumas == []
