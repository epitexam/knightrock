"""The player: movement, dodge, guard, the blade and the body, and what they earn."""

from collections.abc import Iterable, Sequence
from typing import Any

import pygame
from pygame.sprite import Group

from src.platform.assets import shared_library
from src.platform.input.input_manager import InputManager
from src.shared.input_actions import InputAction
from src.simulation.animation.animator import Animator
from src.simulation.combat.combat_component import CombatComponent
from src.simulation.combat.combatant_protocol import Combatant, DamageResult, Finish
from src.simulation.combat.frame_data import Height, MoveId, Stance
from src.simulation.combat.knockback import KnockbackConfig
from src.simulation.combat.refusal import Refusal
from src.simulation.entities.attack_moves import DEATH_BLOW, SHOTS, SLASHES, THROW
from src.simulation.entities.entity import Entity, EntitySnapshot
from src.simulation.entities.id_factory import IdFactory
from src.simulation.entities.player_animation import PLAYER_ANIMATIONS
from src.simulation.entities.player_config import PlayerConfig
from src.simulation.entities.player_controllers import DashController, JumpController
from src.simulation.entities.player_input import PlayerInputHandler
from src.simulation.entities.player_kit import (
    Battery,
    Direction,
    FuryGauge,
    Power,
    PromptController,
    PromptKind,
    PromptOutcome,
    SlotMachine,
)
from src.simulation.physics import resolve_jump
from src.simulation.physics.spatial_hash import SpatialHash
from src.simulation.settings import Battery as BatterySettings
from src.simulation.settings import Clash as ClashSettings
from src.simulation.settings import Combat as CombatSettings
from src.simulation.settings import Fury as FurySettings
from src.simulation.settings import Guard as GuardSettings
from src.simulation.settings import Physics, Rush
from src.simulation.settings import Slot as SlotSettings
from src.simulation.settings import Throw as ThrowSettings
from src.simulation.states.player_states import (
    PlayerState,
    configure_player_state_machine,
    dash_cancel_open,
)


class Player(Entity):
    """The playable fighter.

    Two attack buttons, each thrown high or low: the slash, which spends the
    blade's battery, and the beat -- punches and kicks -- which breaks guards
    and fills the stun gauge. A stunned foe is thrown; a foe a slash would kill
    is left doomed, and a direction given in time lands the death blow, which
    spins the slot machine. The guard is held; Down added to it recharges the
    battery; a dodge at the last moment slows the world (the dark step). Fury,
    filled by hitting without being hit, speeds the slashes up and, full,
    opens the dark side.
    """

    input_manager: InputManager
    speed: float
    floor_control: float
    air_control: float

    #: Always a real component: the player is built with its attack table.
    combat: CombatComponent

    jump: JumpController
    dash: DashController
    battery: Battery
    fury: FuryGauge
    slot: SlotMachine
    prompt: PromptController
    input_handler: PlayerInputHandler

    #: The player's attack poses follow startup/active/recovery frame data.
    #: Enemies keep wall-clock clips: their art is authored per state name,
    #: not as a three-pose swing.
    _phase_driven_attack_art = True

    moving_platforms: Iterable[Any]

    left_held: bool
    right_held: bool

    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
        input_manager: InputManager,
        config: PlayerConfig | None = None,
        spatial_hash: SpatialHash | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialise the player.

        Parameters
        ----------
        pos : tuple[float, float] | pygame.math.Vector2
            Starting position.
        groups : Group | Sequence[Group]
            Sprite groups to add to.
        collision_sprites : Group
            Collision group.
        moving_platforms : Iterable[Any]
            Platforms that can carry the player.
        input_manager : InputManager
            Input source.
        config : PlayerConfig | None
            The player's configuration; the shipped ``player.json`` when not
            given, never a copy kept in code (audit C4).
        spatial_hash : SpatialHash | None
            Shared collision grid covering ``collision_sprites``; see
            :class:`~src.simulation.entities.entity.Entity`.
        """
        if config is None:
            # Local: the data layer imports the player config from this package.
            from src.simulation.data.provider import shipped_gameplay_data

            config = shipped_gameplay_data().player

        attacks = None
        if config.attacks:
            attacks = dict(config.attacks)
        else:
            # No config carried attacks: take the shipped table. Imported here
            # rather than at module scope for the same reason as
            # ``player_config._default_attacks`` -- reading the data file during
            # import would run the loader before the classes it imports exist.
            from src.simulation.combat.attack_data import PLAYER_ATTACKS

            attacks = dict(PLAYER_ATTACKS)

        super().__init__(
            pos,
            config.size,
            config.color,
            groups,
            collision_sprites,
            hitbox_inflate=config.hitbox_inflate,
            hurtbox_inflate=config.hurtbox_inflate,
            hurtbox_zones=config.hurtbox_zones,
            health=config.health,
            max_health=config.max_health,
            faction=config.faction,
            spawn_pos=pos,
            attacks=attacks,
            hurt_duration=config.hurt_duration,
            invincibility_duration=config.invincibility_duration,
            spatial_hash=spatial_hash,
            id_factory=id_factory,
        )

        self.speed = config.speed
        self._run_speed = config.speed
        self.floor_control = config.floor_control
        self.air_control = config.air_control
        # The pivot is per fighter and per group, so this one line is the whole
        # difference between a fighter who turns around and one who changes
        # direction. Enemies keep the "enemy" profile, which inherits it off.
        self.turn_profile = "player"
        self.apply_turn_profile()

        self.jump = JumpController(config)
        # The jump controller is also the lock that damps the run after a wall
        # jump; apply_horizontal_movement reads it from here.
        self.wall_jump_lock = self.jump
        self.dash = DashController(config, original_hitbox_width=self.hitbox.width)
        self.battery = Battery()
        self.fury = FuryGauge()
        self.slot = SlotMachine()
        self.prompt = PromptController()
        #: Seconds of slowed world left after a dark step, on the player's clock.
        self.rush_timer = 0.0
        #: Seconds left for the dodge in progress to become a dark step.
        self.dodge_window = 0.0

        self.moving_platforms = moving_platforms

        self.left_held = False
        self.right_held = False
        self.down_held = False
        self.guard_held = False
        #: Set by the dash state on the tick a dash starts; the gameplay loop
        #: reads it for the screen shake and clears it the same tick.
        self.dash_started_this_frame = False

        self.input_manager = input_manager
        self.input_handler = PlayerInputHandler(self)

        self.animator = Animator(shared_library(), PLAYER_ANIMATIONS, default="idle")
        self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        configure_player_state_machine(self)
        self._setup_interrupts()

    def _setup_interrupts(self) -> None:
        super()._setup_interrupts()

    # -- what the player is doing --------------------------------------------

    @property
    def is_guarding(self) -> bool:
        """Whether the guard is up."""
        return self.state_machine.current_state_name == PlayerState.GUARD

    @property
    def low_stance(self) -> bool:
        """Whether a press now is thrown low: Down held on the floor."""
        return bool(self.down_held) and bool(self.on_surface.get("floor", False))

    @property
    def is_invincible(self) -> bool:
        """Untouchable in the states that say so, and for the whole dark side."""
        return super().is_invincible or self.fury.in_dark

    @property
    def world_time_scale(self) -> float:
        """The clock of everything but the player.

        A prompt freezes the fight around the player, a dark step slows it,
        and so does the stasis power.
        """
        if self.prompt.active:
            return self.prompt.time_scale
        if self.rush_timer > 0.0:
            return Rush.TIME_SCALE
        if self.slot.active(Power.STASIS):
            return SlotSettings.STASIS_TIME_SCALE
        return 1.0

    @property
    def finish(self) -> Finish:
        """Every blow kills on the dark side and under stasis or blitz; else a kill dooms."""
        if self.fury.in_dark or self.slot.active(Power.STASIS) or self.slot.active(Power.BLITZ):
            return Finish.KILL
        return Finish.DOOM

    @property
    def attack_speed(self) -> float:
        """How fast the player's attacks run: the fastest of what speeds them up."""
        speed = self.fury.speed
        if self.rush_timer > 0.0:
            speed = max(speed, Rush.ATTACK_SPEED)
        if self.fury.in_dark:
            speed = max(speed, FurySettings.DARK_ATTACK_SPEED)
        if self.slot.active(Power.BLITZ):
            speed = max(speed, SlotSettings.BLITZ_ATTACK_SPEED)
        return speed

    def may_attack_now(self) -> bool:
        """Whether an attack press is worth reading at all this tick.

        Posture, cooldown, cancellation and the reaction states are answered by
        ``CombatComponent.start_attack``. What is left is whether the fighter
        is still committed to a dash.
        """
        if self.state_machine.current_state_name == PlayerState.DASH:
            return dash_cancel_open(self)
        return True

    def is_wall_sliding(self) -> bool:
        """Return True when sliding down a wall."""
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"] and (on_left_wall or on_right_wall) and self.velocity.y > 0
        )

    @property
    def stance(self) -> Stance:
        """The posture the fighter is in: ``WALL``, then ``AIR``, then ``GROUND``."""
        if self.is_wall_sliding():
            return Stance.WALL
        if not self.on_surface["floor"]:
            return Stance.AIR
        return Stance.GROUND

    def _on_floor_contact(self) -> None:
        """Reset midair and wall jumps when landing."""
        self.jump.restore_ground_jumps()

    def _on_wall_contact(self) -> None:
        """Reset midair jumps when touching a wall."""
        self.jump.restore_midair_jumps()

    # -- the clock -------------------------------------------------------------

    def update_timers(self, delta_time: float) -> None:
        self.jump.update(delta_time, self.on_surface["floor"])
        self.dash.update(delta_time)
        self.fury.update(delta_time)
        self.slot.update(delta_time)
        if self.combat.charging.is_charging:
            self.battery.spend(BatterySettings.CHARGE_COST_PER_S * delta_time)
        self.rush_timer = max(0.0, self.rush_timer - delta_time)
        if self.dodge_window > 0.0:
            self.dodge_window -= delta_time
            if self.dodge_window <= 0.0:
                self._close_dodge_window()
        kind = self.prompt.kind
        outcome = self.prompt.update(delta_time)
        if kind is not None and outcome is not None:
            self._settle_prompt(kind, outcome)

    def open_dodge_window(self) -> None:
        """A dodge begins: for ``Rush.WINDOW``, a hit reaching it here is a dark step."""
        self.dodge_window = Rush.WINDOW
        self.dodge_ghost = self.hurtbox.copy()

    def _close_dodge_window(self) -> None:
        self.dodge_window = 0.0
        self.dodge_ghost = None

    def _apply_momentum(self) -> None:
        """Hand the attack speed to the attack clock; a dark side keeps the dash full."""
        self._sync_speeds()
        if self.fury.in_dark:
            self.dash.refill()

    def _sync_speeds(self) -> None:
        """Derive the attack clock and the run speed. Neither is stored."""
        self.combat.attack_speed = self.attack_speed
        mult = 1.0
        if self.fury.in_dark:
            mult = max(mult, FurySettings.DARK_MOVE_MULT)
        if self.slot.active(Power.BLITZ):
            mult = max(mult, SlotSettings.BLITZ_MOVE_MULT)
        self.speed = self._run_speed * mult

    # -- attacking -------------------------------------------------------------

    def start_move(self, move: MoveId) -> Refusal:
        """Start ``move``, paying its battery: a slash on an empty one is weak.

        Paid only once the move has started: a buffered press is retried every
        tick until a cancel window opens, and the refusals cost nothing. A dark
        step makes the slashes free; cleave makes them harder.
        """
        slash = move in SLASHES
        shot = move in SHOTS
        if shot and self.battery.is_empty:
            return Refusal.BUSY
        power = 1.0
        if slash:
            if self.battery.is_empty and self.rush_timer <= 0.0:
                power = BatterySettings.EMPTY_POWER
            if self.slot.active(Power.CLEAVE):
                power *= SlotSettings.CLEAVE_MULT
        refusal = self.combat.start_attack(move, power)
        if refusal is Refusal.NONE and slash and self.rush_timer <= 0.0:
            self.battery.spend(BatterySettings.SLASH_COST)
        if refusal is Refusal.NONE and shot and self.rush_timer <= 0.0:
            self.battery.spend(BatterySettings.SHOT_COST)
        return refusal

    def _foe_in_front(self, reach: float, wanted: str) -> Entity | None:
        """The nearest living foe within ``reach`` in front, in the state ``wanted``."""
        best: Entity | None = None
        best_gap = reach
        for other in self.roster:
            if other is self or other.is_dead or other.faction == self.faction:
                continue
            if other.state_machine.current_state_name != wanted:
                continue
            if other.hitbox.bottom < self.hitbox.top or other.hitbox.top > self.hitbox.bottom:
                continue
            dx = other.hitbox.centerx - self.hitbox.centerx
            if (dx >= 0.0) != self.facing_right:
                continue
            gap = abs(dx) - (other.hitbox.width + self.hitbox.width) / 2
            if gap <= best_gap:
                best, best_gap = other, gap
        return best

    def downed_in_reach(self) -> Entity | None:
        """A foe lying on the ground in front, close enough to be stabbed."""
        return self._foe_in_front(ThrowSettings.RANGE, "downed")

    def try_grab(self) -> bool:
        """Grab a stunned foe standing in front, on the ground: the throw's prompt opens.

        The grab cuts short whatever the fighter was swinging -- the beat that
        stunned the foe is usually still in its recovery -- but never a throw
        or a death blow being played out.
        """
        if self.prompt.active or self.stance is not Stance.GROUND:
            return False
        running = self.combat.current_attack_def
        if running is not None and running.invincible:
            return False
        target = self._foe_in_front(ThrowSettings.RANGE, "dizzy")
        # A foe stunned in the air is juggled, not grabbed: the slam is thrown
        # along the floor and would pass under it.
        if target is None or not target.on_surface.get("floor", False):
            return False
        self.combat.cancel_attack()
        # Held: whatever was carrying it -- the blow that stunned it -- stops.
        target.velocity.update(0.0, 0.0)
        self.prompt.open(PromptKind.THROW, target.id, self.rng)
        return True

    def answer_prompt(self, direction: Direction) -> None:
        kind = self.prompt.kind
        outcome = self.prompt.give(direction)
        if kind is not None and outcome is not None:
            self._settle_prompt(kind, outcome)

    def mash_prompt(self) -> None:
        kind = self.prompt.kind
        outcome = self.prompt.press()
        if kind is not None and outcome is not None:
            self._settle_prompt(kind, outcome)

    def _prompt_target(self) -> Entity | None:
        for other in self.roster:
            if other.id == self.prompt.target_id and not other.is_dead:
                return other
        return None

    def _settle_prompt(self, kind: PromptKind, outcome: PromptOutcome) -> None:
        """Play out what an answered prompt earned, or what a failed one costs."""
        target = self._prompt_target()
        success = outcome is PromptOutcome.SUCCESS
        if kind is PromptKind.DEATH_BLOW:
            if success and target is not None:
                self._strike_at(target, DEATH_BLOW)
                self.fury.gain(FurySettings.DEATH_BLOW)
                self.slot.spin(self.rng)
            elif target is not None:
                target.recover_from_doom()
        elif kind is PromptKind.THROW:
            if success and target is not None:
                self._strike_at(target, THROW)
                self.fury.gain(FurySettings.THROW)
            elif not success:
                self.stagger(ThrowSettings.FAIL_STAGGER)
        elif success:
            if target is not None:
                target.lose_lock()
            self.fury.gain(FurySettings.PER_HIT)
        else:
            self.receive_damage(ClashSettings.LOSS_DAMAGE, None, None, interrupt=False)
            self.stagger(ClashSettings.LOSS_STAGGER)

    def _strike_at(self, target: Entity, move: MoveId) -> None:
        """Turn to ``target``, step up to it, and play ``move`` on it."""
        self.facing_right = target.hitbox.centerx >= self.hitbox.centerx
        side = -1.0 if self.facing_right else 1.0
        self.hitbox.centerx = target.hitbox.centerx + side * (
            (target.hitbox.width + self.hitbox.width) / 2 + 2.0
        )
        self.sync_rects()
        self.combat.cancel_attack()
        self.combat.start_attack(move)

    # -- what the player's blows earn ------------------------------------------

    def on_hit_confirmed(
        self, target: Combatant, combo_advanced: bool, result: DamageResult
    ) -> None:
        """A hit landed: fury, the dash charges, and the death blow's prompt.

        A blow that leaves its target doomed opens the prompt for the death
        blow, unless one is already up. A hit landed out of a dash gives the
        dash back, and every ``COMBO_DASH_REFILL_HITS`` hits of one combo give
        a charge back.
        """
        self.fury.gain(FurySettings.PER_HIT if combo_advanced else 0.0)
        if result.doomed and not self.prompt.active:
            # The input handler short-circuits while a prompt is up, so a press
            # buffered just before it would otherwise survive the whole prompt
            # and fire as a ghost attack when it closes.
            self.input_handler.clear_buffer()
            self.prompt.open(PromptKind.DEATH_BLOW, target.id, self.rng)
        dash = self.dash
        if dash.charges >= dash.max_charges:
            return
        refresh = (
            Physics.DASH_REFRESH_ON_HIT
            and self.state_machine.current_state_name == PlayerState.DASH
        )
        every = CombatSettings.COMBO_DASH_REFILL_HITS
        milestone = combo_advanced and every > 0 and self.combat.combo_count % every == 0
        if refresh or milestone:
            dash.charges += 1

    def on_hit_evaded(self) -> bool:
        """A hit passed through the dodge or its ghost: a dark step, if in time.

        In time is within ``Rush.WINDOW`` of the dodge beginning. It slows the
        world for ``Rush.DURATION``, gives the dash back and fills some fury.
        One at a time: a second hit dodged during a rush is only dodged.
        """
        if self.dodge_window <= 0.0 or self.rush_timer > 0.0:
            return False
        self._close_dodge_window()
        self.rush_timer = Rush.DURATION
        self.fury.gain(FurySettings.DARK_STEP)
        self.dash.refill()
        return True

    def on_clash(self, other: Combatant) -> None:
        """Blades met: the lock's prompt opens, won by mashing the slash."""
        if not self.prompt.active and not other.is_dead:
            self.input_handler.clear_buffer()
            self.prompt.open(PromptKind.CLASH, other.id, self.rng)

    def on_deflected(self, source_center_x: float) -> None:
        """A blow stopped by a guard bounces off: the move ends, the fighter recoils.

        Mashing into a guard is the opening the enemy waits for: the recoil
        outlasts the start of its counter, and it costs battery on top of the
        slash that was spent.
        """
        self.combat.cancel_attack()
        self.input_handler.clear_buffer()
        self.battery.spend(BatterySettings.DEFLECT_COST)
        away = -1.0 if source_center_x >= self.hitbox.centerx else 1.0
        self.velocity.x = away * GuardSettings.DEFLECT_PUSH
        self.stagger(GuardSettings.DEFLECT_STAGGER)

    def guards_against(self, height: Height, unblockable: bool, source_center_x: float) -> bool:
        """The raised guard stops a blow from the front at any height, for some battery.

        An unblockable blow -- a heavy one -- breaks it instead, and the
        fighter staggers.
        """
        if not self.is_guarding or not self._faces_source(source_center_x):
            return False
        if unblockable:
            self.stagger(CombatSettings.HURT_DURATION)
            return False
        self.battery.spend(BatterySettings.GUARD_COST)
        away = -1.0 if source_center_x >= self.hitbox.centerx else 1.0
        self.velocity.x = away * GuardSettings.PUSH
        return True

    def _faces_source(self, source_center_x: float | None) -> bool:
        if source_center_x is None:
            return True
        if source_center_x >= self.hitbox.centerx:
            return self.facing_right
        return not self.facing_right

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        """Take the hit; a hit taken costs fury and closes the dodge window."""
        if not self._can_receive_damage():
            return DamageResult()
        result = super().receive_damage(amount, source_center_x, knockback, interrupt)
        if interrupt and self.combat.hurt_timer > 0:
            self.combat.hurt_timer = min(
                self.combat.hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )
        if result.applied:
            self.fury.lose(FurySettings.HURT_LOSS)
            self._close_dodge_window()
        return result

    # -- the rest of the tick --------------------------------------------------

    def _animation_name(self) -> str | None:
        """Map the current player state to its sprite-sheet animation."""
        state: str | None = self.state_machine.current_state_name
        if state is None:
            return None
        if state == PlayerState.ATTACK:
            return self._attack_animation()
        if state in (PlayerState.HURT, PlayerState.KNOCKBACK, PlayerState.STAGGER):
            return "hit"
        mapping: dict[str, str] = {
            PlayerState.IDLE: "idle",
            PlayerState.WALK_SLOW: "walk_slow",
            PlayerState.WALK: "walk",
            PlayerState.RUN: "run",
            PlayerState.DASH: "dash",
            PlayerState.JUMP: "jump",
            PlayerState.FALL: "fall",
            PlayerState.WALL_SLIDE: "wall",
        }
        return mapping.get(state)

    def _attack_animation(self) -> str:
        """The clip the running move asks for; the plain swing in the air or on the floor."""
        definition = self.combat.current_attack_def
        if definition is not None:
            return definition.animation
        return "air_attack" if not self.on_surface["floor"] else "attack"

    def _pre_update(self, delta_time: float) -> None:
        """Process input and timers before combat and state machine updates."""
        self.input_handler.update(delta_time)
        self.update_timers(delta_time)
        self._apply_momentum()

    def _post_update(self, delta_time: float) -> None:
        """Clear consumed inputs after state machine and physics updates."""
        if self.state_machine.current_state_name == PlayerState.DASH:
            self.dash.cancel_request()

    def handle_jump(self) -> None:
        """Process jump input with coyote time, wall jumps, and midair jumps."""
        resolve_jump(self)

    def _on_reset(self) -> None:
        self.jump.reset()
        self.dash.reset()
        self.battery.reset()
        self.fury.reset()
        self.slot.reset()
        self.prompt.reset()
        self.rush_timer = 0.0
        self._close_dodge_window()
        self.move_axis = 0.0
        self.input_handler.clear_buffer()
        self.hitbox.width = self.dash.original_hitbox_width

        self.left_held = False
        self.right_held = False
        self.down_held = False
        self.guard_held = False

    def respawn(self) -> None:
        self.reset_position()

    def save_state(self) -> EntitySnapshot:
        snapshot = super().save_state()
        # Added to the entity's own extras, never in place of them: replacing the
        # dict dropped the juggle and OTG state (audit C3).
        handler = self.input_handler
        snapshot.extra |= {
            "jump": self.jump.save_state(),
            "dash": self.dash.save_state(),
            "battery": self.battery.amount,
            "fury": self.fury.save_state(),
            "slot": self.slot.save_state(),
            "prompt": self.prompt.save_state(),
            "rush_timer": self.rush_timer,
            "dodge_window": self.dodge_window,
            "dodge_ghost": None if self.dodge_ghost is None else tuple(self.dodge_ghost),
            "buffered_action": (
                None if handler.buffered_action is None else handler.buffered_action.value
            ),
            "buffered_low": handler.buffered_low,
            "buffer_timer": handler.buffer_timer,
            "held_for": {button.value: held for button, held in handler.held_for.items()},
            "charge_button": None if handler.charge_button is None else handler.charge_button.value,
            "last_axis": handler.last_axis,
            "last_down": handler.last_down,
            "left_held": self.left_held,
            "right_held": self.right_held,
            "down_held": self.down_held,
            "guard_held": self.guard_held,
            "fast_fall": self.fast_fall,
        }
        return snapshot

    def load_state(self, snapshot: EntitySnapshot) -> None:
        super().load_state(snapshot)
        extra = snapshot.extra
        self.jump.load_state(extra["jump"])
        self.dash.load_state(extra["dash"])
        self.battery.amount = extra["battery"]
        self.fury.load_state(extra["fury"])
        self.slot.load_state(extra["slot"])
        self.prompt.load_state(extra["prompt"])
        self.rush_timer = extra["rush_timer"]
        self.dodge_window = extra["dodge_window"]
        ghost = extra["dodge_ghost"]
        self.dodge_ghost = None if ghost is None else pygame.FRect(ghost)
        self._sync_speeds()
        handler = self.input_handler
        buffered = extra["buffered_action"]
        handler.buffered_action = None if buffered is None else InputAction(buffered)
        handler.buffered_low = extra["buffered_low"]
        handler.buffer_timer = extra["buffer_timer"]
        handler.held_for = {InputAction(name): held for name, held in extra["held_for"].items()}
        button = extra["charge_button"]
        handler.charge_button = None if button is None else InputAction(button)
        handler.last_axis = extra["last_axis"]
        handler.last_down = extra["last_down"]
        self.left_held = extra["left_held"]
        self.right_held = extra["right_held"]
        self.down_held = extra["down_held"]
        self.guard_held = extra["guard_held"]
        self.fast_fall = extra["fast_fall"]
