"""Gameplay data driven by JSON (audit Phase 3 #4).

Dataclasses Python (``AttackDefinition``, ``EnemyConfig``, ``PlayerConfig``)
were the single source of truth — excellent for determinism, opaque for
designers.  This package externalizes the *values* to JSON files under
``assets/data/gameplay/`` while keeping the frozen dataclasses as the
runtime model:

- files are **strict**: unknown keys, missing fields, bad versions and
  unknown attack references raise :class:`GameplayDataError`;
- if a file is missing (older bundle, modder setup), the loader falls
  back to the historical Python values with a warning, so the game never
  refuses to boot for a data problem.

Layout
------
``attacks.json`` groups attacks in named sets (``player``, ``goblin``,
``slime``, ``dummy``); ``enemies.json`` references those sets by name
(or defines attacks inline); ``player.json`` holds overrides plus an
attack-name list; ``levels.json`` maps level ids to TMX paths.

``KNIGHTROCK_DATA_DIR`` may point at an alternate root containing
``gameplay/*.json`` (modders, tests).
"""
