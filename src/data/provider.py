"""Single entry point loading all gameplay data (Phase 3 #4).

Source of truth: the JSON files in ``data/gameplay/``, and only them. The
attacks, the enemies and the player are required; only the level list keeps a
built-in fallback. They used
to be shadowed by hand-maintained copies in Python -- ``src/combat/attack_data.py``
held all fourteen attacks a second time, with a CI test asserting the two were
equal. That test's failure mode was a repr rather than a diff, and a field added
to one side was silently absent from the other.

``src/combat/attack_data.py`` is now a lazy shim that reads ``attacks.json``, so
there is one copy of the balance and it is the one the game loads. ``attacks.json``
is therefore required: a malformed one raises (:class:`GameplayDataError`), and a
missing one raises too. Booting on a balance nobody reviewed is a worse outcome
than not booting.

:class:`GameplayData` is a plain value bundle -- attack sets, enemy configs, the
player config and the level registry.

``KNIGHTROCK_DATA_DIR`` may point at an alternate root containing
``gameplay/*.json`` (modders, tests).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from src.combat.frame_data import AttackDefinition, MoveId
from src.data.attacks import ATTACKS_FILENAME, read_attacks_file
from src.data.enemies import ENEMIES_FILENAME, read_enemies_file
from src.data.levels import LEVELS_FILENAME, read_levels_file
from src.data.player import PLAYER_FILENAME, read_player_file
from src.data.roots import gameplay_data_root
from src.entities.enemies.schema import EnemyConfig
from src.entities.player_config import PlayerConfig

logger = logging.getLogger(__name__)

# The gameplay JSON files are tracked in the repository (unlike ``assets/``,
# which is git-ignored and only materialized at build time), so designers can
# review and edit gameplay values in a pull request.


@dataclass(frozen=True)
class GameplayData:
    """Every gameplay value group in one immutable bundle."""

    attack_sets: Mapping[str, dict[MoveId, AttackDefinition]]
    enemies: Mapping[str, EnemyConfig]
    player: PlayerConfig
    levels: Mapping[int, str]


def load_gameplay_data(root: str | Path | None = None) -> GameplayData:
    """Load every gameplay JSON file.

    ``attacks.json`` is required and raises if it is missing or malformed. It
    used to fall back to a second copy of the tables kept in
    ``src/combat/attack_data.py`` -- which is now a shim that reads this same
    file, so there is nothing to fall back to, and a game that booted on
    unreviewed balance would be worse than one that refuses to start.
    """
    directory = Path(root) if root is not None else gameplay_data_root()

    attacks_path = directory / ATTACKS_FILENAME
    attack_sets: dict[str, dict[MoveId, AttackDefinition]] = read_attacks_file(attacks_path)

    # Required, like the attacks, and for the same reason: the Python copies
    # these files used to fall back on were a second source of truth, and the
    # debug bench and the enemy-type check read that copy rather than the file
    # (audit C4). A missing file now raises from the reader.
    enemies: dict[str, EnemyConfig] = read_enemies_file(directory / ENEMIES_FILENAME, attack_sets)
    player: PlayerConfig = read_player_file(directory / PLAYER_FILENAME, attack_sets)

    levels: dict[int, str]
    levels_path = directory / LEVELS_FILENAME
    if levels_path.exists():
        levels = read_levels_file(levels_path)
    else:
        logger.warning("Gameplay JSON %s missing: using built-in level paths", levels_path)
        from src.core.level.level_manager import LEVEL_PATHS

        levels = dict(LEVEL_PATHS)

    return GameplayData(attack_sets=attack_sets, enemies=enemies, player=player, levels=levels)


@cache
def shipped_gameplay_data() -> GameplayData:
    """The gameplay data under :func:`gameplay_data_root`, loaded once.

    For the code that builds a fighter without being handed a bundle -- a
    ``Player`` or an enemy made outside a level, the tests -- so that what it
    gets is the files and not a copy of them. ``Game`` loads its own bundle
    from the same place.
    """
    return load_gameplay_data()
