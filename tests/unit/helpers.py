"""Shared test helpers (audit F7.2).

`make_phase`/`make_attack`/`make_entity`/`entity_at`/`activate` used to be
redefined across several test files (test_hitbox_pipeline,
test_damage_resolution, test_combat_behaviors). Single source, reused via
``from tests.unit.helpers import ...``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pygame
from pygame.sprite import Group

from src.combat.frame_data import (
    FRAME_RATE,
    AttackDefinition,
    HitboxKeyframe,
    HitboxSpec,
    HitProperties,
    PhaseDefinition,
)
from src.combat.knockback import KnockbackConfig
from src.core.input.input_state import InputState
from src.entities.entity import Entity
from src.entities.hurtbox_zones import HurtboxZoneDef

if TYPE_CHECKING:
    from src.ui.ui_manager import UIManager


def make_phase(
    *,
    startup: int = 1,
    active: int = 2,
    recovery: int = 1,
    size: tuple[float, float] = (30.0, 20.0),
    offset: tuple[float, float] = (20.0, 0.0),
    extra: tuple[tuple[tuple[float, float], tuple[float, float]], ...] = (),
    keyframes: tuple[tuple[int, tuple[float, float], tuple[float, float]], ...] = (),
    damage: int = 10,
    reset_targets: bool = True,
    unblockable: bool = False,
    priority: int = 0,
    clash: str = "trade",
    height: str = "mid",
) -> PhaseDefinition:
    """Build a single phase definition with sensible defaults."""
    return PhaseDefinition(
        startup_frames=startup,
        active_frames=active,
        recovery_frames=recovery,
        hitbox_size=size,
        hitbox_offset=offset,
        extra_hitboxes=tuple(
            HitboxSpec(size=box_size, offset=box_offset) for box_size, box_offset in extra
        ),
        hitbox_keyframes=tuple(
            HitboxKeyframe(frame=frame, size=box_size, offset=box_offset)
            for frame, box_size, box_offset in keyframes
        ),
        hit=HitProperties(
            damage=damage,
            knockback=KnockbackConfig(power=(0.0, 0.0)),
            unblockable=unblockable,
            priority=priority,
            clash=clash,
            height=height,
        ),
        reset_targets=reset_targets,
    )


def make_attack(*phases: PhaseDefinition, lock_direction: bool = True) -> AttackDefinition:
    """Build an attack definition wrapping the given phases.

    The cooldown matches the attack's own duration: the strict loader
    (``attack_loading``) rejects shorter ones.
    """
    total_frames = sum(phase.total_frames for phase in phases)
    return AttackDefinition(
        phases=phases,
        cooldown=total_frames / FRAME_RATE,
        lock_direction=lock_direction,
    )


def make_entity(
    *,
    pos: tuple[float, float] = (100.0, 100.0),
    size: tuple[float, float] = (40.0, 40.0),
    color: tuple[int, int, int] = (255, 255, 255),
    faction: str = "neutral",
    health: float = 100.0,
    max_health: float = 100.0,
    attacks: dict[str, AttackDefinition] | None = None,
    invincibility: float = 0.0,
    hurtbox_inflate: tuple[float, float] = (0.0, 0.0),
    hurtbox_zones: Sequence[HurtboxZoneDef] | None = None,
) -> Entity:
    """Build a bare :class:`Entity` in isolated sprite groups."""
    return Entity(
        pos=pos,
        size=size,
        color=color,
        groups=Group(),
        collision_sprites=Group(),
        faction=faction,
        health=health,
        max_health=max_health,
        attacks=attacks,
        invincibility_duration=invincibility,
        hurtbox_inflate=hurtbox_inflate,
        hurtbox_zones=hurtbox_zones,
    )


def entity_at(
    x: float,
    *,
    faction: str = "neutral",
    definition: AttackDefinition | None = None,
    hurtbox_inflate: tuple[float, float] = (0.0, 0.0),
    hurtbox_zones: Sequence[HurtboxZoneDef] | None = None,
) -> Entity:
    """Place an entity at ``(x, 0)`` with an optional ``test`` attack."""
    attacks = {"test": definition} if definition is not None else None
    return make_entity(
        pos=(float(x), 0.0),
        faction=faction,
        attacks=attacks,
        hurtbox_inflate=hurtbox_inflate,
        hurtbox_zones=hurtbox_zones,
    )


def activate(entity: Entity) -> None:
    """Start the ``test`` attack and advance into its active phase."""
    assert entity.combat.start_attack("test")
    entity.combat.update(1 / 60)
    entity.combat.sync_attack_box()
    assert entity.combat.attack_box is not None


class _ActiveAttackerCombat(SimpleNamespace):
    """Active attacker double whose box overlaps the target."""

    def __init__(self, attack_box: pygame.FRect, hit: HitProperties) -> None:
        targets_hit: set[str] = set()
        super().__init__(
            state=SimpleNamespace(is_active=True),
            attack_box=attack_box,
            attack_boxes=(attack_box,),
            swept_attack_boxes=(attack_box,),
            current_phase=SimpleNamespace(hit=hit),
            charge_multiplier=1.0,
            targets_hit=targets_hit,
            can_contact=lambda target_id: target_id not in targets_hit,
            record_contact=targets_hit.add,
            capture_attack_origin=lambda: None,
            cancel_attack=lambda: None,
        )
        self._air_count = 0

    @property
    def air_combo_count(self) -> int:
        return self._air_count

    def record_hit_landed(self, airborne: bool) -> None:
        if airborne:
            self._air_count += 1


def make_active_attacker(target: Entity) -> SimpleNamespace:
    """Build a lightweight active attacker whose box overlaps the target."""
    hit = HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(100.0, 0.0)),
    )
    attack_box = target.hurtbox.copy()
    combat = _ActiveAttackerCombat(attack_box, hit)
    return SimpleNamespace(
        id="attacker",
        is_dead=False,
        faction="enemy",
        hitbox=pygame.FRect(-20.0, 0.0, 10.0, 10.0),
        combat=combat,
        hurtbox=target.hurtbox.copy(),
        hurtboxes=target.hurtboxes,
        hurtbox_mult=target.hurtbox_mult,
        hurtbox_tags=target.hurtbox_tags,
        hurtbox_zone_names=target.hurtbox_zone_names,
        swept_hurtbox=lambda: target.swept_hurtbox(),
        swept_hurtboxes=lambda: target.swept_hurtboxes(),
        capture_sweep_origin=target.capture_sweep_origin,
    )


@dataclass
class SpyCombat:
    """Minimal combat component recording explicit interruptions."""

    hit_interrupts: list[bool] = field(default_factory=list)
    is_hurt: bool = False
    hurt_timer: float = 0.0

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None:
        self.hit_interrupts.append(interrupt)
        self.is_hurt = interrupt
        if interrupt:
            self.hurt_timer = duration if duration is not None else 0.25

    def reset_hurt_state(self) -> None:
        self.is_hurt = False
        self.hurt_timer = 0.0

    def reset(self) -> None:
        self.reset_hurt_state()


@dataclass
class SpyStateMachine:
    """Record forced state changes without requiring concrete game states."""

    changes: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def change_state(self, name: str, **kwargs: object) -> None:
        self.changes.append((name, kwargs))


class InputStub:
    """Constructor-only input provider used by player-based tests."""

    down_held: bool = False


class ScriptedInputProvider:
    def __init__(self, states: list[InputState]) -> None:
        self._states = states

    def poll(self) -> InputState:
        if self._states:
            return self._states.pop(0)
        return InputState()


class AttackerStub:
    """Minimal hit carrier: hitbox plus neutral combo tracking."""

    def __init__(self, centerx: float = 0.0) -> None:
        self.hitbox = pygame.FRect(centerx - 5.0, 0.0, 10.0, 10.0)
        self.combat = SimpleNamespace(air_combo_count=0, record_hit_landed=lambda airborne: None)


__all__ = [
    "AttackerStub",
    "InputStub",
    "SpyCombat",
    "SpyStateMachine",
    "ScriptedInputProvider",
    "activate",
    "entity_at",
    "make_active_attacker",
    "make_attack",
    "make_entity",
    "make_overlay",
    "make_phase",
]


def make_overlay(surface: pygame.Surface, density: float = 1.0) -> UIManager:
    """The real interface, for a test that needs one.

    `Renderer` takes its overlay by injection and defaults to drawing nothing
    (`src/core/rendering/overlay.py`), so a test that asserts on health bars,
    the HUD or a debug panel has to say it wants the interface rather than
    getting it as a side effect of constructing a renderer.
    """
    from src.ui.ui_manager import UIManager

    return UIManager(surface, density)


def overlay_entity(name: str = "Goblin", **overrides) -> SimpleNamespace:
    """A minimal sprite the world debug overlay can draw and label.

    The overlay reads everything off ``getattr``, so its tests need an object
    that is *nearly* a sprite rather than a real one -- a ``SimpleNamespace``
    with a class name, because ``display_name`` falls back to the class name
    and the fallback is itself worth testing.

    Three test modules need this, and the overlay's readers are unforgiving
    about a missing field: a factory that quietly omits ``hurtbox_tags`` makes
    the next test fail somewhere unrelated. The defaults are therefore the
    complete field set, and a test that wants one absent deletes it.
    """
    from pygame.math import Vector2

    base = {
        "hitbox": pygame.FRect(100, 100, 40, 48),
        "hurtbox": pygame.FRect(98, 98, 44, 52),
        "hurtboxes": (pygame.FRect(98, 98, 44, 52),),
        "hurtbox_zone_names": ("",),
        "hurtbox_mult": (1.0,),
        "hurtbox_tags": ((),),
        "velocity": Vector2(0, 0),
        "faction": "enemy",
        "health": 75.0,
        "max_health": 100.0,
        "stagger_timer": 0.0,
        "otg_timer": 0.0,
        "gravity_scale": 1.0,
        "on_surface": {"floor": True, "left": False, "right": False},
        "state_machine": SimpleNamespace(current_state_name="idle"),
        "combat": SimpleNamespace(
            state=SimpleNamespace(attack_name=None, sub_state=None, phase_index=0, frame_counter=0),
            targets_hit=set(),
        ),
    }
    base.update(overrides)
    return type(name, (SimpleNamespace,), {})(**base)


def lit_pixels(surface: pygame.Surface, step: int = 2) -> int:
    """How many sampled pixels on ``surface`` are not black.

    A shape either drew or it did not, and counting is the probe that says so
    without depending on which colour it was or exactly where. Sampled on a
    grid because a full scan of a 1024x768 surface is 786k ``get_at`` calls.
    """
    black = (0, 0, 0)
    return sum(
        1
        for x in range(0, surface.get_width(), step)
        for y in range(0, surface.get_height(), step)
        if surface.get_at((x, y))[:3] != black
    )
