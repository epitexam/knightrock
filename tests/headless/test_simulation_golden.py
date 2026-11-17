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

from src.combat.knockback import NULL_KNOCKBACK
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import InputProvider
from src.core.input.input_state import InputState
from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.core.sprites import MovingPlatform
from tests.fakes import HazardStub
from tests.headless.conftest import make_viewport

SEED = 20260913
TICKS = 300

# The scenarios build a programmatic LevelData with no art dependency:
# Animator.preload skips missing clip directories, so these run on a bare
# checkout just as they do with assets/ present. Keep them ungated -- they are
# the only whole-pipeline regression net and must run in CI.


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
    return Level(make_viewport().surface, data, InputManager(_HoldRight()))


class _HoldRight(InputProvider):
    """A pad held right for the whole scenario.

    The level reads its input on every simulated tick, so the hold has to be what
    each read returns. It used to be planted once with ``apply_remote_state``,
    which only worked while nothing ever polled.
    """

    def poll(self) -> InputState:
        return InputState(move_axis=1.0)


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

    hazard = HazardStub(
        pygame.FRect(150.0, 150.0, 40.0, 40.0), damage=7.0, knockback=NULL_KNOCKBACK
    )
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
# Re-captured again for the gravity correction (commit "fix(physics):
# correct gravity value to improve gameplay balance"): Physics.GRAVITY
# 2000 -> 1500, which moves vy from tick 1 in every scenario. Proven the
# sole cause: reverting only GRAVITY reproduces the three digests above
# bit-identically, so no other pipeline change drifted these observables.
# Re-captured RIDE for the locomotion feature (commit "locomotion: 3-tier
# player walk/run states + enemy patrol_speed"): enemies now cruise at
# patrol_speed (chase_speed * 0.5 by default) instead of chase_speed while
# patrolling, which shifts goblin/slime positions from tick 1 onward.  The
# other two scenarios do not observe patrol translation (enemies either
# chase immediately or leave the frame of interest), so they stay valid.
# PHYSICS was cc0cb54c… here, before the next recapture below.
# Re-captured PHYSICS and RESPAWN for the per-pair contact damage cooldown
# (commit "fix(combat): a contact pair may not damage twice in a row"):
# MomentumGate asks whether the target is already hurt, but the contact box
# resolves with ``interrupt=False``, which never put a target in the hurt
# state -- so the guard could not fire and an overlapping pair re-applied the
# damage every tick. 12 ticks, ~0.2s, about a quarter of the player's own
# i-frame window. The goblin-on-goblin overlap in these scenarios is what
# moves.
# Re-captured RIDE for the per-target hazard cooldown (commit
# "fix(combat): give hazards a per-target damage cooldown"): a saw
# re-emits its box every tick and no enemy configures an invincibility
# window, so a lifetime rider died inside the cooldown window and never
# reached the exit. 24 ticks, ~0.4s, roughly the player's own i-frame
# window.  PHYSICS and RESPAWN carry no hazard and are unaffected.
# Re-captured PHYSICS and RIDE for audit C2 (2026-11-12): a contact or hazard
# cooldown is armed by a contact that landed, no longer by a pair that was only
# near. The first body contact lands on tick 9 instead of 12, the first hazard
# hit on tick 3 instead of 24; the cadence after a contact is unchanged.
# PHYSICS was e84b65ba… here, before the next recapture below.
# RIDE re-captured again for the combat retune (2026-11-12, docs/audit/
# combat-dynamism.md): the goblin's claw now has a 16-frame startup and a
# 16-frame recovery, and hit-stop starts from 30ms instead of 50ms.
# RIDE re-captured for the knockback rework (2026-11-13): the push of a hit
# now decays the same way in hurt, stagger and knockback (a ground slide that
# stops, a light air drag) instead of one exponential rate per state. PHYSICS
# and RESPAWN did not move.
# All three re-captured for the combat rework (2026-11-14): the enemies' data
# changed -- the goblin's claws deal 12 and 14 instead of 8 and 9, and a goblin
# has 80 health instead of 60 (the digest hashes health). Proven the sole
# cause: with the enemy damage and health as they were, the three digests of
# the commit before are reproduced bit for bit, so the stun gauge, the
# per-entity clock, the parry and the rest of the rework moved nothing here.
# PHYSICS and RIDE re-captured for the move catalogue rework (2026-11-15): the
# goblin's claws are now short arcs from the shoulder (22 px instead of a box
# reaching 66), the slime's splash became a lobbed glob, and a blow stopped by
# a guard makes its thrower recoil. The previous catalogue was overwritten
# before a bit-for-bit check could be run, so the sole-cause proof of the
# earlier re-captures is not available for this one; RESPAWN, which only
# falls and respawns, did not move.
PHYSICS_DIGEST = "c84740a6cd47840a75bbc0eb206b1b8e5f75c82c216ed3b0aa00c6b1fba79d92"
RIDE_DIGEST = "e86caa42e85d9db9217dee6f85c417eaa3c412bcbb42b2126ad0a013b2eecd5d"
RESPAWN_DIGEST = "3e37730c583750c0b95d7d1c785eaff271f81cd96a5c248c8125c9f6a867ec46"


def test_physics_ai_and_contact_damage_are_unchanged() -> None:
    """300 ticks of gravity, AI, separation and contact damage."""
    assert run(build_physics_level()) == PHYSICS_DIGEST


def test_moving_platform_hazard_and_exit_are_unchanged() -> None:
    """300 ticks riding a moving platform through a hazard and onto the exit."""
    assert run(build_ride_level()) == RIDE_DIGEST


def test_death_border_and_respawn_are_unchanged() -> None:
    """300 ticks of falling below the death border, dying and respawning."""
    assert run(build_respawn_level()) == RESPAWN_DIGEST
