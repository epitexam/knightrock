"""Knockback feel + depth: wall bounce, shake, hitstop, DI, juggle scaling."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest
from pygame.math import Vector2

from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.core.rendering.camera import Camera
from src.core.settings import Combat as CombatSettings
from src.states.reaction_states import KnockbackState
from tests.unit.helpers import make_active_attacker, make_attack, make_entity, make_phase


def _hitting_attacker():
    return make_entity(faction="player", attacks={"punch": make_attack(make_phase())})


def _wall(box: pygame.FRect):
    return SimpleNamespace(rect=box, hitbox=box.copy(), old_hitbox=box.copy())


class KnockedEntity:
    """Entity double stuck in its knockback reaction state."""

    def __init__(self, hitbox: pygame.FRect) -> None:
        self.rect = hitbox.copy()
        self.hitbox = hitbox
        self.old_hitbox = hitbox.copy()
        self.velocity = Vector2(0, 0)
        self.move_axis = 0.0
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.collision_sprites: list = []
        self.state_machine = SimpleNamespace(current_state_name="knockback")

    def sync_rects(self) -> None:
        self.rect.midbottom = self.hitbox.midbottom

    def _on_floor_contact(self) -> None:
        pass

    def _on_wall_contact(self) -> None:
        pass


def test_launched_entity_bounces_off_walls() -> None:
    from src.physics.collisions import resolve_collisions

    entity = KnockedEntity(pygame.FRect(62, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)
    entity.velocity.x = 500.0
    wall = _wall(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(100.0)
    assert entity.velocity.x == pytest.approx(-500.0 * CombatSettings.WALL_BOUNCE_FACTOR)


def test_grounded_entity_still_stops_dead() -> None:
    from src.physics.collisions import resolve_collisions

    entity = KnockedEntity(pygame.FRect(62, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)
    entity.velocity.x = 500.0
    entity.state_machine = SimpleNamespace(current_state_name="idle")
    wall = _wall(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.velocity.x == 0.0


def test_camera_shake_decays_and_is_deterministic() -> None:
    # zoom=1.0: same ticks must give the same world-space pixels.
    first, second = Camera(800, 600, zoom=1.0), Camera(800, 600, zoom=1.0)
    first.add_trauma(2.0)  # clamped to 1.0
    second.add_trauma(1.0)
    assert first.trauma == pytest.approx(1.0)

    box = pygame.FRect(0, 0, 10, 10)
    assert first.apply(box) == second.apply(box)  # same ticks, same pixels
    first.follow(box, 1 / 60)
    assert first.trauma < 1.0


def test_camera_rests_without_trauma() -> None:
    # zoom=1.0: an unzoomed, unshaken camera is the identity mapping.
    camera = Camera(800, 600, zoom=1.0)
    box = pygame.FRect(100, 100, 40, 40)
    assert camera.apply(box) == box
    assert camera.shake_offset() == Vector2(0, 0)


def test_heavy_hit_extends_hitstop_and_tracks_impact() -> None:
    from src.core.level.systems.combat_system import CombatSystem

    target = make_entity(pos=(100.0, 100.0), faction="player")
    attacker = make_active_attacker(target)
    attacker.combat.current_phase.hit = HitProperties(
        damage=10, knockback=KnockbackConfig(power=(600.0, 0.0))
    )
    system = CombatSystem()
    system.process_attacks([attacker, target])

    assert system.impact == pytest.approx(600.0)
    assert system.hit_stop_timer == pytest.approx(
        CombatSettings.HITSTOP_BASE
        + 10 * CombatSettings.HITSTOP_DAMAGE_FACTOR
        + 600.0 * CombatSettings.HITSTOP_KNOCKBACK_FACTOR
    )


def test_airborne_victim_steers_its_flight() -> None:
    entity = SimpleNamespace(
        velocity=Vector2(600, 0),
        move_axis=1.0,
        on_surface={"floor": False, "left": False, "right": False},
    )
    state = KnockbackState(entity, Mock(return_value="idle"))
    state.enter(knockback_direction=1.0, knockback_force=600.0, knockback_up_force=0.0)

    state.update(1 / 60)

    assert entity.velocity.x > 600.0
    assert entity.velocity.x <= 600.0 + CombatSettings.KNOCKBACK_DI_CAP


def test_neutral_stick_leaves_flight_untouched() -> None:
    entity = SimpleNamespace(
        velocity=Vector2(600, 0),
        move_axis=0.0,
        on_surface={"floor": False, "left": False, "right": False},
    )
    state = KnockbackState(entity, Mock(return_value="idle"))
    state.enter(knockback_direction=1.0, knockback_force=600.0, knockback_up_force=0.0)

    state.update(1 / 60)

    assert entity.velocity.x == pytest.approx(600.0)


def test_enemy_drops_stale_axis_on_launch() -> None:
    from src.states.enemy_states import EnemyKnockbackState

    entity = SimpleNamespace(
        velocity=Vector2(0, 0),
        move_axis=1.0,
        on_surface={"floor": False, "left": False, "right": False},
        combat=SimpleNamespace(is_hurt=False),
    )
    EnemyKnockbackState(entity).enter(
        knockback_direction=1.0, knockback_force=600.0, knockback_up_force=0.0
    )

    assert entity.move_axis == 0.0


def test_juggle_damage_decays_with_air_count() -> None:
    from src.combat.hit_resolver import HitResolver

    attacker = _hitting_attacker()
    for _ in range(3):
        attacker.combat.record_hit_landed(True)
    assert attacker.combat.air_combo_count == 3

    target = make_entity(faction="enemy")  # airborne by default (no floor)
    assert target.on_surface["floor"] is False
    HitResolver.resolve(
        attacker, target, HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0)))
    )

    assert target.health == pytest.approx(100.0 - 10.0 * 0.7)


def test_grounded_hits_ignore_juggle_scaling() -> None:
    from src.combat.hit_resolver import HitResolver

    attacker = _hitting_attacker()
    for _ in range(5):
        attacker.combat.record_hit_landed(True)

    target = make_entity(faction="enemy")
    target.on_surface["floor"] = True
    HitResolver.resolve(
        attacker, target, HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0)))
    )

    assert target.health == pytest.approx(90.0)
