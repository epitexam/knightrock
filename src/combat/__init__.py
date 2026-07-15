"""
Combat system package.

This package provides a frame-accurate, modular combat engine built around
the concept of frame data (startup, active, recovery).  It handles attack
state progression, hit detection, damage resolution, combo tracking, and
charge mechanics.

Public API
----------
The most commonly used classes and functions are re-exported here so that
external modules can import them directly from ``src.combat`` without
needing to know the internal file structure.

Example
-------
>>> from src.combat import CombatComponent, AttackDefinition
>>> from src.combat import CombatSystem, DamageType
"""

# ── Data Structures & Enums ───────────────────────────────────────────
from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig
from src.combat.frame_data import (
    FRAME_RATE,
    PhaseState,
    HitProperties,
    PhaseDefinition,
    AttackDefinition,
)

# ── Protocols ─────────────────────────────────────────────────────────
from src.combat.combatant_protocol import Combatant, BlockingCombatant

# ── Core Components ───────────────────────────────────────────────────
from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.combat.combat_system import CombatSystem

# ── Utilities ─────────────────────────────────────────────────────────
from src.combat.attack_loading import load_attacks

# ── Attack Database ───────────────────────────────────────────────────
from src.combat.attack_data import PLAYER_ATTACKS, GOBLIN_ATTACKS, SLIME_ATTACKS


__all__ = [
    # Data & Enums
    "DamageType",
    "KnockbackConfig",
    "FRAME_RATE",
    "PhaseState",
    "HitProperties",
    "PhaseDefinition",
    "AttackDefinition",
    # Protocols
    "Combatant",
    "BlockingCombatant",
    # Core
    "CombatComponent",
    "NullCombatComponent",
    "CombatSystem",
    # Utilities
    "load_attacks",
    # Database
    "PLAYER_ATTACKS",
    "GOBLIN_ATTACKS",
    "SLIME_ATTACKS",
]