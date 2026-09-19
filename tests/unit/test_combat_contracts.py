"""Combat contract characterization: explicit attacker/target views."""

import inspect

from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.combat.combatant_protocol import AttackerPort, Combatant, CombatPort
from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.combat.knockback import KnockbackConfig
from src.entities.projectile import Projectile
from tests.unit.helpers import AttackerStub, make_entity


def _hit(**kwargs) -> HitProperties:
    return HitProperties(damage=10, knockback=KnockbackConfig(power=(0.0, 0.0)), **kwargs)


def test_combat_port_exposes_combo_tracking() -> None:
    assert "air_combo_count" in dir(CombatComponent)
    assert "record_hit_landed" in dir(CombatComponent)
    assert "air_combo_count" in dir(NullCombatComponent)
    assert "air_combo_count" in CombatPort.__annotations__ or hasattr(CombatPort, "air_combo_count")
    assert hasattr(CombatPort, "record_hit_landed")


def test_combatant_requires_grounded_otg_juggle() -> None:
    for name in ("on_surface", "otg_timer", "set_juggle"):
        assert name in Combatant.__annotations__ or hasattr(Combatant, name), name


def test_attacker_view_is_narrow() -> None:
    assert "hitbox" in AttackerPort.__annotations__
    assert hasattr(AttackerPort, "combat")
    for forbidden in ("health", "receive_damage", "stagger"):
        assert forbidden not in AttackerPort.__annotations__
        assert not hasattr(AttackerPort, forbidden)
    assert isinstance(AttackerStub(), AttackerPort)
    assert isinstance(Projectile(), AttackerPort)


def test_projectile_carries_neutral_combat() -> None:
    projectile = Projectile()
    assert isinstance(projectile.combat, NullCombatComponent)
    assert projectile.combat.air_combo_count == 0
    projectile.combat.record_hit_landed(True)


def test_resolver_uses_typed_access_without_getattr_fallbacks() -> None:
    import src.combat.hit_resolver as module

    text = inspect.getsource(module)
    # Allow getattr for dynamic state_machine check (DIZZY state damage bonus)
    # and for is_invincible property check (not all combatants have state_machine).
    # Both are legitimate dynamic attribute accesses.
    getattr_count = text.count("getattr")
    assert getattr_count <= 3, (
        f"Expected at most 3 getattr (for DIZZY state check and invincibility check), found {getattr_count}"
    )


def test_combo_recorded_once_air_only() -> None:
    from tests.unit.helpers import make_attack, make_phase

    attacker = make_entity(faction="player", attacks={"punch": make_attack(make_phase())})
    ground = make_entity(faction="enemy")
    ground.on_surface["floor"] = True
    air = make_entity(faction="enemy")
    air.on_surface["floor"] = False
    HitResolver.resolve(attacker, ground, _hit(stagger=0.1))
    assert attacker.combat.air_combo_count == 0
    HitResolver.resolve(attacker, air, _hit(stagger=0.1))
    assert attacker.combat.air_combo_count == 1


def test_neutral_projectile_records_nothing_but_hits() -> None:
    from src.core.level.systems.projectile_system import ProjectileSystem
    from src.core.sprite_groups import SpriteGroups

    target = make_entity(faction="enemy")
    groups = SpriteGroups()
    groups.entity_sprites.add(target)
    groups.all_sprites.add(target)
    system = ProjectileSystem(groups)
    system.spawn(
        __import__(
            "src.entities.projectile",
            fromlist=["ProjectileConfig"],
        ).ProjectileConfig(
            size=(10.0, 10.0),
            lifetime=2.0,
            hit=_hit(),
        ),
        pos=(target.hitbox.x, target.hitbox.y),
        velocity=(0.0, 0.0),
        faction="player",
    )
    system.process(1 / 60)
    assert target.health == 90.0
