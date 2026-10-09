"""Momentum-based contact damage between opposing entities (P4.1 pipeline)."""

from collections.abc import Callable, Iterable
from typing import Any

from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import HitProperties
from src.combat.knockback import NULL_KNOCKBACK
from src.combat.shapes import ShapeKind
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.core.settings import Combat as CombatSettings
from src.physics.entity_grid import EntityGrid


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

    CONTACT_COOLDOWN_TICKS = 12

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
        #: ``(id(entity), target_id) -> ticks left before that entity may
        #: damage that target again``.
        self._cooldowns: dict[tuple[int, str], int] = {}
        #: Pairs the gate admitted this tick, so a pair cleared by the
        #: broadphase arms its cooldown once however often it was asked about.
        self._armed: set[tuple[int, str]] = set()

    def _can_contact(self, entity_key: int) -> Callable[[str], bool]:
        """The contact gate for one entity, carrying its own cooldown.

        ``MomentumGate`` asks whether the target is already hurt, but contact
        damage resolves with ``interrupt=False``, which never puts a target in
        the hurt state -- so the pair that should have stopped repeating did
        not, and an overlap re-applied the damage every tick. This is the half
        of that guarantee that actually holds: a pair reacts once, then waits.
        """

        def can_contact(target_id: str) -> bool:
            pair = (entity_key, target_id)
            if self._cooldowns.get(pair, 0) > 0:
                return False
            self._armed.add(pair)
            return True

        return can_contact

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
            for pair in [pair for pair in self._cooldowns if pair[0] not in live]:
                del self._cooldowns[pair]
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
            can_contact=self._can_contact(id(entity)),
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
        self._armed = set()
        self.contact_system.resolve(self.produce_boxes(entities), entities, entity_grid)
        for pair in self._armed:
            self._cooldowns[pair] = self.CONTACT_COOLDOWN_TICKS
        for pair in [pair for pair, left in self._cooldowns.items() if left <= 1]:
            del self._cooldowns[pair]
        for pair in self._cooldowns:
            self._cooldowns[pair] -= 1
