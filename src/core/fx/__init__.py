"""Render-only impact FX: dust, speed lines, sparks, stars and impact rings.

Dust lives in ``groups.fx_sprites`` (no collision, no damage): it is
integrated by :class:`PhysicsSystem`, drawn by :class:`Renderer` like any
visible sprite, and excluded from rollback snapshots and golden digests --
pure juice, zero simulation impact. That last phrase is a claim the package
now keeps: the randomness here comes from its own stream rather than from an
entity's, so nothing in this package advances state the simulation owns. See
``spawners._fx_rng`` and ``tests/unit/test_fx_invariants.py``.

Three modules, split along the line that decides what a change touches:

- :mod:`src.core.fx.draw` -- the whole-pixel arithmetic every shape rests on.
- :mod:`src.core.fx.particles` -- what a particle looks like and how it moves.
  It builds its pixels once, at construction.
- :mod:`src.core.fx.spawners` -- whether a particle is allowed, and where it
  goes. It owns the budgets and the FX RNG.

The look, in one sentence: whole pixels, dark ink rims, and alpha that moves
in discrete steps, because the game is magnified with nearest-neighbour
scaling and a soft particle turns to mush at that magnification.

Which particles rebuild their surface
-------------------------------------
A particle that redraws its pixels every frame pays for a drawing, not for an
allocation, so the only question is whether its *look* changes. Two of them
used to, and both stopped: the shockwave is drawn once at full size and shown
through a few pre-scaled steps, and the dizzy swirl is a shared ladder of
rotation steps. Everything here builds its surface at construction and then
only moves or fades, which is what ``tests/unit/test_fx_surfaces.py`` pins.
"""

from __future__ import annotations

from src.core.fx.particles import (
    DashShockwaveParticle,
    DizzyVortexParticle,
    DustParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    StreakParticle,
    SweatParticle,
    clear_frame_cache,
    vortex_frames,
)
from src.core.fx.spawners import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    dash_direction,
    iter_landing_entities,
    spawn_dash_burst,
    spawn_dash_shockwave,
    spawn_dash_streak,
    spawn_dash_wind,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_shatter_arc,
    spawn_sweat_drops,
)

__all__ = [
    "FX_FAMILY_BUDGETS",
    "MAX_FX_SPRITES",
    "DashShockwaveParticle",
    "DizzyVortexParticle",
    "DustParticle",
    "ShatterArcParticle",
    "ShieldArcParticle",
    "OrbitParticle",
    "StreakParticle",
    "SweatParticle",
    "clear_frame_cache",
    "dash_direction",
    "iter_landing_entities",
    "spawn_dash_burst",
    "spawn_dash_shockwave",
    "spawn_dash_streak",
    "spawn_dash_wind",
    "spawn_dizzy_stars",
    "spawn_dizzy_vortex",
    "spawn_guard_arc",
    "spawn_shatter_arc",
    "spawn_impact_decal",
    "spawn_landing_dust",
    "spawn_sweat_drops",
    "vortex_frames",
]
