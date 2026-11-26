"""Guard feedback: the block ring, guard events, the guard's stop, overlay cues."""

from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.presentation import fx
from src.presentation.fx import (
    ShieldArcParticle,
    spawn_guard_arc,
    spawn_shatter_arc,
)
from src.presentation.fx.tuning import FxGuard
from src.shared.colors import FXColors
from src.simulation.entities.player import Player
from src.simulation.level.systems.combat_system import CombatSystem
from src.simulation.level.systems.contact_system import GuardEvent
from src.simulation.level.systems.feedback_system import FeedbackSystem
from src.simulation.level.systems.gameplay_loop import CombatLoop, GameplayLoop
from src.simulation.settings import Clash as ClashSettings
from src.simulation.settings import Finisher as FinisherSettings
from src.simulation.settings import Guard as GuardSettings
from src.simulation.settings import Rush as RushSettings
from src.simulation.settings import Stun as StunSettings
from tests.unit.helpers import InputStub, make_active_attacker


def _entity() -> SimpleNamespace:
    return SimpleNamespace(hitbox=pygame.FRect(100, 100, 40, 48), facing_right=True)


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


def test_guard_spawners_respect_budget() -> None:
    full = Group()
    for _ in range(fx.MAX_FX_SPRITES):
        full.add(ShieldArcParticle((0.0, 0.0), 1.0))

    assert spawn_guard_arc(full, _entity()) is None
    assert spawn_shatter_arc(full, _entity()) is None


def _guard_player(guarding: bool = True) -> Player:
    player = Player(
        pos=(0.0, 0.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.state_machine.current_state_name = "guard" if guarding else "idle"
    player.facing_right = False
    return player


def test_a_hit_taken_without_a_guard_is_no_guard_event() -> None:
    player = _guard_player(guarding=False)
    attacker = make_active_attacker(player)
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert system.guard_events == []
    assert player.health < player.max_health


def test_a_guarded_blow_is_a_guard_event_with_its_stop() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert [event.kind for event in system.guard_events] == ["guard"]
    assert system.guard_events[0].target is player
    assert system.hit_stop_timer >= GuardSettings.GUARD_HITSTOP
    assert player.health == player.max_health


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
    return CombatLoop(), camera


#: A player who did not start a dash this tick.
_NO_DASH = SimpleNamespace(dash_started_this_frame=False)


def test_game_loop_drains_guard_events_into_fx_and_trauma() -> None:
    player = _guard_player()
    attacker = make_active_attacker(player)
    loop, camera = _loop_with_camera()
    loop.combat_system.process_attacks([attacker, player])  # type: ignore[list-item]
    groups = SimpleNamespace(fx_sprites=Group())

    FeedbackSystem(groups).after_combat(  # type: ignore[arg-type]
        0.0,
        loop._collect_guard_events(),
        _NO_DASH,
        camera,  # type: ignore[arg-type]
    )

    assert len(groups.fx_sprites) == 1, "the ring alone"
    assert camera.traumas == [pytest.approx(GuardSettings.GUARD_TRAUMA)]
    assert loop.combat_system.guard_events == []


def test_game_loop_guard_trauma_uses_strongest_event() -> None:
    player = _guard_player()
    _, camera = _loop_with_camera()
    groups = SimpleNamespace(fx_sprites=Group())
    events = [GuardEvent("clash", player), GuardEvent("stun", player), GuardEvent("dodge", player)]

    FeedbackSystem(groups).after_combat(  # type: ignore[arg-type]
        0.0,
        events,
        _NO_DASH,
        camera,  # type: ignore[arg-type]
    )

    assert len(groups.fx_sprites) == 0, "only a guard draws a ring"
    assert camera.traumas == [pytest.approx(StunSettings.TRAUMA)]


@pytest.mark.parametrize(
    ("kind", "trauma"),
    [
        ("guard", GuardSettings.GUARD_TRAUMA),
        ("stun", StunSettings.TRAUMA),
        ("doom", FinisherSettings.DOOM_TRAUMA),
        ("dodge", RushSettings.TRAUMA),
        ("clash", ClashSettings.TRAUMA),
    ],
)
def test_each_outcome_of_an_exchange_has_its_own_shake(kind: str, trauma: float) -> None:
    player = _guard_player()
    _, camera = _loop_with_camera()
    groups = SimpleNamespace(fx_sprites=Group())

    FeedbackSystem(groups).after_combat(  # type: ignore[arg-type]
        0.0,
        [GuardEvent(kind, player)],
        _NO_DASH,
        camera,  # type: ignore[arg-type]
    )

    assert camera.traumas == [pytest.approx(trauma)]


def test_game_loop_skips_fx_without_events() -> None:
    loop, camera = _loop_with_camera()
    groups = SimpleNamespace(fx_sprites=Group())

    FeedbackSystem(groups).after_combat(  # type: ignore[arg-type]
        0.0,
        loop._collect_guard_events(),
        _NO_DASH,
        camera,  # type: ignore[arg-type]
    )

    assert len(groups.fx_sprites) == 0
    assert camera.traumas == []
