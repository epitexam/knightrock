"""
Hit resolution: damage calculation, knockback, stagger, and special effects.

The ``HitResolver`` is a stateless utility that computes and applies the
consequences of a single hit.  It is called by ``CombatSystem`` whenever
a hitbox collision is detected.
"""

from __future__ import annotations

from src.combat.combatant_protocol import Combatant, DamageResult
from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig


class HitResolver:
    """Static utility for resolving a hit between an attacker and a target.

    All methods are stateless; the resolver holds no mutable state and can
    be used as a namespace or called via class methods.
    """

    @staticmethod
    def resolve(
        attacker: Combatant,
        target: Combatant,
        hit: HitProperties,
        charge_multiplier: float = 1.0,
    ) -> DamageResult:
        """Calculate and apply damage, knockback, stagger, and finisher.

        The resolution flow:

        1. Compute final damage = ``hit.damage × charge_multiplier × type_modifier``.
        2. Compute scaled knockback by applying ``charge_multiplier`` to the
           base knockback power vectors.
        3. Apply damage and inspect its explicit ``DamageResult``.
        4. Stop immediately for blocked or immune hits.
        5. Resolve armor break and finishers only after applied damage.
        6. Interrupt and stagger only living targets not already reacting to
           heavy knockback or protected by super armor.

        Parameters
        ----------
        attacker : Combatant
            The entity performing the attack.
        target : Combatant
            The entity being hit.
        hit : HitProperties
            Hit properties from the active phase definition.
        charge_multiplier : float
            Damage and knockback multiplier from charging (default 1.0).

        Returns
        -------
        DamageResult
            Combined outcome, including any finisher damage.
        """
        type_mult = target.get_damage_modifier(hit.damage_type)
        final_damage = int(hit.damage * charge_multiplier * type_mult)

        if final_damage <= 0:
            return DamageResult()

        scaled_power = (
            hit.knockback.power[0] * charge_multiplier,
            hit.knockback.power[1] * charge_multiplier,
        )
        effective_knockback = KnockbackConfig(
            power=scaled_power, mode=hit.knockback.mode)

        source_x: float = attacker.hitbox.centerx

        armor_absorbs_reaction = (
            target.has_super_armor and not hit.super_armor_break
        )
        applied_knockback = None if armor_absorbs_reaction else effective_knockback
        result = target.receive_damage(
            final_damage, source_x, applied_knockback
        )

        # Blocking, invincibility, death, or any future immunity is authoritative:
        # no interruption, stagger, armor break, or finisher may leak through.
        if not result.applied:
            return result

        if target.has_super_armor and hit.super_armor_break:
            target.break_super_armor()

        if (
            hit.is_finisher
            and not result.killed
            and target.health <= target.max_health * 0.2
        ):
            finisher_result = target.receive_damage(
                target.health, source_x, effective_knockback
            )
            result = DamageResult(
                applied=result.applied or finisher_result.applied,
                blocked=finisher_result.blocked,
                killed=finisher_result.killed,
                actual_damage=(
                    result.actual_damage + finisher_result.actual_damage
                ),
                heavy_knockback=(
                    result.heavy_knockback
                    or finisher_result.heavy_knockback
                ),
            )

        if (
            not result.killed
            and not armor_absorbs_reaction
            and not result.heavy_knockback
        ):
            target.combat.on_hit(interrupt=True)
            if hit.stagger > 0:
                target.stagger(hit.stagger)

        return result
