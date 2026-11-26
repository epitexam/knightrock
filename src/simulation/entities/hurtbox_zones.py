"""Configuration and derivation helpers for multi-hurtbox zones (P2, axe B).

A zone is a named damage-receiving area derived from the entity's pushbox:
``box = pushbox.inflate(inflate)`` centred on the pushbox centre moved down by
``offset_y``, with a localized damage multiplier and reserved invulnerability
tags. Without the offset every zone shared the body's centre, so a ``head``
was a band across the middle of the body. The legacy
single-hurtbox behavior is exactly one unnamed zone carrying the entity's
``hurtbox_inflate``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from src.simulation.data.errors import GameplayDataError


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
        Static invulnerability tags matched against hit tags.
    invuln_states :
        Runtime states in which the zone is invulnerable. The built-in
        ``airborne`` state is activated when the entity has no floor contact.
    offset_y :
        How far below the pushbox centre the zone is centred, in pixels;
        negative raises it. The horizontal centre is the body's.
    """

    name: str = ""
    inflate: tuple[float, float] = (0.0, 0.0)
    mult: float = 1.0
    tags: tuple[str, ...] = field(default=())
    invuln_states: tuple[str, ...] = field(default=())
    offset_y: float = 0.0


def _string_list(raw: Any, where: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
        raise GameplayDataError(f"{where}: must be a list of strings")
    return tuple(raw)


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
            offset_y = float(zone_raw.get("offset_y", 0.0))
        except (TypeError, ValueError) as exc:
            raise GameplayDataError(f"{zone_where}: invalid numeric value: {exc}") from exc
        if not mult > 0.0:
            raise GameplayDataError(f"{zone_where}.mult: must be strictly positive")
        tags = _string_list(zone_raw.get("tags", []), f"{zone_where}.tags")
        invuln_states = _string_list(
            zone_raw.get("invuln_states", []), f"{zone_where}.invuln_states"
        )
        zones.append(
            HurtboxZoneDef(
                name=str(zone_raw.get("name", "")),
                inflate=inflate,
                mult=mult,
                tags=tags,
                invuln_states=invuln_states,
                offset_y=offset_y,
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
            **({"invuln_states": list(zone.invuln_states)} if zone.invuln_states else {}),
            **({"offset_y": zone.offset_y} if zone.offset_y else {}),
        }
        for zone in zones
    ]


__all__ = ["HurtboxZoneDef", "hurtbox_zones_to_dict", "read_hurtbox_zones"]
