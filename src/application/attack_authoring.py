"""Authoring export for replayed attacks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from src.combat.frame_data import AttackDefinition
from src.data.attacks import write_attacks_file


def export_attack(
    attack_sets: Mapping[str, Mapping[str, AttackDefinition]],
    attack_name: str,
    destination: str | Path | None = None,
) -> Path:
    """Export one attack by name without modifying runtime data files."""
    matches: dict[str, dict[str, AttackDefinition]] = {}
    for set_name, attacks in attack_sets.items():
        if attack_name in attacks:
            matches[set_name] = {attack_name: attacks[attack_name]}
    if not matches:
        raise KeyError(f"Unknown attack: {attack_name}")
    root = Path(
        destination
        if destination is not None
        else os.environ.get("KNIGHTROCK_EXPORT_DIR", Path.home() / ".knightrock" / "exports")
    )
    return write_attacks_file(root / f"{attack_name}.json", matches)
