"""Délégation plate vers les controllers via ``__getattr__`` (audit F1.1, Phase 2 #3).

``Player`` agrège des controllers de capacité (``JumpController``,
``BlockController``, ``DashController``) mais expose historiquement une
cinquantaine de ``@property`` plates qui ne faisaient que relayer la
lecture/écriture d'un attribut du controller sous-jacent (protocoles
physiques ``JumpEntity``/``WallJumpLock`` et UI de debug).

Le mixin :class:`ControllerView` remplace ce boilerplate par une table de
correspondance ``nom_plat -> (controller, attribut_réel)`` : lecture via
``__getattr__`` (uniquement appelé quand l'attribut normal est absent),
écriture via ``__setattr__``.  Les vrais attributs d'instance gardent la
priorité, et les noms inconnus lèvent toujours ``AttributeError``.
"""

from collections.abc import Mapping
from typing import Any, ClassVar


class ControllerView:
    """Achemine les attributs plats vers les controllers (contient le DIP)."""

    CONTROLLER_VIEWS: ClassVar[Mapping[str, tuple[str, str]]] = {}

    def __getattr__(self, name: str) -> Any:
        """Relay a flat read to the owning controller."""
        view = type(self).CONTROLLER_VIEWS.get(name)
        if view is None:
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
        controller_name, attribute_name = view
        return getattr(getattr(self, controller_name), attribute_name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Relay a flat write to the owning controller when mapped."""
        view = type(self).CONTROLLER_VIEWS.get(name)
        if view is not None and hasattr(self, view[0]):
            setattr(getattr(self, view[0]), view[1], value)
            return
        super().__setattr__(name, value)
