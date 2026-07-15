"""
Core frame data structures for the combat system.

This module defines the data structures used to describe attacks in terms of
**frame data** — the fundamental unit of timing in fighting games and action
games.  Every attack is broken down into *phases*, and each phase into three
sub-states: **startup**, **active**, and **recovery**, measured in frames at
a fixed reference frame rate.

Constants
---------
FRAME_RATE : int
    Reference frame rate (FPS) used to convert frame counts to seconds.

Classes
-------
PhaseState
    Enum representing the sub-state of an attack phase.
HitProperties
    Properties applied when an attack connects with a target.
PhaseDefinition
    Frame data and hitbox definition for a single hit event.
AttackDefinition
    Complete definition of an attack move composed of one or more phases.
"""

from dataclasses import dataclass, field
from enum import Enum

from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig

FRAME_RATE: int = 60
"""Reference frame rate in frames per second.

All frame counts in ``PhaseDefinition`` are expressed at this rate.
The ``AttackStateMachine`` converts frame counts to real time using
``1 / FRAME_RATE`` as the fixed timestep.
"""


class PhaseState(Enum):
    """Sub-state of an attack phase within the frame data system.

    Attributes
    ----------
    IDLE : str
        No attack is in progress.
    STARTUP : str
        Windup frames before the hitbox becomes active.
    ACTIVE : str
        Frames during which the hitbox can detect and hit targets.
    RECOVERY : str
        Cool-down frames after the hitbox deactivates, before returning
        to IDLE or advancing to the next phase.
    """
    IDLE = "idle"
    STARTUP = "startup"
    ACTIVE = "active"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class HitProperties:
    """Immutable properties applied when an attack successfully connects.

    Parameters
    ----------
    damage : int
        Hit points removed from the target on contact.
        Indicative scale (assuming 100 HP total):
            - light   :  5–10  (fast, spammable)
            - medium  : 10–18  (standard combo hit)
            - heavy   : 18–28  (slow, high-commitment)
            - finisher: 25–40  (long cooldown, knockback)

    knockback : KnockbackConfig
        Impulse applied to the target on hit.  See ``KnockbackConfig``.

    damage_type : DamageType
        Damage category (SLASH, BLUNT, PIERCE) used for resistance
        calculations and visual effects.  Defaults to SLASH.

    stagger : float
        Duration in seconds the target is stunned after being hit.
        0 means no stagger.  Ignored if the target has super armor,
        unless ``super_armor_break`` is True.
            - micro stagger : 0.05–0.10  (cosmetic only)
            - light stagger : 0.10–0.20  (interrupts actions)
            - heavy stagger : 0.25–0.50  (full stop, combo window)

    super_armor_break : bool
        If True, this hit cancels the target's super armor, forcing
        the stagger and knockback even on armored opponents.

    is_finisher : bool
        If True, instantly kills a target whose HP is below 20 %.
        Use sparingly — best on slow, high-risk moves.
    """
    damage: int
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)
    damage_type: DamageType = DamageType.SLASH
    stagger: float = 0.0
    super_armor_break: bool = False
    is_finisher: bool = False


@dataclass(frozen=True)
class PhaseDefinition:
    """Immutable frame data and hitbox definition for a single hit event.

    A phase represents one hitbox event, broken down into three sub-states:
    **startup** (windup), **active** (hitbox live), and **recovery**
    (follow-through).  Multi-hit attacks consist of multiple phases executed
    in sequence.

    Parameters
    ----------
    startup_frames : int
        Number of windup frames before the hitbox activates.
            - very fast : 1–3   (jab, flicker)
            - normal    : 4–7   (standard swing)
            - slow      : 8–12  (heavy, charged)

    active_frames : int
        Number of frames the hitbox remains active and can connect.
            - precise  : 1–2  (jab, poke)
            - normal   : 3–5  (standard swing)
            - generous : 5–8  (wide slash, lingering hitbox)

    recovery_frames : int
        Number of cool-down frames after the hitbox deactivates.
        Longer recovery means more commitment and punishes whiffs.
            - fast   : 2–4   (light normals, cancels)
            - normal : 5–8   (standard attacks)
            - heavy  : 9–15  (commitment moves, smashes)

    hitbox_size : tuple[float, float]
        Width and height of the hitbox in pixels (w, h) during the active
        phase.  Sprites are approximately 40×48 px.
            - light jab       : (30–45, 18–25)
            - standard hit    : (45–60, 25–35)
            - wide swing      : (60–80, 30–45)
            - launcher / slam : (30–45, 50–70)

    hitbox_offset : tuple[float, float]
        Offset from the attacker's hitbox centre (x, y) during the active
        phase.  Positive x shifts forward (auto-mirrored when facing left).
        Positive y shifts downward; negative y shifts upward.

    hit : HitProperties
        Properties applied on successful hit during the active phase.

    reset_targets : bool
        If True, the set of already-hit targets is cleared when this
        phase begins, allowing the same target to be hit by a later phase.

    cancel_into : tuple[str, ...]
        Tuple of attack names this phase can cancel into during recovery
        frames.  An empty tuple means the phase cannot be cancelled.

    Examples
    --------
    >>> PhaseDefinition(
    ...     startup_frames=3, active_frames=4, recovery_frames=3,
    ...     hitbox_size=(40, 20), hitbox_offset=(24, -4),
    ...     hit=HitProperties(damage=8,
    ...                       knockback=KnockbackConfig(power=(150, -50)),
    ...                       stagger=0.1),
    ... )
    """
    startup_frames: int
    active_frames: int
    recovery_frames: int
    hitbox_size: tuple[float, float]
    hitbox_offset: tuple[float, float]
    hit: HitProperties
    reset_targets: bool = True
    cancel_into: tuple[str, ...] = ()

    @property
    def total_frames(self) -> int:
        """Total number of frames in this phase (startup + active + recovery)."""
        return self.startup_frames + self.active_frames + self.recovery_frames


@dataclass(frozen=True)
class AttackDefinition:
    """Immutable definition of an attack move composed of one or more phases.

    An attack is a sequence of phases executed in order.  Each phase has its
    own frame data, hitbox, and hit properties, enabling multi-hit combos
    and complex attack patterns.

    Parameters
    ----------
    phases : tuple[PhaseDefinition, ...]
        Ordered tuple of hitbox events.  The sequence advances automatically
        when the current phase's recovery frames expire.

    cooldown : float
        Minimum time in seconds before this attack can be started again,
        measured from the moment it was triggered (not from when it ended).

    lock_direction : bool
        If True, the attacker's facing direction is frozen for the entire
        sequence.  Recommended for most ground moves.

    combo_reset : bool
        If True, starting this attack resets the combo counter to zero.
        Use on finishers or special moves.

    chargeable : bool
        If True, the attack button can be held to charge before releasing.
        Damage scales linearly from 1× to 2× over ``max_charge_time``.

    max_charge_time : float
        Maximum charge duration in seconds.  Ignored when ``chargeable``
        is False.  Typical range: 0.5–2.0.

    Examples
    --------
    >>> AttackDefinition(
    ...     phases=(
    ...         PhaseDefinition(
    ...             startup_frames=7, active_frames=4, recovery_frames=4,
    ...             hitbox_size=(55, 35), hitbox_offset=(32, -10),
    ...             hit=HitProperties(damage=18, stagger=0.3,
    ...                               super_armor_break=True,
    ...                               knockback=KnockbackConfig(power=(300, -200))),
    ...         ),
    ...     ),
    ...     cooldown=0.80, lock_direction=True, combo_reset=True,
    ...     chargeable=True, max_charge_time=1.0,
    ... )
    """
    phases: tuple[PhaseDefinition, ...]
    cooldown: float
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0

    @property
    def total_frames(self) -> int:
        """Total frame count across all phases."""
        return sum(p.total_frames for p in self.phases)