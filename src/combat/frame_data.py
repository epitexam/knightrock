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
from enum import Enum, StrEnum
from functools import cached_property
from typing import NewType

from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import AnchorKind, EasingKind, ShapeKind, ShapePose, ease, interpolate_angle

FRAME_RATE: int = 60
"""Reference frame rate in frames per second.

All frame counts in PhaseDefinition are expressed at this rate.
The AttackStateMachine converts frame counts to real time using
1 / FRAME_RATE as the fixed timestep.
"""

MoveId = NewType("MoveId", str)
"""The name of one attack, as the key it is stored under everywhere.

A ``NewType``, not an ``Enum``: attacks come from ``data/gameplay/*.json`` and
are meant to be authorable there, so the set of valid names cannot be closed at
import time or every new move would be a code change. What this buys is the
typing, so a name flowing from the input layer into the attack tables cannot be
passed off as an arbitrary string by accident.

It costs nothing at runtime and enforces nothing. A typo is still a ``str``, and
the places a misspelled name actually hurts are loud already -- an unknown key
in a data file raises, and ``start_attack`` refuses an unregistered move rather
than starting nothing.
"""


def move_id(name: str) -> MoveId:
    """Name a move, so a table says which string is an identity.

    Reads as a call rather than a cast because a bare ``MoveId("x")`` at every
    ``cancel_into`` drowns a table in punctuation, and the point of the alias is
    that it is used often enough to be worth naming.
    """
    return MoveId(name)


class AttackButton(StrEnum):
    """A press of an attack button in a stance: what a chain is continued by.

    Two buttons, the blade and the body, each thrown high or low. The stance is
    held, not toggled, so it is read with the press.
    """

    SLASH_HIGH = "slash_high"
    SLASH_LOW = "slash_low"
    BEAT_HIGH = "beat_high"
    BEAT_LOW = "beat_low"
    SHOOT = "shoot"


class Stance(Enum):
    """The posture an attack has to be thrown from.

    Most specific first: ``WALL`` before ``AIR`` (sliding a wall is airborne).
    Not the blade's high or low stance, which is part of the press
    (:class:`AttackButton`).
    """

    GROUND = "ground"
    """Standing or moving on the floor -- the default posture."""

    AIR = "air"
    """No floor contact, not sliding a wall."""

    WALL = "wall"
    """Airborne and in contact with a wall the fighter is holding into."""


class Clash(StrEnum):
    """What two equal-priority hits do when they meet."""

    TRADE = "trade"
    """Both connect."""
    CLASH = "clash"
    """Both are cancelled, with a clash spark."""


class Height(StrEnum):
    """Where a hit lands: what a guard held high or low stops.

    A low guard stops ``low``; a high guard stops everything else.
    """

    HIGH = "high"
    MID = "mid"
    LOW = "low"
    OVERHEAD = "overhead"


#: The hit fields that take a closed set of names: field, type, and the
#: message a bad value has always raised.
_NAMED_HIT_FIELDS: tuple[tuple[str, type[StrEnum], str], ...] = (
    ("clash", Clash, "Hit clash must be 'trade' or 'clash'"),
    ("height", Height, "Hit height must be 'high', 'mid', 'low' or 'overhead'"),
)


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
        Gravity multiplier applied to an airborne victim:
        < 1.0 floats the juggle, > 1.0 slams it down. 1.0 = untouched.
    otg_allowed : bool
        If True, this hit may connect during the OTG protection window
        granted on landing from a juggle. Ground hits
        otherwise bounce off a recently knocked-down victim.
    unblockable : bool
        If True, no guard stops the hit, and it breaks the guard it meets.
    priority : int
        Hit-vs-hit rank for simultaneous box overlaps (higher wins).
    clash : str
        Equal-priority outcome: ``"trade"`` (both connect) or
        ``"clash"`` (both attacks cancel with a clash event).
    height : str
        Where the hit lands: ``"high"``, ``"mid"``, ``"low"`` or ``"overhead"``.
        An enemy holding its guard at that height stops it.
    tags : tuple[str, ...]
        Category tags used by hurt-zone invulnerability matching.
    flinch : bool
        A grounded target only flinches: the hit stuns it as usual but does
        not push it, so the next link of a chain is still in reach. An
        airborne target is pushed as usual, or a juggle could not carry.
    hit_stop : float | None
        The world's freeze on contact, in seconds. ``None`` derives it from
        the damage and the knockback (``Combat.HITSTOP_*``); a number is for a
        hit whose weight is not in those two, such as a chain's finisher.
    stun : float
        What the hit adds to its target's stun gauge. A full gauge stuns the
        target (``Entity.add_stun``); light blows add little, heavy ones a lot.
    execute : bool
        If True, the hit kills a helpless target outright -- stunned, on the
        ground or doomed -- whatever its health. A doomed target is reached by
        nothing else.
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
    clash: Clash = Clash.TRADE
    height: Height = Height.MID
    tags: tuple[str, ...] = ()
    flinch: bool = False
    hit_stop: float | None = None
    stun: float = 0.0
    execute: bool = False

    def __post_init__(self) -> None:
        if self.damage < 0:
            raise ValueError("Hit damage cannot be negative")
        if self.hit_stop is not None and self.hit_stop < 0:
            raise ValueError("Hit-stop cannot be negative")
        if self.stun < 0:
            raise ValueError("Stun cannot be negative")
        if self.stagger < 0:
            raise ValueError("Hit stagger cannot be negative")
        if self.juggle_gravity_mult <= 0:
            raise ValueError("Juggle gravity multiplier must be strictly positive")
        if self.priority < 0:
            raise ValueError("Hit priority cannot be negative")
        # A name from a data file arrives as a plain string; it is turned into
        # its enum member here, so every reader past this point holds one.
        for name, kind, message in _NAMED_HIT_FIELDS:
            try:
                object.__setattr__(self, name, kind(getattr(self, name)))
            except ValueError:
                raise ValueError(message) from None
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


@dataclass(frozen=True, init=False)
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
    #: The one source of truth for geometry: index 0 is the primary box.
    boxes: tuple[HitboxSpec, ...]
    hit: HitProperties
    reset_targets: bool = True
    cancel_into: tuple[MoveId, ...] = ()
    cancel_on_hit: bool = False
    """Open ``cancel_into`` from the moment this phase has hit someone, not
    only in its recovery: the chain continues on contact, which is what lets a
    string of hits flow without waiting out each swing."""
    launches: str | None = None
    """The shot (``src/entities/shots.py``) this phase throws as it turns
    active. A launching phase strikes with the shot alone: its box marks the
    hand it leaves from, for the eye and the debug view, and never touches."""

    def __init__(
        self,
        startup_frames: int,
        active_frames: int,
        recovery_frames: int,
        hitbox_size: tuple[float, float] | None = None,
        hitbox_offset: tuple[float, float] | None = None,
        hit: HitProperties | None = None,
        hitbox_shape: ShapeKind = ShapeKind.AABB,
        hitbox_angle: float = 0.0,
        hitbox_easing: EasingKind = EasingKind.LINEAR,
        hitbox_anchor: AnchorKind = AnchorKind.CENTER,
        hitbox_anchor_offset: tuple[float, float] = (0.0, 0.0),
        extra_hitboxes: tuple[HitboxSpec, ...] = (),
        hitbox_keyframes: tuple[HitboxKeyframe, ...] = (),
        reset_targets: bool = True,
        cancel_into: tuple[MoveId, ...] = (),
        cancel_on_hit: bool = False,
        launches: str | None = None,
        *,
        boxes: tuple[HitboxSpec, ...] | None = None,
    ) -> None:
        """Accept the historical flat spelling and store only ``boxes``.

        The flat arguments are an adapter for v1 data, test fixtures and
        ``dataclasses.replace``; nothing reads them after construction. The v2
        loader passes ``boxes`` directly, so the old v2-to-flat round trip is
        gone.
        """
        if hit is None:
            raise TypeError("An attack phase requires a hit")
        if boxes is None:
            if hitbox_size is None or hitbox_offset is None:
                raise TypeError("An attack phase requires a size and an offset")
            boxes = (
                HitboxSpec(
                    size=hitbox_size,
                    offset=hitbox_offset,
                    keyframes=hitbox_keyframes,
                    shape=hitbox_shape,
                    angle=hitbox_angle,
                    easing=hitbox_easing,
                    anchor=hitbox_anchor,
                    anchor_offset=hitbox_anchor_offset,
                ),
                *extra_hitboxes,
            )
        object.__setattr__(self, "startup_frames", startup_frames)
        object.__setattr__(self, "active_frames", active_frames)
        object.__setattr__(self, "recovery_frames", recovery_frames)
        object.__setattr__(self, "boxes", boxes)
        object.__setattr__(self, "hit", hit)
        object.__setattr__(self, "reset_targets", reset_targets)
        object.__setattr__(self, "cancel_into", cancel_into)
        object.__setattr__(self, "cancel_on_hit", cancel_on_hit)
        object.__setattr__(self, "launches", launches)
        self.__post_init__()

    # Legacy flat views: read-only adapters, never storage.
    @property
    def hitbox_size(self) -> tuple[float, float]:
        return self.boxes[0].size

    @property
    def hitbox_offset(self) -> tuple[float, float]:
        return self.boxes[0].offset

    @property
    def hitbox_shape(self) -> ShapeKind:
        return self.boxes[0].shape

    @property
    def hitbox_angle(self) -> float:
        return self.boxes[0].angle

    @property
    def hitbox_easing(self) -> EasingKind:
        return self.boxes[0].easing

    @property
    def hitbox_anchor(self) -> AnchorKind:
        return self.boxes[0].anchor

    @property
    def hitbox_anchor_offset(self) -> tuple[float, float]:
        return self.boxes[0].anchor_offset

    @property
    def hitbox_keyframes(self) -> tuple[HitboxKeyframe, ...]:
        return self.boxes[0].keyframes

    @property
    def extra_hitboxes(self) -> tuple[HitboxSpec, ...]:
        return self.boxes[1:]

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
        for index, spec in enumerate(self.boxes):
            label = "Hitbox keyframe" if index == 0 else f"Extra hitbox #{index - 1} keyframe"
            _check_keyframe_span(spec.keyframes, span, label)

    def hitbox_at(self, frame: int) -> BoxGeometry:
        """Primary ``(size, offset)`` at a phase frame, geometry only.

        A read-only shim over the shape path: callers that only need the two
        tuples still work, while the single interpolator is the one that feeds
        the live hitboxes.
        """
        return self.hitbox_shape_at(frame)[0]

    @cached_property
    def hitbox_spec(self) -> HitboxSpec:
        """The primary hitbox under the extended shape model.

        Cached, and the cache is the point: this is reached once per box per
        tick by ``HitboxManager._position_rects``, and every field it reads is
        frozen on the phase. Built fresh each time it was 2.9us -- a
        ``HitboxSpec``, its validator, and the throwaway ``ShapePose`` that
        validator constructs -- for an answer that cannot change until the phase
        does. ``extra_hitboxes`` already stored its specs for the same reason;
        the primary was the only one recomputing.
        """
        return self.boxes[0]

    def hitbox_shape_at(self, frame: int) -> tuple[BoxGeometry, float]:
        """Interpolate the primary geometry and angle at a phase frame.

        The primary box goes through the same ``HitboxSpec`` as every extra
        box; the flat ``hitbox_*`` fields remain only as the data source the
        spec is built from.
        """
        spec = self.hitbox_spec
        return interpolate_shape_keyframes(
            spec.keyframes, (spec.size, spec.offset), frame, spec.easing
        )

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
    stances : tuple[Stance, ...]
        Postures this attack can be thrown from. A whitelist, not a blacklist:
        a posture added later has to be opted into deliberately, so a new
        posture does not silently make every existing move available from it.
        Defaults to ground only, which is what all shipped moves were
        implicitly restricted to before the field existed.
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
    invincible : bool
        If True, nothing hits the fighter while this attack runs: the death
        blow and the throw are played out untouched.
    lunge_speed_multiplier : float
        Multiplier applied to the entity's speed to compute the forward
        lunge velocity applied when this attack starts on the ground.
        0.0 disables the lunge entirely.
    vertical_lunge : float
        Vertical velocity, as a multiple of the fighter's jump height, used to
        bound the fighter's vertical speed when this attack starts **off the
        ground**. Signed: positive rises (matching the jump, whose velocity is
        ``-jump_height``), negative dives. 0.0 = no impulse.

        The horizontal twin above is grounded only, because a fighter who
        lunges on the ground overshoots the target while a fighter who rises in
        the air has nowhere to overshoot into. There is nothing to be gained by
        pretending otherwise, and the sign is shared so that "up" is the same
        word in both fields.

        A floor on the fighter's momentum, not a replacement for it: a rise
        takes ``min(current, -lunge)``, a dive ``max(current, +lunge)``. See
        ``PlayerAttackState.enter``, which is where that is applied.

        Distinct from the *hit's* knockback, which moves the target. This moves
        the attacker, and it is applied once at the start of the sequence: the
        fighter's arc carries them and the hitbox travels with them.
    attack_move_multiplier : float
        Multiplier applied to the entity's movement speed for the whole
        sequence, read every frame while the attack is live (see
        ``CombatComponent.movement_multiplier``). 1.0 = unrestricted,
        0.0 = frozen in place. Distinct from ``lunge_speed_multiplier``,
        which is a one-off impulse on the first grounded frame.

    Properties
    ----------
    total_frames : int
        Total frame count across all phases.

    animation : str
        Sprite-sheet clip to play while this move runs. This is art, not
        balance, so it lives here rather than in the renderer: the point is that
        a move can name its own clip. The player used to return ``"attack"`` for
        every grounded move, which meant no move could ever have art of its own
        -- the mapping existed, it just had one entry. A name with no directory
        under ``assets/graphics/player/`` is a no-op in :class:`Animator`, so a
        clip that has not landed yet falls back to the last one rather than
        breaking the render.
    """

    phases: tuple[PhaseDefinition, ...]
    cooldown: float
    stances: tuple[Stance, ...] = (Stance.GROUND,)
    animation: str = "attack"
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0
    charge_move_multiplier: float = 1.0
    uninterruptible: bool = False
    invincible: bool = False
    lunge_speed_multiplier: float = 0.35
    vertical_lunge: float = 0.0
    attack_move_multiplier: float = 0.3
    follow_ups: tuple[tuple[AttackButton, MoveId], ...] = ()
    """The move a button throws while this one runs: the next link of a chain.

    Pairs rather than a mapping so the definition stays immutable and hashable.
    A follow-up still goes through ``start_attack``, so it must also be in the
    ``cancel_into`` of a phase -- the loader checks that it is."""

    def follow_up(self, button: AttackButton) -> MoveId | None:
        """The move ``button`` chains into from this one, or ``None``."""
        for pressed, move in self.follow_ups:
            if pressed is button:
                return move
        return None

    def __post_init__(self) -> None:
        if not self.phases:
            raise ValueError("An attack requires at least one phase")
        if not self.stances:
            raise ValueError(
                "Attack 'stances' cannot be empty: an attack reachable from no "
                "posture could never be thrown"
            )
        if len(set(self.stances)) != len(self.stances):
            duplicated = sorted({stance.value for stance in self.stances})
            raise ValueError(f"Attack 'stances' has duplicates: {', '.join(duplicated)}")
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
