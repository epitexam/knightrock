"""Hazard contact damage system (saws, spikes, floor spikes)."""

from collections.abc import Iterable

from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import ShapeKind
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox


def _always_contact(_target_id: str) -> bool:
    return True


class HazardDamageSystem:
    """Apply configured damage to entities overlapping an active hazard.

    The per-hazard ``damage``/``knockback`` attributes take precedence when
    present (they can be set through the TMX ``damage`` object property).
    Contact resolution is delegated to the unified pipeline (P4.1): hazards
    carry no faction and no memory, so every overlapping entity is a valid
    target and the damage never interrupts.
    """

    DEFAULT_DAMAGE = 20.0
    DEFAULT_KNOCKBACK = KnockbackConfig(power=(150.0, -60.0))

    def __init__(self, contact_system: ContactSystem | None = None) -> None:
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )

    def produce_boxes(
        self, entity_sprites: Iterable, hazard_sprites: Iterable
    ) -> tuple[OffensiveBox, ...]:
        """One offensive box per hazard, damage/knockback from the hazard."""
        boxes: list[OffensiveBox] = []
        for hazard in hazard_sprites:
            box = getattr(hazard, "hitbox", getattr(hazard, "rect", None))
            if box is None:
                continue
            damage = float(getattr(hazard, "damage", self.DEFAULT_DAMAGE))
            knockback = getattr(hazard, "knockback", None) or self.DEFAULT_KNOCKBACK
            contact_shape = getattr(hazard, "contact_shape", None)
            swept_rect_factory = getattr(hazard, "swept_contact_rect", None)
            swept_rect = (
                swept_rect_factory()
                if callable(swept_rect_factory)
                else box
            )
            swept_shapes = (
                hazard.swept_contact_shapes()
                if contact_shape is not None
                and contact_shape.kind is not ShapeKind.AABB
                and callable(getattr(hazard, "swept_contact_shapes", None))
                else ()
            )
            boxes.append(
                OffensiveBox(
                    box=box,
                    swept=(swept_rect,),
                    hit=HitProperties(damage=damage, knockback=knockback),
                    swept_shapes=swept_shapes,
                    faction=None,
                    owner_id="",
                    can_contact=_always_contact,
                    kind="hazard",
                    interrupt=False,
                )
            )
        return tuple(boxes)

    def process(
        self,
        entity_sprites: Iterable,
        hazard_sprites: Iterable,
        entity_grid=None,
    ) -> None:
        """Apply damage for every overlap between a hazard and a live entity."""
        entities = tuple(entity_sprites)
        self.contact_system.resolve(
            self.produce_boxes(entities, hazard_sprites), entities, entity_grid
        )
