"""ProjectileSystem tests (audit Phase 5 #3)."""

import pygame
from pygame.sprite import Group

from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.sprite_groups import SpriteGroups
from src.entities.projectile import ProjectileConfig
from src.physics.entity_grid import EntityGrid
from tests.unit.helpers import make_entity


def _config(**kwargs) -> ProjectileConfig:
    hit = HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(0.0, 0.0)),
    )
    return ProjectileConfig(size=(10.0, 10.0), lifetime=2.0, hit=hit, **kwargs)


def _groups_with_target(target) -> SpriteGroups:
    groups = SpriteGroups()
    groups.entity_sprites.add(target)
    groups.all_sprites.add(target)
    return groups


def test_spawn_moves_and_expires_back_into_pool() -> None:
    target = make_entity(pos=(1000.0, 1000.0), faction="enemy")
    groups = _groups_with_target(target)
    system = ProjectileSystem(groups)

    first = system.spawn(_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player")
    assert first in groups.projectile_sprites

    system.process(1 / 60)
    assert first.hitbox.x > 0.0

    system.process(5.0)  # beyond lifetime
    assert len(groups.projectile_sprites) == 0
    assert system.pool.available == 1

    second = system.spawn(_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player")
    assert second is first  # pooled instance reused
    assert system.pool.created == 1


def test_projectile_hits_enemy_through_hit_resolver() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="enemy")
    groups = _groups_with_target(target)
    system = ProjectileSystem(groups)

    system.spawn(_config(), pos=(100.0, 100.0), velocity=(0.0, 0.0), faction="player")
    system.process(1 / 60)

    assert target.health == 90.0
    assert len(groups.projectile_sprites) == 0  # consumed on hit
    assert system.pool.available == 1


def test_friendly_fire_is_ignored() -> None:
    target = make_entity(pos=(100.0, 100.0), faction="player")
    groups = _groups_with_target(target)
    system = ProjectileSystem(groups)

    system.spawn(_config(), pos=(100.0, 100.0), velocity=(0.0, 0.0), faction="player")
    system.process(1 / 60)

    assert target.health == 100.0
    assert len(groups.projectile_sprites) == 1  # still flying


def test_pierce_hits_multiple_targets_once_each() -> None:
    left = make_entity(pos=(100.0, 100.0), faction="enemy")
    right = make_entity(pos=(100.0, 100.0), faction="enemy")
    groups = SpriteGroups()
    groups.entity_sprites.add(left, right)
    groups.all_sprites.add(left, right)
    system = ProjectileSystem(groups)

    system.spawn(_config(pierce=True), pos=(100.0, 100.0), velocity=(0.0, 0.0), faction="player")
    system.process(1 / 60)

    assert left.health == 90.0
    assert right.health == 90.0
    assert len(groups.projectile_sprites) == 1  # pierce keeps flying

    before = (left.health, right.health)
    system.process(1 / 60)
    assert (left.health, right.health) == before  # no double damage


def test_wall_collision_releases_projectile() -> None:
    target = make_entity(pos=(1000.0, 1000.0), faction="enemy")
    groups = _groups_with_target(target)
    wall = pygame.sprite.Sprite()
    wall.rect = pygame.Rect(50, 95, 40, 40)
    groups.collision_sprites.add(wall)
    system = ProjectileSystem(groups)

    system.spawn(_config(), pos=(0.0, 100.0), velocity=(600.0, 0.0), faction="player")
    for _ in range(10):
        system.process(1 / 60)

    assert len(groups.projectile_sprites) == 0
    assert system.pool.available == 1


def test_grid_and_exhaustive_paths_agree() -> None:
    def run(with_grid: bool) -> float:
        target = make_entity(pos=(100.0, 100.0), faction="enemy")
        groups = _groups_with_target(target)
        system = ProjectileSystem(groups)
        system.spawn(_config(), pos=(100.0, 100.0), velocity=(0.0, 0.0), faction="player")
        grid = EntityGrid(cell_size=128) if with_grid else None
        if grid is not None:
            grid.rebuild(groups.entity_sprites)
        system.process(1 / 60, grid)
        return target.health

    assert run(False) == run(True) == 90.0


def test_zero_delta_freezes_projectiles_for_hit_stop() -> None:
    target = make_entity(pos=(1000.0, 1000.0), faction="enemy")
    groups = _groups_with_target(target)
    system = ProjectileSystem(groups)
    projectile = system.spawn(_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player")
    system.process(0.0)
    assert projectile.hitbox.x == 0.0
    assert len(Group(*groups.projectile_sprites).sprites()) == 1
