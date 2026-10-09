from src.combat.attack_data import GOBLIN_ATTACKS
from src.combat.frame_data import AttackDefinition, MoveId
from src.entities.enemies.schema import EnemyConfig


def _shell_attacks() -> dict[MoveId, AttackDefinition]:
    """The goblin's table: this enemy swings with the same claw data.

    Kept as its own function rather than a shared constant, because the day
    ``shell`` grows its own frames the table diverges and this is the seam
    where it does.
    """
    return dict(GOBLIN_ATTACKS)


SHELL_CONFIG = EnemyConfig(
    size=(44.0, 52.0),
    color=(150, 110, 60),
    health=90.0,
    attacks=_shell_attacks(),
    attack_name="claw_swipe",
    chase_speed=65.0,
    vision_range=280.0,
    attack_range=55.0,
    patrol_interval=3.0,
    idle_duration=1.2,
    has_ai=True,
    pushable=True,
    super_armor=True,
    passive_friction=12.0,
    parry_stun_threshold=3,
    parry_stun_duration=1.4,
    animations={
        "idle": "assets/graphics/enemies/shell/idle",
        "attack": "assets/graphics/enemies/shell/fire",
    },
)
