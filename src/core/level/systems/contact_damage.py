"""Momentum-based contact damage between opposing entities (P4.1 pipeline)."""

from collections.abc import Callable, Iterable

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties
from src.combat.knockback import NULL_KNOCKBACK
from src.combat.shapes import ShapeKind
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.core.settings import Combat as CombatSettings
from src.physics.entity_grid import EntityGrid


def _always_contact(_target_id: str) -> bool:
    return True


def _momentum_gate(
    speed: float,
) -> Callable[[Combatant], bool]:
    """Legacy momentum rules, applied per source/target pair.

    A pair only reacts above ``CONTACT_DAMAGE_THRESHOLD``; the faster side
    deals the damage (equal speeds keep the legacy double application), and
    a target already in hurt state is left alone — the check that stopped
    contact damage from re-applying every tick.
    """

    def accept(other: Combatant) -> bool:
        other_speed = other.velocity.length()
        if max(speed, other_speed) < CombatSettings.CONTACT_DAMAGE_THRESHOLD:
            return False
        if getattr(other, "is_invincible", False):
            return False
        if getattr(getattr(other, "combat", None), "is_hurt", False):
            return False
        return speed >= other_speed

    return accept


class ContactDamageSystem:
    """Applies contact damage when entities overlap, based on momentum threshold."""

    def __init__(self, contact_system: ContactSystem | None = None) -> None:
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )

    def produce_boxes(self, entity_sprites: Iterable[Combatant]) -> tuple[OffensiveBox, ...]:
        """One candidate box per moving-eligible entity (momentum-gated)."""
        boxes: list[OffensiveBox] = []
        for entity in entity_sprites:
            if getattr(entity, "is_dead", False) or getattr(entity, "is_invincible", False):
                continue
            box = entity.hitbox
            contact_shape = getattr(entity, "contact_shape", None)
            swept_factory = getattr(entity, "swept_contact_shapes", None)
            swept_shapes = (
                swept_factory()
                if contact_shape is not None
                and contact_shape.kind is not ShapeKind.AABB
                and callable(swept_factory)
                else ()
            )
            boxes.append(
                OffensiveBox(
                    box=box,
                    swept=(box,),
                    swept_shapes=swept_shapes,
                    hit=HitProperties(
                        damage=CombatSettings.CONTACT_DAMAGE_AMOUNT,
                        knockback=NULL_KNOCKBACK,
                    ),
                    faction=getattr(entity, "faction", None),
                    owner_id=getattr(entity, "id", "") or "",
                    can_contact=_always_contact,
                    kind="contact",
                    interrupt=False,
                    accept=_momentum_gate(entity.velocity.length()),
                )
            )
        return tuple(boxes)

    def process(
        self,
        entity_sprites: Iterable[Combatant],
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Process the current state.

        Pair candidates come from the per-tick :class:`EntityGrid` when one
        is provided (O(n · k) instead of the legacy exhaustive O(n²)); the
        unified broadphase restores group order, so behaviour is unchanged.
        Without a grid the pairs are tested exhaustively — still correct,
        just slower.
        """
        entities = tuple(entity_sprites)
        self.contact_system.resolve(self.produce_boxes(entities), entities, entity_grid)
