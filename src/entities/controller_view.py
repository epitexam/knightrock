"""Flat delegation to controllers via ``__getattr__`` (audit F1.1, Phase 2 #3).

``Player`` aggregates ability controllers (``JumpController``,
``BlockController``, ``DashController``) but historically exposed ~50 flat
``@property`` attributes that only relayed reads/writes of an attribute on
the underlying controller (``JumpEntity``/``WallJumpLock`` physics protocols
and debug UI).

The :class:`ControllerView` mixin replaces that boilerplate with a mapping
table ``flat_name -> (controller, real_attribute)``: reads via
``__getattr__`` (only called when the normal attribute is missing), writes
via ``__setattr__``.  Real instance attributes keep priority, and unknown
names always raise ``AttributeError``.
"""

from collections.abc import Mapping
from typing import Any, ClassVar


class ControllerView:
    """Route flat attributes to the controllers (holds the DIP)."""

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
