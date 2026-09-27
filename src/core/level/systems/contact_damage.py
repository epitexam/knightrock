"""Momentum-based contact damage between opposing entities (P4.1 pipeline)."""

from collections.abc import Iterable
from typing import Any

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties
from src.combat.knockback import NULL_KNOCKBACK
from src.combat.shapes import ShapeKind
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.core.settings import Combat as CombatSettings
from src.physics.entity_grid import EntityGrid


def _always_contact(_target_id: str) -> bool:
    return True


class MomentumGate:
    """Legacy momentum rules, applied per source/target pair.

    A pair only reacts above ``CONTACT_DAMAGE_THRESHOLD``; the faster side
    deals the damage (equal speeds keep the legacy double application), and a
    target already in hurt state is left alone — the check that stopped
    contact damage from re-applying every tick.

    An object rather than a closure because the gate is installed once per
    entity in a box that lives across ticks, and only the speed changes: a
    closure would have to be rebuilt every tick to carry a new speed, which
    is the allocation this class exists to remove.
    """

    __slots__ = ("speed",)

    def __init__(self, speed: float) -> None:
        self.speed = speed

    def __call__(self, other: Combatant) -> bool:
        other_speed = other.velocity.length()
        if max(self.speed, other_speed) < CombatSettings.CONTACT_DAMAGE_THRESHOLD:
            return False
        if getattr(other, "is_invincible", False):
            return False
        if getattr(getattr(other, "combat", None), "is_hurt", False):
            return False
        return self.speed >= other_speed


class ContactDamageSystem:
    """Applies contact damage when entities overlap, based on momentum threshold."""

    def __init__(self, contact_system: ContactSystem | None = None) -> None:
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        #: One live :class:`OffensiveBox` per entity, keyed by ``id()`` and
        #: holding the entity itself so the key cannot be recycled onto a
        #: different object while the entry lives. See :meth:`produce_boxes`.
        self._boxes: dict[int, tuple[Any, OffensiveBox]] = {}
        #: Shared by every contact box: the amount and the knockback are
        #: constants of the rule, not of the entity, so there is nothing to
        #: make per-entity. Built once because a frozen ``HitProperties`` is
        #: fourteen fields and a validating pass, and this ran once per entity
        #: per tick to produce the same object every time.
        self._hit = HitProperties(
            damage=CombatSettings.CONTACT_DAMAGE_AMOUNT,
            knockback=NULL_KNOCKBACK,
        )

    def produce_boxes(self, entity_sprites: Iterable[Combatant]) -> tuple[OffensiveBox, ...]:
        """One candidate box per moving-eligible entity (momentum-gated).

        Only the geometry and the gate's speed are recomputed per tick. The
        cache is pruned to the entities actually present, so a removed entity
        does not keep its box -- or the entity itself, which the cache holds a
        reference to -- alive.

        Keyed by ``id()`` rather than by the object, so an entity does not
        have to be hashable: a duck-typed test double need not be. The entry
        holds the entity it was keyed by, so a live id cannot belong to two
        objects, and the identity check below turns even a stale key into a
        miss rather than into somebody else's box.
        """
        boxes: list[OffensiveBox] = []
        live: set[int] = set()
        for entity in entity_sprites:
            if getattr(entity, "is_dead", False) or getattr(entity, "is_invincible", False):
                continue
            key = id(entity)
            live.add(key)
            entry = self._boxes.get(key)
            if entry is None or entry[0] is not entity:
                entry = (entity, self._build_box(entity))
                self._boxes[key] = entry
            self._refresh(entry[1], entity)
            boxes.append(entry[1])
        if len(self._boxes) != len(live):
            for key in [known for known in self._boxes if known not in live]:
                del self._boxes[key]
        return tuple(boxes)

    def _build_box(self, entity: Combatant) -> OffensiveBox:
        """The box for a newly seen entity, with its per-entity fields set."""
        return OffensiveBox(
            box=entity.hitbox,
            swept=(entity.hitbox,),
            swept_shapes=(),
            hit=self._hit,
            faction=getattr(entity, "faction", None),
            owner_id=getattr(entity, "id", "") or "",
            can_contact=_always_contact,
            kind="contact",
            interrupt=False,
            accept=MomentumGate(entity.velocity.length()),
        )

    def _refresh(self, entry: OffensiveBox, entity: Combatant) -> None:
        """Point a live box at where the entity is this tick.

        Run on the tick the box is built as well as on every later one, so the
        first tick of an entity is shaped exactly like the rest.
        """
        hitbox = entity.hitbox
        entry.box = hitbox
        entry.swept = (hitbox,)
        entry.swept_shapes = self._swept_shapes(entity)
        gate = entry.accept
        if isinstance(gate, MomentumGate):
            gate.speed = entity.velocity.length()

    @staticmethod
    def _swept_shapes(entity: Combatant) -> tuple:
        """The shape sweep for an entity, or nothing for a plain AABB one."""
        contact_shape = getattr(entity, "contact_shape", None)
        if contact_shape is None or contact_shape.kind is ShapeKind.AABB:
            return ()
        factory = getattr(entity, "swept_contact_shapes", None)
        return factory() if callable(factory) else ()

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
