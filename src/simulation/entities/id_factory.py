"""Entity and projectile ids, behind an injectable factory.

Ids used to come from module-level ``count()`` objects shared by every
``Game`` and every test in the process. The shared factory below keeps those
sequences byte-for-byte for existing callers; a caller that owns a world can
pass its own factory and get ids isolated from other worlds.
"""

from __future__ import annotations

from itertools import count

from src.simulation.ecs.table import Handle


class IdFactory:
    """Allocates entity and projectile ids with separate sequences."""

    def __init__(self, start: int = 0) -> None:
        self._entities = count(start)
        self._projectiles = count(start)

    def entity_id(self) -> str:
        return f"e{next(self._entities)}"

    def projectile_id(self) -> str:
        return f"p{next(self._projectiles)}"

    def entity_handle(self) -> Handle:
        """A fresh entity identity, with the generation the table will track."""
        return self.entity_id(), 0

    def projectile_handle(self) -> Handle:
        """A fresh projectile identity, with the generation the table will track."""
        return self.projectile_id(), 0


_shared: IdFactory | None = None


def shared_id_factory() -> IdFactory:
    """The process-wide factory, created lazily like the asset library."""
    global _shared
    if _shared is None:
        _shared = IdFactory()
    return _shared
