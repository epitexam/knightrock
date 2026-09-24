"""
Core frame data structures for the combat system.

This module defines the data structures used to describe attacks in terms of
frame data — the fundamental unit of timing in fighting games and action
games. Every attack is broken down into phases, and each phase into three
sub-states: startup, active, and recovery, measured in frames at a fixed
reference frame rate.
"""

import math
from dataclasses import dataclass, field
from enum import Enum

from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import AnchorKind, EasingKind, ShapeKind, ShapePose, ease, interpolate_angle

FRAME_RATE: int = 60
"""Reference frame rate in frames per second.

All frame counts in PhaseDefinition are expressed at this rate.
The AttackStateMachine converts frame counts to real time using
1 / FRAME_RATE as the fixed timestep.
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

    Attributes
    ----------
    damage : int
        Hit points removed from the target on contact.
        Indicative scale (assuming 100 HP total):
        - light   :  5-10  (fast, spammable)
        - medium  : 10-18  (standard combo hit)
        - heavy   : 18-28  (slow, high-commitment)
        - finisher: 25-40  (long cooldown, knockback)
    knockback : KnockbackConfig
        Impulse applied to the target on hit. See KnockbackConfig.
    damage_type : DamageType
        Damage category (SLASH, BLUNT, PIERCE) used for resistance
        calculations and visual effects. Defaults to SLASH.
    stagger : float
        Duration in seconds the target is stunned after being hit.
        0 means no stagger. Ignored if the target has super armor,
        unless super_armor_break is True.
        - micro stagger : 0.05-0.10  (cosmetic only)
        - light stagger : 0.10-0.20  (interrupts actions)
        - heavy stagger : 0.25-0.50  (full stop, combo window)
    super_armor_break : bool
        If True, this hit cancels the target's super armor, forcing
        the stagger and knockback even on armored opponents.
    is_finisher : bool
        If True, instantly kills a target whose HP is below 20%.
        Use sparingly — best on slow, high-risk moves.
    juggle_gravity_mult : float
        Gravity multiplier applied to an airborne victim (Phase 5 #4):
        < 1.0 floats the juggle, > 1.0 slams it down. 1.0 = untouched.
    otg_allowed : bool
        If True, this hit may connect during the OTG protection window
        granted on landing from a juggle (Phase 5 #4). Ground hits
        otherwise bounce off a recently knocked-down victim.
    unblockable : bool
        If True, the hit bypasses guard and parry (chip/posture unchanged).
    priority : int
        Hit-vs-hit rank for simultaneous box overlaps (higher wins).
    clash : str
        Equal-priority outcome: ``"trade"`` (both connect) or
        ``"clash"`` (both attacks cancel with a clash event).
    height : str
        Guard height: ``"high"``, ``"mid"``, ``"low"`` or ``"overhead"``.
        Checked against ``Guard.HEIGHT_BLOCK`` with the target crouching.
    block_mask : str
        Posture allowed to block this hit: ``"any"``, ``"stand"`` or ``"crouch"``.
    tags : tuple[str, ...]
        Category tags used by hurt-zone invulnerability matching.
    hit_level : str
        Guard pressure level: ``"light"``, ``"med"`` or ``"heavy"``.
    """

    damage: float
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)
    damage_type: DamageType = DamageType.SLASH
    stagger: float = 0.0
    super_armor_break: bool = False
    is_finisher: bool = False
    juggle_gravity_mult: float = 1.0
    otg_allowed: bool = False
    unblockable: bool = False
    priority: int = 0
    clash: str = "trade"
    height: str = "mid"
    hit_level: str = "med"
    block_mask: str = "any"
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.damage < 0:
            raise ValueError("Hit damage cannot be negative")
        if self.stagger < 0:
            raise ValueError("Hit stagger cannot be negative")
        if self.juggle_gravity_mult <= 0:
            raise ValueError("Juggle gravity multiplier must be strictly positive")
        if self.priority < 0:
            raise ValueError("Hit priority cannot be negative")
        if self.clash not in ("trade", "clash"):
            raise ValueError("Hit clash must be 'trade' or 'clash'")
        if self.height not in ("high", "mid", "low", "overhead"):
            raise ValueError("Hit height must be 'high', 'mid', 'low' or 'overhead'")
        if self.hit_level not in ("light", "med", "heavy"):
            raise ValueError("Hit level must be 'light', 'med' or 'heavy'")
        if self.block_mask not in ("any", "stand", "crouch"):
            raise ValueError("Block mask must be 'any', 'stand' or 'crouch'")
        if not isinstance(self.tags, tuple) or any(
            not isinstance(tag, str) or not tag for tag in self.tags
        ):
            raise ValueError("Hit tags must be a tuple of non-empty strings")


@dataclass(frozen=True)
class HitboxKeyframe:
    """One animated hitbox sample on the startup-to-active curve.

    ``frame`` is counted from the start of the phase's startup
    (``0`` = phase start, ``startup_frames + active_frames`` = end of
    the active window). ``size``/``offset`` follow the same convention
    as the phase's primary box. ``HitboxManager`` linearly interpolates
    between the surrounding keyframes at the current ``frame_counter``.

    Attributes
    ----------
    frame : int
        Frame index of this sample, within
        ``0..startup_frames + active_frames``.
    size : tuple[float, float]
        Box dimensions in pixels, both strictly positive.
    offset : tuple[float, float]
        Box center offset ``(x, y)`` relative to the owner's hitbox
        center (x auto-mirrored when facing left).
    """

    frame: int
    size: tuple[float, float]
    offset: tuple[float, float]
    angle: float = 0.0

    def __post_init__(self) -> None:
        if self.frame < 0:
            raise ValueError("Hitbox keyframe index cannot be negative")
        if not (self.size[0] > 0 and self.size[1] > 0):
            raise ValueError("Hitbox dimensions must be strictly positive")
        if not math.isfinite(self.angle):
            raise ValueError("Hitbox keyframe angle must be finite")


BoxGeometry = tuple[tuple[float, float], tuple[float, float]]
"""``(size, offset)`` pair interpolated from keyframes for one box."""


def _check_keyframe_span(keyframes: tuple[HitboxKeyframe, ...], span: int, label: str) -> None:
    """Validate increasing frames within the startup-to-active ``span``."""
    previous = -1
    for keyframe in keyframes:
        if keyframe.frame <= previous:
            raise ValueError(f"{label}s must use strictly increasing frames")
        if keyframe.frame > span:
            raise ValueError(f"{label} exceeds the startup-to-active frame span")
        previous = keyframe.frame


def interpolate_keyframes(
    keyframes: tuple[HitboxKeyframe, ...],
    static: BoxGeometry,
    frame: int,
) -> BoxGeometry:
    """Linearly interpolate ``(size, offset)`` at a phase ``frame``.

    ``frame`` counts from the start of startup (``0`` = phase start),
    matching ``AttackStateMachine.frame_counter`` within each sub-state.
    With no keyframes the static box is returned. Otherwise the
    surrounding keyframes are interpolated linearly; outside their range
    the nearest endpoint is held.
    """
    if not keyframes:
        return static
    if frame <= keyframes[0].frame:
        first = keyframes[0]
        return (first.size, first.offset)
    # Pairwise walk over offset slices: the second slice is one shorter
    # by construction, so strict=True would always raise (B905 exempt).
    for before, after in zip(keyframes, keyframes[1:]):  # noqa: B905
        if frame <= after.frame:
            span = after.frame - before.frame
            blend = (frame - before.frame) / span
            size = (
                before.size[0] + (after.size[0] - before.size[0]) * blend,
                before.size[1] + (after.size[1] - before.size[1]) * blend,
            )
            offset = (
                before.offset[0] + (after.offset[0] - before.offset[0]) * blend,
                before.offset[1] + (after.offset[1] - before.offset[1]) * blend,
            )
            return (size, offset)
    last = keyframes[-1]
    return (last.size, last.offset)


def interpolate_shape_keyframes(
    keyframes: tuple[HitboxKeyframe, ...],
    static: BoxGeometry,
    frame: int,
    easing: EasingKind = EasingKind.LINEAR,
) -> tuple[BoxGeometry, float]:
    """Interpolate size, offset and angle at a phase frame."""
    if not keyframes:
        return static, 0.0
    if frame <= keyframes[0].frame:
        first = keyframes[0]
        return (first.size, first.offset), first.angle
    for before, after in zip(keyframes, keyframes[1:]):  # noqa: B905
        if frame <= after.frame:
            progress = (frame - before.frame) / (after.frame - before.frame)
            easing_progress = ease(easing, progress)
            size = (
                before.size[0] + (after.size[0] - before.size[0]) * easing_progress,
                before.size[1] + (after.size[1] - before.size[1]) * easing_progress,
            )
            offset = (
                before.offset[0] + (after.offset[0] - before.offset[0]) * easing_progress,
                before.offset[1] + (after.offset[1] - before.offset[1]) * easing_progress,
            )
            return (size, offset), interpolate_angle(before.angle, after.angle, progress, easing)
    last = keyframes[-1]
    return (last.size, last.offset), last.angle


@dataclass(frozen=True)
class HitboxSpec:
    """Size and offset of a single offensive rectangle within a phase.

    A phase always carries its legacy primary box (``hitbox_size`` /
    ``hitbox_offset``); each entry of ``PhaseDefinition.extra_hitboxes``
    adds one disjoint box following the same convention: ``size`` is the
    rectangle dimensions in pixels, ``offset`` its center relative to the
    owner's hitbox center (mirrored on the x-axis when facing left).
    ``keyframes`` optionally animates the box over the phase's
    startup-to-active frames (same samples as the primary curve);
    empty = static box. Span validation lives in
    ``PhaseDefinition.__post_init__`` (the spec alone cannot know it).

    Attributes
    ----------
    size : tuple[float, float]
        Width and height in pixels, both strictly positive.
    offset : tuple[float, float]
        Center offset ``(x, y)`` relative to the owner's hitbox center.
    keyframes : tuple[HitboxKeyframe, ...]
        Optional animated samples for this box (empty = static).
    """

    size: tuple[float, float]
    offset: tuple[float, float]
    keyframes: tuple[HitboxKeyframe, ...] = ()
    shape: ShapeKind = ShapeKind.AABB
    angle: float = 0.0
    easing: EasingKind = EasingKind.LINEAR
    anchor: AnchorKind = AnchorKind.CENTER
    anchor_offset: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if not (self.size[0] > 0 and self.size[1] > 0):
            raise ValueError("Hitbox dimensions must be strictly positive")
        if not math.isfinite(self.angle):
            raise ValueError("Hitbox angle must be finite")
        if not all(math.isfinite(value) for value in self.anchor_offset):
            raise ValueError("Hitbox anchor offset must be finite")
        ShapePose(self.shape, self.size, self.offset, self.angle)
        previous = -1
        for keyframe in self.keyframes:
            if keyframe.frame <= previous:
                raise ValueError("Hitbox keyframes must use strictly increasing frames")
            previous = keyframe.frame


@dataclass(frozen=True)
class PhaseDefinition:
    """Immutable frame data and hitbox definition for a single hit event.

    A phase represents one hitbox event, broken down into three sub-states:
    startup (windup), active (hitbox live), and recovery (follow-through).
    Multi-hit attacks consist of multiple phases executed in sequence.

    Attributes
    ----------
    startup_frames : int
        Number of windup frames before the hitbox activates.
        - very fast : 1-3   (jab, flicker)
        - normal    : 4-7   (standard swing)
        - slow      : 8-12  (heavy, charged)
    active_frames : int
        Number of frames the hitbox remains active and can connect.
        - precise  : 1-2  (jab, poke)
        - normal   : 3-5  (standard swing)
        - generous : 5-8  (wide slash, lingering hitbox)
    recovery_frames : int
        Number of cool-down frames after the hitbox deactivates.
        Longer recovery means more commitment and punishes whiffs.
        - fast   : 2-4   (light normals, cancels)
        - normal : 5-8   (standard attacks)
        - heavy  : 9-15  (commitment moves, smashes)
    hitbox_size : tuple[float, float]
        Width and height of the hitbox in pixels (w, h) during the active
        phase. Sprites are approximately 40x48 px.
        - light jab       : (30-45, 18-25)
        - standard hit    : (45-60, 25-35)
        - wide swing      : (60-80, 30-45)
        - launcher / slam : (30-45, 50-70)
    hitbox_offset : tuple[float, float]
        Offset from the attacker's hitbox center (x, y) during the active
        phase. Positive x shifts forward (auto-mirrored when facing left).
        Positive y shifts downward; negative y shifts upward.
    extra_hitboxes : tuple[HitboxSpec, ...]
        Additional disjoint boxes active alongside the primary box
        (twin blades, boss weak points...). Empty by default: legacy
        attacks keep a single rectangle. Each entry follows the same
        size/offset convention as the primary box.
    hitbox_keyframes : tuple[HitboxKeyframe, ...]
        Optional animated curve for the primary box: samples of
        ``(frame, size, offset)`` interpolated linearly over the phase's
        startup-to-active frames. Empty by default (static legacy box).
        Entries must be sorted by strictly increasing ``frame`` within
        ``0..startup_frames + active_frames``.
    hit : HitProperties
        Properties applied on successful hit during the active phase.
    reset_targets : bool
        If True, the set of already-hit targets is cleared when this
        phase begins, allowing the same target to be hit by a later phase.
    cancel_into : tuple[str, ...]
        Tuple of attack names this phase can cancel into during recovery
        frames. An empty tuple means the phase cannot be cancelled.

    Properties
    ----------
    total_frames : int
        Total number of frames in this phase (startup + active + recovery).
    """

    startup_frames: int
    active_frames: int
    recovery_frames: int
    hitbox_size: tuple[float, float]
    hitbox_offset: tuple[float, float]
    hit: HitProperties
    hitbox_shape: ShapeKind = ShapeKind.AABB
    hitbox_angle: float = 0.0
    hitbox_easing: EasingKind = EasingKind.LINEAR
    hitbox_anchor: AnchorKind = AnchorKind.CENTER
    hitbox_anchor_offset: tuple[float, float] = (0.0, 0.0)
    extra_hitboxes: tuple[HitboxSpec, ...] = ()
    hitbox_keyframes: tuple[HitboxKeyframe, ...] = ()
    reset_targets: bool = True
    cancel_into: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.startup_frames < 0 or self.recovery_frames < 0:
            raise ValueError("Startup and recovery frames cannot be negative")
        if self.active_frames <= 0:
            raise ValueError("An attack phase requires at least one active frame")
        if any(size <= 0 for size in self.hitbox_size):
            raise ValueError("Hitbox dimensions must be strictly positive")
        if not math.isfinite(self.hitbox_angle):
            raise ValueError("Hitbox angle must be finite")
        if not all(math.isfinite(value) for value in self.hitbox_anchor_offset):
            raise ValueError("Hitbox anchor offset must be finite")
        ShapePose(self.hitbox_shape, self.hitbox_size, self.hitbox_offset, self.hitbox_angle)
        span = self.startup_frames + self.active_frames
        _check_keyframe_span(self.hitbox_keyframes, span, "Hitbox keyframe")
        for index, spec in enumerate(self.extra_hitboxes):
            _check_keyframe_span(spec.keyframes, span, f"Extra hitbox #{index} keyframe")

    def hitbox_at(self, frame: int) -> BoxGeometry:
        """Interpolate the primary ``(size, offset)`` at a phase ``frame``.

        ``frame`` counts from the start of startup (``0`` = phase start),
        matching ``AttackStateMachine.frame_counter`` within each
        sub-state. Delegates to :func:`interpolate_keyframes` over the
        primary curve (static legacy box when empty).
        """
        return interpolate_keyframes(
            self.hitbox_keyframes, (self.hitbox_size, self.hitbox_offset), frame
        )

    @property
    def hitbox_spec(self) -> HitboxSpec:
        """Return the primary hitbox using the extended shape model."""
        return HitboxSpec(
            size=self.hitbox_size,
            offset=self.hitbox_offset,
            keyframes=self.hitbox_keyframes,
            shape=self.hitbox_shape,
            angle=self.hitbox_angle,
            easing=self.hitbox_easing,
            anchor=self.hitbox_anchor,
            anchor_offset=self.hitbox_anchor_offset,
        )

    def hitbox_shape_at(self, frame: int) -> tuple[BoxGeometry, float]:
        """Interpolate the primary geometry and angle at a phase frame."""
        return interpolate_shape_keyframes(
            self.hitbox_keyframes,
            (self.hitbox_size, self.hitbox_offset),
            frame,
            self.hitbox_easing,
        )

    def extra_box_at(self, index: int, frame: int) -> BoxGeometry:
        """Interpolate extra box ``index`` at a phase ``frame``.

        Each box follows its own curve (static ``(size, offset)`` when it
        carries no keyframes); the primary curve is never reused here.
        """
        spec = self.extra_hitboxes[index]
        return interpolate_keyframes(spec.keyframes, (spec.size, spec.offset), frame)

    def extra_shape_at(self, index: int, frame: int) -> tuple[BoxGeometry, float]:
        """Interpolate extra box geometry and angle at a phase frame."""
        spec = self.extra_hitboxes[index]
        return interpolate_shape_keyframes(
            spec.keyframes,
            (spec.size, spec.offset),
            frame,
            spec.easing,
        )

    @property
    def total_frames(self) -> int:
        """Total number of frames in this phase (startup + active + recovery)."""
        return self.startup_frames + self.active_frames + self.recovery_frames


@dataclass(frozen=True)
class AttackDefinition:
    """Immutable definition of an attack move composed of one or more phases.

    An attack is a sequence of phases executed in order. Each phase has its
    own frame data, hitbox, and hit properties, enabling multi-hit combos
    and complex attack patterns.

    Attributes
    ----------
    phases : tuple[PhaseDefinition, ...]
        Ordered tuple of hitbox events. The sequence advances automatically
        when the current phase's recovery frames expire.
    cooldown : float
        Minimum time in seconds before this attack can be started again,
        measured from the moment it was triggered (not from when it ended).
    lock_direction : bool
        If True, the attacker's facing direction is frozen for the entire
        sequence. Recommended for most ground moves.
    combo_reset : bool
        If True, starting this attack resets the combo counter to zero.
        Use on finishers or special moves.
    chargeable : bool
        If True, the attack button can be held to charge before releasing.
        Damage scales linearly from 1x to 2x over max_charge_time.
    max_charge_time : float
        Maximum charge duration in seconds. Ignored when chargeable
        is False. Typical range: 0.5-2.0.
    charge_move_multiplier : float
        Multiplier applied to the entity's movement speed while charging
        this attack. Ignored when chargeable is False.
        1.0 = no slowdown, 0.0 = fully immobilized while charging.
    uninterruptible : bool
        If True, this attack sequence cannot be cancelled by taking a hit.
        The entity still receives damage normally, but the attack keeps
        running: no hurt state is entered and the attack is not ended.
    lunge_speed_multiplier : float
        Multiplier applied to the entity's speed to compute the forward
        lunge velocity applied when this attack starts on the ground.
        0.0 disables the lunge entirely.

    Properties
    ----------
    total_frames : int
        Total frame count across all phases.
    """

    phases: tuple[PhaseDefinition, ...]
    cooldown: float
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0
    charge_move_multiplier: float = 1.0
    uninterruptible: bool = False
    lunge_speed_multiplier: float = 0.35
    attack_move_multiplier: float = 0.3

    def __post_init__(self) -> None:
        if not self.phases:
            raise ValueError("An attack requires at least one phase")
        if self.cooldown < 0:
            raise ValueError("Attack cooldown cannot be negative")
        if self.max_charge_time <= 0:
            raise ValueError("Maximum charge time must be strictly positive")
        if self.charge_move_multiplier < 0 or self.attack_move_multiplier < 0:
            raise ValueError("Movement multipliers cannot be negative")
        if self.lunge_speed_multiplier < 0:
            raise ValueError("Lunge speed multiplier cannot be negative")

    @property
    def total_frames(self) -> int:
        """Total frame count across all phases."""
        return sum(p.total_frames for p in self.phases)
