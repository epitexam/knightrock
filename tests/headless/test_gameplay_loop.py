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


def test_update_sequences_the_stages_in_their_historical_order() -> None:
    """The pipeline order is load-bearing: it must not drift (audit F1.6)."""
    calls: list[str] = []
    loop = GameplayLoop(
        platform_system=_noop_stage("platform", calls),
        hazard_system=_noop_stage("hazard", calls),
        physics_system=_noop_stage("physics", calls),
        contact_damage_system=_noop_stage("contact_damage", calls),
        hazard_damage_system=_noop_stage("hazard_damage", calls),
        respawn_system=_noop_stage("respawn", calls),
        progression_system=_noop_stage("progression", calls),
    )
    loop.separation_system = SimpleNamespace(
        process=lambda sprites, grid=None: calls.append("separation")
    )
    loop.combat_system = SimpleNamespace(
        process_attacks=lambda combatants, grid=None: calls.append("combat")
    )

    loop.update(1 / 60, _empty_groups(), None)

    assert calls == [
        "platform",
        "hazard",
        "physics",
        "separation",
        "combat",
        "contact_damage",
        "hazard_damage",
        "respawn",
        "progression",
    ]


def test_update_is_a_noop_while_suspended_even_unwired() -> None:
    """A hit-stop tick short-circuits before the staged wiring is resolved."""
    loop = GameplayLoop()

    loop.update(0.0, _empty_groups(), None)  # must not raise


def test_update_without_the_world_stages_fails_fast() -> None:
    loop = GameplayLoop()

    with pytest.raises(RuntimeError, match="platform_system"):
        loop.update(1 / 60, _empty_groups(), None)
