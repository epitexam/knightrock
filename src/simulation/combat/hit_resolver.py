"""
Hit resolution: what one landed melee or projectile hit does.

``HitResolver`` is stateless; ``ContactSystem`` calls it once per contact. The
whole outcome of a hit, in the order it happens, and where each part lives:

1. **Whether it lands** -- an invincible target is not hit (a hit that passes
   through a dodge at the last moment is a dark step); a doomed one is reached
   by a death blow only; a guard held at the hit's height stops it
   (``guards_against``, the player's automatic one and an enemy's high or low
   one). Here.
2. **Damage** -- base x charge x zone x damage type x juggle, x the bonus on a
   helpless target; an ``execute`` hit kills a helpless target outright, and a
   fighter on a killing spree (``Finish.KILL``) kills with every blow. Here.
3. **Doom** -- a blow that would kill, thrown by a fighter who finishes by
   death blow (``Finish.DOOM``), leaves a doomable target doomed instead: all
   but dead, waiting for the blow. Here.
4. **Defence** -- the target's own ``receive_damage``: health, flash,
   knockback, i-frames and the heavy launch (``ReactionComponent``). Hazards
   and body contact call it directly, without this resolver.
5. **After an applied hit** -- the stun gauge, armour break, juggle gravity,
   the attacker's combo and what the attacker gets for the hit
   (``on_hit_confirmed``), then hurt and stagger unless the target died, was
   stunned, absorbed the hit or was launched. Here, in
   :func:`_apply_post_effects`.
6. **On the world** -- hit-stop and camera impact, in ``ContactSystem``.

The pins for all of it are in ``tests/golden/hit_outcomes.json``.
"""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

from src.core.settings import Combat as CombatSettings
from src.simulation.combat.combatant_protocol import AttackerPort, Combatant, DamageResult, Finish
from src.simulation.combat.frame_data import HitProperties
from src.simulation.combat.knockback import KnockbackConfig


def _is_grounded(target: Combatant) -> bool:
    """Grounded victim: no juggle, OTG rules may apply."""
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


def _flinched(knockback: KnockbackConfig, hit: HitProperties, grounded: bool) -> KnockbackConfig:
    """A flinch hit does not push a grounded target sideways; anything else is unchanged."""
    if not (hit.flinch and grounded) or knockback.power[0] == 0.0:
        return knockback
    return KnockbackConfig(power=(0.0, knockback.power[1]), mode=knockback.mode)


def _apply_post_effects(
    attacker: AttackerPort,
    target: Combatant,
    hit: HitProperties,
    was_airborne: bool,
    juggle_scale: float,
    final_damage: float,
    absorbs_reaction: bool,
    result: DamageResult,
) -> None:
    """Post-hit reactions, in preserved order.

    Armor break, juggle, combo recording, then interrupt/stagger unless the
    target died, was stunned by this hit, absorbed the reaction, or knockback
    launched it.
    """
    if target.has_super_armor and hit.super_armor_break:
        target.break_super_armor()

    if was_airborne and hit.juggle_gravity_mult != 1.0:
        target.set_juggle(hit.juggle_gravity_mult, CombatSettings.JUGGLE_GRAVITY_TIME)

    combo_advanced = attacker.combat.record_hit_landed(was_airborne)
    attacker.on_hit_confirmed(target, combo_advanced, result)

    if result.killed or result.stunned or absorbs_reaction or result.heavy_knockback:
        return
    target.combat.on_hit(interrupt=True)
    if hit.stagger > 0:
        effective_stagger = (
            hit.stagger * juggle_scale + final_damage * CombatSettings.HITSTUN_DAMAGE_FACTOR
        )
        target.stagger(effective_stagger)


class HitRefusal(Enum):
    """Why the defence layer refuses a hit before damage is considered.

    A classification, not an effect: the caller still decides what a refusal
    means. In particular an invincible target must get its ``on_hit_evaded``
    side effect from the caller, at the same point in the order as before.
    """

    INVINCIBLE = "invincible"
    DOOMED = "doomed"
    NO_DAMAGE = "no_damage"
    OTG = "otg"


def hit_refusal(
    target: Combatant, hit: HitProperties, final_damage: float, grounded: bool
) -> HitRefusal | None:
    """Classify a defensive refusal in the same order the guards always ran."""
    if target.is_invincible:
        return HitRefusal.INVINCIBLE
    if target.is_doomed and not hit.execute:
        return HitRefusal.DOOMED
    if final_damage <= 0:
        return HitRefusal.NO_DAMAGE
    if _otg_blocked(grounded, float(target.otg_timer or 0.0), hit):
        return HitRefusal.OTG
    return None


def _misses(
    target: Combatant, hit: HitProperties, final_damage: float, grounded: bool
) -> DamageResult | None:
    """The outcome of a hit that does not land at all, or ``None`` if it does.

    A dodge, a hurt or a launch cannot be hit, and a dodge may make it a dark
    step; a doomed target is reached by a death blow only.
    """
    refusal = hit_refusal(target, hit, final_damage, grounded)
    if refusal is None:
        return None
    if refusal is HitRefusal.INVINCIBLE:
        return DamageResult(evaded=target.on_hit_evaded())
    return DamageResult()


def _doom(attacker: AttackerPort, target: Combatant, was_airborne: bool) -> DamageResult:
    """Leave ``target`` doomed in place of the blow that would have killed it."""
    taken = max(0.0, target.health)
    target.doom()
    result = DamageResult(applied=True, doomed=True, actual_damage=taken - target.health)
    combo_advanced = attacker.combat.record_hit_landed(was_airborne)
    attacker.on_hit_confirmed(target, combo_advanced, result)
    return result


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
        """Decide whether the hit lands, then apply damage, knockback and stun.

        ``charge_multiplier`` scales the damage, the knockback and the stun: a
        charged slash, or a slash thrown on an empty battery. ``zone_mult`` is
        the damage multiplier of the hurtbox zone hit; it scales damage only.

        A helpless target -- stunned, on the ground -- takes the blows without
        being pushed or interrupted, until it recovers or an ``execute`` hit
        kills it.
        """
        type_mult = target.get_damage_modifier(hit.damage_type)
        grounded_before = _is_grounded(target)
        was_airborne = not grounded_before
        juggle_scale = 1.0
        if was_airborne:
            juggle_scale = _juggle_scale(attacker.combat.air_combo_count or 0)
        final_damage = hit.damage * charge_multiplier * zone_mult * type_mult * juggle_scale

        helpless = target.is_helpless
        if helpless:
            final_damage *= CombatSettings.DIZZY_DAMAGE_MULT

        missed = _misses(target, hit, final_damage, grounded_before)
        if missed is not None:
            return missed

        source_x: float = attacker.hitbox.centerx
        if not helpless and target.guards_against(hit.height, hit.unblockable, source_x):
            return DamageResult(guarded=True)

        final_damage = _finisher_damage(hit, target, final_damage)
        executes = hit.execute and helpless
        finish = attacker.finish
        if executes or finish is Finish.KILL:
            final_damage = max(final_damage, target.health)
        elif finish is Finish.DOOM and target.doomable and final_damage >= target.health:
            return _doom(attacker, target, was_airborne)
        effective_knockback = _flinched(
            _scaled_knockback(hit, charge_multiplier, juggle_scale), hit, grounded_before
        )

        absorbs_reaction = (helpless and not executes) or (
            target.has_super_armor and not hit.super_armor_break
        )
        applied_knockback = None if absorbs_reaction else effective_knockback
        result = target.receive_damage(final_damage, source_x, applied_knockback)

        # Invincibility frames, death, or any future immunity is authoritative.
        if not result.applied:
            return result

        result = replace(
            result,
            stunned=not result.killed and target.add_stun(hit.stun * charge_multiplier),
            executed=executes and result.killed,
        )
        _apply_post_effects(
            attacker,
            target,
            hit,
            was_airborne,
            juggle_scale,
            final_damage,
            absorbs_reaction,
            result,
        )
        return result
