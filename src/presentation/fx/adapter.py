"""Presentation implementation of the simulation's effects port.

The port keeps simulation-owned entities opaque; the casts here name the
concrete shapes the real spawners expect, at the only place they are known.
"""

from __future__ import annotations

from typing import cast

import pygame

from src.presentation.fx import (
    spawn_corpse,
    spawn_dash_dust,
    spawn_dash_grains,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_footstep_dust,
    spawn_footstep_grains,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_landing_grains,
    spawn_sweat_drops,
)
from src.presentation.fx.spawners import FxBody, FxSubject
from src.simulation.fx_tuning import FootstepTier

_Group = pygame.sprite.Group[pygame.sprite.Sprite]


class PresentationFx:
    """Delegate each effect request to the real spawner in this layer."""

    def spawn_corpse(self, group: _Group, entity: object) -> None:
        spawn_corpse(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group), cast("FxSubject", entity)
        )

    def spawn_dash_dust(self, group: _Group, entity: object, *, burst: bool) -> None:
        spawn_dash_dust(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            burst,
        )

    def spawn_dash_grains(self, group: _Group, entity: object, *, burst: bool) -> None:
        spawn_dash_grains(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            burst,
        )

    def spawn_dizzy_stars(self, group: _Group, entity: object, count: int, ttl: float) -> None:
        spawn_dizzy_stars(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            count,
            ttl,
        )

    def spawn_dizzy_vortex(self, group: _Group, entity: object) -> None:
        spawn_dizzy_vortex(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group), cast("FxSubject", entity)
        )

    def spawn_footstep_dust(
        self, group: _Group, entity: object, *, foot: bool, tier: object
    ) -> None:
        spawn_footstep_dust(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            foot,
            cast("FootstepTier", tier),
        )

    def spawn_footstep_grains(self, group: _Group, entity: object, *, foot: bool) -> None:
        spawn_footstep_grains(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            foot,
        )

    def spawn_guard_arc(self, group: _Group, target: object, *, contact: object) -> None:
        spawn_guard_arc(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxBody", target),
            contact=cast("tuple[float, float] | None", contact),
        )

    def spawn_impact_decal(self, group: _Group, entity: object, impact: object) -> None:
        spawn_impact_decal(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            cast("float", impact),
        )

    def spawn_landing_dust(self, group: _Group, entity: object, impact: object) -> None:
        spawn_landing_dust(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            cast("float", impact),
        )

    def spawn_landing_grains(self, group: _Group, entity: object, impact: object) -> None:
        spawn_landing_grains(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group),
            cast("FxSubject", entity),
            cast("float", impact),
        )

    def spawn_sweat_drops(self, group: _Group, entity: object) -> None:
        spawn_sweat_drops(
            cast("pygame.sprite.Group[pygame.sprite.Sprite]", group), cast("FxSubject", entity)
        )
