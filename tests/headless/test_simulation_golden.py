"""Golden digests: the level simulation must not drift (Phase 3 #2 guard).

Three 300-tick scenarios hash every observable bit of simulation state
(position, velocity, health, death flag, tick counter, respawn timer, death
tally, exit flag).  The expected digests were captured on the *pre-refactor*
commit (``033c9d1``, where ``Level.update`` still drove every stage inline)
and must stay identical after ``Level`` became a facade over the gameplay
loop's pipeline (audit F1.2/F1.6): that equality is what proves the new
pipeline kept the exact same stage order and semantics.

If a digest fails after an *intentional* gameplay change, re-capture it —
never loosen the scenario to make it pass.

The scenarios are independent of global randomness: entities are re-seeded
per insertion index, and the simulation uses per-entity ``random.Random``
instances only.
"""

import hashlib
import random

import pygame
import pytest

from src.combat.knockback import NULL_KNOCKBACK
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.paths import PROJECT_ROOT
from src.core.sprites import MovingPlatform

SEED = 20260913
TICKS = 300

# Building a real Level loads the player/enemy animations from ``assets/``,
# which is untracked (see .gitignore): a bare checkout cannot run these
# scenarios.  The pre-existing headless tests have exactly the same
# requirement, so this is a pre-existing CI limitation, not a new one.
PLAYER_ASSET_DIR = PROJECT_ROOT / "assets" / "graphics" / "player"

requires_assets = pytest.mark.skipif(
    not PLAYER_ASSET_DIR.is_dir(),
    reason="needs the untracked assets/graphics tree to build a real Level",
)


class InputStub:
    """Same minimal contract as the headless test fixture."""

    move_axis = 1.0
    left_held = right_held = block_held = down_held = False
    jump_just_pressed = dash_just_pressed = reset_just_pressed = False
    attack1_just_pressed = attack2_just_pressed = attack2_just_released = False
    attack3_just_pressed = attack4_just_pressed = special_attack_just_pressed = False

    def update(self) -> None:
        """No-op."""


def _object(name: str, x: float, y: float) -> ObjectData:
    return ObjectData(
        name=name,
        x=x,
        y=y,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )


def _build(level_config: LevelConfig, objects: list[ObjectData]) -> Level:
    data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={"Entities": ObjectLayerData(name="Entities", objects=objects)},
        config=level_config,
    )
    return Level(pygame.display.get_surface(), data, InputStub())


def build_physics_level() -> Level:
    """Gravity, AI, separation and contact damage (no terrain, no border)."""
    return _build(
        LevelConfig(death_border_bottom=0.0),
        [
            _object("player", 100.0, 100.0),
            _object("goblin", 110.0, 100.0),  # overlapping: separation + contact
            _object("goblin", 400.0, 100.0),  # far: chases, then fights
            _object("slime", 250.0, 60.0),
            _object("dummy", 160.0, 100.0),
        ],
    )


def seed_entities(level: Level) -> None:
    """Make the run reproducible (Entity falls back to an os.urandom RNG)."""
    for index, entity in enumerate(level.groups.entity_sprites):
        entity.rng = random.Random(SEED + index)
        if hasattr(entity, "patrol_direction"):
            entity.patrol_direction = 1 if entity.rng.random() > 0.5 else -1


def frame(level: Level) -> tuple:
    """One tick of observable simulation state."""
    entities = tuple(
        (
            round(entity.hitbox.x, 4),
            round(entity.hitbox.y, 4),
            round(entity.velocity.x, 4),
            round(entity.velocity.y, 4),
            round(getattr(entity, "health", 0.0), 4),
            bool(getattr(entity, "is_dead", False)),
        )
        for entity in level.groups.entity_sprites
    )
    return entities + (
        level.tick,
        round(level.respawn_timer, 4),
        level.deaths,
        level.exit_reached,
        round(level.player.hitbox.x, 4),
        round(level.player.hitbox.y, 4),
    )


def run(level: Level) -> str:
    """Seed, simulate ``TICKS`` ticks and return the run digest."""
    seed_entities(level)
    frames = []
    for _ in range(TICKS):
        level.update(1 / 60)
        frames.append(frame(level))
    return hashlib.sha256(repr(frames).encode()).hexdigest()


def build_ride_level() -> Level:
    """Platform stage: a rider carried across a hazard, then onto the exit.

    The player spawns with its feet exactly on the platform top, so it rides
    from tick 1 (``PlatformSystem`` + the carry in ``PhysicsSystem``), crosses
    a lethal hazard (``HazardSystem`` + ``HazardDamageSystem``) and reaches the
    exit (``ProgressionSystem``).
    """
    level = build_physics_level()
    platform = MovingPlatform(
        pos=(100.0, 156.0),  # player hitbox bottom is exactly 156 at spawn
        surf=pygame.Surface((128, 16)),
        waypoints=[(100.0, 156.0), (232.0, 156.0)],
        speed=60.0,
        groups=(level.groups.moving_platforms, level.groups.collision_sprites),
    )
    level.spatial_hash.add(platform)

    hazard = pygame.sprite.Sprite()
    hazard.hitbox = pygame.FRect(150.0, 150.0, 40.0, 40.0)
    hazard.rect = hazard.hitbox.copy()
    hazard.damage = 7.0
    hazard.knockback = NULL_KNOCKBACK
    level.groups.hazard_sprites.add(hazard)

    exit_sprite = pygame.sprite.Sprite()
    exit_sprite.rect = pygame.FRect(214.0, 120.0, 32.0, 40.0)
    level.groups.exit_sprites.add(exit_sprite)
    return level


def build_respawn_level() -> Level:
    """Respawn stage: the pit rule kills the player and the system revives it."""
    return _build(
        LevelConfig(death_border_bottom=300.0),
        [
            _object("player", 100.0, 100.0),
            _object("goblin", 110.0, 100.0),
        ],
    )


# Re-captured with the tuned physics assists (commit "feat(physics-feel):
# activate the GameFeel/Collision/PlatformRide assists"): jump cut 2.5,
# ground snap 3 px, step-up 8 px, corner correct 12 px, graze threshold
# 2 px, deep-overlap resolve cap 16 px, sticky carry 0.5.  PHYSICS and
# RESPAWN were also already stale on HEAD (pre-existing drift before this
# retune); the recapture is the documented procedure for intentional
# gameplay changes (see the module docstring).
# Re-captured again for the apex-hang/fast-fall gravity (commit
# "feat(physics-gravity): apex hang and fast fall"): GameFeel
# APEX_GRAVITY_DIVISOR 2.0 around |vy| < 120 px/s, and the new down
# action (InputState.down_held, KB_DOWN) multiplying fall gravity x1.5.
PHYSICS_DIGEST = "79a9ff26167a9f82194d52ad66c1437e6ee49ac2035bf6105d8bcc8f3c2300ae"
RIDE_DIGEST = "3205fca59d654f936af6cf99c6a51e7cb5546cd2376e82e17f6123e879a07c50"
RESPAWN_DIGEST = "dcedaf8302bf08ee64052dffa24730d5f5512ccd474ac655eeabe01eea91a2ae"


@requires_assets
def test_physics_ai_and_contact_damage_are_unchanged() -> None:
    """300 ticks of gravity, AI, separation and contact damage."""
    assert run(build_physics_level()) == PHYSICS_DIGEST


@requires_assets
def test_moving_platform_hazard_and_exit_are_unchanged() -> None:
    """300 ticks riding a moving platform through a hazard and onto the exit."""
    assert run(build_ride_level()) == RIDE_DIGEST


@requires_assets
def test_death_border_and_respawn_are_unchanged() -> None:
    """300 ticks of falling below the death border, dying and respawning."""
    assert run(build_respawn_level()) == RESPAWN_DIGEST
