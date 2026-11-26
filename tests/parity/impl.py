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
    "core.display.__init__": "src.presentation.display.__init__",
    "core.display.detection": "src.presentation.display.detection",
    "core.display.framing": "src.presentation.display.framing",
    "core.display.letterbox": "src.presentation.display.letterbox",
    "core.display.monitors": "src.presentation.display.monitors",
    "core.display.presentation": "src.presentation.display.presentation",
    "core.display.sdl_probe": "src.presentation.display.sdl_probe",
    "core.display.stage": "src.presentation.display.stage",
    "core.display.viewport": "src.presentation.display.viewport",
    "core.display.window_watch": "src.presentation.display.window_watch",
    "core.rendering.__init__": "src.presentation.rendering.__init__",
    "core.rendering.afterimages": "src.presentation.rendering.afterimages",
    "core.rendering.camera": "src.presentation.rendering.camera",
    "core.rendering.overlay": "src.presentation.rendering.overlay",
    "core.rendering.render_hints": "src.presentation.rendering.render_hints",
    "core.rendering.renderer": "src.presentation.rendering.renderer",
    "core.rendering.sprite_transforms": "src.presentation.rendering.sprite_transforms",
    "core.rendering.static_layer": "src.presentation.rendering.static_layer",
    "core.rendering.strike_trails": "src.presentation.rendering.strike_trails",
    "core.rendering.tile_chunk_index": "src.presentation.rendering.tile_chunk_index",
    "core.fx.__init__": "src.presentation.fx.__init__",
    "core.fx.draw": "src.presentation.fx.draw",
    "core.fx.frames": "src.presentation.fx.frames",
    "core.fx.particles": "src.presentation.fx.particles",
    "core.fx.spawners": "src.presentation.fx.spawners",
    "core.fx.tuning": "src.presentation.fx.tuning",
    "ui.__init__": "src.presentation.ui.__init__",
    "ui.controls_view": "src.presentation.ui.controls_view",
    "ui.fonts": "src.presentation.ui.fonts",
    "ui.grid_view": "src.presentation.ui.grid_view",
    "ui.hud": "src.presentation.ui.hud",
    "ui.menu_model": "src.presentation.ui.menu_model",
    "ui.menu_view": "src.presentation.ui.menu_view",
    "ui.metrics": "src.presentation.ui.metrics",
    "ui.panel_renderer": "src.presentation.ui.panel_renderer",
    "ui.pixel": "src.presentation.ui.pixel",
    "ui.player_ui": "src.presentation.ui.player_ui",
    "ui.scale": "src.presentation.ui.scale",
    "ui.styles": "src.presentation.ui.styles",
    "ui.text": "src.presentation.ui.text",
    "ui.text_cache": "src.presentation.ui.text_cache",
    "ui.title_backdrop": "src.presentation.ui.title_backdrop",
    "ui.ui_manager": "src.presentation.ui.ui_manager",
    "ui.world_overlay.__init__": "src.presentation.ui.world_overlay.__init__",
    "ui.world_overlay.bars": "src.presentation.ui.world_overlay.bars",
    "ui.world_overlay.cards": "src.presentation.ui.world_overlay.cards",
    "ui.world_overlay.geo": "src.presentation.ui.world_overlay.geo",
    "ui.world_overlay.metrics": "src.presentation.ui.world_overlay.metrics",
    "ui.world_overlay.panels": "src.presentation.ui.world_overlay.panels",
    "ui.world_overlay.shapes": "src.presentation.ui.world_overlay.shapes",
    "ui.world_overlay.shared": "src.presentation.ui.world_overlay.shared",
    "ui.world_overlay.velocity": "src.presentation.ui.world_overlay.velocity",
    "ui.world_ui": "src.presentation.ui.world_ui",
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
