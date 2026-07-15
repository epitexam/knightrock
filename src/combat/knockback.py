"""
Data structure defining the push impulse applied to a target on hit.

Knockback is separated into its own module so it can be reused by both
frame data definitions and the hit resolver without circular imports.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class KnockbackConfig:
    """Immutable push velocity applied to the target on hit.

    Parameters
    ----------
    power : tuple[float, float]
        Horizontal (x) and vertical (y) impulse in px/s applied on hit.

        x — push strength away from the attacker.
            Typical range: 100–500.  Above 600 sends the target offscreen.
            0 produces a purely vertical launch.
        y — vertical push; **negative values push upward**.
            Typical range: -50 (grounded) to -1200 (full uppercut launch).
            Positive y slams the target downward (air-to-ground moves).

    mode : {"from_attacker", "fixed"}
        ``from_attacker`` — x direction is derived from the relative
        positions of attacker and target (standard).  Always pushes away.
        ``fixed`` — power is applied as-is, ignoring positions.  Use for
        traps, environmental hazards, or moves with a fixed launch angle.

    Examples
    --------
    >>> KnockbackConfig(power=(250, -150))
    KnockbackConfig(power=(250.0, -150.0), mode='from_attacker')
    >>> KnockbackConfig(power=(0, -800), mode="fixed")
    KnockbackConfig(power=(0.0, -800.0), mode='fixed')
    """
    power: tuple[float, float] = (250.0, -150.0)
    mode: Literal["from_attacker", "fixed"] = "from_attacker"