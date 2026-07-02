"""
Centralized attack data for all entities.
Enables balancing without modifying the code.
"""
from src.combat.attack_types import AttackPhase, AttackSequence, KnockbackConfig


PLAYER_ATTACKS = {

    "light_attack": AttackSequence(
        phases=[
            AttackPhase(
                size=(40.0, 20.0),
                offset=(24.0, -4.0),
                damage=8,
                duration=0.10,
                knockback=KnockbackConfig(power=(150.0, -50.0)),
                damage_type="slash",
                stagger=0.1,
            ),
        ],
        cooldown=0.30,
        lock_direction=True,
    ),

    "heavy_attack": AttackSequence(
        phases=[
            AttackPhase(
                size=(55.0, 35.0),
                offset=(32.0, -10.0),
                damage=18,
                duration=0.25,
                knockback=KnockbackConfig(power=(300.0, -200.0)),
                damage_type="blunt",
                stagger=0.3,
                super_armor_break=True,
            ),
        ],
        cooldown=0.80,
        lock_direction=True,
    ),

    "uppercut": AttackSequence(
        phases=[
            AttackPhase(
                size=(30.0, 50.0),
                offset=(18.0, -30.0),
                damage=16,
                duration=0.20,
                knockback=KnockbackConfig(power=(400.0, -2500.0)),
                damage_type="blunt",
                stagger=0.4,
                super_armor_break=True,
            ),
        ],
        cooldown=0.90,
        lock_direction=True,
    ),

    "dash_attack": AttackSequence(
        phases=[
            AttackPhase(
                size=(60.0, 20.0),
                offset=(38.0, -6.0),
                damage=14,
                duration=0.12,
                knockback=KnockbackConfig(power=(500.0, -50.0)),
                damage_type="pierce",
                stagger=0.2,
                super_armor_break=True,
            ),
        ],
        cooldown=0.60,
        lock_direction=True,
    ),

    "air_attack": AttackSequence(
        phases=[
            AttackPhase(
                size=(45.0, 25.0),
                offset=(26.0, -2.0),
                damage=10,
                duration=0.14,
                knockback=KnockbackConfig(power=(180.0, -120.0)),
                damage_type="slash",
                stagger=0.1,
            ),
        ],
        cooldown=0.35,
        lock_direction=False,
    ),
}

GOBLIN_ATTACKS = {
    "claw_swipe": AttackSequence(
        phases=[
            AttackPhase(
                size=(40, 20),
                offset=(20, -4),
                damage=0,
                duration=0.15,
                knockback=KnockbackConfig(power=(10.0, -80.0)),
                damage_type="slash",
                stagger=0.0,
            ),
            AttackPhase(
                size=(48, 24),
                offset=(24, 4),
                damage=0,
                duration=0.15,
                knockback=KnockbackConfig(power=(100.0, -150.0)),
                damage_type="slash",
                stagger=0.0,
            ),
        ],
        cooldown=1.0,
        lock_direction=True,
    ),
}
