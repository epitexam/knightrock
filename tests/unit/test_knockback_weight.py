"""Weight, the ground bounce and the body a kill leaves: the knockback rework."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest
from pygame.math import Vector2
from pygame.sprite import Group

from src.combat.knockback import KnockbackConfig
from src.core.fx import FX_FAMILY_BUDGETS, CorpseParticle, spawn_corpse
from src.core.fx.tuning import Corpse
from src.core.level.systems.feedback_system import FeedbackSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.settings import Combat as CombatSettings
from src.data.enemies import read_enemy_config
from src.data.errors import GameplayDataError
from src.data.provider import shipped_gameplay_data
from src.entities.enemies.factory import create_enemy
from src.states import state_names
from tests.unit.helpers import make_entity

# --- weight -----------------------------------------------------------------


def _enemy(name: str, weight: float | None = None):
    from dataclasses import replace

    config = shipped_gameplay_data().enemies[name]
    if weight is not None:
        config = replace(config, weight=weight, super_armor=False)
    enemy = create_enemy(name, (100.0, 100.0), Group(), Group(), None, config=config)
    enemy.on_surface["floor"] = True
    return enemy


def test_a_hit_moves_a_fighter_by_its_power_over_its_weight() -> None:
    light, heavy = _enemy("goblin", weight=0.5), _enemy("goblin", weight=2.0)
    hit = KnockbackConfig(power=(200.0, -100.0))

    light.receive_damage(1.0, light.hitbox.centerx - 50.0, hit)
    heavy.receive_damage(1.0, heavy.hitbox.centerx - 50.0, hit)

    assert light.velocity == Vector2(400.0, -200.0)
    assert heavy.velocity == Vector2(100.0, -50.0)


def test_the_same_blow_launches_the_light_and_only_shoves_the_heavy() -> None:
    """The launch threshold reads the knockback as felt, not as dealt."""
    light, heavy = _enemy("goblin", weight=0.8), _enemy("goblin", weight=1.5)
    hit = KnockbackConfig(power=(350.0, -100.0))  # 364 px/s: under the threshold at weight 1

    launched = light.receive_damage(1.0, light.hitbox.centerx - 50.0, hit)
    shoved = heavy.receive_damage(1.0, heavy.hitbox.centerx - 50.0, hit)

    assert launched.heavy_knockback is True
    assert light.state_machine.current_state_name == state_names.KNOCKBACK
    assert shoved.heavy_knockback is False
    assert heavy.state_machine.current_state_name != state_names.KNOCKBACK


def test_weight_one_is_the_hit_as_written() -> None:
    goblin = _enemy("goblin")
    hit = KnockbackConfig(power=(200.0, -100.0))

    goblin.receive_damage(1.0, goblin.hitbox.centerx - 50.0, hit)

    assert goblin.weight == 1.0
    assert goblin.velocity == Vector2(200.0, -100.0)


def test_the_shipped_weights_order_the_enemies_by_bulk() -> None:
    enemies = shipped_gameplay_data().enemies
    assert enemies["slime"].weight < enemies["goblin"].weight < enemies["shell"].weight


@pytest.mark.parametrize("weight", [0, -1.0, "heavy", None])
def test_a_weight_that_cannot_divide_is_refused(weight: object) -> None:
    raw = {"size": [36.0, 48.0], "color": [1, 2, 3], "health": 10.0, "attacks": {}}

    with pytest.raises(GameplayDataError, match="weight"):
        read_enemy_config({**raw, "weight": weight}, "enemies.test", {})


# --- ground bounce ----------------------------------------------------------


def _launched(vx: float = 300.0):
    entity = make_entity()
    entity.state_machine = SimpleNamespace(current_state_name=state_names.KNOCKBACK)
    entity.velocity = Vector2(vx, 0.0)
    return entity


def test_a_launched_fighter_rebounds_off_a_hard_landing() -> None:
    entity = _launched()

    entity._bounce_off_the_ground(700.0)

    assert entity.velocity.y == pytest.approx(-700.0 * CombatSettings.GROUND_BOUNCE_FACTOR)
    assert entity.velocity.x == pytest.approx(300.0 * CombatSettings.GROUND_BOUNCE_KEEP)


def test_a_soft_landing_does_not_bounce() -> None:
    entity = _launched()

    entity._bounce_off_the_ground(CombatSettings.GROUND_BOUNCE_MIN_SPEED - 1.0)

    assert entity.velocity == Vector2(300.0, 0.0)


def test_only_a_launch_bounces() -> None:
    """A jump that lands hard is a jump that landed."""
    entity = make_entity()
    entity.velocity = Vector2(300.0, 0.0)

    entity._bounce_off_the_ground(1200.0)

    assert entity.velocity == Vector2(300.0, 0.0)


def test_the_bounce_cannot_bounce_again() -> None:
    """One rebound by construction: what it keeps is under what it takes to bounce."""
    from src.core.settings import Physics

    rebound = Physics.MAX_FALL_SPEED * CombatSettings.GROUND_BOUNCE_FACTOR
    assert rebound < CombatSettings.GROUND_BOUNCE_MIN_SPEED


# --- the body a kill leaves -------------------------------------------------


def _dying(velocity: tuple[float, float], *, floor: bool = True, facing_right: bool = True):
    return SimpleNamespace(
        image=pygame.Surface((36, 48), pygame.SRCALPHA),
        rect=pygame.FRect(100, 100, 36, 48),
        hitbox=pygame.FRect(100, 100, 36, 48),
        velocity=Vector2(velocity),
        on_surface={"floor": floor},
        facing_right=facing_right,
    )


def test_the_body_leaves_with_the_killing_hit() -> None:
    corpse = spawn_corpse(Group(), _dying((-400.0, -500.0)))

    assert isinstance(corpse, CorpseParticle)
    assert corpse.velocity == Vector2(-400.0 * Corpse.BOOST, -500.0 * Corpse.BOOST)
    assert Vector2(corpse.rect.center) == Vector2(118.0, 124.0)


def test_a_kill_with_no_push_still_throws_the_body_backwards() -> None:
    corpse = spawn_corpse(Group(), _dying((0.0, 0.0), facing_right=True))

    assert corpse is not None
    assert corpse.velocity == Vector2(-Corpse.MIN_KICK, Corpse.MIN_POP)


def test_the_body_rebounds_off_the_floor_its_fighter_stood_on() -> None:
    corpse = spawn_corpse(Group(), _dying((300.0, 0.0)))
    assert corpse is not None and corpse.ground_y == 148.0

    lowest = 0.0
    for _ in range(int(Corpse.TTL * 60) - 1):
        corpse.update(1 / 60)
        lowest = max(lowest, corpse.pos.y + 24.0)

    assert lowest <= 148.0 + 1e-6


def test_a_body_killed_in_the_air_has_no_floor() -> None:
    corpse = spawn_corpse(Group(), _dying((300.0, 0.0), floor=False))

    assert corpse is not None and corpse.ground_y is None


def test_the_body_is_whole_then_steps_out_and_is_gone() -> None:
    group: Group = Group()
    corpse = spawn_corpse(group, _dying((300.0, -300.0)))
    assert corpse is not None

    corpse.update(Corpse.TTL * Corpse.FADE_FROM * 0.5)
    assert corpse.image.get_alpha() == 255
    corpse.update(Corpse.TTL * 0.45)
    assert corpse.image.get_alpha() < 255
    corpse.update(Corpse.TTL)

    assert corpse not in group


def test_the_body_tumbles_in_whole_notches() -> None:
    corpse = spawn_corpse(Group(), _dying((300.0, -300.0), floor=False))
    assert corpse is not None
    upright = corpse.image.get_size()

    sizes = set()
    for _ in range(20):
        corpse.update(1 / 60)
        sizes.add(corpse.image.get_size())

    assert len(sizes) > 1 and upright in sizes
    assert all(notch % Corpse.SPIN_STEP == 0 for notch in corpse._turns)


def test_the_bodies_are_budgeted() -> None:
    group: Group = Group()
    for _ in range(FX_FAMILY_BUDGETS["corpse"] + 3):
        spawn_corpse(group, _dying((300.0, 0.0)))

    assert len(group) == FX_FAMILY_BUDGETS["corpse"]


def test_the_body_does_not_touch_the_fighter_it_came_from() -> None:
    """Render-only: the simulation's entity is read, never written."""
    dying = _dying((300.0, -200.0))
    image = dying.image

    corpse = spawn_corpse(Group(), dying)

    assert corpse is not None and corpse.image is not image
    assert dying.velocity == Vector2(300.0, -200.0)
    assert dying.rect == pygame.FRect(100, 100, 36, 48)


def test_a_reaped_enemy_leaves_a_body_and_the_player_does_not() -> None:
    feedback = Mock(spec=FeedbackSystem)
    loop = GameplayLoop(feedback_system=feedback)
    player, foe, alive = make_entity(), make_entity(), make_entity()
    player.die()
    foe.die()
    group = Group(player, foe, alive)

    loop.remove_dead_entities(group, player)

    feedback.before_removal.assert_called_once_with(foe)
    assert foe not in group and player in group and alive in group


def test_the_loop_without_feedback_still_reaps() -> None:
    foe = make_entity()
    foe.die()
    group = Group(foe)

    GameplayLoop.combat_only().remove_dead_entities(group, None)

    assert foe not in group
