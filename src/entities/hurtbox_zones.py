"""Configuration and derivation helpers for multi-hurtbox zones (P2, axe B).

A zone is a named damage-receiving area derived from the entity's pushbox:
``box = pushbox.inflate(inflate)`` re-centered on the pushbox center, with a
localized damage multiplier and reserved invulnerability tags. The legacy
single-hurtbox behavior is exactly one unnamed zone carrying the entity's
``hurtbox_inflate``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from src.data.errors import GameplayDataError


@dataclass(frozen=True)
class HurtboxZoneDef:
    """Static per-zone configuration (config, never runtime state).

    Attributes
    ----------
    name :
        Zone identifier for debug overlay and future hit-tag matching
        (``head`` / ``torso`` / ``legs`` by convention; free-form).
    inflate :
        ``(x, y)`` inflation applied to the pushbox, same convention as
        the legacy ``hurtbox_inflate`` (may be negative to shrink).
    mult :
        Localized damage multiplier applied when a hit lands on the zone
        (``1.0`` = neutral; reserved ``head`` multiplier use case).
    tags :
        Reserved invulnerability tags (P2: no hit carries tags yet, so no
        zone is invulnerable; matched against hit tags in a later tier).
    """

    name: str = ""
    inflate: tuple[float, float] = (0.0, 0.0)
    mult: float = 1.0
    tags: tuple[str, ...] = field(default=())


def read_hurtbox_zones(raw: Any, where: str) -> tuple[HurtboxZoneDef, ...] | None:
    """Parse the optional ``hurtbox_zones`` list.

    ``None`` (field absent) keeps the legacy fallback on
    ``hurtbox_inflate``; a present list must hold at least one zone.

    Raises
    ------
    GameplayDataError
        On a non-list payload, a non-object zone, a missing/malformed
        zone, a non-positive ``mult``, or malformed ``tags``.
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise GameplayDataError(f"{where}: must be a list of zone objects, got {raw!r}")
    zones: list[HurtboxZoneDef] = []
    for index, zone_raw in enumerate(raw):
        zone_where = f"{where}[{index}]"
        if not isinstance(zone_raw, dict):
            raise GameplayDataError(f"{zone_where}: must be an object, got {zone_raw!r}")
        try:
            inflate_raw = zone_raw.get("inflate", [0.0, 0.0])
            if not isinstance(inflate_raw, list) or len(inflate_raw) != 2:
                raise ValueError(inflate_raw)
            inflate = (float(inflate_raw[0]), float(inflate_raw[1]))
            mult = float(zone_raw.get("mult", 1.0))
        except (TypeError, ValueError) as exc:
            raise GameplayDataError(f"{zone_where}: invalid numeric value: {exc}") from exc
        if not mult > 0.0:
            raise GameplayDataError(f"{zone_where}.mult: must be strictly positive")
        tags_raw = zone_raw.get("tags", [])
        if not isinstance(tags_raw, list) or not all(isinstance(tag, str) for tag in tags_raw):
            raise GameplayDataError(f"{zone_where}.tags: must be a list of strings")
        zones.append(
            HurtboxZoneDef(
                name=str(zone_raw.get("name", "")),
                inflate=inflate,
                mult=mult,
                tags=tuple(tags_raw),
            )
        )
    if not zones:
        raise GameplayDataError(f"{where}: must contain at least one zone")
    return tuple(zones)


def hurtbox_zones_to_dict(
    zones: Sequence[HurtboxZoneDef] | None,
) -> list[dict[str, Any]] | None:
    """Serialize zones back to their JSON shape (``None`` stays ``None``)."""
    if zones is None:
        return None
    return [
        {
            "name": zone.name,
            "inflate": list(zone.inflate),
            "mult": zone.mult,
            "tags": list(zone.tags),
        }
        for zone in zones
    ]


__all__ = ["HurtboxZoneDef", "hurtbox_zones_to_dict", "read_hurtbox_zones"]

