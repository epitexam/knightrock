"""Gameplay data driven by JSON (audit Phase 3 #4).

Dataclasses Python (``AttackDefinition``, ``EnemyConfig``, ``PlayerConfig``)
were the single source of truth — excellent for determinism, opaque for
designers.  This package externalizes the *values* to JSON files under
``data/gameplay/`` (tracked in git, unlike ``assets/``) while keeping the
frozen dataclasses as the runtime model:

- files are **strict**: unknown keys, missing fields, bad versions and
  unknown attack references raise :class:`GameplayDataError`;
- ``attacks.json``, ``enemies.json`` and ``player.json`` are required: there is
  no second Python copy to fall back to, so a missing or malformed balance file
  refuses to boot rather than starting on values nobody reviewed. Only
  ``levels.json`` has a built-in fallback path.

Layout
------
``attacks.json`` groups attacks in named sets (``player``, ``goblin``,
``slime``, ``dummy``); ``enemies.json`` references those sets by name
(or defines attacks inline); ``player.json`` holds overrides plus an
attack-name list; ``levels.json`` maps level ids to TMX paths.

``KNIGHTROCK_DATA_DIR`` may point at an alternate root containing
``gameplay/*.json`` (modders, tests).
"""
