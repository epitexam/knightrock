"""
Defines the types of damage that can be dealt in the combat system.

Damage types are used to calculate resistance multipliers and determine
visual/audio feedback (sparks, blood, impact sounds).
"""

from enum import Enum


class DamageType(Enum):
    """Enumeration of possible damage types.

    Attributes
    ----------
    SLASH : str
        Cutting damage — swords, claws, blades.
    BLUNT : str
        Impact damage — hammers, fists, body slams.
    PIERCE : str
        Penetrating damage — spears, arrows, thrusts.
    """
    SLASH = "slash"
    BLUNT = "blunt"
    PIERCE = "pierce"