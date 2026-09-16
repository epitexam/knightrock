# Plan de refactoring Knightrock — transmission au prochain agent

## 1. Objectif et périmètre

Réduire le couplage du gameplay, expliciter ses contrats et renforcer les garde-fous sans changer les règles du jeu. Ce plan décrit des travaux à réaliser, pas des changements déjà implémentés.

**Environnement :** Python 3.14, pygame-ce, pytmx, uv ; pytest, pytest-cov, Ruff et mypy déjà présents. Branche observée : `feature/core-rework`.

**Chemins :** relatifs à la racine du dépôt. Exécuter les commandes depuis cette racine.

Baseline historique de l'audit : 511 tests passants, 89 % de couverture des instructions, mypy sans erreur sur 118 fichiers, une erreur d'import Ruff et un fichier non formaté. Remesurer avant intervention. Les performances runtime et la couverture des branches n'ont pas été mesurées.

### Nuances indispensables

- Les quatre composantes cycliques détectées incluaient `TYPE_CHECKING` et les imports locaux. Ce ne sont PAS quatre cycles d'import bloquants démontrés. Le script exploratoire avait aussi des limites sur les imports relatifs : ne pas reprendre son graphe comme preuve définitive.
- Les 61 définitions de méthodes d'Entity incluent beaucoup de propriétés et délégations. Les 773 lignes du fichier ne prouvent pas une « god-class » ; cibler les responsabilités et accès croisés réels.
- Aucun doublon exact de corps de fonction d'au moins 12 lignes détecté ne signifie pas absence de duplication proche.
- Un arbre Git modifié n'est pas un défaut de qualité. Ne jamais committer, stasher ou supprimer le travail de l'utilisateur pour améliorer une note.
- La note de 76/100 est subjective ; les comparaisons avec d'autres projets et gains de points annoncés ne sont pas des benchmarks vérifiés ni des critères de réception.

### Préserver le travail existant

Modifications locales présentes avant l'audit :

- `src/core/level/level.py`
- `src/core/rendering/renderer.py`
- `src/core/settings.py`
- `src/entities/entity.py`

Lire leur diff et conserver leurs fonctionnalités. Un plan antérieur existe dans `notes/refactoring_plan.md` : le lire et réconcilier les travaux déjà effectués, sans écrasement aveugle. Les numéros de lignes de l'audit sont indicatifs ; chercher les symboles.

## 2. Règles et ordre d'exécution

1. Baseline, puis un lot à la fois, avec tests de caractérisation avant déplacement des règles.
2. Préserver ordre des événements, collisions, mises à jour et résultats de simulation/rollback.
3. Pas de nouveau framework, ECS, service locator ou dépendance pour ce chantier.
4. Pas de nouveaux `Any`, `cast`, `type: ignore` ou replis silencieux pour contourner un contrat.
5. Ne pas actualiser les résultats golden uniquement pour masquer une régression.
6. Après chaque lot : tests ciblés, suite complète, Ruff, format check, mypy et revue du diff. Consigner les résultats réels.

| Lot | Priorité | Dépendance | Livrable |
|---|---|---|---|
| RF-0 | Préparation | Aucune | Baseline et corrections mécaniques |
| RF-1 | Haute | RF-0 | Contrats de combat explicites |
| RF-2 | Haute | RF-0 | Assemblage valide avant mutation |
| RF-3 | Haute | RF-1 | Responsabilités des réactions clarifiées |
| RF-4 | Moyenne | RF-0 | Collisions lisibles |
| RF-5 | Moyenne | RF-1 | Résolution des coups simplifiée |
| RF-6 | Moyenne | RF-1 pour le combat | Autres fonctions complexes clarifiées |
| RF-7 | Moyenne | RF-1 à RF-3 | Dépendances et contrat rollback vérifiés |
| RF-8 | Moyenne | Baseline puis autres lots | CI et typage renforcés |

RF-2 et RF-4 sont indépendants de RF-1. Éviter néanmoins de modifier simultanément les mêmes fichiers ou fixtures. Chaque lot doit rester un diff revuable, pas une réécriture globale.

## 3. RF-0 — Baseline et hygiène

Dans `src/entities/entity.py`, corriger uniquement Ruff I001 si encore présent. Dans `src/core/rendering/renderer.py`, reformater l'ajout d'afterimage dans `_ghosts` si nécessaire.

Ne pas convertir les 272 diagnostics exploratoires issus de règles Ruff non activées en corrections automatiques : beaucoup sont stylistiques ou intentionnels.

**Réception :** baseline enregistrée, Ruff et formatage passent, diff mécanique isolé et aucun travail utilisateur perdu.

## 4. RF-1 — Contrats explicites du combat

### Fichiers

- `src/combat/combatant_protocol.py`
- `src/combat/hit_resolver.py`
- `src/combat/combat_component.py`
- `src/entities/entity.py`
- `src/core/level/systems/projectile_system.py`
- `src/entities/projectile.py`
- `tests/unit/helpers.py`

`HitResolver` annonce des `Combatant` mais sonde `on_surface`, `otg_timer`, `set_juggle`, `combat.air_combo_count`, puis `record_hit_landed` avec repli vers `combo.on_hit_landed`. Les défauts silencieux masquent des contrats incomplets.

### Étapes

1. Inventorier les appelants, projectiles et doubles de tests inclus. Distinguer les besoins de l'attaquant de ceux de la cible : ne pas exiger santé et réactions d'un objet qui ne fait que porter un coup.
2. Compléter les protocoles existants, ou introduire deux vues étroites si l'asymétrie le justifie. Préférer des propriétés en lecture seule lorsque possible.
3. Réutiliser `record_hit_landed`, déjà présent sur `CombatComponent` et `NullCombatComponent`.
4. Remplacer les sondages concernés par des accès typés ; adapter les doubles incomplets plutôt que garder des fallbacks pour eux. Documenter les capacités vraiment optionnelles et leur absence.
5. Conserver formules et ordre des effets ; reporter la décomposition algorithmique à RF-5. Ne pas supprimer globalement tout `getattr` du projet.

### Tests et réception

Étendre selon les cas :

- `tests/unit/test_damage_resolution.py`
- `tests/unit/test_juggle.py`
- `tests/unit/test_knockback_feel.py`
- `tests/unit/test_projectile_system.py`
- `tests/unit/test_type_annotations.py`

Vérifier combo enregistré une seule fois, sol/air, OTG autorisé/interdit, composant neutre, projectile normal/perçant, immunité et blocage sans effets secondaires. Les contrats doivent être vérifiables statiquement ; un test runtime seul ne suffit pas. Aucun fallback supprimé sans migration des appelants.

## 5. RF-2 — Assemblage valide de GameplayLoop

### Fichiers

- `src/core/level/systems/gameplay_loop.py`
- `src/core/level/level.py`
- `tests/headless/test_gameplay_loop.py`
- `tests/headless/test_level_orchestration.py`
- `tests/unit/test_simulation_and_config.py`
- `tests/unit/test_hitbox_pipeline.py`

Le constructeur accepte 12 systèmes optionnels. `update()` en exige plusieurs via `_require`, mais `spawn.process()` et `begin_tick()` précèdent la validation complète : la promesse d'échec avant mutation est trop forte.

**Direction préférée :** rendre obligatoires les étapes nécessaires à une boucle complète, avec paramètres nommés. Les tests du cœur combat/séparation doivent utiliser des fixtures d'assemblage explicites. Extraire une classe distincte uniquement si l'usage autonome le justifie.

Si une transition impose une boucle partielle, valider complètement à l'entrée d'`update`, avant toute mutation. Ce n'est pas équivalent à une construction valide par défaut. Conserver les extensions réellement facultatives.

### Étapes et invariants

1. Caractériser l'ordre courant avec des doubles enregistrant les appels.
2. Tester qu'un câblage invalide ne modifie ni cooldown, ni hit-stop, ni groupes, ni tick, ni rollback ; idéalement il échoue dès la construction.
3. Adapter `Level` et tous les tests utilisant `GameplayLoop()` nu.
4. Préserver l'ordre spawn, plateformes, hazards, intégration, séparation/combat, projectiles, dégâts de contact/hazards, retrait des morts, respawn, progression.
5. Préserver caméra, notifications et bookkeeping pendant le hit-stop ; le tick faisant expirer le hit-stop reste suspendu conformément au test existant.
6. Factoriser éventuellement la fin commune sans doubler les notifications/snapshots ni changer les deltas.

**Réception :** câblage invalide rejeté avant mutation, ordre inchangé, tests headless et rollback passants, aucun assemblage implicite uniquement destiné aux tests.

## 6. RF-3 — Réactions : propriété et mutations

### Fichiers

- `src/entities/entity.py`
- `src/entities/components/reaction.py`
- `src/entities/components/movement.py`
- `src/entities/vitals.py`
- `src/states/reaction_states.py`
- `src/entities/player.py`

`ReactionComponent` reçoit l'Entity entière et intervient sur vélocité, protections, temporisateurs, combat et machine à états. La séparation en fichier n'a pas entièrement séparé les responsabilités.

1. Documenter pour chaque donnée son propriétaire, ses écrivains autorisés, son reset et son snapshot : vélocité/contacts, santé/protections, stagger, juggle/OTG, états de combat et de réaction.
2. Définir une vue étroite basée sur les opérations nécessaires. Un protocole recopiant toute Entity ne réduit pas le couplage.
3. Remplacer l'écriture directe `owner.combat.is_hurt = False` protégée par `hasattr` par une opération métier. Vérifier si `reset_hurt_state` a les mêmes effets sur les timers avant de l'utiliser.
4. Conserver `receive_damage` comme entrée publique et le blocage spécifique à Player. Garantir une autorité claire pour interruption, lancement lourd et stagger.
5. Conserver les façades utiles ; ne pas viser arbitrairement moins de lignes. Ne déplacer juggle/OTG qu'avec reset et restauration cohérents.

### Tests et réception

Étendre les tests pertinents :

- `tests/unit/test_reaction_states.py`
- `tests/unit/test_reaction_friction.py`
- `tests/unit/test_reset_position.py`
- `tests/unit/test_rollback_snapshots.py`
- `tests/headless/test_rollback_e2e.py`

Réception : propriété documentée, interface limitée, aucun état dupliqué, blocage/super-armure/lancement/stagger préservés, round-trip save/load et reset cohérents. Séparer tout correctif fonctionnel découvert du déplacement structurel.

## 7. RF-4 — Résolution des collisions

**Cible :** `src/physics/collisions.py`, fonction `resolve_collisions`, complexité Ruff historique 18.

1. Lire aussi `src/physics/movement.py` : sous-pas et cache des voisins conditionnent la résolution.
2. Caractériser les deux axes, signes de vélocité, contact marginal, chevauchement profond, sol/plafond/murs, plateformes one-way et ordre de plusieurs obstacles.
3. Extraire des décisions nommées : éligibilité d'un obstacle, résolution horizontale/verticale, application d'une correction. Réutiliser les helpers existants de step-up, corner-correction et correction plafonnée.
4. Préserver `old_hitbox`, ordre des candidats, tolérances, plafonds de correction, signalement crushed, rebond en knockback et synchronisation des rectangles.
5. Préserver l'absence de requêtes spatiales redondantes lorsque les voisins sont déjà fournis. Ne pas introduire un tri nouveau ou une allocation par obstacle sans justification.

### Matrice de tests

- `tests/unit/test_collisions.py`
- `tests/unit/test_collisions_extra.py`
- `tests/unit/test_collision_robustness.py`
- `tests/unit/test_one_way_platforms.py`
- `tests/unit/test_game_feel.py`
- `tests/unit/test_movement_collision_cache.py`
- `tests/unit/test_knockback_feel.py`
- `tests/headless/test_simulation_golden.py`

**Réception :** mêmes positions, vélocités et contacts pour les scénarios caractérisés ; complexité réduite dans les fonctions ET logique plus compréhensible. Viser C901 <= 10 par fonction, mais documenter une exception justifiée plutôt que découper artificiellement. Pas de promesse de gain de FPS sans mesure.

## 8. RF-5 — Décomposer HitResolver sans changer les règles

**Cible :** `src/combat/hit_resolver.py`, `resolve`, complexité Ruff historique 13. Dépend de RF-1.

Séparer calculs purs et application des effets lorsque cela clarifie les règles : admissibilité OTG, modificateurs de dégâts/knockback, puis réactions après résultat. Garder une orchestration linéaire explicite plutôt qu'une chaîne de stratégies générique.

### Invariants à caractériser

- Les compteurs de combo utilisés pour calculer la décroissance sont ceux AVANT l'enregistrement du coup.
- Charge, résistance, décroissance et plancher juggle conservent leurs formules et leur ordre.
- Finisher conserve son seuil et son interaction avec les modificateurs.
- Blocage, immunité ou dégâts non appliqués arrêtent les effets secondaires.
- Super-armure, bris d'armure, lancement lourd et stagger ne s'appliquent pas deux fois.
- La mortalité et les champs de `DamageResult` restent cohérents ; les effets de juggle et combo conservent la sémantique courante caractérisée.

**Validation :** tests RF-1 plus `tests/unit/test_combat_behaviors.py`. Ajouter des cas combinés et limites numériques avec pytest, sans dépendance supplémentaire. Réception : résultat identique, fonctions nommées par leur rôle métier, aucun sondage dynamique réintroduit.


## 9. RF-6 — Trois autres points de complexité

### CombatSystem._collect_candidates — C901 historique 13

Fichier : `src/core/level/systems/combat_system.py`.

Séparer filtres d'éligibilité et collecte géométrique sans changer les deux passes collecte/résolution. Préserver ordre déterministe, factions, auto-exclusion, plusieurs hitbox, déduplication des cibles et suivi par phase. Vérifier métriques et collisions simultanées ; conserver les recherches locales via EntityGrid.

Tests : `tests/unit/test_hitbox_pipeline.py`, `tests/unit/test_entity_pairing_systems.py` et `tests/headless/test_entity_grid_integration.py`.

### SpawnSystem.process — C901 historique 12

Fichier : `src/core/level/systems/spawn_system.py`.

Séparer décrément des cooldowns, spawn d'ennemis et commandes de démonstration. Une table de commandes n'est utile que si elle simplifie les règles. Préserver ordre, touches maintenues/pressées, délais, projectiles facultatifs et attributs utilisés par l'UI debug. Ne pas modifier les contrôles.

Tests : `tests/unit/test_debug_commands.py` et `tests/unit/test_level_world_systems.py`. Ajouter les cas de cooldown et d'actions simultanées manquants.

### PlayerInputHandler._handle_attack_input — C901 historique 12

Fichier : `src/entities/player_input.py`.

Isoler charge active et demande d'attaque. Préserver la priorité : charge active, capacité d'attaquer, spéciale, légère, lourde, uppercut, dash attack. Ne pas transformer les `elif` en actions indépendantes. Préserver légère au sol/aérienne, buffer de légère refusée, annulation de charge, relâchement et fallback de lourde.

Tests : `tests/unit/test_player.py`, `tests/unit/test_player_states.py` et `tests/unit/test_player_controllers.py`. Ajouter si nécessaire un test dédié au handler suivant les conventions existantes.

**Réception commune :** branches métier couvertes, ordre inchangé, complexité réduite sans indirection superflue.

## 10. RF-7 — Frontières et contrat rollback

Dans `src/core/level/systems/tick_system.py`, `TickOwner` expose `save_state`, mais `rollback.record(level)` porte `type: ignore[arg-type]` car `src/core/rollback/rollback.py` attend un `Level` concret.

Faire accepter à `record` la capacité minimale de capture nécessaire. Placer un éventuel protocole partagé dans une couche de contrats adaptée, sans importer le système de tick dans le rollback. Ne pas imposer les besoins de restauration à une opération de capture. Supprimer l'ignore après vérification statique et tests `tests/unit/test_rollback_system.py` et headless rollback.

Si l'analyse d'import est reprise, distinguer imports runtime au premier niveau, `TYPE_CHECKING` et imports locaux ; résoudre correctement imports relatifs et réexports. Examiner l'impact des cycles restants avant toute modification.

`core` contient settings, bootstrap et orchestration : des flèches réciproques entre packages ne démontrent pas une violation de couches. Ne pas déplacer settings ou introduire des interfaces de scènes uniquement pour rendre un graphe acyclique.

**Réception :** contrat de capture cohérent, ignore supprimé sans dépendance inversée artificielle, démarrage sans rupture d'import. Documenter les dépendances intentionnelles plutôt que promettre « zéro cycle » sans qualification.

## 11. RF-8 — CI, couverture et typage progressif

Fichiers :

- `pyproject.toml`
- `.github/workflows/build.yml`
- `README.md`

1. Après baseline mypy verte dans l'environnement CI, retirer `|| true`. Ce changement peut être livré tôt.
2. Renforcer module par module : contrats/resolver, boucle, réactions, collisions. Réduire les exceptions larges `disallow_untyped_defs = false`, en conservant celles des modules non migrés. Vérifier l'effet des overrides plutôt que supposer une couverture complète du typage.
3. Mesurer séparément instructions et branches : les 89 % historiques ne sont pas directement comparables au pourcentage combiné de `--cov-branch`.
4. Proposer un seuil initial d'instructions de 80 % après confirmation de la baseline. Pour la métrique avec branches, choisir un seuil à partir du résultat mesuré puis l'augmenter progressivement.
5. Tester les branches métier manquantes ; ne pas exclure du code ou ajouter des assertions artificielles pour le score.
6. Envisager C901 comme garde-fou après RF-4 à RF-6 ; justifier les exceptions plutôt qu'utiliser une mesure AST maison.
7. Actualiser commandes, seuils et commentaires de dette dans le README et la configuration.

**Réception :** erreur mypy bloquante, seuil cohérent avec la métrique publiée, Ruff/format/tests bloquants, instructions locales alignées avec la CI.

## 12. Commandes de validation

Utiliser l'environnement déjà synchronisé, sans nouvelle dépendance. `uv run` peut remplacer les exécutables de l'environnement selon les conventions du projet.

```bash
# Depuis la racine du dépôt
git status --short
git diff --stat
git diff --check
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest tests
```

Rapports de couverture séparés, sans comparer leurs pourcentages comme une même métrique :

```bash
# Depuis la racine du dépôt
uv run pytest tests --cov=src --cov-report=term-missing
uv run pytest tests --cov=src --cov-branch --cov-report=term-missing
uv run ruff check src --select C901
```

C901 est diagnostique tant que les cinq écarts historiques ne sont pas traités. Pour chaque lot, exécuter aussi pytest sur les fichiers de tests indiqués dans sa section. Utiliser les fixtures headless existantes ; ne pas assimiler une erreur de dépendance ou d'affichage à une régression métier.

## 13. Réception globale et transmission

- [ ] RF-0 : baseline enregistrée, modifications utilisateur préservées.
- [ ] RF-1 : capacités de combat explicites, appelants et doubles migrés.
- [ ] RF-2 : câblage invalide rejeté avant mutation, ordre du tick préservé.
- [ ] RF-3 : propriété des états documentée, interface des réactions limitée.
- [ ] RF-4 : collisions simplifiées sans changement géométrique ni requêtes redondantes.
- [ ] RF-5 : règles du resolver caractérisées, calculs et effets clarifiés.
- [ ] RF-6 : trois autres points de complexité traités ou exception motivée.
- [ ] RF-7 : contrat rollback cohérent, dépendances qualifiées sans faux diagnostic.
- [ ] RF-8 : mypy bloquant, typage progressif, couverture et documentation alignées.
- [ ] Suite complète verte, résultats golden et rollback préservés ; aucun test désactivé pour masquer une régression.
- [ ] Revue finale des fichiers modifiés et du diff effectuée.

Si un affichage est disponible, tester manuellement déplacement/saut/dash, blocage, charge, juggle/OTG, projectiles, plateformes, mort/respawn, pause et overlays/afterimages. Sinon noter « validation manuelle non réalisée ». Les tests headless ne démontrent ni le confort de jeu ni les performances à 60 Hz. Un profilage éventuel est une validation complémentaire, pas une optimisation obligatoire sans mesure.

Pour chaque lot terminé, consigner : date et révision, fichiers touchés, décisions d'interface, tests ajoutés, commandes et résultats, correctif fonctionnel éventuel, dette reportée avec justification. Cocher uniquement après validation. Un lot validé vaut mieux qu'une migration partielle de tous les lots.
