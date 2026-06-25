"""
Centralized attack data for all entities.
Enables balancing without modifying the code.
"""
from src.combat.attack_types import AttackPhase, AttackSequence, KnockbackConfig


PLAYER_ATTACKS = {
    "ground_combo": AttackSequence(
        phases=[
            AttackPhase(
                size=(38.0, 22.0),
                offset=(22.0, -2.0),
                damage=7,
                duration=0.10,
                knockback=KnockbackConfig(power=(200.0, -80.0)),
            ),
            AttackPhase(
                size=(46.0, 26.0),
                offset=(28.0, -6.0),
                damage=13,
                duration=0.16,
                knockback=KnockbackConfig(power=(300.0, -130.0)),
            ),
        ],
        cooldown=0.65,
        lock_direction=True,
    ),
    "heavy_smash": AttackSequence(
        phases=[
            AttackPhase(
                size=(55.0, 42.0),
                offset=(34.0, -26.0),
                damage=20,
                duration=0.25,
                knockback=KnockbackConfig(power=(250.0, -320.0)),
            ),
            AttackPhase(
                size=(68.0, 16.0),
                offset=(28.0, 8.0),
                damage=8,
                duration=0.15,
                knockback=KnockbackConfig(power=(420.0, -30.0)),
            ),
        ],
        cooldown=1.3,
        lock_direction=True,
    ),
    "uppercut": AttackSequence(
        phases=[
            AttackPhase(
                size=(36.0, 20.0),
                offset=(22.0, 2.0),
                damage=6,
                duration=0.08,
                knockback=KnockbackConfig(power=(150.0, -60.0)),
            ),
            AttackPhase(
                size=(30.0, 52.0),
                offset=(16.0, -32.0),
                damage=15,
                duration=0.20,
                knockback=KnockbackConfig(power=(900.0, -1200.0)),
            ),
        ],
        cooldown=0.9,
        lock_direction=True,
    ),
    "dash_strike": AttackSequence(
        phases=[
            AttackPhase(
                size=(58.0, 20.0),
                offset=(36.0, -8.0),
                damage=14,
                duration=0.14,
                knockback=KnockbackConfig(power=(480.0, -60.0)),
            ),
        ],
        cooldown=0.7,
        lock_direction=True,
    ),
    "air_combo": AttackSequence(
        phases=[
            AttackPhase(
                size=(50.0, 26.0),
                offset=(28.0, -4.0),
                damage=9,
                duration=0.13,
                knockback=KnockbackConfig(power=(220.0, -100.0)),
            ),
            AttackPhase(
                size=(40.0, 34.0),
                offset=(20.0, 14.0),
                damage=14,
                duration=0.17,
                knockback=KnockbackConfig(power=(180.0, 250.0)),
            ),
        ],
        cooldown=0.95,
        lock_direction=False,
    ),
}

GOBLIN_ATTACKS = {
    "claw_swipe": AttackSequence(
        phases=[
            AttackPhase(
                size=(50, 30),
                offset=(25, -5),
                damage=10,
                duration=0.15,
                knockback=KnockbackConfig(power=(200.0, -100.0)),
            ),
            AttackPhase(
                size=(65, 35),
                offset=(32, 5),
                damage=15,
                duration=0.15,
                knockback=KnockbackConfig(power=(260.0, -180.0)),
            ),
        ],
        cooldown=1.0,
        lock_direction=True,
    ),
}