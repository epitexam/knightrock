"""Strikes made visible: each family of blow drawn its own way.

Render-only, like the afterimages: nothing here is read by the simulation or
captured by a snapshot. What is drawn follows the hitbox -- the live attack
shapes of every fighter -- so the player sees exactly what can hit, but each
family has its own :class:`Look`:

- the blade cuts a thin, sharp crescent, a heavy cut a wider one;
- the body leaves a short streak and a knuckle or a heel at its tip;
- a charged cut is gold, brighter the longer it was held; a full charge is
  white-hot and leaves afterimages; the death blow is a dark red slash;
- an enemy's blow is red, a blow no guard stops is violet.

Three things are drawn besides the blows:

- **the charge** gathering at the hand while a button is held, a ring that
  closes in as it fills and flashes when it is full;
- **the warning** of an enemy blow while it winds up: a chevron at the height
  it will strike (red high or low, violet when no guard stops it), so the
  guard can be chosen from the screen;
- **the shots**, each with its own shape and trail: the bolt, the piercing
  bolt, the crescent of a full cut, the slime's glob.

A segment per live shape: the long axis of a turned box (a blade) or of a
capsule (a limb), from its inner end to its tip. The segments a strike leaves
over the last frames join into a ribbon that fades as it ages.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pygame

from src.combat.frame_data import Height, PhaseState
from src.combat.shapes import ShapeKind, ShapePose
from src.core.colors import Color
from src.core.rendering.camera import Camera

#: A sample is taken only if the tip moved at least this far (world px).
MIN_STEP = 1.0
#: A dark line under every edge: a pale blade on a pale sky still reads.
OUTLINE: tuple[int, int, int, int] = (20, 28, 60, 140)

Point = tuple[float, float]
Screen = Callable[[Point], Point]


@dataclass(frozen=True)
class Look:
    """How one family of strike is drawn."""

    core: Color
    """The body of the swath."""
    edge: Color
    """Its leading edge, and the blade or the tip."""
    ttl: float
    """How long a sample stays, in seconds: how long the swath lingers."""
    alpha: int
    """Opacity of the newest part of the swath."""
    rim: int
    """Width of the leading edge, in screen px."""
    live: str
    """What marks the live shape: ``"blade"`` a bright edge along it, ``"limb"`` a
    short streak and a tip, ``"ring"`` a widening shock."""
    glow: int = 0
    """A soft halo this wide around the edge, in screen px."""
    samples: int = 10
    """How many samples the swath keeps: more is a longer wake."""


BLADE = Look((180, 220, 255), (250, 252, 255), 0.09, 150, 2, "blade")
HEAVY_BLADE = Look((165, 205, 255), (255, 255, 255), 0.14, 175, 3, "blade", glow=4)
CHARGED = Look((255, 205, 110), (255, 248, 215), 0.18, 185, 3, "blade", glow=6, samples=12)
CHARGED_FULL = Look((255, 236, 170), (255, 255, 255), 0.26, 215, 4, "blade", glow=10, samples=16)
DEATH = Look((70, 0, 18), (255, 50, 70), 0.32, 220, 3, "blade", glow=8, samples=16)
BODY = Look((255, 205, 150), (255, 240, 215), 0.07, 120, 2, "limb")
CHARGED_BODY = Look((255, 160, 70), (255, 235, 190), 0.16, 175, 3, "limb", glow=6, samples=12)
THROW = Look((255, 225, 190), (255, 255, 255), 0.22, 160, 3, "ring")
ENEMY = Look((255, 95, 75), (255, 205, 180), 0.10, 160, 2, "limb")
ENEMY_BLADE = Look((255, 95, 75), (255, 205, 180), 0.10, 160, 2, "blade")
ENEMY_UNBLOCKABLE = Look((190, 110, 255), (240, 215, 255), 0.14, 180, 3, "limb", glow=5)
ENEMY_RING = Look((255, 95, 75), (255, 205, 180), 0.14, 150, 3, "ring")

#: Charge colours: gathering, then full.
CHARGE_COLORS: dict[str, tuple[Color, Color]] = {
    "slash": ((150, 210, 255), (255, 225, 130)),
    "kick": ((255, 170, 90), (255, 225, 150)),
    "shot": ((110, 230, 255), (220, 255, 255)),
}
#: The warning's colours: a guard stops it, nothing does.
WARN_COLOR: Color = (255, 70, 60)
WARN_UNBLOCKABLE: Color = (200, 120, 255)
#: How many frames before the blow the warning shows.
WARN_FRAMES = 14
#: The shots' colours: body, core.
SHOT_COLORS: dict[str, tuple[Color, Color]] = {
    "bolt": ((100, 215, 255), (240, 255, 255)),
    "charged_bolt": ((140, 235, 255), (255, 255, 255)),
    "crescent": ((255, 225, 150), (255, 255, 240)),
    "glob": ((110, 200, 80), (190, 245, 150)),
}
#: How long a shot's trail lingers, in seconds.
SHOT_TTL = 0.12


#: The player's moves drawn their own way; the rest follow their shape.
NAMED_LOOKS: dict[str, Look] = {
    "death_blow": DEATH,
    "charged_slash_full": CHARGED_FULL,
    "charged_slash": CHARGED,
    "charged_kick": CHARGED_BODY,
    "stab": HEAVY_BLADE,
    "slash_high_4": HEAVY_BLADE,
    "slash_low_4": HEAVY_BLADE,
}


def _enemy_look(shape: ShapePose, unblockable: bool) -> Look:
    if shape.kind is ShapeKind.CIRCLE:
        return ENEMY_RING
    if unblockable:
        return ENEMY_UNBLOCKABLE
    return ENEMY_BLADE if shape.kind is ShapeKind.OBB else ENEMY


def look_for(enemy: bool, move: str, shape: ShapePose, unblockable: bool) -> Look:
    """The look of a live strike: who throws it, which move, what shape."""
    if enemy:
        return _enemy_look(shape, unblockable)
    named = NAMED_LOOKS.get(move)
    if named is not None:
        return named
    if shape.kind is ShapeKind.CIRCLE:
        return THROW
    return BODY if shape.kind is ShapeKind.CAPSULE else BLADE


@dataclass
class _Sample:
    inner: Point
    outer: Point
    radius: float
    age: float = 0.0


@dataclass
class _Trail:
    look: Look
    strength: float = 1.0
    """A charged cut's opacity grows with the charge it was thrown at."""
    samples: list[_Sample] = field(default_factory=list)
    live: ShapePose | None = None


@dataclass
class _Charge:
    hand: Point
    ratio: float
    family: str
    full_for: float = 0.0
    """How long the charge has been full: a flash on the first instant."""


@dataclass
class _Warning:
    point: Point
    facing: float
    progress: float
    unblockable: bool


@dataclass
class _Shot:
    look: str
    trail: list[tuple[Point, float]] = field(default_factory=list)
    head: Point = (0.0, 0.0)
    heading: Point = (1.0, 0.0)
    size: tuple[float, float] = (8.0, 8.0)
    live: bool = False


def _segment(shape: ShapePose) -> tuple[Point, Point]:
    """The inner end and the tip of a box's or a capsule's long axis."""
    half = shape.size[0] / 2.0
    radians = math.radians(shape.angle)
    dx, dy = half * math.cos(radians), half * math.sin(radians)
    x, y = shape.position
    return (x - dx, y - dy), (x + dx, y + dy)


def _charge_family(move: str | None) -> str:
    if move is None:
        return "slash"
    if "kick" in move:
        return "kick"
    if "shot" in move:
        return "shot"
    return "slash"


#: Where a warning sits on the attacker's front, by the height of the blow
#: (from the hitbox centre, y down).
_WARN_HEIGHT: dict[Height, float] = {
    Height.HIGH: -14.0,
    Height.OVERHEAD: -14.0,
    Height.MID: 0.0,
    Height.LOW: 18.0,
}


class StrikeTrails:
    """The strikes in flight, the charges building, the warnings and the shots."""

    def __init__(self) -> None:
        self._trails: dict[tuple[int, int, int, int], _Trail] = {}
        self._charges: dict[int, _Charge] = {}
        self._warnings: list[_Warning] = []
        self._shots: dict[int, _Shot] = {}
        self._clock = 0.0

    def __len__(self) -> int:
        return len(self._trails)

    # -- sampling ---------------------------------------------------------------

    def update(self, fighters: Iterable[Any], dt: float, shots: Iterable[Any] = ()) -> None:
        """Age every sample, then sample the fighters and the shots in flight."""
        self._clock += dt
        for trail in self._trails.values():
            trail.live = None
            for sample in trail.samples:
                sample.age += dt
            trail.samples = [s for s in trail.samples if s.age < trail.look.ttl]
        self._warnings = []
        charging: set[int] = set()
        for fighter in fighters:
            self._sample(fighter)
            if self._sample_charge(fighter, dt):
                charging.add(id(fighter))
            self._sample_warning(fighter)
        self._charges = {key: charge for key, charge in self._charges.items() if key in charging}
        self._trails = {
            key: trail for key, trail in self._trails.items() if trail.samples or trail.live
        }
        self._sample_shots(shots, dt)

    def _sample(self, fighter: Any) -> None:
        combat = getattr(fighter, "combat", None)
        if combat is None or getattr(fighter, "is_dead", False):
            return
        state = combat.state
        if not state.is_active:
            return
        shapes = combat.attack_shapes
        phase = combat.current_phase
        if not shapes or phase is None or phase.launches:
            return
        enemy = getattr(fighter, "faction", "") != "player"
        move = str(state.attack_name or "")
        for index, shape in enumerate(shapes):
            key = (id(fighter), int(combat.attacks_started), int(state.phase_index), index)
            trail = self._trails.get(key)
            if trail is None:
                look = look_for(enemy, move, shape, phase.hit.unblockable)
                charge = float(getattr(combat, "charge_multiplier", 1.0) or 1.0)
                trail = _Trail(look, strength=min(1.0, 0.55 + 0.45 * (charge - 1.0)))
                if look is not CHARGED:
                    trail.strength = 1.0
                self._trails[key] = trail
            trail.live = shape
            inner, outer = _segment(shape)
            radius = shape.size[1] / 2.0
            if shape.kind is ShapeKind.CIRCLE:
                inner = outer = shape.position
                radius = shape.size[0] / 2.0
            last = trail.samples[-1] if trail.samples else None
            if (
                last is not None
                and math.dist(last.outer, outer) < MIN_STEP
                and math.dist(last.inner, inner) < MIN_STEP
                and abs(last.radius - radius) < MIN_STEP
            ):
                continue
            trail.samples.append(_Sample(inner, outer, radius))
            del trail.samples[: -trail.look.samples]

    def _sample_charge(self, fighter: Any, dt: float) -> bool:
        combat = getattr(fighter, "combat", None)
        charging = getattr(combat, "charging", None)
        if charging is None or not charging.is_charging or getattr(fighter, "is_dead", False):
            return False
        side = 1.0 if fighter.facing_right else -1.0
        hand = (fighter.hitbox.centerx + 14.0 * side, fighter.hitbox.centery + 6.0)
        ratio = float(charging.ratio)
        charge = self._charges.get(id(fighter))
        if charge is None:
            charge = _Charge(hand, ratio, _charge_family(charging.attack_name))
            self._charges[id(fighter)] = charge
        charge.hand, charge.ratio = hand, ratio
        charge.full_for = charge.full_for + dt if ratio >= 1.0 else 0.0
        return True

    def _sample_warning(self, fighter: Any) -> None:
        if getattr(fighter, "faction", "player") == "player" or getattr(fighter, "is_dead", False):
            return
        combat = getattr(fighter, "combat", None)
        if combat is None:
            return
        state = combat.state
        phase = state.current_phase_def
        if phase is None or state.sub_state is not PhaseState.STARTUP:
            return
        left = phase.startup_frames - state.frame_counter
        if left > WARN_FRAMES:
            return
        side = 1.0 if fighter.facing_right else -1.0
        y = fighter.hitbox.centery + _WARN_HEIGHT.get(phase.hit.height, 0.0)
        x = fighter.hitbox.centerx + side * (fighter.hitbox.width / 2.0 + 6.0)
        self._warnings.append(
            _Warning((x, y), side, 1.0 - left / WARN_FRAMES, phase.hit.unblockable)
        )

    def _sample_shots(self, shots: Iterable[Any], dt: float) -> None:
        alive: set[int] = set()
        for shot in shots:
            if not getattr(shot, "active", False):
                continue
            key = id(shot)
            alive.add(key)
            record = self._shots.get(key)
            look = str(shot.config.look)
            if record is None or record.look != look or not record.live:
                record = _Shot(look)
                self._shots[key] = record
            head = (shot.hitbox.centerx, shot.hitbox.centery)
            speed = math.hypot(shot.velocity.x, shot.velocity.y) or 1.0
            record.head = head
            record.heading = (shot.velocity.x / speed, shot.velocity.y / speed)
            record.size = tuple(shot.config.size)  # type: ignore[assignment]
            record.live = True
            record.trail = [(p, age + dt) for p, age in record.trail if age + dt < SHOT_TTL]
            record.trail.append((head, 0.0))
        for key, record in list(self._shots.items()):
            if key in alive:
                continue
            record.live = False
            record.trail = [(p, age + dt) for p, age in record.trail if age + dt < SHOT_TTL]
            if not record.trail:
                del self._shots[key]

    # -- drawing ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, camera: Camera) -> None:
        """Paint the swaths, the live strikes, the charges, the warnings and the shots."""
        density = camera.density

        def screen(point: Point) -> Point:
            moved = camera.apply(pygame.FRect(point[0], point[1], 0.0, 0.0))
            return (moved.x, moved.y)

        for trail in self._trails.values():
            if trail.look.live == "ring":
                self._draw_rings(surface, trail, screen, density)
                continue
            self._draw_swath(surface, trail, screen)
            if trail.live is not None:
                self._draw_live(surface, trail, screen, density)
        for shot in self._shots.values():
            self._draw_shot(surface, shot, screen, density)
        for charge in self._charges.values():
            self._draw_charge(surface, charge, screen, density)
        for warning in self._warnings:
            self._draw_warning(surface, warning, screen, density)

    @staticmethod
    def _layer(
        surface: pygame.Surface, points: list[Point], pad: int = 2
    ) -> tuple[pygame.Surface, Point] | None:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        left, top = math.floor(min(xs)) - pad, math.floor(min(ys)) - pad
        width, height = math.ceil(max(xs)) - left + pad + 1, math.ceil(max(ys)) - top + pad + 1
        if width <= 0 or height <= 0 or width > surface.get_width() * 2:
            return None
        return pygame.Surface((width, height), pygame.SRCALPHA), (left, top)

    def _draw_swath(self, surface: pygame.Surface, trail: _Trail, screen: Screen) -> None:
        samples = trail.samples
        if len(samples) < 2:
            return
        look = trail.look
        inner = [screen(s.inner) for s in samples]
        outer = [screen(s.outer) for s in samples]
        made = self._layer(surface, inner + outer, pad=look.glow + 2)
        if made is None:
            return
        layer, (left, top) = made
        strength = trail.strength
        for i in range(len(samples) - 1):
            fade = 1.0 - samples[i].age / look.ttl
            share = 0.35 + 0.65 * (i + 1) / len(samples)
            alpha = max(0, int(look.alpha * fade * share * strength))
            quad = [inner[i], outer[i], outer[i + 1], inner[i + 1]]
            pygame.draw.polygon(layer, (*look.core, alpha), [(x - left, y - top) for x, y in quad])
        rim = [(x - left, y - top) for x, y in outer]
        pygame.draw.lines(layer, OUTLINE, False, rim, look.rim + 2)
        if look.glow:
            pygame.draw.lines(layer, (*look.edge, int(60 * strength)), False, rim, look.glow)
        pygame.draw.lines(layer, (*look.edge, int(look.alpha * strength)), False, rim, look.rim)
        surface.blit(layer, (left, top))

    def _draw_live(
        self, surface: pygame.Surface, trail: _Trail, screen: Screen, density: float
    ) -> None:
        shape = trail.live
        assert shape is not None
        look = trail.look
        inner, outer = _segment(shape)
        a, b = screen(inner), screen(outer)
        made = self._layer(surface, [a, b], pad=look.glow + 8)
        if made is None:
            return
        layer, (left, top) = made
        la, lb = (a[0] - left, a[1] - top), (b[0] - left, b[1] - top)
        if look.live == "blade":
            # The blade: a hard, bright line, haloed when charged.
            if look.glow:
                pygame.draw.line(layer, (*look.edge, 70), la, lb, look.rim + look.glow)
            pygame.draw.line(layer, OUTLINE, la, lb, look.rim + 3)
            pygame.draw.line(layer, (*look.core, 230), la, lb, look.rim + 1)
            pygame.draw.line(layer, (*look.edge, 255), la, lb, max(1, look.rim - 1))
        else:
            # A limb: a short streak behind the tip, and the knuckle or the heel.
            tip = max(2, int(round(min(shape.size[1] / 2.0, 5.0) * density)))
            back = (lb[0] + (la[0] - lb[0]) * 0.45, lb[1] + (la[1] - lb[1]) * 0.45)
            if look.glow:
                pygame.draw.circle(layer, (*look.core, 70), lb, tip + look.glow)
            pygame.draw.line(layer, (*look.core, 170), back, lb, max(2, tip))
            pygame.draw.circle(layer, OUTLINE, lb, tip + 1)
            pygame.draw.circle(layer, (*look.core, 235), lb, tip)
            pygame.draw.circle(layer, (*look.edge, 255), lb, max(1, tip // 2))
        surface.blit(layer, (left, top))

    def _draw_rings(
        self, surface: pygame.Surface, trail: _Trail, screen: Screen, density: float
    ) -> None:
        look = trail.look
        for sample in trail.samples:
            fade = 1.0 - sample.age / look.ttl
            center = screen(sample.outer)
            radius = max(2, int(round(sample.radius * density)))
            made = self._layer(
                surface,
                [
                    (center[0] - radius, center[1] - radius),
                    (center[0] + radius, center[1] + radius),
                ],
            )
            if made is None:
                continue
            layer, (left, top) = made
            local = (center[0] - left, center[1] - top)
            pygame.draw.circle(layer, (*look.core, int(look.alpha * 0.25 * fade)), local, radius)
            pygame.draw.circle(
                layer, (*look.edge, int(look.alpha * fade)), local, radius, max(2, radius // 7)
            )
            surface.blit(layer, (left, top))

    def _draw_charge(
        self, surface: pygame.Surface, charge: _Charge, screen: Screen, density: float
    ) -> None:
        gathering, full = CHARGE_COLORS.get(charge.family, CHARGE_COLORS["slash"])
        center = screen(charge.hand)
        ratio = charge.ratio
        is_full = ratio >= 1.0
        color = full if is_full else gathering
        radius = max(3, int(round((16.0 - 10.0 * ratio) * density)))
        flash = is_full and charge.full_for < 0.12
        reach = radius + int(10 * density) + (int(8 * density) if flash else 0)
        made = self._layer(
            surface,
            [(center[0] - reach, center[1] - reach), (center[0] + reach, center[1] + reach)],
        )
        if made is None:
            return
        layer, (left, top) = made
        local = (center[0] - left, center[1] - top)
        alpha = int(90 + 140 * ratio)
        pulse = 0.5 + 0.5 * math.sin(self._clock * (22.0 if is_full else 10.0))
        if is_full:
            pygame.draw.circle(
                layer, (*color, int(60 + 60 * pulse)), local, radius + int(4 * density)
            )
        pygame.draw.circle(layer, (*color, alpha), local, radius, max(1, int(2 * density)))
        # Three sparks drawn in towards the hand as the charge grows.
        for k in range(3):
            angle = self._clock * 7.0 + k * (2 * math.pi / 3)
            r = radius + (1.0 - ratio) * 8.0 * density
            spark = (local[0] + math.cos(angle) * r, local[1] + math.sin(angle) * r)
            pygame.draw.circle(layer, (*color, alpha), spark, max(1, int(1.5 * density)))
        if flash:
            pygame.draw.circle(layer, (255, 255, 255, 200), local, reach, max(1, int(2 * density)))
        surface.blit(layer, (left, top))

    def _draw_warning(
        self, surface: pygame.Surface, warning: _Warning, screen: Screen, density: float
    ) -> None:
        center = screen(warning.point)
        size = max(3.0, 5.0 * density)
        color = WARN_UNBLOCKABLE if warning.unblockable else WARN_COLOR
        # Blinks faster as the blow comes: the last frames read as a flash.
        blink = 0.5 + 0.5 * math.sin(self._clock * (12.0 + 30.0 * warning.progress))
        alpha = int(110 + 145 * max(warning.progress, blink * warning.progress))
        made = self._layer(
            surface,
            [
                (center[0] - size * 2, center[1] - size * 2),
                (center[0] + size * 2, center[1] + size * 2),
            ],
        )
        if made is None:
            return
        layer, (left, top) = made
        x, y = center[0] - left, center[1] - top
        f = warning.facing
        chevron = [(x - f * size, y - size), (x + f * size, y), (x - f * size, y + size)]
        pygame.draw.lines(layer, (*color, alpha), False, chevron, max(2, int(2 * density)))
        surface.blit(layer, (left, top))

    def _draw_shot(
        self, surface: pygame.Surface, shot: _Shot, screen: Screen, density: float
    ) -> None:
        body, core = SHOT_COLORS.get(shot.look, SHOT_COLORS["bolt"])
        points = [screen(p) for p, _ in shot.trail]
        head = screen(shot.head)
        reach = max(shot.size) * density + 12
        made = self._layer(
            surface,
            [*points, (head[0] - reach, head[1] - reach), (head[0] + reach, head[1] + reach)],
        )
        if made is None:
            return
        layer, (left, top) = made
        local = [(x - left, y - top) for x, y in points]
        lh = (head[0] - left, head[1] - top)
        hx, hy = shot.heading
        width = max(2, int(round(min(shot.size) * density)))
        # The wake: a line along the last positions, thinner and fainter behind.
        for i in range(len(local) - 1):
            age = shot.trail[i][1]
            fade = 1.0 - age / SHOT_TTL
            pygame.draw.line(
                layer, (*body, int(170 * fade)), local[i], local[i + 1], max(1, int(width * fade))
            )
        if not shot.live:
            surface.blit(layer, (left, top))
            return
        if shot.look == "glob":
            radius = max(3, int(round(shot.size[0] / 2.0 * density)))
            pygame.draw.circle(layer, (*body, 235), lh, radius)
            pygame.draw.circle(
                layer, (*core, 255), (lh[0] - radius / 3, lh[1] - radius / 3), max(1, radius // 3)
            )
        elif shot.look == "crescent":
            radius = max(4, int(round(shot.size[1] / 2.0 * density)))
            facing = 1.0 if hx >= 0 else -1.0
            rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            rect.center = (int(lh[0] - facing * radius * 0.6), int(lh[1]))
            start, stop = (-1.1, 1.1) if facing > 0 else (math.pi - 1.1, math.pi + 1.1)
            pygame.draw.arc(layer, (*body, 120), rect.inflate(6, 6), start, stop, max(2, width + 4))
            pygame.draw.arc(layer, (*core, 255), rect, start, stop, max(2, width // 2 + 2))
        else:
            length = max(6.0, shot.size[0] * density)
            tail = (lh[0] - hx * length, lh[1] - hy * length)
            if shot.look == "charged_bolt":
                pygame.draw.line(layer, (*body, 90), tail, lh, width + 8)
            pygame.draw.line(layer, (*body, 230), tail, lh, width)
            pygame.draw.line(layer, (*core, 255), tail, lh, max(1, width // 2))
        surface.blit(layer, (left, top))
