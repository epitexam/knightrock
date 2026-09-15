"""Tests d'orchestration headless du GameplayLoop (Phase 1 #10)."""

from types import SimpleNamespace

import pytest

from src.core.level.systems.gameplay_loop import GameplayLoop


def test_hit_stop_suspends_simulation_for_its_duration() -> None:
    loop = GameplayLoop()

    loop.combat_system.hit_stop_timer = 0.05
    suspended_delta = loop.begin_tick(1 / 60)

    assert suspended_delta == 0.0
    # update_timer a déjà consommé le dt pendant que la simulation était figée.
    assert loop.combat_system.hit_stop_timer < 0.05

    loop.combat_system.hit_stop_timer = 0.0
    normal_delta = loop.begin_tick(1 / 60)

    assert normal_delta == pytest.approx(1 / 60)


def test_begin_tick_returns_full_delta_without_hit_stop() -> None:
    loop = GameplayLoop()

    delta = loop.begin_tick(1 / 60)

    assert delta == pytest.approx(1 / 60)


def test_remove_dead_entities_spares_the_player() -> None:
    loop = GameplayLoop()
    player = PlayerStub()
    corpse = CorpseStub()

    loop.remove_dead_entities([corpse, player], player)

    assert corpse.killed
    assert not player.killed


def test_remove_dead_entities_keeps_living_entities() -> None:
    loop = GameplayLoop()
    living = CorpseStub(is_dead=False)

    loop.remove_dead_entities([living], None)

    assert not living.killed


def test_process_combat_and_separation_is_noop_while_suspended() -> None:
    loop = GameplayLoop()
    loop.separation_system = SeparationStub()

    loop.process_combat_and_separation(0.0, [], [])

    assert not loop.separation_system.ran


class PlayerStub:
    """Joueur simulé : ne doit jamais être tué par le système."""

    def __init__(self) -> None:
        self.is_dead = False
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class CorpseStub:
    """Sprite simulé dont le statut mort est piloté par le test."""

    def __init__(self, *, is_dead: bool = True) -> None:
        self.is_dead = is_dead
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class SeparationStub:
    def __init__(self) -> None:
        self.ran = False

    def process(self, entity_sprites) -> None:
        self.ran = True


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
        process=lambda sprites, grid=None: calls.append("separation")
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


def test_update_is_a_noop_while_suspended_even_unwired() -> None:
    """A hit-stop tick short-circuits before the staged wiring is resolved."""
    loop = GameplayLoop()
    loop.combat_system.hit_stop_timer = 0.05

    # The spawner still runs (raw frame delta: cooldown decay), the camera
    # still tracks and the tick is still bookkept — only the world stages
    # are skipped, so a bare loop needs just the cross-cutting stages.
    calls: list[str] = []
    loop.spawn_system = _noop_spawn_stage("spawn", calls)
    loop.camera_system = _noop_camera_stage("camera", calls)
    loop.notification_system = _noop_tail_stage("notifications", calls)
    loop.tick_system = _noop_tick_stage("tick", calls)

    loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())

    assert calls == ["spawn", "camera", "notifications", "tick"]


def test_update_without_the_world_stages_fails_fast() -> None:
    loop = GameplayLoop(
        spawn_system=_noop_spawn_stage("spawn", []),
        camera_system=_noop_camera_stage("camera", []),
        notification_system=_noop_tail_stage("notifications", []),
        tick_system=_noop_tick_stage("tick", []),
    )

    with pytest.raises(RuntimeError, match="platform_system"):
        loop.update(1 / 60, _empty_groups(), None, _noop_level(), _noop_rollback())
