"""What the drawing reads on a fighter and the simulation never does."""

from dataclasses import dataclass


@dataclass(slots=True)
class RenderHints:
    """Render-only state of one entity: never snapshotted, never read by a rule.

    Kept apart from the entity's simulation state so the split is a type and
    not a comment per field: a rollback restores everything on the entity
    except this object, and nothing in the fixed tick may branch on it.
    """

    flash_timer: float = 0.0
    """Seconds left of the white wash a hit that dealt damage leaves."""

    parry_flash_timer: float = 0.0
    """Seconds left of the gold wash a perfect guard leaves."""

    reaction_age: float = 0.0
    """Seconds for which the last hit reaction still counts as fresh."""

    landed_impact: float = 0.0
    """Fall speed on the tick the entity touched down, 0 on every other tick."""

    turn_ratio: float = 0.0
    """How far through a pivot the fighter is: 1 at the start, 0 when the facing lands."""

    def tick(self, delta_time: float) -> None:
        """Run the three timers down; the other two are written each tick by their owners."""
        if self.flash_timer > 0.0:
            self.flash_timer = max(0.0, self.flash_timer - delta_time)
        if self.parry_flash_timer > 0.0:
            self.parry_flash_timer = max(0.0, self.parry_flash_timer - delta_time)
        if self.reaction_age > 0.0:
            self.reaction_age = max(0.0, self.reaction_age - delta_time)
