"""Combat system: frame-accurate attacks built around frame data.

Startup / active / recovery, hit detection, damage resolution, combo tracking
and charge mechanics. The per-tick hit-detection *system* (``CombatSystem``) is
a level pipeline stage and lives in ``src.core.level.systems`` (audit §4).

Nothing is re-exported here. The package docstring used to advertise a public
API -- ``from src.combat import CombatComponent, AttackDefinition`` -- behind 18
re-exports, and no module in the repository took it up: every one of them
imports from the leaf module that defines the name. Keeping a second spelling
of an 18-name surface is a rename hazard, not a convenience.
"""
