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
    "entities.__init__": "src.simulation.entities.__init__",
    "entities.attack_moves": "src.simulation.entities.attack_moves",
    "entities.components.__init__": "src.simulation.entities.components.__init__",
    "entities.components.animation_publisher": "src.simulation.entities.components.animation_publisher",
    "entities.components.doom": "src.simulation.entities.components.doom",
    "entities.components.environment": "src.simulation.entities.components.environment",
    "entities.components.movement": "src.simulation.entities.components.movement",
    "entities.components.reaction": "src.simulation.entities.components.reaction",
    "entities.enemies.__init__": "src.simulation.entities.enemies.__init__",
    "entities.enemies.enemy": "src.simulation.entities.enemies.enemy",
    "entities.enemies.factory": "src.simulation.entities.enemies.factory",
    "entities.enemies.schema": "src.simulation.entities.enemies.schema",
    "entities.entity": "src.simulation.entities.entity",
    "entities.hurtbox_zones": "src.simulation.entities.hurtbox_zones",
    "entities.id_factory": "src.simulation.entities.id_factory",
    "entities.player": "src.simulation.entities.player",
    "entities.player_animation": "src.simulation.entities.player_animation",
    "entities.player_config": "src.simulation.entities.player_config",
    "entities.player_controllers": "src.simulation.entities.player_controllers",
    "entities.player_input": "src.simulation.entities.player_input",
    "entities.player_kit": "src.simulation.entities.player_kit",
    "entities.projectile": "src.simulation.entities.projectile",
    "entities.shots": "src.simulation.entities.shots",
    "entities.vitals": "src.simulation.entities.vitals",
    "states.__init__": "src.simulation.states.__init__",
    "states.enemy_states": "src.simulation.states.enemy_states",
    "states.ledge_state": "src.simulation.states.ledge_state",
    "states.null_state_machine": "src.simulation.states.null_state_machine",
    "states.player_states": "src.simulation.states.player_states",
    "states.reaction_states": "src.simulation.states.reaction_states",
    "states.state_machine": "src.simulation.states.state_machine",
    "states.state_names": "src.simulation.states.state_names",
    "states.turn_state": "src.simulation.states.turn_state",
    "data.__init__": "src.simulation.data.__init__",
    "data.attack_writer": "src.simulation.data.attack_writer",
    "data.attacks": "src.simulation.data.attacks",
    "data.enemies": "src.simulation.data.enemies",
    "data.errors": "src.simulation.data.errors",
    "data.levels": "src.simulation.data.levels",
    "data.player": "src.simulation.data.player",
    "data.provider": "src.simulation.data.provider",
    "data.roots": "src.simulation.data.roots",
    "core.ecs.__init__": "src.simulation.ecs.__init__",
    "core.ecs.combat_table": "src.simulation.ecs.combat_table",
    "core.ecs.geometry_table": "src.simulation.ecs.geometry_table",
    "core.ecs.movement_table": "src.simulation.ecs.movement_table",
    "core.ecs.presentation": "src.simulation.ecs.presentation",
    "core.ecs.projectile_table": "src.simulation.ecs.projectile_table",
    "core.ecs.table": "src.simulation.ecs.table",
    "core.ecs.vitals_table": "src.simulation.ecs.vitals_table",
    "core.level.__init__": "src.simulation.level.__init__",
    "core.level.level": "src.simulation.level.level",
    "core.level.level_data": "src.simulation.level.level_data",
    "core.level.level_manager": "src.simulation.level.level_manager",
    "core.level.level_registry": "src.simulation.level.level_registry",
    "core.level.properties": "src.simulation.level.properties",
    "core.level.scene_host": "src.simulation.level.scene_host",
    "core.level.systems.__init__": "src.simulation.level.systems.__init__",
    "core.level.systems.camera_system": "src.simulation.level.systems.camera_system",
    "core.level.systems.combat_system": "src.simulation.level.systems.combat_system",
    "core.level.systems.combat_trace": "src.simulation.level.systems.combat_trace",
    "core.level.systems.contact_damage": "src.simulation.level.systems.contact_damage",
    "core.level.systems.contact_system": "src.simulation.level.systems.contact_system",
    "core.level.systems.feedback_system": "src.simulation.level.systems.feedback_system",
    "core.level.systems.gameplay_loop": "src.simulation.level.systems.gameplay_loop",
    "core.level.systems.hazard_damage": "src.simulation.level.systems.hazard_damage",
    "core.level.systems.hazard_system": "src.simulation.level.systems.hazard_system",
    "core.level.systems.notification_system": "src.simulation.level.systems.notification_system",
    "core.level.systems.physics_system": "src.simulation.level.systems.physics_system",
    "core.level.systems.platform_system": "src.simulation.level.systems.platform_system",
    "core.level.systems.progression_system": "src.simulation.level.systems.progression_system",
    "core.level.systems.projectile_system": "src.simulation.level.systems.projectile_system",
    "core.level.systems.respawn_system": "src.simulation.level.systems.respawn_system",
    "core.level.systems.separation_system": "src.simulation.level.systems.separation_system",
    "core.level.systems.spawn_system": "src.simulation.level.systems.spawn_system",
    "core.level.systems.tick_system": "src.simulation.level.systems.tick_system",
    "core.level.tmx_adapter": "src.simulation.level.tmx_adapter",
    "core.level.world_builder": "src.simulation.level.world_builder",
    "core.rollback.__init__": "src.simulation.rollback.__init__",
    "core.rollback.rollback": "src.simulation.rollback.rollback",
    "core.rollback.snapshots": "src.simulation.rollback.snapshots",
    "core.animation.__init__": "src.simulation.animation.__init__",
    "core.animation.animator": "src.simulation.animation.animator",
    "core.sprites": "src.simulation.sprites",
    "core.sprite_groups": "src.simulation.sprite_groups",
    "core.hazards": "src.simulation.hazards",
    "core.object_pool": "src.simulation.object_pool",
    "core.settings": "src.simulation.settings",
    "core.atomic_json": "src.simulation.atomic_json",
    "core.assets": "src.platform.assets",
    "core.resource_coordinator": "src.platform.resource_coordinator",
    "core.asset_library": "src.platform.assets",
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
