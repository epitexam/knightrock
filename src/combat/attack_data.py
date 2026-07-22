"""
Centralized attack data for all entities.

This module converts design intent into precise frame data using the new
architecture. Balancing can be done here without modifying core systems.
"""

from src.combat.frame_data import (
    AttackDefinition,
    HitProperties,
    PhaseDefinition,
)
from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig


PLAYER_ATTACKS = {

    "light_attack": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=3,
                active_frames=6,
                recovery_frames=3,
                hitbox_size=(40.0, 20.0),
                hitbox_offset=(24.0, -4.0),
                hit=HitProperties(
                    damage=8,
                    knockback=KnockbackConfig(power=(150.0, -50.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.1,
                ),
            ),
        ),
        cooldown=0.30,
        lock_direction=True,
    ),

    "heavy_attack": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=8,
                active_frames=6,
                recovery_frames=8,
                hitbox_size=(55.0, 35.0),
                hitbox_offset=(32.0, -10.0),
                hit=HitProperties(
                    damage=18,
                    knockback=KnockbackConfig(power=(300.0, -200.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.3,
                    super_armor_break=True,
                ),
            ),
        ),
        cooldown=0.80,
        lock_direction=True,
        combo_reset=True,
        chargeable=True,
        max_charge_time=1.0,
    ),

    "uppercut": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=5,
                active_frames=5,
                recovery_frames=9,
                hitbox_size=(30.0, 50.0),
                hitbox_offset=(18.0, -30.0),
                hit=HitProperties(
                    damage=16,
                    knockback=KnockbackConfig(power=(400.0, -2500.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.4,
                    super_armor_break=True,
                ),
            ),
        ),
        cooldown=0.90,
        lock_direction=True,
        combo_reset=True,
    ),

    "dash_attack": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=2,
                active_frames=7,
                recovery_frames=5,
                hitbox_size=(60.0, 20.0),
                hitbox_offset=(38.0, -6.0),
                hit=HitProperties(
                    damage=14,
                    knockback=KnockbackConfig(power=(500.0, -50.0)),
                    damage_type=DamageType.PIERCE,
                    stagger=0.2,
                    super_armor_break=True,
                ),
            ),
        ),
        cooldown=0.60,
        lock_direction=True,
    ),

    "air_attack": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=3,
                active_frames=8,
                recovery_frames=4,
                hitbox_size=(45.0, 25.0),
                hitbox_offset=(26.0, -2.0),
                hit=HitProperties(
                    damage=10,
                    knockback=KnockbackConfig(power=(180.0, -120.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.1,
                ),
            ),
        ),
        cooldown=0.35,
        lock_direction=False,
    ),

    "special_attack": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=6,
                active_frames=8,
                recovery_frames=4,
                hitbox_size=(30.0, 30.0),
                hitbox_offset=(0.0, -20.0),
                hit=HitProperties(
                    damage=12,
                    knockback=KnockbackConfig(power=(100.0, -100.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.5,
                    super_armor_break=True,
                ),
                reset_targets=True,
            ),
            PhaseDefinition(
                startup_frames=6,
                active_frames=8,
                recovery_frames=4,
                hitbox_size=(40.0, 40.0),
                hitbox_offset=(0.0, -20.0),
                hit=HitProperties(
                    damage=12,
                    knockback=KnockbackConfig(power=(100.0, -100.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.5,
                    super_armor_break=True,
                ),
                reset_targets=True,
            ),
            PhaseDefinition(
                startup_frames=6,
                active_frames=8,
                recovery_frames=4,
                hitbox_size=(50.0, 50.0),
                hitbox_offset=(0.0, -20.0),
                hit=HitProperties(
                    damage=12,
                    knockback=KnockbackConfig(power=(100.0, -100.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.5,
                    super_armor_break=True,
                ),
                reset_targets=True,
            ),

            PhaseDefinition(
                startup_frames=6,
                active_frames=8,
                recovery_frames=4,
                hitbox_size=(70.0, 70.0),
                hitbox_offset=(0.0, -20.0),
                hit=HitProperties(
                    damage=12,
                    knockback=KnockbackConfig(power=(100.0, -100.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.5,
                    super_armor_break=True,
                ),
                reset_targets=True,
            ),
            PhaseDefinition(
                startup_frames=3,
                active_frames=10,
                recovery_frames=25,
                hitbox_size=(90.0, 90.0),
                hitbox_offset=(0.0, -20.0),
                hit=HitProperties(
                    damage=30,
                    knockback=KnockbackConfig(power=(900.0, -600.0)),
                    damage_type=DamageType.PIERCE,
                    stagger=0.8,
                    super_armor_break=True,
                ),
            ),
        ),
        cooldown=0.5,
        lock_direction=True,
        combo_reset=True,
    ),
}

GOBLIN_ATTACKS = {
    "claw_swipe": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=4,
                active_frames=5,
                recovery_frames=4,
                hitbox_size=(40, 20),
                hitbox_offset=(20, -4),
                hit=HitProperties(
                    damage=8,
                    knockback=KnockbackConfig(power=(100.0, -80.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.1,
                ),
            ),
            PhaseDefinition(
                startup_frames=2,
                active_frames=5,
                recovery_frames=5,
                hitbox_size=(48, 24),
                hitbox_offset=(24, 4),
                hit=HitProperties(
                    damage=10,
                    knockback=KnockbackConfig(power=(120.0, -150.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.15,
                ),
                reset_targets=True,
            ),
        ),
        cooldown=1.0,
        lock_direction=True,
    ),
}

SLIME_ATTACKS = {
    "body_slam": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=6,
                active_frames=5,
                recovery_frames=7,
                hitbox_size=(36.0, 22.0),
                hitbox_offset=(22.0, 2.0),
                hit=HitProperties(
                    damage=6,
                    knockback=KnockbackConfig(power=(90.0, -120.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.08,
                ),
            ),
        ),
        cooldown=1.25,
        lock_direction=True,
    ),
}
