"""Fixed-tick systems orchestrated by a level (audit F1.2 / F1.6, §4).

``core/level/level.py`` is a *facade* that assembles the world and hands the
per-tick work to :class:`GameplayLoop`, which owns the ordered pipeline. This
package holds the stages it sequences: the per-tick world steps (platforms,
physics, hazards, respawn, progression), the entity-pairing systems (combat,
separation, contact/hazard damage), the debug spawner and the tick bookkeeping.

Nothing is re-exported here. Every consumer imports from the stage's own
module -- ``level.py`` and ``gameplay_loop.py`` reach each of them directly --
so a name in this package would be a second spelling of a module attribute
that has to be found before it can be renamed. It used to re-export all 20 and
was imported by nobody, including the test that would have covered it.
"""
