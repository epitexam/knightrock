"""Player configuration dataclass for data-driven player initialization."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.frame_data import AttackDefinition


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
    color: tuple[int, int, int] = (0, 255, 0)
    health: float = 100.0
    max_health: float = 100.0
    hitbox_inflate: tuple[float, float] = (-8.0, 0.0)
    attacks: Mapping[str, AttackDefinition] = field(default_factory=_default_attacks)
    speed: float = 450.0
    floor_control: float = 25.0
    air_control: float = 12.0
    jump_height: float = 550.0
    wall_jump_height: float = 550.0 * 0.90 * 1.15
    wall_jump_push_multiplier: float = 1.3
    wall_jump_lock_duration: float = 0.18
    wall_jump_min_lock: float = 0.08
    wall_slide_speed: float = 100.0
    max_midair_jumps: int = 1
    max_wall_jumps: int | float = float('inf')
    coyote_duration: float = 0.12
    jump_buffer_duration: float = 0.10
    max_block_stamina: float = 0.75
    block_cooldown_normal: float = 0.5
    block_cooldown_broken: float = 2.0
    max_dash_charges: int = 2
    dash_speed: float = 1500.0
    dash_duration: float = 0.12
    dash_friction: float = 15.0
    dash_penalty_duration: float = 2.20
    dash_recharge_time: float = 0.40
    dash_gravity_mult: float = 0.0
    hurt_duration: float = 0.12
    invincibility_duration: float = 0.18
    faction: str = "player"
