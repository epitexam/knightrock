"""Architecture resolver driven by ``KNIGHTROCK_ARCH``.

``legacy`` points at the current module tree. ``new`` points at the candidate
packages as they appear; during the early phases both resolve to the same
modules, which is what makes a legacy-vs-legacy run a valid sanity check of
the harness.

The resolver is deliberately the *only* place that maps a logical capability
to a module path, so the runner never imports a concrete package by hand.
"""

from __future__ import annotations

import importlib
import os

LEGACY = "legacy"
NEW = "new"
ARCHES = (LEGACY, NEW)

#: Logical module names that have moved to the candidate tree. Entries are
#: added one capability at a time, after that capability has passed the parity
#: check. Physics is the first migrated tranche.
NEW_PATHS: dict[str, str] = {
    "physics.collisions": "src.simulation.physics.collisions",
    "physics.entity_grid": "src.simulation.physics.entity_grid",
    "physics.gravity": "src.simulation.physics.gravity",
    "physics.movement": "src.simulation.physics.movement",
    "physics.platforms": "src.simulation.physics.platforms",
    "physics.spatial_hash": "src.simulation.physics.spatial_hash",
    "physics.spatial_query": "src.simulation.physics.spatial_query",
    "physics.velocity": "src.simulation.physics.velocity",
    "combat.attack_data": "src.simulation.combat.attack_data",
    "combat.attack_loading": "src.simulation.combat.attack_loading",
    "combat.attack_state": "src.simulation.combat.attack_state",
    "combat.charge_handler": "src.simulation.combat.charge_handler",
    "combat.combatant_protocol": "src.simulation.combat.combatant_protocol",
    "combat.combat_component": "src.simulation.combat.combat_component",
    "combat.combo_tracker": "src.simulation.combat.combo_tracker",
    "combat.determinism": "src.simulation.combat.determinism",
    "combat.frame_data": "src.simulation.combat.frame_data",
    "combat.hitbox_manager": "src.simulation.combat.hitbox_manager",
    "combat.hit_resolver": "src.simulation.combat.hit_resolver",
    "combat.knockback": "src.simulation.combat.knockback",
    "combat.null_combat": "src.simulation.combat.null_combat",
    "combat.refusal": "src.simulation.combat.refusal",
    "combat.shapes": "src.simulation.combat.shapes",
    "combat.sweep": "src.simulation.combat.sweep",
    "core.input.bindings_codec": "src.platform.input.bindings_codec",
    "core.input.device_registry": "src.platform.input.device_registry",
    "core.input.event_router": "src.platform.input.event_router",
    "core.input.input_bindings": "src.platform.input.input_bindings",
    "core.input.input_manager": "src.platform.input.input_manager",
    "core.input.input_provider": "src.platform.input.input_provider",
    "core.input.input_state": "src.shared.input_state",
}


def current_arch() -> str:
    arch = os.environ.get("KNIGHTROCK_ARCH", LEGACY)
    if arch not in ARCHES:
        raise ValueError(f"unknown KNIGHTROCK_ARCH {arch!r}; expected one of {ARCHES}")
    return arch


def module_name(logical: str) -> str:
    """Resolve ``core.level.level`` to the importable module for this arch."""
    if current_arch() == NEW and logical in NEW_PATHS:
        return NEW_PATHS[logical]
    return f"src.{logical}"


def import_module(logical: str):  # type: ignore[no-untyped-def]
    return importlib.import_module(module_name(logical))
