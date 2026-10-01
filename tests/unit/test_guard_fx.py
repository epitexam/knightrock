"""Guard feedback: the block ring, guard events, parry hit-stop, overlay cues."""

from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core import fx
from src.core.colors import FXColors
from src.core.fx import (
    ShieldArcParticle,
    spawn_guard_arc,
    spawn_shatter_arc,
)
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.settings import FxGuard
from src.core.settings import Guard as GuardSettings
from src.entities.player import Player
from tests.unit.helpers import InputStub, make_active_attacker


def _entity() -> SimpleNamespace:
    return SimpleNamespace(hitbox=pygame.FRect(100, 100, 40, 48))


def test_the_block_arc_fades_and_reaps_itself() -> None:
    group = Group()
    arc = spawn_guard_arc(group, _entity())
    assert arc is not None
    group.add(arc)

    arc.update(FxGuard.ARC_TTL / 2.0)

    assert arc.alive()
    assert 0 <= (arc.image.get_alpha() if arc.image else 255) < 255
    arc.update(FxGuard.ARC_TTL)

    assert not arc.alive()
    assert len(group) == 0


def test_a_block_is_one_ring_and_nothing_else() -> None:
    """A block is a single arc, not a fan of thrown particles.

    The fan read as an explosion inside the defender, and the particles were
    the last thing carrying a four-pointed star into every exchange.
    """
    entity = _entity()
    group = Group()

    arc = spawn_guard_arc(group, entity)

    assert isinstance(arc, ShieldArcParticle)
    assert len(group) == 1
    assert [type(sprite) for sprite in group] == [ShieldArcParticle]


def test_a_perfect_block_is_the_same_ring_in_gold() -> None:
    entity = _entity()
    group = Group()

    arc = spawn_guard_arc(group, entity, parried=True)

    assert arc is not None
    assert len(group) == 1
    assert arc.parried is True
    assert arc.body == FXColors.parry_spark


def test_a_break_spawns_the_broken_ring() -> None:
    """The ring coming apart, on the side the guard gave way on."""
    entity = _entity()
    entity.facing_right = True
    group = Group()

    shatter = spawn_shatter_arc(group, entity)

    assert shatter is not None
    assert shatter.side == 1.0
    assert len(group) == 1
    assert len(shatter.steps) == FxGuard.SHARD_STEPS


def test_guard_spawners_respect_budget_and_missing_hitbox() -> None:
    full = Group()
    for _ in range(fx.MAX_FX_SPRITES):
        full.add(ShieldArcParticle((0.0, 0.0), 1.0))

    assert spawn_guard_arc(full, _entity()) is None
    assert spawn_shatter_arc(full, _entity()) is None
    assert spawn_guard_arc(Group(), SimpleNamespace()) is None
    assert spawn_shatter_arc(Group(), SimpleNamespace()) is None


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

    assert len(groups.fx_sprites) == 1, "the gold ring alone"
    assert camera.traumas == [pytest.approx(GuardSettings.PARRY_TRAUMA)]
    assert loop.combat_system.guard_events == []


def test_game_loop_guard_trauma_uses_strongest_event() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    loop, camera = _loop_with_camera()
    loop.combat_system.process_attacks([attacker, player])  # type: ignore[list-item]
    groups = SimpleNamespace(fx_sprites=Group())

    loop._emit_guard_fx(groups, loop.camera_system)

    assert len(groups.fx_sprites) == 1, "the ring alone"
    assert camera.traumas == [pytest.approx(GuardSettings.GUARD_TRAUMA)]


def test_game_loop_skips_fx_without_events() -> None:
    loop, camera = _loop_with_camera()
    groups = SimpleNamespace(fx_sprites=Group())

    loop._emit_guard_fx(groups, loop.camera_system)

    assert len(groups.fx_sprites) == 0
    assert camera.traumas == []
