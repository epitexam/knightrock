"""Player configuration dataclass for data-driven player initialization."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.frame_data import AttackDefinition
from src.core.colors import Colors
from src.core.settings import Combat, Physics


def _default_attacks() -> dict[str, AttackDefinition]:
    """Return default attacks dictionary."""
    return dict(PLAYER_ATTACKS)


@dataclass(frozen=True)
class PlayerConfig:
    """Reusable data needed to create and configure the player entity.
    
    Attributes
    ----------
    size : tuple[float, float]
        Width and height of the player sprite.
    color : tuple[int, int, int]
        RGB color for the player sprite.
    health : float
        Starting health points.
    max_health : float
        Maximum health cap.
    hitbox_inflate : tuple[float, float]
        (x, y) inflation for the hitbox relative to the rect.
    attacks : Mapping[str, AttackDefinition]
        Dictionary of attack definitions.
    speed : float
        Base movement speed.
    floor_control : float
        Horizontal control when on the ground.
    air_control : float
        Horizontal control when airborne.
    jump_height : float
        Vertical impulse for a normal jump.
    wall_jump_height : float
        Vertical impulse for a wall jump.
    wall_jump_push_multiplier : float
        Horizontal push multiplier for wall jumps.
    wall_jump_lock_duration : float
        Duration to lock controls after a wall jump.
    wall_jump_min_lock : float
        Minimum lock duration after a wall jump.
    wall_slide_speed : float
        Descent speed when sliding down a wall.
    max_midair_jumps : int
        Maximum number of jumps allowed while airborne.
    max_wall_jumps : int | float
        Maximum number of wall jumps allowed.
    coyote_duration : float
        Duration after leaving a surface where jump is still allowed.
    jump_buffer_duration : float
        Duration to buffer a jump input before landing.
    max_block_stamina : float
        Maximum stamina for blocking.
    block_cooldown_normal : float
        Cooldown after a normal block.
    block_cooldown_broken : float
        Cooldown after a broken block.
    max_dash_charges : int
        Maximum number of dash charges.
    dash_speed : float
        Horizontal speed during a dash.
    dash_duration : float
        Duration of a dash in seconds.
    dash_friction : float
        Friction applied during a dash.
    dash_penalty_duration : float
        Duration of penalty after a dash.
    dash_recharge_time : float
        Time to recharge one dash charge.
    dash_gravity_mult : float
        Gravity multiplier during a dash.
    hurt_duration : float
        Duration of the hurt state.
    invincibility_duration : float
        Duration of invincibility frames after taking damage.
    faction : str
        Faction identifier for combat targeting.
    """
    size: tuple[float, float] = (48.0, 56.0)
    color: tuple[int, int, int] = Colors.green
    health: float = 100.0
    max_health: float = 100.0
    hitbox_inflate: tuple[float, float] = (-8.0, 0.0)
    hurtbox_inflate: tuple[float, float] = (0.0, 0.0)
    attacks: Mapping[str, AttackDefinition] = field(default_factory=_default_attacks)
    speed: float = Physics.PLAYER_SPEED
    floor_control: float = Physics.FLOOR_CONTROL
    air_control: float = Physics.AIR_CONTROL
    jump_height: float = Physics.JUMP_FORCE
    wall_jump_height: float = Physics.JUMP_FORCE * 0.90 * 1.15
    wall_jump_push_multiplier: float = 1.3
    wall_jump_lock_duration: float = 0.18
    wall_jump_min_lock: float = 0.08
    wall_slide_speed: float = Physics.WALL_SLIDE_SPEED
    max_midair_jumps: int = 1
    max_wall_jumps: int | float = float('inf')
    coyote_duration: float = Physics.COYOTE_DURATION
    jump_buffer_duration: float = Physics.JUMP_BUFFER_DURATION
    max_block_stamina: float = Physics.MAX_BLOCK_STAMINA
    block_cooldown_normal: float = Combat.BLOCK_COOLDOWN_NORMAL
    block_cooldown_broken: float = Combat.BLOCK_COOLDOWN_BROKEN
    max_dash_charges: int = Physics.DASH_MAX_CHARGES
    dash_speed: float = Physics.DASH_SPEED
    dash_duration: float = Physics.DASH_DURATION
    dash_friction: float = Physics.DASH_FRICTION
    dash_penalty_duration: float = Physics.DASH_PENALTY_TIME
    dash_recharge_time: float = Physics.DASH_RECHARGE_TIME
    dash_gravity_mult: float = Physics.DASH_GRAVITY_MULT
    hurt_duration: float = Combat.PLAYER_HURT_DURATION
    invincibility_duration: float = Combat.INVINCIBILITY_DURATION
    faction: str = "player"
