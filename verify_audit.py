#!/usr/bin/env python3
"""
Script de vérification que tous les points de l'audit sont respectés.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class AuditVerifier:
    """Vérifie que tous les points de l'audit sont respectés."""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Tuple[bool, str]]] = {
            "🔴 Architecture": {},
            "🟠 Conception": {},
            "🟡 Qualité": {},
            "🔵 Style": {},
        }
        self.src_path = Path("src")
        
    def verify_all(self):
        """Vérifie tous les points de l'audit."""
        print("=" * 80)
        print("VÉRIFICATION COMPLÈTE DE L'AUDIT")
        print("=" * 80)
        
        # Architecture
        self._check_1_no_goblin_trainingdummy_subclasses()
        self._check_2_no_null_combat_waste()
        self._check_3_unified_config_pattern()
        self._check_4_single_config_import_path()
        
        # Conception
        self._check_5_consistent_pos_annotations()
        self._check_6_player_reference_typing()
        self._check_7_reset_position_complete()
        self._check_8_no_getattr_moving_platforms()
        
        # Qualité
        self._check_9_docstrings_quality()
        self._check_10_no_redundant_reassignment()
        self._check_11_no_duplicate_knockback_logic()
        self._check_12_consistent_exports()
        
        # Style
        self._check_13_class_annotations()
        self._check_14_private_variables_consistency()
        self._check_15_no_duplicate_stagger()
        self._check_16_separated_responsibilities()
        
        # Affichage des résultats
        self._display_results()
        
        # Retourne True si tout est OK
        return self._all_passed()
    
    def _read_file(self, path: str) -> str:
        """Lit un fichier et retourne son contenu."""
        full_path = self.src_path / path
        if not full_path.exists():
            return ""
        return full_path.read_text()
    
    def _check_1_no_goblin_trainingdummy_subclasses(self):
        """Vérifie que Goblin et TrainingDummy n'existent plus comme sous-classes."""
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie qu'il n'y a pas de classe Goblin ou TrainingDummy
        has_goblin = "class Goblin(Enemy)" in enemy_file
        has_dummy = "class TrainingDummy(Enemy)" in enemy_file
        
        if not has_goblin and not has_dummy:
            self.results["🔴 Architecture"]["1. Pas de sous-classes Goblin/TrainingDummy"] = (True, "✅ Goblin et TrainingDummy supprimés")
        else:
            self.results["🔴 Architecture"]["1. Pas de sous-classes Goblin/TrainingDummy"] = (False, "❌ Goblin ou TrainingDummy toujours présents")
    
    def _check_2_no_null_combat_waste(self):
        """Vérifie que combat=None ne crée pas de NullCombatComponent jeté."""
        entity_file = self._read_file("entities/entity.py")
        player_file = self._read_file("entities/player.py")
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie que Player et Enemy créent CombatComponent avant super()
        player_has_combat_init = "combat_component = CombatComponent(" in player_file
        enemy_has_combat_init = "combat_component = CombatComponent(" in enemy_file
        
        # Vérifie que combat est passé à super()
        player_passes_combat = "combat=combat_component" in player_file
        enemy_passes_combat = "combat=combat_component" in enemy_file
        
        if player_has_combat_init and enemy_has_combat_init and player_passes_combat and enemy_passes_combat:
            self.results["🔴 Architecture"]["2. Pas de NullCombatComponent gaspillé"] = (True, "✅ CombatComponent créé avant super().__init__()")
        else:
            self.results["🔴 Architecture"]["2. Pas de NullCombatComponent gaspillé"] = (False, "❌ NullCombatComponent peut être créé et jeté")
    
    def _check_3_unified_config_pattern(self):
        """Vérifie que PlayerConfig existe et est utilisé."""
        player_config_exists = (self.src_path / "entities/player_config.py").exists()
        player_uses_config = "PlayerConfig" in self._read_file("entities/player.py")
        
        if player_config_exists and player_uses_config:
            self.results["🔴 Architecture"]["3. Pattern de config unifié"] = (True, "✅ PlayerConfig dataclass créé et utilisé")
        else:
            self.results["🔴 Architecture"]["3. Pattern de config unifié"] = (False, "❌ PlayerConfig manquant ou non utilisé")
    
    def _check_4_single_config_import_path(self):
        """Vérifie que enemy.py n'importe plus directement les configs."""
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie qu'il n'y a pas d'imports directs de configs
        has_direct_dummy_import = "from src.entities.enemies.types.dummy import DUMMY_CONFIG" in enemy_file
        has_direct_goblin_import = "from src.entities.enemies.types.goblin import GOBLIN_CONFIG" in enemy_file
        
        # Vérifie que factory.py utilise ENEMY_CONFIGS
        factory_file = self._read_file("entities/enemies/factory.py")
        uses_enemy_configs = "ENEMY_CONFIGS" in factory_file
        
        if not has_direct_dummy_import and not has_direct_goblin_import and uses_enemy_configs:
            self.results["🔴 Architecture"]["4. Chemin d'import des configs unifié"] = (True, "✅ enemy.py utilise ENEMY_CONFIGS via factory")
        else:
            self.results["🔴 Architecture"]["4. Chemin d'import des configs unifié"] = (False, "❌ Imports directs de configs dans enemy.py")
    
    def _check_5_consistent_pos_annotations(self):
        """Vérifie que pos a des annotations cohérentes."""
        entity_file = self._read_file("entities/entity.py")
        enemy_file = self._read_file("entities/enemies/enemy.py")
        player_file = self._read_file("entities/player.py")
        
        # Vérifie les annotations dans les signatures __init__
        entity_has_sequence = "pos: Sequence[float] | Vector2" in entity_file
        enemy_has_sequence = "pos: Sequence[float] | Vector2" in enemy_file
        player_has_tuple_or_vector = "pos: tuple[float, float] | pygame.math.Vector2" in player_file
        
        if entity_has_sequence and enemy_has_sequence and player_has_tuple_or_vector:
            self.results["🟠 Conception"]["5. Annotations pos cohérentes"] = (True, "✅ pos utilise Sequence[float] | Vector2 (ou tuple pour Player)")
        else:
            self.results["🟠 Conception"]["5. Annotations pos cohérentes"] = (False, "❌ Annotations pos incohérentes")
    
    def _check_6_player_reference_typing(self):
        """Vérifie que player_reference utilise un Protocol."""
        enemy_file = self._read_file("entities/enemies/enemy.py")
        factory_file = self._read_file("entities/enemies/factory.py")
        
        # Vérifie qu'il y a un PlayerReference Protocol
        has_protocol = "class PlayerReference(Protocol)" in enemy_file
        uses_protocol_in_enemy = "player_reference: PlayerReference" in enemy_file
        uses_protocol_in_factory = "player_reference: PlayerReference" in factory_file
        
        if has_protocol and uses_protocol_in_enemy and uses_protocol_in_factory:
            self.results["🟠 Conception"]["6. Typage player_reference"] = (True, "✅ PlayerReference Protocol utilisé")
        else:
            self.results["🟠 Conception"]["6. Typage player_reference"] = (False, "❌ player_reference toujours typé comme Any")
    
    def _check_7_reset_position_complete(self):
        """Vérifie que reset_position réinitialise le state machine."""
        entity_file = self._read_file("entities/entity.py")
        
        # Vérifie que reset_position appelle state_machine.change_state
        has_state_machine_reset = "state_machine.change_state" in entity_file
        
        if has_state_machine_reset:
            self.results["🟠 Conception"]["7. reset_position complet"] = (True, "✅ reset_position appelle state_machine.change_state('idle')")
        else:
            self.results["🟠 Conception"]["7. reset_position complet"] = (False, "❌ reset_position ne réinitialise pas le state machine")
    
    def _check_8_no_getattr_moving_platforms(self):
        """Vérifie qu'il n'y a plus de getattr pour moving_platforms."""
        entity_file = self._read_file("entities/entity.py")
        
        # Vérifie qu'il n'y a pas de getattr(self, "moving_platforms"
        has_getattr = 'getattr(self, "moving_platforms"' in entity_file or "getattr(self, 'moving_platforms'" in entity_file
        
        # Vérifie que moving_platforms est initialisé dans __init__
        has_init = "self.moving_platforms" in entity_file
        
        if not has_getattr and has_init:
            self.results["🟠 Conception"]["8. Pas de getattr pour moving_platforms"] = (True, "✅ moving_platforms initialisé dans __init__")
        else:
            self.results["🟠 Conception"]["8. Pas de getattr pour moving_platforms"] = (False, "❌ getattr toujours utilisé")
    
    def _check_9_docstrings_quality(self):
        """Vérifie que les docstrings sont de bonne qualité."""
        entity_file = self._read_file("entities/entity.py")
        enemy_file = self._read_file("entities/enemies/enemy.py")
        player_file = self._read_file("entities/player.py")
        
        # Vérifie que les docstrings ne sont pas vides ou incorrectes
        bad_docstrings = [
            '"""Represent a Entity."""',
            '"""Represent an enemy goblin"',
            '"""Represent a non-aggressive training target."""',
            '"""Apply gravity."""',
            '"""Return whether see player."""',
        ]
        
        has_bad_docstrings = any(bad in entity_file or bad in enemy_file or bad in player_file for bad in bad_docstrings)
        
        # Vérifie que les docstrings sont présentes et détaillées
        has_good_entity_docstring = '"""Base class for any game entity' in entity_file
        has_good_enemy_docstring = '"""Enemy entity configured by data' in enemy_file
        has_good_player_docstring = '"""Playable character with full state machine' in player_file
        
        if not has_bad_docstrings and has_good_entity_docstring and has_good_enemy_docstring and has_good_player_docstring:
            self.results["🟡 Qualité"]["9. Docstrings de qualité"] = (True, "✅ Docstrings améliorées (Google-style)")
        else:
            self.results["🟡 Qualité"]["9. Docstrings de qualité"] = (False, "❌ Docstrings vides ou incorrectes")
    
    def _check_10_no_redundant_reassignment(self):
        """Vérifie qu'il n'y a pas de réaffectations redondantes."""
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie qu'il n'y a pas de réaffectations inutiles
        # Comme self.facing_right = True après super().__init__ qui le fait déjà
        has_redundant_facing = enemy_file.count("self.facing_right = True") > 1
        has_redundant_super_armor = enemy_file.count("self.super_armor = ") > 1
        
        if not has_redundant_facing and not has_redundant_super_armor:
            self.results["🟡 Qualité"]["10. Pas de réaffectations redondantes"] = (True, "✅ Pas de réaffectations inutiles")
        else:
            self.results["🟡 Qualité"]["10. Pas de réaffectations redondantes"] = (False, "❌ Réaffectations redondantes présentes")
    
    def _check_11_no_duplicate_knockback_logic(self):
        """Vérifie qu'il n'y a pas de logique de knockback dupliquée."""
        entity_file = self._read_file("entities/entity.py")
        player_file = self._read_file("entities/player.py")
        
        # Vérifie que compute_knockback_direction existe dans entity.py
        has_knockback_helper = "def compute_knockback_direction" in entity_file
        
        # Vérifie que Player utilise cette fonction
        player_uses_helper = "compute_knockback_direction" in player_file
        
        if has_knockback_helper and player_uses_helper:
            self.results["🟡 Qualité"]["11. Pas de logique knockback dupliquée"] = (True, "✅ compute_knockback_direction partagé")
        else:
            self.results["🟡 Qualité"]["11. Pas de logique knockback dupliquée"] = (False, "❌ Logique knockback dupliquée")
    
    def _check_12_consistent_exports(self):
        """Vérifie que __init__.py exporte les bons symboles."""
        enemies_init = self._read_file("entities/enemies/__init__.py")
        
        # Vérifie les exports
        has_enemy = "Enemy" in enemies_init
        has_enemy_config = "EnemyConfig" in enemies_init
        has_enemy_configs = "ENEMY_CONFIGS" in enemies_init
        has_create_enemy = "create_enemy" in enemies_init
        has_is_enemy_type = "is_enemy_type" in enemies_init
        
        # Vérifie que Goblin et TrainingDummy ne sont PAS exportés
        has_goblin = "Goblin" in enemies_init
        has_dummy = "TrainingDummy" in enemies_init
        
        if (has_enemy and has_enemy_config and has_enemy_configs and 
            has_create_enemy and has_is_enemy_type and 
            not has_goblin and not has_dummy):
            self.results["🟡 Qualité"]["12. Exports cohérents"] = (True, "✅ __init__.py exporte EnemyConfig et ENEMY_CONFIGS")
        else:
            self.results["🟡 Qualité"]["12. Exports cohérents"] = (False, "❌ Exports incohérents")
    
    def _check_13_class_annotations(self):
        """Vérifie que Player et Enemy ont des annotations de classe."""
        player_file = self._read_file("entities/player.py")
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie que Player a des annotations de classe
        player_has_annotations = "input_manager: InputManager" in player_file
        player_has_speed = "speed: float" in player_file
        
        # Vérifie que Enemy a des annotations de classe
        enemy_has_annotations = "config: EnemyConfig" in enemy_file
        enemy_has_player = "player: PlayerReference" in enemy_file
        
        if player_has_annotations and player_has_speed and enemy_has_annotations and enemy_has_player:
            self.results["🔵 Style"]["13. Annotations de classe"] = (True, "✅ Player et Enemy ont des annotations de classe")
        else:
            self.results["🔵 Style"]["13. Annotations de classe"] = (False, "❌ Annotations de classe manquantes")
    
    def _check_14_private_variables_consistency(self):
        """Vérifie que les variables privées utilisent _ prefix de manière cohérente."""
        player_file = self._read_file("entities/player.py")
        
        # Vérifie que les variables internes ont _ prefix
        has_private_dash = "_dash_duration_timer" in player_file
        has_private_original = "_original_hitbox_width" in player_file
        has_private_requested = "_dash_requested" in player_file
        has_private_input = "_space_held" in player_file and "_left_held" in player_file
        
        if has_private_dash and has_private_original and has_private_requested and has_private_input:
            self.results["🔵 Style"]["14. Variables privées cohérentes"] = (True, "✅ Variables privées avec _ prefix")
        else:
            self.results["🔵 Style"]["14. Variables privées cohérentes"] = (False, "❌ Variables privées sans _ prefix")
    
    def _check_15_no_duplicate_stagger(self):
        """Vérifie qu'il n'y a pas de méthode stagger dupliquée."""
        entity_file = self._read_file("entities/entity.py")
        enemy_file = self._read_file("entities/enemies/enemy.py")
        
        # Vérifie qu'il n'y a qu'une seule méthode stagger (dans Entity)
        entity_has_stagger = "def stagger(self, duration: float)" in entity_file
        enemy_has_stagger = "def stagger(self, duration: float)" in enemy_file
        
        if entity_has_stagger and not enemy_has_stagger:
            self.results["🔵 Style"]["15. Pas de stagger dupliqué"] = (True, "✅ Une seule méthode stagger dans Entity")
        else:
            self.results["🔵 Style"]["15. Pas de stagger dupliqué"] = (False, "❌ Méthode stagger dupliquée")
    
    def _check_16_separated_responsibilities(self):
        """Vérifie que update() a des responsabilités séparées."""
        player_file = self._read_file("entities/player.py")
        
        # Vérifie que Player a des méthodes privées pour séparer les responsabilités
        has_pre_update = "def _pre_update(self, delta_time: float)" in player_file
        has_post_update = "def _post_update(self, delta_time: float)" in player_file
        has_handle_attack = "def _handle_attack_input(self)" in player_file
        has_update_timers = "def update_timers(self, delta_time: float)" in player_file
        
        if has_pre_update and has_post_update and has_handle_attack and has_update_timers:
            self.results["🔵 Style"]["16. Responsabilités séparées"] = (True, "✅ update() délègue à des méthodes privées")
        else:
            self.results["🔵 Style"]["16. Responsabilités séparées"] = (False, "❌ update() trop monolithique")
    
    def _display_results(self):
        """Affiche les résultats de la vérification."""
        total_passed = 0
        total_failed = 0
        
        print("\n")
        for category, checks in self.results.items():
            print(f"\n{category}")
            print("-" * 80)
            for check_name, (passed, message) in checks.items():
                status = "✅" if passed else "❌"
                print(f"  {status} {check_name}")
                print(f"     {message}")
                if passed:
                    total_passed += 1
                else:
                    total_failed += 1
        
        print("\n" + "=" * 80)
        print(f"RÉSULTATS : {total_passed} ✅ | {total_failed} ❌")
        print("=" * 80)
    
    def _all_passed(self) -> bool:
        """Retourne True si tous les checks sont passés."""
        for category, checks in self.results.items():
            for check_name, (passed, _) in checks.items():
                if not passed:
                    return False
        return True


if __name__ == "__main__":
    verifier = AuditVerifier()
    all_passed = verifier.verify_all()
    
    if all_passed:
        print("\n🎉 TOUS LES POINTS DE L'AUDIT SONT RESPECTÉS ! 🎉\n")
        sys.exit(0)
    else:
        print("\n⚠️  Certains points de l'audit ne sont pas respectés. Voir ci-dessus. ⚠️\n")
        sys.exit(1)
