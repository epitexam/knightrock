"""Enemy entities configured by data with AI state machines and combat capabilities."""

import random
from collections.abc import Sequence
from typing import Protocol

import pygame
from pygame.math import Vector2
from pygame.sprite import Group

from src.platform.assets import shared_library
from src.simulation.animation.animator import AnimationSpec, Animator
from src.simulation.combat.frame_data import Height, MoveId, PhaseState, move_id
from src.simulation.entities.enemies.schema import EnemyConfig, EnemyMove
from src.simulation.entities.entity import Entity, EntitySnapshot
from src.simulation.entities.id_factory import IdFactory
from src.simulation.physics import apply_velocity_friction
from src.simulation.physics.spatial_hash import SpatialHash
from src.simulation.settings import AI, Locomotion
from src.simulation.settings import Animation as AnimationSettings
from src.simulation.settings import Clash as ClashSettings
from src.simulation.settings import Combat as CombatSettings
from src.simulation.settings import Guard as GuardSettings
from src.simulation.states.enemy_states import (
    EnemyAttackState,
    EnemyChargeState,
    EnemyChaseState,
    EnemyDizzyState,
    EnemyDoomedState,
    EnemyDownedState,
    EnemyHurtState,
    EnemyIdleState,
    EnemyKnockbackState,
    EnemyPatrolState,
    EnemyStaggerState,
    EnemyState,
    EnemyTurnState,
)
from src.simulation.states.ledge_state import LedgeState
from src.simulation.states.state_machine import StateMachine

#: The states an enemy is free in: it turns to face the player and holds its guard.
_FREE_STATES = (
    EnemyState.IDLE,
    EnemyState.PATROL,
    EnemyState.CHASE,
    EnemyState.TURN,
    EnemyState.LEDGE,
)


class PlayerReference(Protocol):
    """Protocol for player reference to enable proper typing.

    This protocol defines the minimal interface that a player reference
    must provide for enemy AI to function correctly.
    """

    hitbox: pygame.FRect


class Enemy(Entity):
    """Enemy entity configured by data instead of per-enemy boilerplate.

    This class provides a data-driven approach to enemy creation, where all
    enemy parameters are defined in EnemyConfig dataclasses. This eliminates
    the need for individual enemy subclasses that only differ in their
    configuration.

    Attributes
    ----------
    config : EnemyConfig
        Data class holding enemy parameters.
    player : PlayerReference | None
        Reference to the player entity for AI targeting.
    chase_speed : float
        Movement speed when chasing the player.
    patrol_speed : float
        Movement speed while patrolling (slow cruise).
    vision_range : float
        Distance at which the enemy can detect the player.
    attack_range : float
        Distance required to initiate an attack.
    attack_name : str | None
        Name of the attack definition loaded into the combat component.
    idle_duration : float
        Time spent in the idle state before patrolling.
    passive_friction : float
        Friction applied when the enemy has no AI.
    patrol_direction : int
        1 for right, -1 for left.
    patrol_timer : float
        Time elapsed in current patrol direction.
    patrol_interval : float
        Time before changing patrol direction.
    pushable : bool
        Whether the enemy can be pushed by attacks.
    super_armor : bool
        Whether the enemy has super armor (ignores stagger).
    """

    config: EnemyConfig
    player: PlayerReference | None
    enemy_type: str | None
    chase_speed: float
    patrol_speed: float
    vision_range: float
    attack_range: float
    attack_name: MoveId | None
    moves: tuple[EnemyMove, ...]
    idle_duration: float
    passive_friction: float
    patrol_direction: int
    patrol_timer: float
    patrol_interval: float
    pushable: bool
    super_armor: bool
    can_jump: bool
    jump_height: float
    jump_cooldown: float
    leap_speed_mult: float

    def __init__(
        self,
        pos: Sequence[float] | Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: PlayerReference | None,
        config: EnemyConfig,
        rng: random.Random | None = None,
        enemy_type: str | None = None,
        spatial_hash: SpatialHash | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize an enemy from its configuration.

        Parameters
        ----------
        pos : Sequence[float] | Vector2
            Starting top-left position.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this enemy to.
        collision_sprites : Group
            Group of sprites that block movement.
        player_reference : PlayerReference | None
            Reference to the player entity.
        config : EnemyConfig
            Data class holding enemy parameters.
        rng : random.Random | None
            Optional random number generator instance for deterministic behaviors.
        enemy_type : str | None
            Registry name of this enemy (e.g. ``"goblin"``), shown in the
            debug label card. ``None`` when built without the factory.
        spatial_hash : SpatialHash | None
            Shared collision grid covering ``collision_sprites``; see
            :class:`~src.simulation.entities.entity.Entity`.
        """
        max_health = config.max_health if config.max_health is not None else config.health

        super().__init__(
            pos=pos,
            size=config.size,
            color=config.color,
            groups=groups,
            collision_sprites=collision_sprites,
            hitbox_inflate=config.hitbox_inflate,
            hurtbox_inflate=config.hurtbox_inflate,
            hurtbox_zones=config.hurtbox_zones,
            health=config.health,
            max_health=max_health,
            faction="enemy",
            spawn_pos=pos,
            attacks=config.attacks if config.attacks else None,
            hurt_duration=CombatSettings.HURT_DURATION,
            rng=rng,
            spatial_hash=spatial_hash,
            id_factory=id_factory,
        )

        self.config = config
        self.player = player_reference
        self.enemy_type = enemy_type
        self.chase_speed = config.chase_speed
        self.patrol_speed = (
            config.patrol_speed
            if config.patrol_speed is not None
            else config.chase_speed * Locomotion.ENEMY_PATROL_SPEED_MULT
        )
        self.vision_range = config.vision_range
        self.attack_range = config.attack_range
        self.attack_name = move_id(config.attack_name) if config.attack_name else None
        if config.moves:
            self.moves = tuple(config.moves)
        elif config.attack_name:
            self.moves = (EnemyMove(config.attack_name, config.attack_range),)
        else:
            self.moves = ()
        self.idle_duration = config.idle_duration
        self.passive_friction = config.passive_friction
        self.weight = config.weight

        self.speed = self.patrol_speed
        self.floor_control = CombatSettings.ENEMY_FLOOR_CONTROL
        self.air_control = CombatSettings.ENEMY_AIR_CONTROL

        if config.reverse is None:
            self.patrol_direction = 1 if self.rng.random() > 0.5 else -1
        else:
            # Authored, so deterministic: a property written on every placement
            # is a statement about that placement, and a coin would answer it
            # with noise half the time.
            self.patrol_direction = -1 if config.reverse else 1
        self.patrol_timer = 0.0
        self.patrol_interval = config.patrol_interval

        self.pushable = config.pushable
        self.super_armor = config.super_armor
        self.otg_guard_duration = CombatSettings.ENEMY_OTG_INVULN_DURATION
        # An enemy with no AI has no state to be stunned or doomed in: it has
        # no gauge, and a blow that kills it kills it.
        self.stun_max = config.stun_max if config.has_ai else None
        self.stun_duration = config.stun_duration
        self.doomable = config.has_ai
        # The guard: held high or low while the enemy is not attacking, and
        # dropped for a while once broken.
        self.guards = config.guards and config.has_ai
        self.guard: Height | None = None
        self.guard_timer = 0.0
        self.guard_broken_timer = 0.0
        # Blockable blows taken in a row, and how long the count still holds.
        self.hit_streak = 0
        self.streak_timer = 0.0
        # Seconds left to strike back after a blocked blow, and whether the
        # attack running is that counter -- thrown behind the guard.
        self.counter_timer = 0.0
        self.countering = False

        self.can_jump = config.can_jump
        self.jump_height = config.jump_height
        self.jump_cooldown = config.jump_cooldown
        self.leap_speed_mult = config.leap_speed_mult

        # Pivot group, then sub-group. The group is the faction the enemy
        # already belongs to; a type inside that group names a sub-group in its
        # own config, which is how "all enemies take it, except the slimes" is
        # said: one line in ``settings.PROFILES`` and ``"turn_profile"`` in that
        # type's config. Leaving it None means the group, which for enemies is
        # off -- an enemy pivoting on the spot would advertise its own turn to
        # the player.
        self.turn_profile = config.turn_profile or "enemy"
        self.apply_turn_profile()

        if config.animations:
            specs = {
                name: AnimationSpec(name, directory, AnimationSettings.FRAME_DURATION, loop=True)
                for name, directory in config.animations.items()
            }
            self.animator = Animator(shared_library(), specs, default=next(iter(specs)))

        if self.player is not None:
            self.facing_right = self.player.hitbox.centerx > self.hitbox.centerx
        else:
            self.facing_right = True

        if config.has_ai:
            self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        """Create the shared melee enemy state machine."""
        self.state_machine = StateMachine(self)
        self.state_machine.add_state(EnemyState.IDLE, EnemyIdleState(self))
        self.state_machine.add_state(EnemyState.PATROL, EnemyPatrolState(self))
        self.state_machine.add_state(EnemyState.CHASE, EnemyChaseState(self))
        self.state_machine.add_state(EnemyState.TURN, EnemyTurnState(self))
        self.state_machine.add_state(EnemyState.ATTACK, EnemyAttackState(self))
        self.state_machine.add_state(EnemyState.CHARGE, EnemyChargeState(self))
        self.state_machine.add_state(EnemyState.HURT, EnemyHurtState(self))
        self.state_machine.add_state(EnemyState.KNOCKBACK, EnemyKnockbackState(self))
        self.state_machine.add_state(EnemyState.STAGGER, EnemyStaggerState(self))
        self.state_machine.add_state(EnemyState.DIZZY, EnemyDizzyState(self))
        self.state_machine.add_state(EnemyState.DOWNED, EnemyDownedState(self))
        self.state_machine.add_state(EnemyState.DOOMED, EnemyDoomedState(self))
        self.state_machine.add_state(
            EnemyState.LEDGE, LedgeState(self, exit_resolver=lambda: EnemyState.IDLE)
        )
        self.state_machine.set_initial_state(EnemyState.IDLE)
        self._setup_interrupts()

    def _setup_interrupts(self) -> None:
        """Register enemy-specific state machine interrupts."""
        super()._setup_interrupts()

    def face_player(self) -> None:
        """Orient the enemy toward the player if player exists."""
        if self.player is None or self.is_dead:
            return
        self.face_towards(self.player.hitbox.centerx)

    def turn_around(self) -> None:
        """Face away, keeping the patrol leg in sync with the new facing."""
        super().turn_around()
        self.patrol_direction *= -1

    def jump_apex(self) -> float:
        """Reachable height above the feet for the configured hop."""
        if self.jump_height <= 0.0 or self.normal_gravity <= 0.0:
            return 0.0
        return self.jump_height * self.jump_height / (2.0 * self.normal_gravity)

    def leap_air_time(self) -> float:
        """Flight seconds of the configured leap back to takeoff height."""
        if self.jump_height <= 0.0 or self.normal_gravity <= 0.0:
            return 0.0
        rise_time = self.jump_height / self.normal_gravity
        if self.fall_gravity <= 0.0:
            return rise_time
        return float(rise_time + (2.0 * self.jump_apex() / self.fall_gravity) ** 0.5)

    def jump_range(self) -> float:
        """Horizontal reach of the configured leap at sprint speed.

        Closed-form flight (rise on ``normal_gravity``, fall on
        ``fall_gravity``) times the boosted leap speed — and the leap
        glides ballistically (no air steering, see the chase state), so
        the estimate matches the flight instead of guessing.
        """
        if self.jump_height <= 0.0 or self.normal_gravity <= 0.0:
            return 0.0
        return float(self.speed * self.leap_speed_mult * self.leap_air_time())

    def _animation_name(self) -> str | None:
        """Map the current EnemyState to the config-provided animation."""
        if not self.config.animations:
            return None
        name = str(self.state_machine.current_state_name)
        return name if name in self.config.animations else None

    def _pre_update(self, delta_time: float) -> None:
        """Update facing direction before combat updates."""
        if (
            self.config.has_ai
            and self.player is not None
            and self.state_machine.current_state_name in _FREE_STATES
        ):
            self.face_player()
        self._tick_guard(delta_time)
        self._tick_counter(delta_time)

    def _tick_guard(self, delta_time: float) -> None:
        """Hold a guard while free to, and switch its height now and then."""
        if not self.guards:
            return
        if self.guard_broken_timer > 0.0:
            self.guard_broken_timer = max(0.0, self.guard_broken_timer - delta_time)
            self.guard = None
            return
        if self.state_machine.current_state_name not in _FREE_STATES:
            self.guard = None
            return
        self.guard_timer -= delta_time
        if self.guard is None or self.guard_timer <= 0.0:
            self.guard = Height.HIGH if self.rng.random() < 0.5 else Height.LOW
            self.guard_timer = self.rng.uniform(GuardSettings.SWITCH_MIN, GuardSettings.SWITCH_MAX)

    def guards_against(self, height: Height, unblockable: bool, source_center_x: float) -> bool:
        """Whether the guard stops a hit at ``height`` from that side.

        A low guard stops a low hit, a high guard everything else, and only
        from the front. An unblockable hit goes through and breaks the guard.

        With no guard at that height, a blockable blow from the front still
        counts: the ``Guard.BLOCK_AFTER_HITS``-th in a row is braced against
        -- the enemy shakes off the stagger, raises its guard at the blow's
        height and stops it -- so the same slash mashed is stopped mid-combo.
        A stopped blow is an opening: the enemy strikes back if it can.
        """
        if not self._faces(source_center_x):
            return False
        same_height = self.guard is not None and (height is Height.LOW) == (
            self.guard is Height.LOW
        )
        if unblockable:
            if same_height:
                self.guard = None
                self.guard_broken_timer = GuardSettings.BROKEN_TIME
            return False
        if same_height or self.counter_covered:
            self.counter_timer = GuardSettings.COUNTER_WINDOW
            return True
        if not self.guards or self.guard_broken_timer > 0.0:
            return False
        self.hit_streak += 1
        self.streak_timer = GuardSettings.STREAK_WINDOW
        if self.hit_streak < GuardSettings.BLOCK_AFTER_HITS:
            return False
        self._brace(height)
        return True

    def lose_lock(self) -> None:
        """A lost blade lock throws the enemy off balance and breaks its guard."""
        super().lose_lock()
        self.guard = None
        self.guard_broken_timer = ClashSettings.WIN_OPEN
        self.hit_streak = 0

    @property
    def counter_covered(self) -> bool:
        """Whether the counter in progress still shields the enemy: not in its recovery.

        The recovery of a counter is the opening the player punishes.
        """
        return self.countering and self.combat.state.sub_state is not PhaseState.RECOVERY

    def _brace(self, height: Height) -> None:
        """Shake off the stagger and raise the guard at ``height``, against the blow."""
        self.hit_streak = 0
        self.stagger_timer = 0.0
        self.combat.cancel_attack()
        self.combat.reset_hurt_state()
        self.state_machine.change_state(EnemyState.IDLE, force=True)
        self.guard = Height.LOW if height is Height.LOW else Height.HIGH
        self.guard_timer = GuardSettings.SWITCH_MAX
        self.counter_timer = GuardSettings.COUNTER_WINDOW

    def _tick_counter(self, delta_time: float) -> None:
        """Let the streak lapse, and strike back after a block if the player is in reach.

        The counter is thrown behind the guard: until its recovery, a blockable
        blow from the front is stopped, so mashing cannot interrupt it; its
        recovery is the opening.
        """
        if self.countering and self.state_machine.current_state_name != EnemyState.ATTACK:
            self.countering = False
        if self.streak_timer > 0.0:
            self.streak_timer = max(0.0, self.streak_timer - delta_time)
            if self.streak_timer == 0.0:
                self.hit_streak = 0
        if self.counter_timer <= 0.0:
            return
        self.counter_timer = max(0.0, self.counter_timer - delta_time)
        if self.state_machine.current_state_name not in _FREE_STATES:
            return
        move = self.plan_move()
        if move is None or not self.is_player_in_range(self.move_range(move)):
            return
        if not self.attack_slot_free():
            return
        self.counter_timer = 0.0
        self.countering = True
        self.state_machine.change_state(EnemyState.ATTACK, move=move)

    def _faces(self, source_center_x: float) -> bool:
        if source_center_x >= self.hitbox.centerx:
            return self.facing_right
        return not self.facing_right

    def save_state(self) -> EntitySnapshot:
        snapshot = super().save_state()
        snapshot.extra |= {
            "guard": None if self.guard is None else self.guard.value,
            "guard_timer": self.guard_timer,
            "guard_broken_timer": self.guard_broken_timer,
            "hit_streak": self.hit_streak,
            "streak_timer": self.streak_timer,
            "counter_timer": self.counter_timer,
            "countering": self.countering,
        }
        return snapshot

    def load_state(self, snapshot: EntitySnapshot) -> None:
        super().load_state(snapshot)
        extra = snapshot.extra
        guard = extra.get("guard")
        self.guard = None if guard is None else Height(guard)
        self.guard_timer = float(extra.get("guard_timer", 0.0))
        self.guard_broken_timer = float(extra.get("guard_broken_timer", 0.0))
        self.hit_streak = int(extra.get("hit_streak", 0))
        self.streak_timer = float(extra.get("streak_timer", 0.0))
        self.counter_timer = float(extra.get("counter_timer", 0.0))
        self.countering = bool(extra.get("countering", False))

    def _update_state_machine(self, delta_time: float) -> None:
        """Update AI state machine or apply passive friction if AI is disabled."""
        if self.config.has_ai:
            self.state_machine.update(delta_time)
        elif self.on_surface["floor"]:
            # No AI means no KnockbackState: passive friction is the only
            # thing stopping a launched dummy, so it must use the configured
            # rate directly (not scaled by dt a second time) and snap to
            # zero instead of sliding forever on an asymptote.
            apply_velocity_friction(self, self.passive_friction, delta_time)

    def can_see_player(self) -> bool:
        """Check if the player is within vision range.

        Returns
        -------
        bool
            True if the player is close enough to be detected.
        """
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < self.vision_range
        )

    def is_player_in_range(self, reach: float | None = None) -> bool:
        """Whether the player is closer than ``reach``, or the attack range.

        Returns
        -------
        bool
            True if the player is close enough to be attacked.
        """
        if self.player is None:
            return False
        return pygame.math.Vector2(self.hitbox.center).distance_to(
            pygame.math.Vector2(self.player.hitbox.center)
        ) < (self.attack_range if reach is None else reach)

    def plan_move(self) -> str | None:
        """Pick the next attack to close in for, weighted by the type's moves.

        A type with one move draws nothing from its random stream, so its
        behaviour is what it was before it could choose.
        """
        if not self.moves:
            return None
        if len(self.moves) == 1:
            return self.moves[0].name
        roll = self.rng.random() * sum(move.weight for move in self.moves)
        for move in self.moves:
            roll -= move.weight
            if roll < 0.0:
                return move.name
        return self.moves[-1].name

    def move_range(self, name: str | None) -> float:
        """How close the player must be for the move called ``name``."""
        for move in self.moves:
            if move.name == name:
                return move.range
        return self.attack_range

    def attack_slot_free(self) -> bool:
        """Whether fewer than ``AI.MAX_ATTACKERS`` others are attacking the same player.

        Counted from the roster's states each time it is asked, so nothing is
        held between ticks and a rollback has nothing to restore.
        """
        busy = 0
        for other in self.roster:
            if other is self or not isinstance(other, Enemy) or other.player is not self.player:
                continue
            if other.state_machine.current_state_name in (EnemyState.ATTACK, EnemyState.CHARGE):
                busy += 1
                if busy >= AI.MAX_ATTACKERS:
                    return False
        return True
