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

The rim, though, is a rule with an exception rather than the rule itself. The
block's ring and the dash trail both dropped theirs: a mid-grey outline at
one pixel per world unit turns a mark into a drawn shape with nothing light
about it, and both of those are read as light -- a shield taking a hit, and
the dust a dash throws. The landing dust keeps its rim because it sits on the
ground against tiles, where the edge is the thing doing the work. Where the
rim goes, a second tone takes over: a brighter arc on the struck side of the
ring, and a lit rim along the top of the cloud.

Dust is grit, and grit has no silhouette
----------------------------------------
The dust is the one effect in the plane that was rebuilt for its look rather
than its behaviour, and it took three passes to get there. It began as a
single disc that faded, which read as a ball being switched off, and became
four large overlapping discs with a disc of highlight set into the top left of
the lot -- which read as a bubble, because the union of four discs of
comparable radius is one smooth convex oval whatever you offset them by, and
because a round patch of light inside a round mass is how a bubble, a pearl
and a children's-book cloud are all drawn. Neither of those is fixable by
making the outline lumpier; the second is not about the outline at all.

So the cloud is a band of small parts -- a connected lower one and a scattered
fringe above it, because a single height distribution pulls the lower parts out
of each other's reach and the sheet falls apart into separate puffs hanging in
the air. It is lit by a one-pixel rim laid along the top left of the whole
silhouette rather than by a patch of light inside it, and that rim cannot
contain a two-by-two square: it is the shape drawn one pixel up and to the left
and then overdrawn by itself, so the same pixel cannot be both covered and
uncovered. ``test_fx_draw`` asserts that arithmetic, and it is what stops the
disc of highlight coming back as a matter of taste.

And most of the parts are chips rather than discs, which took a second pass
once the first two were done. Every arc on a silhouette is a bubble however
small it is: fifteen little circles make fifteen little bubbles along the
outline, and what the eye reads is the arcs rather than the count, so a
"granular" sheet of discs is still a cluster of beads. Straight runs are what
break it. A chip is four to six sides with a heading of its own, drawn about
40 % larger than the disc it replaces because a polygon covers appreciably less
than the circle inscribed in the same radius -- and that is the difference
between a sheet of dust and a heap of gravel, since swapping part for part at
one radius thins the band rather than squaring it.

The other half is :class:`DustGrain`. A kick off a floor throws small particles
that travel further than the mass does and arrive first, and a mark with no
spray around it is a puff of smoke however well it is shaded. Grains are a
separate family on a separate budget, three pixels square at most and never
opaque, so a plane that is already full sheds the grit rather than the landing.
They are the majority of a landing on purpose: the spray is the punctuation and
the sheet is the sentence.

Which particles rebuild their surface
-------------------------------------
A particle that redraws its pixels every frame pays for a drawing, not for an
allocation, so the only question is whether its *look* changes. Two of them
used to, and both stopped: the shockwave is drawn once at full size and shown
through a few pre-scaled steps, and the dizzy swirl is a shared ladder of
rotation steps.

The dust was the last particle still on shipped art -- three anti-aliased PNGs
under ``assets/graphics``, a tree that is gitignored, so the look already
differed from one machine to the next and ``radius`` did nothing at all. It is
painted now, like the rest of the plane, and it opens over its life from a
shared ladder keyed on size, tone *and silhouette*, so a fan of four is four
references into a table rather than four surfaces allocated on the landing
tick. The silhouette is part of that key because tone and size are both global
properties of a mark: a fan that varies only those is one shape stamped four
times at four zoom levels, which is a spinner. The dash trail is painted the
same way and shares the reasoning: a dash lays puffs on a cadence rather than
in one fan, so there are more of them alive at once and the ladder binds
harder, not softer.

Everything here builds its surface at construction and then only moves, fades
or steps through a ladder it built alongside, which is what
``tests/unit/test_fx_surfaces.py`` pins.
"""

from __future__ import annotations

from src.core.fx.particles import (
    DashDustParticle,
    DizzyVortexParticle,
    DustParticle,
    GrainParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    SweatParticle,
    clear_frame_cache,
    dash_frames,
    dash_tint,
    puff_frames,
    vortex_frames,
)
from src.core.fx.spawners import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    iter_landing_entities,
    spawn_dash_dust,
    spawn_dash_grains,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_landing_grains,
    spawn_shatter_arc,
    spawn_sweat_drops,
)

__all__ = [
    "FX_FAMILY_BUDGETS",
    "MAX_FX_SPRITES",
    "DashDustParticle",
    "DizzyVortexParticle",
    "DustParticle",
    "GrainParticle",
    "ShatterArcParticle",
    "ShieldArcParticle",
    "OrbitParticle",
    "SweatParticle",
    "clear_frame_cache",
    "dash_frames",
    "dash_tint",
    "iter_landing_entities",
    "puff_frames",
    "spawn_dash_dust",
    "spawn_dash_grains",
    "spawn_dizzy_stars",
    "spawn_dizzy_vortex",
    "spawn_guard_arc",
    "spawn_shatter_arc",
    "spawn_impact_decal",
    "spawn_landing_dust",
    "spawn_landing_grains",
    "spawn_sweat_drops",
    "vortex_frames",
]
