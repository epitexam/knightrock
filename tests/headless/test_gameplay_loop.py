"""Tests d'orchestration headless du GameplayLoop (Phase 1 #10)."""

import pytest

from src.core.gameplay.gameplay_loop import GameplayLoop


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
