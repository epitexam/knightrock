"""
Centralized attack data for all entities.

This module converts design intent into precise frame data using the new
architecture. Balancing can be done here without modifying core systems.
"""

from src.combat.damage_types import DamageType
from src.combat.frame_data import (
    AttackDefinition,
    HitboxKeyframe,
    HitboxSpec,
    HitProperties,
    PhaseDefinition,
)
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
                cancel_into=("heavy_attack", "uppercut", "dash_attack"),
            ),
        ),
        cooldown=0.30,
        lock_direction=True,
        attack_move_multiplier=0.5,
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
        charge_move_multiplier=0.4,
        attack_move_multiplier=0.15,
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
                    knockback=KnockbackConfig(power=(400.0, -550.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.4,
                    super_armor_break=True,
                ),
            ),
        ),
        cooldown=0.90,
        lock_direction=True,
        combo_reset=True,
        attack_move_multiplier=0.2,
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
                cancel_into=("light_attack", "heavy_attack"),
            ),
        ),
        cooldown=0.60,
        lock_direction=True,
        lunge_speed_multiplier=0.9,
        attack_move_multiplier=0.6,
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
                cancel_into=("light_attack",),
            ),
        ),
        cooldown=0.35,
        lock_direction=False,
        attack_move_multiplier=0.6,
    ),
    # ── Phase 5 showcase (testables via les touches debug 1-4) ──
    "twin_fangs": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=4,
                active_frames=6,
                recovery_frames=6,
                hitbox_size=(45.0, 22.0),
                hitbox_offset=(26.0, -4.0),
                extra_hitboxes=(HitboxSpec(size=(30.0, 18.0), offset=(20.0, -24.0)),),
                hit=HitProperties(
                    damage=8,
                    knockback=KnockbackConfig(power=(180.0, -80.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.15,
                ),
                cancel_into=("light_attack", "heavy_attack"),
            ),
        ),
        cooldown=0.50,
        lock_direction=True,
        attack_move_multiplier=0.5,
    ),
    "sweeping_arc": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=6,
                active_frames=6,
                recovery_frames=5,
                hitbox_size=(40.0, 22.0),
                hitbox_offset=(24.0, -4.0),
                hitbox_keyframes=(
                    HitboxKeyframe(frame=0, size=(28.0, 14.0), offset=(16.0, -2.0)),
                    HitboxKeyframe(frame=6, size=(55.0, 28.0), offset=(30.0, -6.0)),
                    HitboxKeyframe(frame=12, size=(70.0, 34.0), offset=(38.0, -8.0)),
                ),
                hit=HitProperties(
                    damage=12,
                    knockback=KnockbackConfig(power=(220.0, -100.0)),
                    damage_type=DamageType.SLASH,
                    stagger=0.2,
                ),
                cancel_into=("light_attack",),
            ),
        ),
        cooldown=0.70,
        lock_direction=True,
        attack_move_multiplier=0.4,
    ),
    "sky_launcher": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=7,
                active_frames=5,
                recovery_frames=10,
                hitbox_size=(32.0, 48.0),
                hitbox_offset=(16.0, -28.0),
                hit=HitProperties(
                    damage=14,
                    knockback=KnockbackConfig(power=(250.0, -650.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.35,
                    super_armor_break=True,
                    juggle_gravity_mult=0.5,
                ),
            ),
        ),
        cooldown=1.0,
        lock_direction=True,
        combo_reset=False,
        attack_move_multiplier=0.2,
    ),
    "otg_slam": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=9,
                active_frames=4,
                recovery_frames=12,
                hitbox_size=(60.0, 30.0),
                hitbox_offset=(30.0, 10.0),
                hit=HitProperties(
                    damage=20,
                    knockback=KnockbackConfig(power=(200.0, 450.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.4,
                    super_armor_break=True,
                    otg_allowed=True,
                ),
            ),
        ),
        cooldown=1.2,
        lock_direction=True,
        combo_reset=True,
        attack_move_multiplier=0.15,
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
                    is_finisher=True,
                ),
            ),
        ),
        cooldown=2.0,
        lock_direction=True,
        combo_reset=True,
        lunge_speed_multiplier=0.0,
        attack_move_multiplier=0.1,
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
