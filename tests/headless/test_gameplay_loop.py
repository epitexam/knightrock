"""Headless orchestration tests of the GameplayLoop (Phase 1 #10)."""

from types import SimpleNamespace

import pygame
import pytest

from src.core.level.systems.gameplay_loop import GameplayLoop
from tests.unit.helpers import activate, entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def test_hit_stop_suspends_simulation_for_its_duration() -> None:
    loop = GameplayLoop.combat_only()

    loop.combat_system.hit_stop_timer = 0.05
    suspended_delta = loop.begin_tick(1 / 60)

    assert suspended_delta == 0.0
    # update_timer already consumed dt while the simulation was frozen.
    assert loop.combat_system.hit_stop_timer < 0.05

    loop.combat_system.hit_stop_timer = 0.0
    normal_delta = loop.begin_tick(1 / 60)

    assert normal_delta == pytest.approx(1 / 60)


def test_begin_tick_returns_full_delta_without_hit_stop() -> None:
    loop = GameplayLoop.combat_only()

    delta = loop.begin_tick(1 / 60)

    assert delta == pytest.approx(1 / 60)


def test_remove_dead_entities_spares_the_player() -> None:
    loop = GameplayLoop.combat_only()
    player = PlayerStub()
    corpse = CorpseStub()

    loop.remove_dead_entities([corpse, player], player)

    assert corpse.killed
    assert not player.killed


def test_remove_dead_entities_keeps_living_entities() -> None:
    loop = GameplayLoop.combat_only()
    living = CorpseStub(is_dead=False)

    loop.remove_dead_entities([living], None)

    assert not living.killed


def test_process_combat_and_separation_is_noop_while_suspended() -> None:
    loop = GameplayLoop.combat_only()
    loop.separation_system = SeparationStub()

    loop.process_combat_and_separation(0.0, [], [])

    assert not loop.separation_system.ran


class PlayerStub:
    """Simulated player: the system must never kill it."""

    def __init__(self) -> None:
        self.is_dead = False
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class CorpseStub:
    """Simulated sprite whose dead status is driven by the test."""

    def __init__(self, *, is_dead: bool = True) -> None:
        self.is_dead = is_dead
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class SeparationStub:
    def __init__(self) -> None:
        self.ran = False

    def process(self, entity_sprites) -> list:
        self.ran = True
        return []


def _noop_stage(name: str, calls: list[str]):
    """Stage double recording the order in which the loop runs it.

    The stages have heterogeneous signatures (contact damage takes the entity
    grid, hazard damage takes the hazard sprites), hence ``*_args``.
    """
    return SimpleNamespace(process=lambda *args: calls.append(name))


def _empty_groups() -> SimpleNamespace:
    return SimpleNamespace(
        moving_platforms=[],
        hazard_sprites=[],
        entity_sprites=[],
        combat_sprites=[],
    )


def _noop_spawn_stage(name: str, calls: list[str]):
    """Spawner double: ``process(delta, player)`` head signature."""
    return SimpleNamespace(process=lambda *args: calls.append(name))


def _noop_camera_stage(name: str, calls: list[str]):
    """Camera double: ``process(delta, player)`` tail signature."""
    return SimpleNamespace(process=lambda *args: calls.append(name))


def _noop_tail_stage(name: str, calls: list[str]):
    """Notification double: ``process(player, *, deaths, exit_reached)``."""
    return SimpleNamespace(process=lambda *args, **kwargs: calls.append(name))


def _noop_respawn_stage(name: str, calls: list[str]):
    """Respawn double: ``process(delta)`` with a ``deaths`` counter."""
    return SimpleNamespace(deaths=0, process=lambda *args: calls.append(name))


def _noop_progression_stage(name: str, calls: list[str]):
    """Progression double: ``process(player)`` with an ``exit_reached`` flag."""
    return SimpleNamespace(exit_reached=False, process=lambda *args: calls.append(name))


def _noop_tick_stage(name: str, calls: list[str]):
    """Tick double: ``process(level, rollback)`` bookkeeping signature."""
    return SimpleNamespace(process=lambda *args: calls.append(name))


def _noop_rollback() -> SimpleNamespace:
    """Rollback double: recording is a no-op (tick-owner flag gates it)."""
    return SimpleNamespace(record=lambda level: None)


def _noop_level() -> SimpleNamespace:
    """Tick-owner double: rollback disabled, counter ignored, snapshot hook."""
    return SimpleNamespace(tick=0, rollback_enabled=False, save_state=lambda: SimpleNamespace())


def test_update_sequences_the_stages_in_their_historical_order() -> None:
    """The pipeline order is load-bearing: it must not drift (audit F1.6)."""
    calls: list[str] = []
    loop = GameplayLoop(
        platform_system=_noop_stage("platform", calls),
        hazard_system=_noop_stage("hazard", calls),
        physics_system=_noop_stage("physics", calls),
        contact_damage_system=_noop_stage("contact_damage", calls),
        hazard_damage_system=_noop_stage("hazard_damage", calls),
        respawn_system=_noop_respawn_stage("respawn", calls),
        progression_system=_noop_progression_stage("progression", calls),
        spawn_system=_noop_spawn_stage("spawn", calls),
        camera_system=_noop_camera_stage("camera", calls),
        notification_system=_noop_tail_stage("notifications", calls),
        tick_system=_noop_tick_stage("tick", calls),
    )
    loop.separation_system = SimpleNamespace(
        # Returns the entities it displaced; the loop re-syncs the attack boxes
        # of exactly those. An empty list is what a tick with nobody overlapping
        # reports, and it is what makes the ordering assertion below about stage
        # order rather than about how many fighters happened to be adjacent.
        process=lambda sprites, grid=None: (calls.append("separation"), [])[1]
    )
    loop.combat_system = SimpleNamespace(
        in_hit_stop=False,
        update_timer=lambda delta_time: None,
        process_attacks=lambda combatants, grid=None: calls.append("combat"),
    )

    loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())

    assert calls == [
        "spawn",
        "platform",
        "hazard",
        "physics",
        "separation",
        "combat",
        "contact_damage",
        "hazard_damage",
        "respawn",
        "progression",
        "camera",
        "notifications",
        "tick",
    ]


def test_update_is_a_noop_while_suspended_with_full_wiring() -> None:
    """A hit-stop tick short-circuits the world stages."""
    calls: list[str] = []
    loop = GameplayLoop(
        platform_system=_noop_stage("platform", calls),
        hazard_system=_noop_stage("hazard", calls),
        physics_system=_noop_stage("physics", calls),
        contact_damage_system=_noop_stage("contact_damage", calls),
        hazard_damage_system=_noop_stage("hazard_damage", calls),
        respawn_system=_noop_respawn_stage("respawn", calls),
        progression_system=_noop_progression_stage("progression", calls),
        spawn_system=_noop_spawn_stage("spawn", calls),
        camera_system=_noop_camera_stage("camera", calls),
        notification_system=_noop_tail_stage("notifications", calls),
        tick_system=_noop_tick_stage("tick", calls),
    )
    loop.combat_system.hit_stop_timer = 0.05

    loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())

    assert calls == ["spawn", "camera", "notifications", "tick"]


def test_update_with_invalid_wiring_mutates_nothing() -> None:
    """Invalid wiring is rejected before any mutation."""
    from types import SimpleNamespace

    spawn_calls: list[str] = []
    tick_calls: list[str] = []

    class RollbackSpy:
        def __init__(self) -> None:
            self.records = 0

        def record(self, level) -> None:
            self.records += 1

    loop = GameplayLoop(
        spawn_system=SimpleNamespace(process=lambda *a: spawn_calls.append("spawn")),
        camera_system=_noop_camera_stage("camera", []),
        notification_system=_noop_tail_stage("notifications", []),
        tick_system=SimpleNamespace(process=lambda *a: tick_calls.append("tick")),
    )
    loop.combat_system.hit_stop_timer = 0.0
    rollback = RollbackSpy()
    level = _noop_level()
    groups = _empty_groups()

    with pytest.raises(RuntimeError, match="platform_system"):
        loop.update(1 / 60, groups, None, level, rollback)

    assert spawn_calls == []
    assert tick_calls == []
    assert loop.combat_system.hit_stop_timer == 0.0
    assert rollback.records == 0
    assert level.tick == 0


def test_combat_only_update_fails_before_mutation() -> None:
    loop = GameplayLoop.combat_only()
    with pytest.raises(RuntimeError):
        loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())


def test_update_without_the_world_stages_fails_fast() -> None:
    calls: list[str] = []
    loop = GameplayLoop(
        spawn_system=_noop_spawn_stage("spawn", calls),
        camera_system=_noop_camera_stage("camera", calls),
        notification_system=_noop_tail_stage("notifications", calls),
        tick_system=_noop_tick_stage("tick", calls),
    )

    with pytest.raises(RuntimeError, match="platform_system"):
        loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())

    assert calls == []


def _box_positions(entity) -> tuple[tuple[float, float], ...]:
    """Where the live attack boxes are, as values.

    ``HitboxManager`` owns a pool and repositions those very ``FRect`` objects
    rather than building new ones, so ``attack_boxes`` returns the same
    instances every call. Comparing two of those tuples compares an object to
    itself and is true whatever happened -- the assertion has to copy the
    numbers out.
    """
    return tuple((box.centerx, box.centery) for box in entity.combat.attack_boxes)


def test_a_fighter_pushed_by_separation_gets_its_attack_box_moved_with_it() -> None:
    """The saving narrows the re-sync to the displaced; this is what it must not
    cost.

    A fighter mid-swing is positioned by ``Entity.update``, then separation
    pushes its hitbox sideways. The attack box is derived from that hitbox and
    ``sync_rects`` does not know it exists, so without a re-sync the swing would
    be tested against the place the fighter *was*. That is a hit that lands on
    empty air, or misses one that should have connected -- either way, a hitbox
    that disagrees with the sprite above it by exactly the push distance.
    """
    loop = GameplayLoop.combat_only()
    swing = attack(phase(startup=1, active=30, recovery=1, size=(40.0, 20.0), offset=(30.0, 0.0)))
    attacker = entity_at(0.0, faction="player", definition=swing)
    blocker = entity_at(20.0, faction="enemy")
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(attacker, blocker),
        combat_sprites=pygame.sprite.Group(attacker),
    )

    activate(attacker)
    before = _box_positions(attacker)
    assert before, "the fixture is not actually swinging"

    loop.process_combat_and_separation(1 / 60, groups.combat_sprites, groups.entity_sprites)

    after = _box_positions(attacker)
    assert attacker.hitbox.x != pytest.approx(0.0), "separation did not move anyone"
    assert after != before, "the attack box stayed where the fighter used to be"
    assert after[0][0] == pytest.approx(attacker.hitbox.centerx + swing.phases[0].hitbox_offset[0])


def test_a_fighter_nobody_pushed_ends_the_tick_where_it_started() -> None:
    """The bystander case, stated as what it can actually observe.

    Being spared the re-sync and being re-synced redundantly produce the same
    box, because positioning is pure and idempotent -- so this test cannot
    distinguish them, and does not pretend to. Reinstating the unconditional
    loop would leave it green, as it would leave every test in this file green.
    The saving is a measurement, not an assertion; what is asserted here is
    that narrowing the re-sync did not quietly move a fighter nobody touched,
    which is the failure a "sync the pair instead of the entity" implementation
    would make.
    """
    loop = GameplayLoop.combat_only()
    swing = attack(phase(startup=1, active=30, recovery=1, size=(40.0, 20.0), offset=(30.0, 0.0)))
    attacker = entity_at(0.0, faction="player", definition=swing)
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(attacker),
        combat_sprites=pygame.sprite.Group(attacker),
    )

    activate(attacker)
    before = _box_positions(attacker)
    assert before, "the fixture is not actually swinging"

    loop.process_combat_and_separation(1 / 60, groups.combat_sprites, groups.entity_sprites)

    assert _box_positions(attacker) == before
