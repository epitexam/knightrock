"""What a move can throw: the shots a launching phase lets fly.

A phase that names a shot (``launches`` in ``attacks.json``) throws it as it
turns active, from the hand at ``muzzle`` (forward, up from the body's
centre), at ``speed`` forward and ``rise`` upward (negative is up, as on
screen). The flight itself is a pooled :class:`~src.simulation.entities.projectile.Projectile`.

The shots live here rather than in the JSON because they are few, and each
is as much a look (``ProjectileConfig.look``) as a balance: the bolt the
blade spits, the full-charge one that pierces, the slime's lobbed glob.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.shared.damage_types import DamageType
from src.simulation.combat.frame_data import Height, HitProperties
from src.simulation.combat.knockback import KnockbackConfig
from src.simulation.combat.shapes import ShapeKind
from src.simulation.entities.projectile import ProjectileConfig

__all__ = ["SHOTS", "ShotSpec", "charged"]


@dataclass(frozen=True)
class ShotSpec:
    """One shot: what flies, how fast, and from where."""

    config: ProjectileConfig
    speed: float
    rise: float = 0.0
    muzzle: tuple[float, float] = (18.0, -6.0)


SHOTS: dict[str, ShotSpec] = {
    # The blade's battery fired as a short bolt: little damage, a flinch that
    # breaks an enemy's wind-up from out of reach, at a battery cost.
    "bolt": ShotSpec(
        config=ProjectileConfig(
            size=(14.0, 4.0),
            lifetime=0.45,
            shape=ShapeKind.OBB,
            hit=HitProperties(
                damage=3.0,
                knockback=KnockbackConfig(power=(40.0, 0.0)),
                damage_type=DamageType.PIERCE,
                stagger=0.18,
                height=Height.MID,
                flinch=True,
                hit_stop=0.02,
                stun=3.0,
            ),
            look="bolt",
        ),
        speed=560.0,
    ),
    # The full charge: a wide bolt that goes through every guard and every
    # enemy on its line.
    "piercing_bolt": ShotSpec(
        config=ProjectileConfig(
            size=(22.0, 8.0),
            lifetime=0.55,
            shape=ShapeKind.OBB,
            hit=HitProperties(
                damage=9.0,
                knockback=KnockbackConfig(power=(180.0, -60.0)),
                damage_type=DamageType.PIERCE,
                stagger=0.35,
                unblockable=True,
                height=Height.MID,
                hit_stop=0.06,
                stun=12.0,
            ),
            pierce=True,
            look="charged_bolt",
        ),
        speed=680.0,
    ),
    # The full charge of the blade throws its cut forward: a crescent that
    # goes through guards and keeps going, short-lived.
    "crescent": ShotSpec(
        config=ProjectileConfig(
            size=(10.0, 30.0),
            lifetime=0.32,
            shape=ShapeKind.OBB,
            hit=HitProperties(
                damage=7.0,
                knockback=KnockbackConfig(power=(160.0, -50.0)),
                damage_type=DamageType.SLASH,
                stagger=0.3,
                unblockable=True,
                height=Height.MID,
                hit_stop=0.08,
                stun=12.0,
            ),
            pierce=True,
            look="crescent",
        ),
        speed=420.0,
        muzzle=(24.0, 0.0),
    ),
    # The slime spits a glob in an arc: it lands at the player's feet, so it
    # is low -- jumped, or guarded low.
    "glob": ShotSpec(
        config=ProjectileConfig(
            size=(12.0, 12.0),
            lifetime=1.4,
            shape=ShapeKind.CIRCLE,
            hit=HitProperties(
                damage=8.0,
                knockback=KnockbackConfig(power=(90.0, -80.0)),
                damage_type=DamageType.BLUNT,
                stagger=0.2,
                height=Height.LOW,
            ),
            gravity=900.0,
            look="glob",
        ),
        speed=210.0,
        rise=-300.0,
        muzzle=(10.0, -4.0),
    ),
}


def charged(spec: ShotSpec, charge_multiplier: float) -> ShotSpec:
    """``spec`` thrown at ``charge_multiplier``: bigger, harder, as a charged blow is.

    The size grows like a charged blow's reach (``Combat.CHARGE_REACH_GAIN``);
    damage, push and stun by the multiplier itself, as the resolver scales a
    melee hit.
    """
    if charge_multiplier <= 1.0:
        return spec
    from src.simulation.combat.hitbox_manager import charge_reach_scale

    grow = charge_reach_scale(charge_multiplier)
    config = spec.config
    hit = config.hit
    power = hit.knockback.power
    hit = replace(
        hit,
        damage=hit.damage * charge_multiplier,
        stun=hit.stun * charge_multiplier,
        knockback=replace(
            hit.knockback, power=(power[0] * charge_multiplier, power[1] * charge_multiplier)
        ),
    )
    size = (config.size[0] * grow, config.size[1] * grow)
    return replace(spec, config=replace(config, size=size, hit=hit))
