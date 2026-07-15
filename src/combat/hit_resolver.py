"""
Hit resolution: damage calculation, knockback, stagger, and special effects.

The ``HitResolver`` is a stateless utility that computes and applies the
consequences of a single hit.  It is called by ``CombatSystem`` whenever
a hitbox collision is detected.
"""

from __future__ import annotations

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties


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
    ) -> None:
        """Calculate and apply damage, knockback, stagger, and finisher.

        The resolution flow:

        1. Compute final damage = ``hit.damage × charge_multiplier × type_modifier``.
        2. If the target has super armor **and** the hit does not break it:
           - Apply damage without knockback.
           - Notify the target's combat component with ``interrupt=False``.
        3. Otherwise:
           - Break super armor if applicable.
           - Apply damage with knockback.
           - Notify the target's combat component with ``interrupt=True``.
           - Apply stagger if ``hit.stagger > 0``.
        4. If the hit is a finisher and the target is below 20 % HP:
           - Deal damage equal to remaining HP (kills the target).

        Parameters
        ----------
        attacker : Combatant
            The entity performing the attack.
        target : Combatant
            The entity being hit.
        hit : HitProperties
            Hit properties from the active phase definition.
        charge_multiplier : float
            Damage multiplier from charging (default 1.0).

        Raises
        ------
        AttributeError
            If ``target.combat`` does not expose an ``on_hit`` method.
        """
        type_mult = target.get_damage_modifier(hit.damage_type)
        final_damage = int(hit.damage * charge_multiplier * type_mult)

        if final_damage <= 0:
            return

        source_x: float = attacker.hitbox.centerx

        if target.has_super_armor and not hit.super_armor_break:
            target.receive_damage(final_damage, source_x, None)
            target.combat.on_hit(interrupt=False)
        else:
            if target.has_super_armor and hit.super_armor_break:
                target.break_super_armor()

            target.receive_damage(final_damage, source_x, hit.knockback)
            target.combat.on_hit(interrupt=True)

            if hit.stagger > 0:
                target.stagger(hit.stagger)

        if (
            hit.is_finisher
            and not target.is_dead
            and target.health <= target.max_health * 0.2
        ):
            target.receive_damage(int(target.health), source_x, hit.knockback)