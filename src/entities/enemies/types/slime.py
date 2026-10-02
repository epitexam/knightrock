from src.combat.frame_data import AttackDefinition, MoveId
from src.entities.enemies.schema import EnemyConfig


def _shipped_slime_attacks() -> dict[MoveId, AttackDefinition]:
    """The shipped table for this enemy, read from the data file.

    Read lazily so importing this module does not read ``attacks.json``: the
    loader imports the enemy schemas, which import this.
    """
    from src.combat.attack_data import SLIME_ATTACKS

    return dict(SLIME_ATTACKS)


SLIME_CONFIG = EnemyConfig(
    size=(32.0, 32.0),
    color=(80, 200, 220),
    health=40.0,
    attacks=_shipped_slime_attacks(),
    attack_name="body_slam",
    chase_speed=80.0,
    vision_range=250.0,
    attack_range=50.0,
    patrol_interval=1.5,
    idle_duration=0.8,
    has_ai=True,
    pushable=True,
    super_armor=False,
    passive_friction=8.0,
    parry_stun_threshold=3,
    parry_stun_duration=2.0,
)
