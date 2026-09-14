"""Fixed-tick systems orchestrated by a level (audit F1.2 / F1.6, §4).

Target layout (audit §4): ``core/level/level.py`` is a *facade* that assembles
the world and hands the per-tick work to :class:`GameplayLoop`, which owns the
ordered pipeline.  This package hosts:

- the per-tick world stages (platforms, physics, hazards, respawn, progression);
- the entity-pairing systems (combat, separation, contact/hazard damage);
- the debug spawner;
- :class:`GameplayLoop`, the extended pipeline that sequences everything.
"""

from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.systems.separation_system import SeparationSystem
from src.core.level.systems.spawn_system import DebugController

__all__ = [
    "CombatSystem",
    "ContactDamageSystem",
    "DebugController",
    "GameplayLoop",
    "HazardDamageSystem",
    "SeparationSystem",
]
