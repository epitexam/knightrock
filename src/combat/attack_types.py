"""
Data structures for defining attacks.

Classes
-------
KnockbackConfig  : push direction and strength applied on hit.
AttackPhase      : a single hitbox event (size, damage, duration, effects).
AttackSequence   : a full move — one or more phases, cooldown, and flags.
"""
from dataclasses import dataclass, field
from typing import Literal

from src.combat.damage_types import DamageType


@dataclass
class KnockbackConfig:
    """Push velocity applied to the target on hit.

    Parameters
    ----------
    power : tuple[float, float]
        Horizontal (x) and vertical (y) impulse in px/s applied on hit.

        x — push strength away from the attacker.
            Typical range: 100–500. Above 600 sends the target offscreen.
            0 produces a purely vertical launch.
        y — vertical push; **negative values push upward**.
            Typical range: -50 (grounded) to -1200 (full uppercut launch).
            Positive y slams the target downward (useful for air-to-ground moves).

    mode : {"from_attacker", "fixed"}
        ``from_attacker`` — x direction is derived from the attacker's position
        relative to the target (standard). Always pushes the target away.
        ``fixed`` — power is applied as-is, ignoring positions. Use for traps,
        environmental hazards, or moves with a fixed launch angle.
    """
    power: tuple[float, float] = (250.0, -150.0)
    mode: Literal["from_attacker", "fixed"] = "from_attacker"


@dataclass
class AttackPhase:
    """A single hitbox event within an attack sequence.

    Parameters
    ----------
    size : tuple[float, float]
        Width and height of the hitbox in pixels (w, h).
        The player and enemy sprites are approximately 40×48 px.
        Typical ranges:
            - light jab       : (30–45, 18–25)
            - standard hit    : (45–60, 25–35)
            - wide swing      : (60–80, 30–45)
            - launcher / slam : (30–45, 50–70)

    offset : tuple[float, float]
        Offset from the attacker's hitbox centre (x, y).
        Positive x shifts forward (auto-mirrored when facing left).
        Positive y shifts downward; negative y shifts upward.
        Keep x in 15–40 to avoid the hitbox overlapping the attacker's body.
        y of 0 sits at chest height; -20 reaches head height; +15 reaches feet.

    damage : int
        Hit points removed from the target on contact.
        Indicative scale (assuming 100 HP total):
            - light   :  5–10  (fast, spammable)
            - medium  : 10–18  (standard combo hit)
            - heavy   : 18–28  (slow, high-commitment)
            - finisher: 25–40  (long cooldown, knockback)

    duration : float
        Phase lifetime in seconds before advancing to the next phase or ending.
        Short phases feel snappy; long phases feel heavy.
            - very fast : 0.05–0.10  (jab, flicker)
            - normal    : 0.10–0.20  (standard swing)
            - slow      : 0.20–0.35  (heavy, charged)
        Avoid going below 0.05 — detection may miss at high frame rates.

    reset_targets : bool
        If ``True``, the set of already-hit targets is cleared when this phase
        starts, allowing the same target to be hit again by a later phase.
        Set to ``False`` on follow-through phases that should not re-hit.

    knockback : KnockbackConfig
        Impulse applied to the target on hit. See ``KnockbackConfig``.

    damage_type : DamageType
        Damage category (SLASH, BLUNT, PIERCE, …) used for resistances and
        visual effects (sparks, blood, impact sound). Defaults to SLASH.

    stagger : float
        Duration in seconds during which the target cannot act after being hit.
        0 means no stagger (target can act immediately after taking damage).
            - micro stagger : 0.05–0.10  (cosmetic only)
            - light stagger : 0.10–0.20  (interrupts actions)
            - heavy stagger : 0.25–0.50  (full stop, combo window)
        Stagger is ignored if the target has super armor, unless
        ``super_armor_break`` is ``True``.

    super_armor_break : bool
        If ``True``, this phase cancels the target's super armor, forcing the
        stagger even on armored opponents. Reserve for telegraphed heavy attacks.

    is_finisher : bool
        If ``True``, instantly kills a target whose HP is below 20 %.
        Use sparingly — best on slow, high-risk moves with long cooldowns.

    Examples
    --------
    >>> AttackPhase(
    ...     size=(50, 16), offset=(30, 16), damage=8, duration=0.15,
    ...     knockback=KnockbackConfig(power=(250, -50)),
    ...     damage_type=DamageType.BLUNT, stagger=0.1,
    ... )
    """
    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    reset_targets: bool = True
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)
    damage_type: DamageType = DamageType.SLASH
    stagger: float = 0.0
    super_armor_break: bool = False
    is_finisher: bool = False


@dataclass
class AttackSequence:
    """A complete move composed of one or more phases executed in order.

    Parameters
    ----------
    phases : list[AttackPhase]
        Ordered list of hitbox events. The sequence advances to the next phase
        when the current phase's ``duration`` expires.
        One phase = simple attack. Two or more phases = combo or multi-hit.
        Keep total duration (sum of all phase durations) under 0.6 s for
        light moves and under 1.5 s for heavy ones to preserve responsiveness.

    cooldown : float
        Minimum time in seconds before this attack can be started again,
        measured from the moment it was triggered (not from when it ended).
            - spam-able  : 0.30–0.55  (light normals)
            - standard   : 0.55–0.90  (ground combos)
            - heavy      : 0.90–1.50  (smash, uppercut)
            - special    : 1.50–3.00  (rare, high-reward)

    lock_direction : bool
        If ``True``, the attacker's facing direction is frozen for the entire
        sequence. Prevents the hitbox from flipping mid-attack on a direction
        change. Recommended for most ground moves; disable for air moves where
        the player may need to steer mid-air.

    combo_reset : bool
        If ``True``, starting this sequence resets the internal combo counter
        to zero. Use on finishers or special moves to break combo chains and
        prevent the player from looping them indefinitely.

    chargeable : bool
        If ``True``, the attack button can be held to charge the move before
        releasing. Damage scales linearly from 1× at 0 s to 2× at
        ``max_charge_time``. Charging locks movement during the windup.

    max_charge_time : float
        Maximum charge duration in seconds. Damage caps at 2× after this point;
        holding longer has no additional effect. Ignored when ``chargeable``
        is ``False``. Typical range: 0.5–2.0.

    Examples
    --------
    >>> AttackSequence(
    ...     phases=[
    ...         AttackPhase(size=(55, 35), offset=(35, -10), damage=18, duration=0.25,
    ...                     knockback=KnockbackConfig(power=(400, -250)),
    ...                     damage_type=DamageType.BLUNT, stagger=0.4,
    ...                     super_armor_break=True)
    ...     ],
    ...     cooldown=1.2, lock_direction=True, combo_reset=True,
    ...     chargeable=True, max_charge_time=1.0,
    ... )
    """
    phases: list[AttackPhase]
    cooldown: float
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0