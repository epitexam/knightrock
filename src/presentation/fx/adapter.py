"""Presentation implementation of the simulation's effects port."""

from __future__ import annotations

from typing import Any

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


class PresentationFx:
    """Delegate each effect request to the real spawner in this layer."""

    def spawn_corpse(self, group: Any, entity: Any) -> None:
        spawn_corpse(group, entity)

    def spawn_dash_dust(self, group: Any, entity: Any, *, burst: bool) -> None:
        spawn_dash_dust(group, entity, burst=burst)

    def spawn_dash_grains(self, group: Any, entity: Any, *, burst: bool) -> None:
        spawn_dash_grains(group, entity, burst=burst)

    def spawn_dizzy_stars(self, group: Any, entity: Any, count: int, ttl: float) -> None:
        spawn_dizzy_stars(group, entity, count, ttl)

    def spawn_dizzy_vortex(self, group: Any, entity: Any) -> None:
        spawn_dizzy_vortex(group, entity)

    def spawn_footstep_dust(self, group: Any, entity: Any, *, foot: bool, tier: Any) -> None:
        spawn_footstep_dust(group, entity, foot=foot, tier=tier)

    def spawn_footstep_grains(self, group: Any, entity: Any, *, foot: bool) -> None:
        spawn_footstep_grains(group, entity, foot=foot)

    def spawn_guard_arc(self, group: Any, target: Any, *, contact: Any) -> None:
        spawn_guard_arc(group, target, contact=contact)

    def spawn_impact_decal(self, group: Any, entity: Any, impact: Any) -> None:
        spawn_impact_decal(group, entity, impact)

    def spawn_landing_dust(self, group: Any, entity: Any, impact: Any) -> None:
        spawn_landing_dust(group, entity, impact)

    def spawn_landing_grains(self, group: Any, entity: Any, impact: Any) -> None:
        spawn_landing_grains(group, entity, impact)

    def spawn_sweat_drops(self, group: Any, entity: Any) -> None:
        spawn_sweat_drops(group, entity)
