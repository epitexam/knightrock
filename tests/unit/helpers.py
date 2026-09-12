"""Partagés d'aides de test (audit F7.2).

`make_phase`/`make_attack`/`make_entity`/`entity_at`/`activate` étaient
redéfinis dans plusieurs fichiers de test (test_hitbox_pipeline,
test_damage_resolution, test_combat_behaviors). Une seule source,
réutilisée via ``from tests.unit.helpers import ...``.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

import pygame
from pygame.sprite import Group

from src.combat.frame_data import AttackDefinition, HitProperties, PhaseDefinition
from src.combat.knockback import KnockbackConfig
from src.entities.entity import Entity


def make_phase(
    *,
    startup: int = 1,
    active: int = 2,
    recovery: int = 1,
    size: tuple[float, float] = (30.0, 20.0),
    offset: tuple[float, float] = (20.0, 0.0),
    damage: int = 10,
    reset_targets: bool = True,
) -> PhaseDefinition:
    """Build a single phase definition with sensible defaults."""
    return PhaseDefinition(
        startup_frames=startup,
        active_frames=active,
        recovery_frames=recovery,
        hitbox_size=size,
        hitbox_offset=offset,
        hit=HitProperties(
            damage=damage,
            knockback=KnockbackConfig(power=(0.0, 0.0)),
        ),
        reset_targets=reset_targets,
    )


def make_attack(*phases: PhaseDefinition, lock_direction: bool = True) -> AttackDefinition:
    """Build an attack definition wrapping the given phases."""
    return AttackDefinition(
        phases=phases,
        cooldown=0.0,
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
    )


def entity_at(
    x: float,
    *,
    faction: str = "neutral",
    definition: AttackDefinition | None = None,
    hurtbox_inflate: tuple[float, float] = (0.0, 0.0),
) -> Entity:
    """Place an entity at ``(x, 0)`` with an optional ``test`` attack."""
    attacks = {"test": definition} if definition is not None else None
    return make_entity(
        pos=(float(x), 0.0),
        faction=faction,
        attacks=attacks,
        hurtbox_inflate=hurtbox_inflate,
    )


def activate(entity: Entity) -> None:
    """Start the ``test`` attack and advance into its active phase."""
    assert entity.combat.start_attack("test")
    entity.combat.update(1 / 60)
    entity.combat.sync_attack_box()
    assert entity.combat.attack_box is not None


def make_active_attacker(target: Entity) -> SimpleNamespace:
    """Build a lightweight active attacker whose box overlaps the target."""
    hit = HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(100.0, 0.0)),
    )
    targets_hit: set[str] = set()
    combat = SimpleNamespace(
        state=SimpleNamespace(is_active=True),
        attack_box=target.hurtbox.copy(),
        current_phase=SimpleNamespace(hit=hit),
        charge_multiplier=1.0,
        targets_hit=targets_hit,
        can_contact=lambda target_id: target_id not in targets_hit,
        record_contact=targets_hit.add,
    )
    return SimpleNamespace(
        id="attacker",
        is_dead=False,
        faction="enemy",
        hitbox=pygame.FRect(-20.0, 0.0, 10.0, 10.0),
        combat=combat,
    )


@dataclass
class SpyCombat:
    """Minimal combat component recording explicit interruptions."""

    hit_interrupts: list[bool] = field(default_factory=list)
    is_hurt: bool = False

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None:
        del duration
        self.hit_interrupts.append(interrupt)
        self.is_hurt = interrupt

    def reset(self) -> None:
        self.is_hurt = False


@dataclass
class SpyStateMachine:
    """Record forced state changes without requiring concrete game states."""

    changes: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def change_state(self, name: str, **kwargs: object) -> None:
        self.changes.append((name, kwargs))


class InputStub:
    """Constructor-only input provider used by player-based tests."""


class AttackerStub:
    def __init__(self, centerx: float = 0.0) -> None:
        self.hitbox = pygame.FRect(centerx - 5.0, 0.0, 10.0, 10.0)


__all__ = [
    "AttackerStub",
    "InputStub",
    "SpyCombat",
    "SpyStateMachine",
    "activate",
    "entity_at",
    "make_active_attacker",
    "make_attack",
    "make_entity",
    "make_phase",
]
