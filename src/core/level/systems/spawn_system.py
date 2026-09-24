"""SpawnSystem: debug-spawn head of the level pipeline (audit F1.2, Phase 3 #2).

Runs first each tick, before the platforms move, so a runtime-spawned enemy
joins the world before any stage reads it.  It owns the debug-spawn
cooldowns and the spawn logic directly (moved here from the former
``DebugController``), so the level no longer drives anything itself.

Phase 5 test bench: ``DEBUG_ATTACKS`` forces the showcase attacks (twin
blades, animated sweep, launcher, OTG slam) on the player, ``DEBUG_SHOTS``
fires pooled projectiles, and ``DEBUG_JUGGLE_KEY`` pops an airborne dummy
to juggle.  The per-action helpers are plain methods so tests drive them
without polling hardware keys.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import pygame

from src.core.settings import Respawn
from src.core.sprite_groups import SpriteGroups
from src.entities.enemies.factory import create_enemy
from src.entities.projectile import (
    FIREBOLT_CONFIG,
    PIERCING_BOLT_CONFIG,
    Projectile,
    ProjectileConfig,
)
from src.physics.spatial_hash import SpatialHash

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.core.level.systems.projectile_system import ProjectileSystem
    from src.entities.player import Player

DEBUG_SPAWNS = {
    pygame.K_g: "goblin",
    pygame.K_p: "slime",
    pygame.K_t: "dummy",
}

#: Phase 5 showcase attacks forced on the player (touch nothing else).
DEBUG_ATTACKS = {
    pygame.K_1: "twin_fangs",
    pygame.K_2: "sweeping_arc",
    pygame.K_3: "sky_launcher",
    pygame.K_4: "otg_slam",
    pygame.K_5: "p5_shapes",
    pygame.K_6: "circle_burst",
}

#: Phase 5 projectile presets fired from the player.
DEBUG_SHOTS: dict[int, ProjectileConfig] = {
    pygame.K_v: FIREBOLT_CONFIG,
    pygame.K_b: PIERCING_BOLT_CONFIG,
}

#: Spawns an airborne dummy in front of the player to juggle.
DEBUG_JUGGLE_KEY = pygame.K_c

#: Horizontal speed of debug projectiles (px/s).
DEBUG_SHOT_SPEED = 700.0

__all__ = [
    "DEBUG_ATTACKS",
    "DEBUG_JUGGLE_KEY",
    "DEBUG_SHOTS",
    "DEBUG_SHOT_SPEED",
    "DEBUG_SPAWNS",
    "SpawnSystem",
]


class SpawnSystem:
    """Tick the debug spawner (cooldowns decay, key-triggered spawns)."""

    def __init__(
        self,
        groups: SpriteGroups,
        spatial_hash: SpatialHash | None = None,
        projectile_system: ProjectileSystem | None = None,
    ) -> None:
        self.groups = groups
        self.spatial_hash = spatial_hash
        self.projectile_system = projectile_system
        self.spawn_cooldowns = dict.fromkeys(DEBUG_SPAWNS.values(), 0.0)
        self.debug_cooldowns: dict[str, float] = {}
        #: Attack name looped by the debug replay key, ``None`` when off.
        self.attack_replay: str | None = None
        self._last_attack: str | None = None

    @property
    def spawn_cooldown_max(self) -> float:
        """Longest remaining debug-spawn cooldown (audit F5.2)."""
        return max([*self.spawn_cooldowns.values(), *self.debug_cooldowns.values(), 0.0])

    def process(self, delta_time: float, player: Player) -> None:
        """Decay cooldowns, then spawn enemies for the debug keys held."""
        self._decay_cooldowns(delta_time)
        keys = pygame.key.get_pressed()
        self._spawn_enemies(keys, player)
        self._trigger_attacks(keys, player)
        self.tick_attack_replay(player)
        self._fire_shots(keys, player)
        self._pop_juggle(keys, player)

    def _decay_cooldowns(self, delta_time: float) -> None:
        for enemy_name, cooldown in self.spawn_cooldowns.items():
            if cooldown > 0:
                self.spawn_cooldowns[enemy_name] = cooldown - delta_time
        for action, cooldown in self.debug_cooldowns.items():
            if cooldown > 0:
                self.debug_cooldowns[action] = cooldown - delta_time

    def _spawn_enemies(self, keys: Sequence[bool], player: Player) -> None:
        for key, enemy_name in DEBUG_SPAWNS.items():
            if keys[key] and self.spawn_cooldowns[enemy_name] <= 0:
                self._spawn_enemy(enemy_name, player)

    def _trigger_attacks(self, keys: Sequence[bool], player: Player) -> None:
        for key, attack_name in DEBUG_ATTACKS.items():
            if (
                keys[key]
                and self._debug_ready(attack_name)
                and self.trigger_test_attack(player, attack_name)
            ):
                self._arm_debug_cooldown(attack_name)
                self._last_attack = attack_name

    def _fire_shots(self, keys: Sequence[bool], player: Player) -> None:
        for key, config in DEBUG_SHOTS.items():
            action = f"shot_{id(config)}"
            if (
                keys[key]
                and self._debug_ready(action)
                and self.fire_test_projectile(player, config) is not None
            ):
                self._arm_debug_cooldown(action)

    def _pop_juggle(self, keys: Sequence[bool], player: Player) -> None:
        if (
            keys[DEBUG_JUGGLE_KEY]
            and self._debug_ready("juggle_dummy")
            and self.spawn_juggle_dummy(player) is not None
        ):
            self._arm_debug_cooldown("juggle_dummy")

    def trigger_test_attack(self, player: Player, attack_name: str) -> bool:
        """Force a showcase attack on the player (Phase 5 test bench)."""
        start = getattr(getattr(player, "combat", None), "start_attack", None)
        if not callable(start):
            return False
        return bool(start(attack_name))

    def toggle_attack_replay(self, attack_name: str | None = None) -> str | None:
        """Toggle looped replay of ``attack_name``; return the active name (``None`` = off)."""
        if self.attack_replay is not None:
            self.attack_replay = None
            return None
        self.attack_replay = attack_name or self._last_attack or next(iter(DEBUG_ATTACKS.values()))
        return self.attack_replay

    def selected_attack(self) -> str | None:
        """Return the attack currently selected for replay or export."""
        return self.attack_replay or self._last_attack

    def tick_attack_replay(self, player: Player) -> None:
        """Restart the looped attack once idle and its cooldown is ready."""
        if self.attack_replay is None:
            return
        combat = getattr(player, "combat", None)
        if combat is None or getattr(combat, "is_attacking", False):
            return
        if not self._debug_ready(self.attack_replay):
            return
        if self.trigger_test_attack(player, self.attack_replay):
            self._arm_debug_cooldown(self.attack_replay)

    def fire_test_projectile(
        self, player: Player, config: ProjectileConfig = FIREBOLT_CONFIG
    ) -> Projectile | None:
        """Fire a pooled projectile from the player toward its facing."""
        if self.projectile_system is None:
            return None
        direction = 1.0 if getattr(player, "facing_right", True) else -1.0
        hitbox = getattr(player, "hitbox", None)
        if hitbox is None:
            return None
        return self.projectile_system.spawn(
            config,
            pos=(hitbox.centerx, hitbox.centery),
            velocity=(DEBUG_SHOT_SPEED * direction, -50.0),
            faction=getattr(player, "faction", "player"),
        )

    def spawn_juggle_dummy(self, player: Player) -> Any | None:
        """Pop an airborne dummy ahead of the player to juggle (Phase 5 #4)."""
        hitbox = getattr(player, "hitbox", None)
        if hitbox is None:
            return None
        offset_x = 140 if getattr(player, "facing_right", True) else -140
        try:
            enemy = create_enemy(
                "dummy",
                pos=(hitbox.centerx + offset_x, hitbox.top - 150.0),
                groups=(self.groups.all_sprites,),
                collision_sprites=self.groups.collision_sprites,
                player_reference=player,  # type: ignore[arg-type]
            )
        except KeyError:
            return None
        self.groups.combat_sprites.add(enemy)
        self.groups.entity_sprites.add(enemy)
        if self.spatial_hash is not None:
            enemy.spatial_hash = self.spatial_hash
        enemy.velocity.y = -550.0
        enemy.on_surface["floor"] = False
        return enemy

    def _debug_ready(self, action: str) -> bool:
        return self.debug_cooldowns.get(action, 0.0) <= 0

    def _arm_debug_cooldown(self, action: str) -> None:
        self.debug_cooldowns[action] = Respawn.DEBUG_SPAWN_COOLDOWN_S

    def _spawn_enemy(self, enemy_name: str, player: Player) -> None:
        offset_x = 100 if player.facing_right else -100
        enemy = create_enemy(
            enemy_name,
            pos=(player.hitbox.centerx + offset_x, player.hitbox.top),
            groups=(self.groups.all_sprites,),
            collision_sprites=self.groups.collision_sprites,
            player_reference=player,
        )
        self.groups.combat_sprites.add(enemy)
        self.groups.entity_sprites.add(enemy)
        # Runtime-spawned enemies must join the collision grid too (PERF-01).
        if self.spatial_hash is not None:
            enemy.spatial_hash = self.spatial_hash
        self.spawn_cooldowns[enemy_name] = Respawn.DEBUG_SPAWN_COOLDOWN_S
