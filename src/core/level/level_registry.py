"""
Generic registry for extensible dispatch of handlers by name.
"""

import logging
from typing import Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Registry(Generic[T]):
    """
    A registry that maps string names to callable handlers.

    Handlers can be registered and later dispatched by name.
    Unknown names are logged and return None.
    """

    def __init__(self, kind: str):
        """
        Initialize the registry.

        Args:
            kind: A descriptive name for the kind of items handled
                  (used in log messages).
        """
        self._kind = kind
        self._handlers: dict[str, Callable[..., T]] = {}

    def register(self, name: str):
        """
        Decorator to register a function for a given name.

        Example:
            @registry.register("my_type")
            def build_my_type(...):
                ...
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            self._handlers[name] = func
            return func
        return decorator

    def has(self, name: str) -> bool:
        """Return True if a handler is registered for the given name."""
        return name in self._handlers

    def dispatch(self, name: str, *args, **kwargs) -> Optional[T]:
        """
        Invoke the handler for the given name with the provided arguments.

        Returns:
            The handler's return value, or None if no handler exists.
        """
        handler = self._handlers.get(name)
        if handler is None:
            logger.debug("%s: no handler for '%s', ignored", self._kind, name)
            return None
        return handler(*args, **kwargs)
