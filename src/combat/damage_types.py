"""
Defines the types of damage that can be dealt in the combat system.
"""
from enum import Enum

class DamageType(Enum):
    """Enumeration of possible damage types."""
    SLASH = "slash"
    BLUNT = "blunt"
    PIERCE = "pierce"