"""Single entry point loading all gameplay data with fallback (Phase 3 #4).

Source of truth at runtime: the JSON files in ``data/gameplay/``. The
in-code values (``src/combat/attack_data.py`` and siblings) are an
absence-only fallback, never a second source — see the resolution order
below. Parity between both layers is pinned by
``tests/unit/test_gameplay_data.py`` (P0.2): editing one side without the
other fails the suite instead of drifting silently.

:class:`GameplayData` is a plain value bundle — attack sets, enemy configs,
the player config and the level registry — built either from the tracked
JSON files in ``data/gameplay/`` or from the historical in-code values
(fallback, with a warning).  Both layers produce identical frozen
dataclasses, so the simulation cannot tell them apart.

Resolution order per file (JSON errors vs absence):
- file present and valid → use it;
- file present but malformed → :class:`GameplayDataError` (fail loudly:
  a typo must never boot with silently wrong balance);
- file absent → fall back to the in-code source for that file only.

``KNIGHTROCK_DATA_DIR`` may point at an alternate root containing
``gameplay/*.json`` (modders, tests).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.combat.attack_data import GOBLIN_ATTACKS, PLAYER_ATTACKS, SLIME_ATTACKS
from src.combat.frame_data import AttackDefinition
from src.core.paths import resource_path
from src.data.attacks import ATTACKS_FILENAME, read_attacks_file
from src.data.enemies import ENEMIES_FILENAME, read_enemies_file
from src.data.levels import LEVELS_FILENAME, read_levels_file
from src.data.player import PLAYER_FILENAME, read_player_file
from src.entities.enemies.schema import EnemyConfig
from src.entities.player_config import PlayerConfig

logger = logging.getLogger(__name__)

# The gameplay JSON files are tracked in the repository (unlike ``assets/``,
# which is git-ignored and only materialized at build time), so designers can
# review and edit gameplay values in a pull request.
DATA_ROOT = "data"
GAMEPLAY_SUBDIR = "gameplay"

BUILTIN_ATTACK_SETS: dict[str, dict[str, AttackDefinition]] = {
    "player": PLAYER_ATTACKS,
    "goblin": GOBLIN_ATTACKS,
    "slime": SLIME_ATTACKS,
}


@dataclass(frozen=True)
class GameplayData:
    """Every gameplay value group in one immutable bundle."""

    attack_sets: Mapping[str, dict[str, AttackDefinition]] = field(default_factory=dict)
    enemies: Mapping[str, EnemyConfig] = field(default_factory=dict)
    player: PlayerConfig | None = None
    levels: Mapping[int, str] = field(default_factory=dict)


def gameplay_data_root() -> Path:
    """Resolve the root holding ``gameplay/*.json``."""
    override = os.environ.get("KNIGHTROCK_DATA_DIR")
    base = Path(override) if override else Path(resource_path(DATA_ROOT))
    return base / GAMEPLAY_SUBDIR


def _fallback_enemy_configs(
    attack_sets: Mapping[str, dict[str, AttackDefinition]],
) -> dict[str, EnemyConfig]:
    """Rebuild the historical enemy table (mirror of ``configs.py``)."""
    from src.entities.enemies.types.dummy import DUMMY_CONFIG
    from src.entities.enemies.types.goblin import GOBLIN_CONFIG
    from src.entities.enemies.types.slime import SLIME_CONFIG

    _ = attack_sets  # enemy configs carry their own attack tables
    return {
        "goblin": GOBLIN_CONFIG,
        "dummy": DUMMY_CONFIG,
        "slime": SLIME_CONFIG,
    }


def load_gameplay_data(root: str | Path | None = None) -> GameplayData:
    """Load every gameplay JSON file, falling back per missing file."""
    directory = Path(root) if root is not None else gameplay_data_root()

    attack_sets: dict[str, dict[str, AttackDefinition]] = dict(BUILTIN_ATTACK_SETS)
    attacks_path = directory / ATTACKS_FILENAME
    if attacks_path.exists():
        attack_sets = read_attacks_file(attacks_path)
    else:
        logger.warning("Gameplay JSON %s missing: using built-in attack sets", attacks_path)

    enemies: dict[str, EnemyConfig]
    enemies_path = directory / ENEMIES_FILENAME
    if enemies_path.exists():
        enemies = read_enemies_file(enemies_path, attack_sets)
    else:
        logger.warning("Gameplay JSON %s missing: using built-in enemy configs", enemies_path)
        enemies = _fallback_enemy_configs(attack_sets)

    player: PlayerConfig | None = None
    player_path = directory / PLAYER_FILENAME
    if player_path.exists():
        player = read_player_file(player_path, attack_sets)
    else:
        logger.warning("Gameplay JSON %s missing: using built-in player config", player_path)

    levels: dict[int, str]
    levels_path = directory / LEVELS_FILENAME
    if levels_path.exists():
        levels = read_levels_file(levels_path)
    else:
        logger.warning("Gameplay JSON %s missing: using built-in level paths", levels_path)
        from src.core.level.level_manager import LEVEL_PATHS

        levels = dict(LEVEL_PATHS)

    return GameplayData(attack_sets=attack_sets, enemies=enemies, player=player, levels=levels)


def describe_gameplay_source(data: GameplayData) -> dict[str, Any]:
    """Summarize a bundle for the debug scene (counts, not values)."""
    return {
        "attack_sets": sorted(data.attack_sets),
        "attacks": {name: sorted(moves) for name, moves in data.attack_sets.items()},
        "enemies": sorted(data.enemies),
        "player_loaded": data.player is not None,
        "levels": sorted(data.levels),
    }
