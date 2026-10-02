"""The shipped attack tables, loaded from ``data/gameplay/attacks.json``.

This module used to *be* the tables -- 545 lines of ``AttackDefinition(...)``
constructors that the JSON duplicated field for field, with a CI test asserting
the two were equal. Two hand-maintained copies of the same fourteen attacks is
two places to forget a field, and the forgetting was silent: an edited dataclass
that missed its JSON twin produced a failing equality assertion whose message
was a repr, not a diff.

The tables now come from the data file, which is the source the game already
loaded at runtime -- ``src/data/provider.py`` preferred the JSON and only fell
back here when it was absent, so for every shipped build this module was a
*copy* of what the game used.

``PLAYER_ATTACKS`` and friends resolve lazily through :pep:`562`, on first
access rather than at import, so importing this module costs nothing until
something wants a table. The attributes still exist as module attributes, so
``from src.combat.attack_data import PLAYER_ATTACKS`` keeps working across the
dozen modules and tests that read them.

Not a fallback any more. A missing or malformed ``attacks.json`` is an error:
booting on a different balance than the one that was reviewed is worse than not
booting.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

from src.combat.frame_data import MoveId, move_id

if TYPE_CHECKING:  # pragma: no cover - declarations for the type checker
    from src.combat.frame_data import AttackDefinition

    # Declared, not bound: the real values arrive through :func:`__getattr__`
    # below. A module-level assignment would read the data file at import, which
    # is the whole thing this shim is for -- and it would run the loader before
    # the classes the loader imports.
    PLAYER_ATTACKS: dict[MoveId, AttackDefinition]
    GOBLIN_ATTACKS: dict[MoveId, AttackDefinition]
    SLIME_ATTACKS: dict[MoveId, AttackDefinition]

__all__ = ["GOBLIN_ATTACKS", "PLAYER_ATTACKS", "SLIME_ATTACKS", "move_id"]


@cache
def _attack_sets() -> dict[str, dict[MoveId, AttackDefinition]]:
    """Every attack set, from the data file the game actually plays."""
    from src.data.attacks import ATTACKS_FILENAME, read_attacks_file
    from src.data.roots import gameplay_data_root

    return read_attacks_file(gameplay_data_root() / ATTACKS_FILENAME)


def __getattr__(name: str) -> Any:
    """Resolve a shipped table on first access (:pep:`562`).

    Raises for anything that is not one of the three tables, so a typo here is
    an ``AttributeError`` naming what was asked for rather than a silent ``None``.
    """
    if name in ("PLAYER_ATTACKS", "GOBLIN_ATTACKS", "SLIME_ATTACKS"):
        table = dict(_attack_sets()[name.removesuffix("_ATTACKS").lower()])
        globals()[name] = table
        return table
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
