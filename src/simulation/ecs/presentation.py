"""Draw-side adapter for dense entities.

A pygame group needs a ``Sprite`` with an ``image`` and a ``rect``. Once
``Entity`` stops inheriting from ``Sprite``, groups will hold one of these
adapters instead: it carries no simulation state, only the two presentation
fields the renderer and the debug overlay read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from src.simulation.entities.entity import Entity


class PresentationSprite(pygame.sprite.Sprite):
    """The drawable face of one dense entity."""

    def __init__(self, entity: Entity, *groups: pygame.sprite.Group) -> None:
        super().__init__(*groups)
        self.entity = entity
        self._image: pygame.Surface | None = None
        self._rect: pygame.FRect | None = None

    @property
    def image(self) -> pygame.Surface:
        return self.entity.image

    @image.setter
    def image(self, value: pygame.Surface) -> None:
        self._image = value
        self.entity.image = value

    @property
    def rect(self) -> pygame.FRect:
        return self.entity.rect

    @rect.setter
    def rect(self, value: pygame.FRect) -> None:
        self._rect = value
        self.entity.rect = value

    @property
    def hitbox(self) -> pygame.FRect:
        """The debug overlay reads the collider through the draw proxy."""
        return self.entity.hitbox

    @property
    def combat(self) -> object:
        return self.entity.combat

    @property
    def faction(self) -> str:
        return self.entity.faction

    def __getattr__(self, name: str) -> object:
        """Delegate the combatant protocol to the underlying simulation row."""
        entity = self.__dict__.get("entity")
        if entity is None:  # pragma: no cover - guards a partially built proxy
            raise AttributeError(name)
        return getattr(entity, name)
