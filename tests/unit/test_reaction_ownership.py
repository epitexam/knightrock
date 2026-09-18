"""Reaction ownership: narrow interface, no duplicated state."""

import inspect
from types import SimpleNamespace

import pygame
from pygame.math import Vector2

from src.combat.knockback import KnockbackConfig
from src.entities.components.reaction import (
    ReactionComponent,
    ReactionOwner,
)


def _narrow_owner(**overrides) -> SimpleNamespace:
    """Narrow double without a full Entity."""
    base = {
        "velocity": Vector2(0, 0),
        "hitbox": pygame.FRect(0, 0, 40, 48),
        "facing_right": True,
        "is_dead": False,
        "stagger_timer": 0.0,
        "super_armor": False,
        "super_armor_count": 0,
        "combat": SimpleNamespace(
            is_hurt=False,
            hurt_timer=0.0,
            on_hit=lambda duration=None, interrupt=True: setattr(base_combat, "is_hurt", interrupt),
            reset_hurt_state=lambda: (
                setattr(base_combat, "is_hurt", False),
                setattr(base_combat, "hurt_timer", 0.0),
            ),
        ),
        "state_machine": SimpleNamespace(
            changes=[],
            change_state=lambda name, force=False, **kw: changes.append((name, kw)),
        ),
    }
    base_combat = base["combat"]
    changes = base["state_machine"].changes
    base.update(overrides)
    return SimpleNamespace(**base)


def test_no_hasattr_no_direct_hurt_write() -> None:
    import src.entities.components.reaction as module

    text = inspect.getsource(module)
    assert "hasattr(" not in text
    assert "owner.combat.is_hurt = False" not in text
    assert text.count("reset_hurt_state") >= 2


def test_narrow_owner_satisfies_protocol() -> None:
    assert isinstance(_narrow_owner(), ReactionOwner)


def test_heavy_knockback_clears_hurt_state_and_timer() -> None:
    owner = _narrow_owner()
    owner.combat.is_hurt = False
    owner.combat.hurt_timer = 0.0
    component = ReactionComponent(owner)

    launched = component.handle_heavy_knockback(
        KnockbackConfig(power=(0.0, -800.0)), source_center_x=None
    )

    assert launched is True
    assert owner.combat.is_hurt is False
    assert owner.combat.hurt_timer == 0.0
    assert owner.state_machine.changes[0][0] == "knockback"


def test_stagger_clears_hurt_and_sets_timer() -> None:
    owner = _narrow_owner()
    owner.combat.is_hurt = True
    component = ReactionComponent(owner)

    component.stagger(0.3)

    assert owner.stagger_timer == 0.3
    assert owner.combat.is_hurt is False


def test_block_super_armor_launch_stagger_preserved() -> None:
    owner = _narrow_owner(super_armor=True)
    component = ReactionComponent(owner)
    component.stagger(0.2)
    assert owner.stagger_timer == 0.0
    component.stagger(0.2)
    assert owner.stagger_timer == 0.0
    component.stagger(0.2)
    assert owner.stagger_timer == 0.2
    assert owner.super_armor is False
