"""Hazard contact damage system (saws, spikes, floor spikes)."""

from collections.abc import Iterable
from typing import Any

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import ShapeKind
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHashMember


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
        #: One live :class:`OffensiveBox` per hazard, keyed by ``id()`` and
        #: holding the hazard itself so the key cannot be recycled onto a
        #: different object while the entry lives. See :meth:`produce_boxes`.
        self._boxes: dict[int, tuple[Any, OffensiveBox]] = {}

    def _build_box(self, hazard: Any, box: Any) -> OffensiveBox:
        """A hazard's offensive box, built once.

        ``HitProperties`` is a frozen dataclass of fourteen fields with a
        validating ``__post_init__``, and building one costs about as much as
        everything else in this function put together. Nothing in it varies
        per tick -- a hazard's damage and knockback are read from the TMX
        object property at construction and never written again -- so the box
        is built the first time a hazard is seen and only its geometry is
        refreshed afterwards.
        """
        damage = float(getattr(hazard, "damage", self.DEFAULT_DAMAGE))
        knockback = getattr(hazard, "knockback", None) or self.DEFAULT_KNOCKBACK
        return OffensiveBox(
            box=box,
            swept=(box,),
            hit=HitProperties(damage=damage, knockback=knockback),
            swept_shapes=(),
            faction=None,
            owner_id="",
            can_contact=_always_contact,
            kind="hazard",
            interrupt=False,
        )

    def _refresh_geometry(self, entry: OffensiveBox, hazard: Any, box: Any) -> None:
        """Point a live box at where the hazard is this tick.

        Run on the tick the box is built as well as on every later one, so a
        hazard that sweeps is swept on the very first tick it is seen and not
        only from the second onwards.
        """
        entry.box = box
        swept_rect_factory = getattr(hazard, "swept_contact_rect", None)
        entry.swept = (swept_rect_factory(),) if callable(swept_rect_factory) else (box,)
        entry.swept_shapes = self._swept_shapes(hazard)

    def produce_boxes(
        self, entity_sprites: Iterable, hazard_sprites: Iterable
    ) -> tuple[OffensiveBox, ...]:
        """One offensive box per hazard, damage/knockback from the hazard.

        Only the geometry is recomputed per tick; the hit properties are not,
        and the boxes themselves are reused across ticks. The cache is pruned
        to the hazards actually present, so a hazard removed from the level
        does not keep its box -- or the hazard itself, which the cache holds a
        reference to -- alive.

        Keyed by ``id()`` rather than by the object, so a producer does not
        have to be hashable: a duck-typed test double need not be. The entry
        holds the hazard it was keyed by, so a live id cannot belong to two
        objects, and the identity check below turns even a stale key into a
        miss rather than into somebody else's box.
        """
        boxes: list[OffensiveBox] = []
        live: set[int] = set()
        for hazard in hazard_sprites:
            box = getattr(hazard, "hitbox", getattr(hazard, "rect", None))
            if box is None:
                continue
            key = id(hazard)
            live.add(key)
            entry = self._boxes.get(key)
            if entry is None or entry[0] is not hazard:
                entry = (hazard, self._build_box(hazard, box))
                self._boxes[key] = entry
            self._refresh_geometry(entry[1], hazard, box)
            boxes.append(entry[1])
        if len(self._boxes) != len(live):
            for key in [known for known in self._boxes if known not in live]:
                del self._boxes[key]
        return tuple(boxes)

    @staticmethod
    def _swept_shapes(hazard: Any) -> tuple:
        """The shape sweep for a hazard, or nothing for a plain AABB one."""
        contact_shape = getattr(hazard, "contact_shape", None)
        if contact_shape is None or contact_shape.kind is ShapeKind.AABB:
            return ()
        factory = getattr(hazard, "swept_contact_shapes", None)
        return factory() if callable(factory) else ()

    def process(
        self,
        entity_sprites: Iterable[Combatant],
        hazard_sprites: Iterable[SpatialHashMember],
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Apply damage for every overlap between a hazard and a live entity."""
        entities = tuple(entity_sprites)
        self.contact_system.resolve(
            self.produce_boxes(entities, hazard_sprites), entities, entity_grid
        )
