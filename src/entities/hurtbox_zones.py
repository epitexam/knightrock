"""Configuration and derivation helpers for multi-hurtbox zones (P2, axe B).

A zone is a named damage-receiving area derived from the entity's pushbox:
``box = pushbox.inflate(inflate)`` re-centered on the pushbox center, with a
localized damage multiplier and reserved invulnerability tags. The legacy
single-hurtbox behavior is exactly one unnamed zone carrying the entity's
``hurtbox_inflate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


__all__ = ["HurtboxZoneDef"]
