"""HazardSystem: hazard sprite stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/hazard_system``).

Damage application is deliberately *not* part of this stage:
:class:`~src.core.level.systems.hazard_damage.HazardDamageSystem` runs later
in the pipeline, once the entities have moved.
"""

from src.core.sprite_groups import SpriteGroups

__all__ = ["HazardSystem"]


class HazardSystem:
    """Tick the hazard sprites (saws, spikes, orbiting hazards) once per step."""

    def __init__(self, groups: SpriteGroups) -> None:
        self.groups = groups

    def process(self, delta_time: float) -> None:
        """Advance every hazard sprite."""
        for hazard in self.groups.hazard_sprites:
            capture = getattr(hazard, "capture_contact_origin", None)
            if callable(capture):
                capture()
        self.groups.hazard_sprites.update(delta_time)
