"""
Hit resolution: damage calculation, knockback, stagger, and special effects.

The ``HitResolver`` is a stateless utility that computes and applies the
consequences of a single hit.  It is called by ``CombatSystem`` whenever
a hitbox collision is detected.
"""

from __future__ import annotations

from src.combat.combatant_protocol import AttackerPort, Combatant, DamageResult
from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.core.settings import Physics
from src.states.reaction_states import DIZZY_STATE


def _is_grounded(target: Combatant) -> bool:
    """Grounded victim: no juggle, OTG rules may apply (Phase 5 #4)."""
    return bool(target.on_surface.get("floor", False))


def _juggle_scale(attacker_air_count: int) -> float:
    """Diminishing air-hit returns, floored so juggles cost pressure, not HP."""
    return max(
        CombatSettings.JUGGLE_DAMAGE_FLOOR,
        1.0 - float(attacker_air_count or 0) * CombatSettings.JUGGLE_DECAY_STEP,
    )


def _otg_blocked(grounded: bool, otg_timer: float, hit: HitProperties) -> bool:
    """Grounded OTG window without the OTG flag blocks the hit."""
    return bool(grounded and otg_timer > 0.0 and not hit.otg_allowed)


def _finisher_damage(hit: HitProperties, target: Combatant, final_damage: float) -> float:
    """Atomic finisher below 20 % of max health."""
    if hit.is_finisher and target.health - final_damage <= target.max_health * 0.2:
        return target.health
    return final_damage


def _scaled_knockback(
    hit: HitProperties, charge_multiplier: float, juggle_scale: float
) -> KnockbackConfig:
    """Knockback scaled by charge and juggle."""
    scaled_power = (
        hit.knockback.power[0] * charge_multiplier * juggle_scale,
        hit.knockback.power[1] * charge_multiplier * juggle_scale,
    )
    return KnockbackConfig(power=scaled_power, mode=hit.knockback.mode)


def _apply_post_effects(
    attacker: AttackerPort,
    target: Combatant,
    hit: HitProperties,
    was_airborne: bool,
    juggle_scale: float,
    final_damage: float,
    armor_absorbs_reaction: bool,
    result: DamageResult,
) -> None:
    """Post-hit reactions, in preserved order.

    Armor break, juggle, combo recording, then interrupt/stagger unless the
    target died, armor absorbed the reaction, or knockback launched it.
    """
    if target.has_super_armor and hit.super_armor_break:
        target.break_super_armor()

    if was_airborne and hit.juggle_gravity_mult != 1.0:
        target.set_juggle(hit.juggle_gravity_mult, CombatSettings.JUGGLE_GRAVITY_TIME)

    attacker.combat.record_hit_landed(was_airborne)

    # Dash refresh on hit: restore 1 charge when hitting during dash
    if Physics.DASH_REFRESH_ON_HIT:
        dash = getattr(attacker, "dash", None)
        state_machine = getattr(attacker, "state_machine", None)
        if (
            dash is not None
            and state_machine is not None
            and getattr(state_machine, "current_state_name", None) == "dash"
            and getattr(dash, "charges", 0) < getattr(dash, "max_charges", 0)
        ):
            dash.charges = min(dash.charges + 1, dash.max_charges)

    if not result.killed and not armor_absorbs_reaction and not result.heavy_knockback:
        target.combat.on_hit(interrupt=True)
        if hit.stagger > 0:
            effective_stagger = (
                hit.stagger * juggle_scale + final_damage * CombatSettings.HITSTUN_DAMAGE_FACTOR
            )
            target.stagger(effective_stagger)


class HitResolver:
    """Static utility for resolving a hit between an attacker and a target.

    All methods are stateless; the resolver holds no mutable state and can
    be used as a namespace or called via class methods.
    """

    @staticmethod
    def resolve(
        attacker: AttackerPort,
        target: Combatant,
        hit: HitProperties,
        charge_multiplier: float = 1.0,
        zone_mult: float = 1.0,
    ) -> DamageResult:
        """Calculate and apply damage, knockback, stagger, and finisher.

        The resolution flow:

        1. Compute final damage = ``hit.damage × charge_multiplier ×
           zone_mult × type_modifier``. ``zone_mult`` is the P2 localized
           damage multiplier (head ×1.2...); it scales damage only, never
           knockback — the field is named ``damage_mult`` in the design
           doc (§6.1), unlike the charge multiplier.
        2. Compute scaled knockback by applying ``charge_multiplier`` to the
           base knockback power vectors.
        3. Apply damage and inspect its explicit ``DamageResult``.
        4. Stop immediately for guarded, parried, or immune hits.
        5. Resolve armor break and finishers only after applied damage.
        6. Interrupt and stagger only living targets not already reacting to
           heavy knockback or protected by super armor.

        Parameters
        ----------
        attacker : AttackerPort
            Hit carrier (hitbox + combo tracking only).
        target : Combatant
            The entity being hit.
        hit : HitProperties
            Hit properties from the active phase definition.
        charge_multiplier : float
            Damage and knockback multiplier from charging (default 1.0).
        zone_mult : float
            P2 localized damage multiplier of the zone hit (default 1.0).

        Returns
        -------
        DamageResult
            Combined outcome, including any finisher damage.
        """
        type_mult = target.get_damage_modifier(hit.damage_type)
        grounded_before = _is_grounded(target)
        was_airborne = not grounded_before
        juggle_scale = 1.0
        if was_airborne:
            juggle_scale = _juggle_scale(attacker.combat.air_combo_count or 0)
        final_damage = hit.damage * charge_multiplier * zone_mult * type_mult * juggle_scale

        # DIZZY bonus: targets in dizzy state take extra damage
        if getattr(target, "state_machine", None) is not None:
            current = getattr(target.state_machine, "current_state_name", None)
            if current == DIZZY_STATE:
                final_damage *= CombatSettings.DIZZY_DAMAGE_MULT

        # INVINCIBILITY: entities with invincible tag (dash, hurt, knockback) cannot be hit
        if getattr(target, "is_invincible", False):
            return DamageResult()

        if final_damage <= 0:
            return DamageResult()

        if _otg_blocked(grounded_before, float(target.otg_timer or 0.0), hit):
            return DamageResult()

        final_damage = _finisher_damage(hit, target, final_damage)
        effective_knockback = _scaled_knockback(hit, charge_multiplier, juggle_scale)

        source_x: float = attacker.hitbox.centerx

        armor_absorbs_reaction = target.has_super_armor and not hit.super_armor_break
        applied_knockback = None if armor_absorbs_reaction else effective_knockback
        result = target.receive_damage(
            final_damage,
            source_x,
            applied_knockback,
            unblockable=hit.unblockable,
            height=hit.height,
            block_mask=hit.block_mask,
            hit_level=hit.hit_level,
        )

        # Guard, invincibility, death, or any future immunity is authoritative.
        if not result.applied:
            return result

        _apply_post_effects(
            attacker,
            target,
            hit,
            was_airborne,
            juggle_scale,
            final_damage,
            armor_absorbs_reaction,
            result,
        )
        return result
