from src.combat.attack_data import GOBLIN_ATTACKS
from src.combat.frame_data import AttackDefinition, MoveId
from src.entities.enemies.schema import EnemyConfig


def _tooth_attacks() -> dict[MoveId, AttackDefinition]:
    """The goblin's table: this enemy swings with the same claw data.

    Kept as its own function rather than a shared constant, because the day
    ``tooth`` grows its own frames the table diverges and this is the seam
    where it does.
    """
    return dict(GOBLIN_ATTACKS)


TOOTH_CONFIG = EnemyConfig(
    size=(38.0, 46.0),
    color=(190, 90, 120),
    health=50.0,
    attacks=_tooth_attacks(),
    attack_name="claw_swipe",
    chase_speed=165.0,
    vision_range=360.0,
    attack_range=50.0,
    patrol_interval=1.2,
    idle_duration=0.35,
    has_ai=True,
    pushable=True,
    super_armor=False,
    passive_friction=8.0,
    can_jump=True,
    jump_height=560.0,
    leap_speed_mult=1.4,
    parry_stun_threshold=2,
    parry_stun_duration=1.2,
    animations={
        "idle": "assets/graphics/enemies/tooth/run",
        "patrol": "assets/graphics/enemies/tooth/run",
        "chase": "assets/graphics/enemies/tooth/run",
    },
)
