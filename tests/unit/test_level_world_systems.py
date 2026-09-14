"""Unit tests for the level's per-tick world systems (Phase 3 #2, audit F1.2).

The five stages extracted out of ``Level.update`` are exercised in isolation:
platforms, physics integration, hazard ticking, respawn/death-border and exit
progression.  Each system is a plain object driven by ``process(delta_time)``,
so these are pure behavioural tests built on lightweight doubles.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.level.level_data import LevelConfig, LevelData
from src.core.level.systems.hazard_system import HazardSystem
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.level.systems.platform_system import PlatformSystem
from src.core.level.systems.progression_system import ProgressionSystem
from src.core.level.systems.respawn_system import PlayerRespawnSystem
from src.core.settings import Respawn


class RecordingGroup(list):
    """Group double: stays iterable and records the delta it was ticked with."""

    def __init__(self, *sprites) -> None:
        super().__init__(sprites)
        self.delta: float | None = None

    def update(self, delta_time: float) -> None:  # type: ignore[override]
        self.delta = delta_time


def make_level_data(death_border_bottom: float = 0.0) -> LevelData:
    """Minimal level data: the death border is the only thing the systems read."""
    return LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={},
        config=LevelConfig(death_border_bottom=death_border_bottom),
    )


class PlayerStub:
    """Player double: geometry, death flag and the two life transitions."""

    def __init__(self, top: float = 0.0, *, is_dead: bool = False) -> None:
        self.hitbox = pygame.FRect(0.0, top, 40.0, 50.0)
        self.is_dead = is_dead
        self.respawned = 0
        self.died = 0

    def respawn(self) -> None:
        self.respawned += 1
        self.is_dead = False

    def die(self) -> None:
        self.died += 1
        self.is_dead = True


class RiderStub(pygame.sprite.Sprite):
    """Entity double for the platform carry: geometry plus the carry hooks."""

    def __init__(self, pos: tuple[float, float], *, on_floor: bool = True) -> None:
        super().__init__()
        self.hitbox = pygame.FRect(pos[0], pos[1], 40.0, 50.0)
        self.old_hitbox = self.hitbox.copy()
        self.rect = pygame.FRect(self.hitbox)
        self.on_surface = {"floor": on_floor, "left": False, "right": False}
        self.x_at_entity_update: float | None = None

    def sync_rects(self) -> None:
        self.rect = pygame.FRect(self.hitbox)

    def update(self, delta_time: float) -> None:  # type: ignore[override]
        self.x_at_entity_update = self.hitbox.x


class TestPlatformSystem:
    """The platform stage must move first, then refresh the collision grid."""

    def test_moves_the_platforms_then_rebuckets_them(self) -> None:
        platforms = RecordingGroup()
        seen_at_rebucket: list[float | None] = []
        spatial_hash = SimpleNamespace(
            update_all=lambda sprites: seen_at_rebucket.append(sprites.delta)
        )
        system = PlatformSystem(SimpleNamespace(moving_platforms=platforms), spatial_hash)

        system.process(1 / 60)

        assert platforms.delta == pytest.approx(1 / 60)
        # The grid is refreshed after the move, so it observes the tick delta.
        assert seen_at_rebucket == [platforms.delta]


class TestPhysicsSystem:
    """Carry the platform riders, then integrate entities and effects."""

    def _groups(self, rider: RiderStub) -> SimpleNamespace:
        return SimpleNamespace(
            entity_sprites=pygame.sprite.Group(rider),
            moving_platforms=[
                SimpleNamespace(
                    hitbox=pygame.FRect(105.0, 200.0, 100.0, 16.0),
                    old_hitbox=pygame.FRect(100.0, 200.0, 100.0, 16.0),
                )
            ],
            fx_sprites=RecordingGroup(),
        )

    def test_carries_a_rider_before_integrating_the_entities(self) -> None:
        rider = RiderStub((100.0, 150.0))  # hitbox bottom lands on the platform
        groups = self._groups(rider)

        PhysicsSystem(groups).process(1 / 60)

        assert rider.hitbox.x == pytest.approx(105.0)
        # The carry ran before the entity pass: the sprite already sees the new x.
        assert rider.x_at_entity_update == pytest.approx(105.0)
        assert groups.fx_sprites.delta == pytest.approx(1 / 60)

    def test_does_not_carry_an_airborne_entity(self) -> None:
        rider = RiderStub((100.0, 150.0), on_floor=False)

        PhysicsSystem(self._groups(rider)).process(1 / 60)

        assert rider.hitbox.x == pytest.approx(100.0)
        assert rider.x_at_entity_update == pytest.approx(100.0)


class TestHazardSystem:
    """The hazard stage ticks the hazard sprites only."""

    def test_ticks_the_hazard_group(self) -> None:
        hazards = RecordingGroup()

        HazardSystem(SimpleNamespace(hazard_sprites=hazards)).process(1 / 60)

        assert hazards.delta == pytest.approx(1 / 60)


class TestPlayerRespawnSystem:
    """Respawn countdown, death tally and the out-of-bounds rule."""

    def test_waits_for_the_delay_then_respawns_and_counts_the_death(self) -> None:
        player = PlayerStub(is_dead=True)
        system = PlayerRespawnSystem(player, make_level_data())

        system.process(Respawn.DELAY_S - 0.1)

        assert player.respawned == 0
        assert system.deaths == 0

        system.process(0.2)

        assert player.respawned == 1
        assert system.deaths == 1
        assert system.respawn_timer == 0.0

    def test_clears_the_timer_while_the_player_is_alive(self) -> None:
        player = PlayerStub()
        system = PlayerRespawnSystem(player, make_level_data())
        system.respawn_timer = 0.75

        system.process(1 / 60)

        assert system.respawn_timer == 0.0
        assert player.respawned == 0

    def test_death_border_kills_a_falling_player(self) -> None:
        player = PlayerStub(top=500.0)
        system = PlayerRespawnSystem(player, make_level_data(death_border_bottom=400.0))

        system.process(1 / 60)

        assert player.died == 1
        assert player.is_dead

    def test_player_above_the_border_is_left_alone(self) -> None:
        player = PlayerStub(top=100.0)
        system = PlayerRespawnSystem(player, make_level_data(death_border_bottom=400.0))

        system.process(1 / 60)

        assert player.died == 0
        assert not player.is_dead

    def test_disabled_death_border_leaves_the_player_alive(self) -> None:
        """A non-positive border is how a level opts out of the pit rule."""
        player = PlayerStub(top=500.0)
        system = PlayerRespawnSystem(player, make_level_data(death_border_bottom=0.0))

        system.process(1 / 60)

        assert player.died == 0
        assert not player.is_dead


class PlayerSpriteStub(pygame.sprite.Sprite):
    """Sprite-shaped player double: the exit probe needs rect *and* is_dead."""

    def __init__(self, pos: tuple[float, float], *, is_dead: bool = False) -> None:
        super().__init__()
        self.rect = pygame.FRect(pos[0], pos[1], 10.0, 10.0)
        self.is_dead = is_dead


class TestProgressionSystem:
    """Exit detection owns and latches the completion flag."""

    @staticmethod
    def _exit_at(pos: tuple[float, float]) -> pygame.sprite.Sprite:
        sprite = pygame.sprite.Sprite()
        sprite.rect = pygame.FRect(pos[0], pos[1], 10.0, 10.0)
        return sprite

    def test_flags_completion_when_the_player_touches_the_exit(self) -> None:
        system = ProgressionSystem(pygame.sprite.Group(self._exit_at((5.0, 5.0))))

        system.process(PlayerSpriteStub((0.0, 0.0)))  # type: ignore[arg-type]

        assert system.exit_reached is True

    def test_completion_is_not_cleared_by_a_later_tick(self) -> None:
        system = ProgressionSystem(pygame.sprite.Group(self._exit_at((5.0, 5.0))))
        player = PlayerSpriteStub((0.0, 0.0))
        system.process(player)  # type: ignore[arg-type]
        assert system.exit_reached is True

        player.rect.topleft = (500.0, 500.0)  # walked away from the flag
        system.process(player)  # type: ignore[arg-type]

        assert system.exit_reached is True

    def test_stays_incomplete_without_an_exit(self) -> None:
        system = ProgressionSystem(pygame.sprite.Group())

        system.process(PlayerSpriteStub((0.0, 0.0)))  # type: ignore[arg-type]

        assert system.exit_reached is False

    def test_does_not_probe_the_exit_when_the_player_is_dead(self, monkeypatch) -> None:
        probe = Mock(return_value=[object()])
        monkeypatch.setattr(pygame.sprite, "spritecollide", probe)
        system = ProgressionSystem(pygame.sprite.Group())

        system.process(PlayerSpriteStub((0.0, 0.0), is_dead=True))  # type: ignore[arg-type]

        probe.assert_not_called()
        assert system.exit_reached is False
