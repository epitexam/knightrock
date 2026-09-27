"""ProjectileSystem tests (audit Phase 5 #3)."""

import pygame
from pygame.sprite import Group

from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.sprite_groups import SpriteGroups
from src.entities.projectile import ProjectileConfig
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHash
from tests.unit.helpers import make_entity


def _config(**kwargs) -> ProjectileConfig:
    hit = HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(0.0, 0.0)),
    )
    return ProjectileConfig(size=(10.0, 10.0), lifetime=2.0, hit=hit, **kwargs)


def _fleeting_config() -> ProjectileConfig:
    """A projectile that expires on the next tick, so the pool gets it back."""
    return ProjectileConfig(
        size=(10.0, 10.0),
        lifetime=0.01,
        hit=HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0))),
    )


def _big_config() -> ProjectileConfig:
    """A different flight size, to force the surface to be rebuilt."""
    return ProjectileConfig(
        size=(24.0, 18.0),
        lifetime=2.0,
        hit=HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0))),
    )


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


def test_projectile_aabb_sweeps_target_between_ticks() -> None:
    """A fast projectile catches a target crossed between discrete positions."""
    target = make_entity(pos=(95.0, 105.0), faction="enemy", size=(5.0, 5.0))
    groups = _groups_with_target(target)
    system = ProjectileSystem(groups)
    projectile = system.spawn(
        _config(),
        pos=(70.0, 105.0),
        velocity=(2400.0, 0.0),
        faction="player",
    )

    system.process(1 / 60)

    assert projectile.hitbox.x == 110.0
    assert target.health == 90.0


def test_projectile_wall_sweep_catches_wall_between_positions() -> None:
    """A projectile cannot pass through a wall between discrete positions."""
    target = make_entity(pos=(1000.0, 1000.0), faction="enemy")
    groups = _groups_with_target(target)
    wall = pygame.sprite.Sprite()
    wall.rect = pygame.Rect(95, 100, 10, 10)
    groups.collision_sprites.add(wall)
    system = ProjectileSystem(groups)

    system.spawn(
        _config(),
        pos=(70.0, 105.0),
        velocity=(2400.0, 0.0),
        faction="player",
    )
    system.process(1 / 60)

    assert not groups.projectile_sprites
    assert system.pool.available == 1


def test_projectile_wall_sweep_with_spatial_hash_catches_wall_between_positions() -> None:
    """The swept wall query remains correct with the environment hash."""
    target = make_entity(pos=(1000.0, 1000.0), faction="enemy")
    groups = _groups_with_target(target)
    wall = pygame.sprite.Sprite()
    wall.rect = pygame.Rect(95, 100, 10, 10)
    groups.collision_sprites.add(wall)
    spatial_hash = SpatialHash()
    spatial_hash.add(wall)
    system = ProjectileSystem(groups, spatial_hash=spatial_hash)

    system.spawn(_config(), pos=(70.0, 105.0), velocity=(2400.0, 0.0), faction="player")
    system.process(1 / 60)

    assert not groups.projectile_sprites


def test_projectile_grid_and_exhaustive_paths_agree() -> None:
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


# -- the pooled projectile's surface ------------------------------------------
#
# A pooled object that rebuilds its largest field on every launch has not
# really been pooled. The surface is reused when the size matches, and
# rebuilt when it does not, because a surface blitted into a mismatched
# rectangle is resampled by pygame and would draw at the wrong scale.


def test_relaunching_at_the_same_size_reuses_the_surface() -> None:
    system = ProjectileSystem(SpriteGroups())
    first = system.spawn(
        _fleeting_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player"
    )
    # Held in a local on purpose: the pool hands back the same Projectile, so
    # `first.image` reads the attribute as it is *now*, and comparing it to
    # `second.image` would compare the attribute with itself.
    launch_surface = first.image
    system.process(1 / 60)  # expires it back into the pool
    second = system.spawn(
        _fleeting_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player"
    )

    assert first is second, "the pool must hand the same instance back"
    assert second.image is launch_surface, "the same size must reuse the surface"


def test_relaunching_at_a_different_size_rebuilds_the_surface() -> None:
    system = ProjectileSystem(SpriteGroups())
    first = system.spawn(
        _fleeting_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player"
    )
    # Held separately: the pool hands the same Projectile back, so `first.image`
    # reads whatever the attribute says *now*, not what it said at launch.
    small_surface = first.image
    system.process(1 / 60)

    bigger = system.spawn(_big_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player")

    assert bigger is first, "the pool must hand the same instance back"
    assert bigger.image is not small_surface
    assert bigger.image.get_size() == (24, 18)
    assert bigger.rect.size == (24, 18)


def test_a_reused_surface_is_refilled_so_no_state_carries_over() -> None:
    """Reuse must not mean 'keep whatever was there': the fill is the reset."""
    system = ProjectileSystem(SpriteGroups())
    first = system.spawn(
        _fleeting_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player"
    )
    first.image.fill((1, 2, 3))
    system.process(1 / 60)

    second = system.spawn(
        _fleeting_config(), pos=(0.0, 0.0), velocity=(600.0, 0.0), faction="player"
    )

    assert second.image.get_at((5, 5))[:3] == (255, 200, 60), (
        "a refilled surface, not the previous launch's pixels"
    )
