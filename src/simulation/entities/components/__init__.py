"""Per-entity components extracted from ``Entity`` (audit Phase 3 #2).

``Entity`` used to own both its kinematic state (velocity, surface
contacts) and its hit-reaction rules (knockback, heavy launch, stagger)
inline, alongside the already-composed ``Vitals`` and ``CombatComponent``.
This package finishes the composition: the movement and reaction
responsibilities live in dedicated components, wired into ``Entity``
exactly like ``vitals``/``combat``.

Nothing is re-exported here. ``Entity`` imports the two components and the
helpers it uses from ``movement`` and ``reaction`` directly, so every name this
package used to forward was a second spelling that had to be found before it
could be renamed.
"""
