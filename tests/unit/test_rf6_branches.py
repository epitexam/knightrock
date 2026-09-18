"""Spawner cooldowns and attack priority branches."""

import pygame

from src.core.level.systems.spawn_system import SpawnSystem
from src.core.sprite_groups import SpriteGroups


def _system() -> SpawnSystem:
    return SpawnSystem(SpriteGroups())


def test_decay_cooldowns_ticks_both_dicts() -> None:
    system = _system()
    system.spawn_cooldowns["goblin"] = 0.5
    system.debug_cooldowns["twin_fangs"] = 0.3
    system._decay_cooldowns(0.2)
    assert (
        system.spawn_cooldowns["goblin"] == pygame.math.Vector2(0.3, 0).x
        or abs(system.spawn_cooldowns["goblin"] - 0.3) < 1e-9
    )
    assert abs(system.debug_cooldowns["twin_fangs"] - 0.1) < 1e-9
    system._decay_cooldowns(1.0)
    assert system.spawn_cooldowns["goblin"] < 0
    assert system.debug_cooldowns["twin_fangs"] < 0


def test_debug_ready_and_arm_roundtrip() -> None:
    system = _system()
    assert system._debug_ready("twin_fangs") is True
    system._arm_debug_cooldown("twin_fangs")
    assert system._debug_ready("twin_fangs") is False


def test_attack_priority_special_first() -> None:
    import inspect

    from src.entities.player_input import PlayerInputHandler

    text = inspect.getsource(PlayerInputHandler._handle_attack_request)
    special = text.index("special_attack")
    light = text.index("light_attack")
    heavy = text.index("heavy_attack")
    uppercut = text.index("uppercut")
    dash = text.index("dash_attack")
    assert special < light < heavy < uppercut < dash
