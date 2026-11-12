# Feuille de route — Knightrock

Construite à partir de `comprehensive-audit.md` et
`architectural-recommendations.md`. Rien n'est commencé : l'étape B attend
l'accord du développeur.

## Priorités

- **P0 — Critique** : correction, fiabilité.
- **P1 — Élevée** : problème d'architecture à traiter tôt.
- **P2 — Moyenne** : code plus propre et plus simple à maintenir.
- **P3 — Faible** : finitions optionnelles.

## Décisions à prendre avant de commencer

| # | Question | Recommandation | Débloque |
|---|---|---|---|
| D1 | Corriger C1 (appuis perdus pendant le hit-stop) ? **Change le ressenti.** | Oui | Étape 1 |
| D2 | Corriger C2 (délai de contact et de pièges) ? **Change le ressenti.** | Oui | Étape 1 |
| D3 | Touche de réinitialisation : debug seulement, ou « recommencer » qui compte une mort ? | Debug seulement | Étape 1 |
| D4 | Rollback : un mode réseau ou un rembobinage est-il prévu ? | **Oui (multijoueur) → garder et tester** | Étape 3 |
| D5 | Interpolation : le joueur tremble-t-il sur un écran à 120/144 Hz ? | Observer d'abord | Étape 7 |

## Règles pour toutes les étapes

- Une étape = des commits courts, chacun vert : `pytest`, `mypy src main.py tools`,
  `ruff check`, `ruff format --check`.
- Les changements de comportement (étape 1) ne sont **jamais** mêlés à une
  refactorisation.
- Les suppressions de `notes/` présentes dans l'arbre de travail appartiennent
  au développeur : ne pas les committer ni les annuler sans son accord.
- Après chaque étape : lancer le jeu (`uv run python main.py`, puis `--debug`),
  jouer le niveau 0, mettre à jour `docs/audit/final-report.md`.

---

## Étape 0 — Filets de sécurité (P0, sans changement de comportement)

| Champ | Contenu |
|---|---|
| Problème | Le refactor du combat (étape 4) touche le cœur du jeu ; les tests actuels commencent tous « en contact » et utilisent beaucoup de faux objets. |
| Fichiers | Nouveaux tests seulement : `tests/unit/test_hit_outcome_matrix.py`, `tests/headless/test_contact_sequences.py`, `tests/headless/test_hitstop_input.py` |
| Changement | (1) Matrice de caractérisation de l'issue d'un coup (attaques livrées × situations de la cible), avec de vrais `Player`/`Enemy`. (2) Tests de séquence approche → contact pour le contact et les pièges. (3) Test d'appui pendant le hit-stop. Les tests de (2) et (3) sont écrits pour le **comportement voulu** et marqués `xfail(strict=True)` jusqu'à l'étape 1. |
| Bénéfice | Rend les étapes 1 et 4 vérifiables. |
| Dépendances | Aucune |
| Complexité | Moyenne |
| Risque de régression | Nul (tests seulement) |
| Validation | La matrice passe sur le code actuel ; les `xfail` échouent bien. |

## Étape 1 — Correctifs de gameplay (P0, après D1 à D3)

| Champ | Contenu |
|---|---|
| Problème | C1, C2, C5 |
| Fichiers | `src/application/scenes/gameplay_scene.py`, `src/core/level/level.py`, `src/core/level/systems/gameplay_loop.py`, `src/core/input/input_provider.py`, `src/application/game.py` (transmission des évènements manette au verrou), `src/core/level/systems/contact_damage.py`, `src/core/level/systems/hazard_damage.py`, `src/entities/player_input.py`, `src/core/input/input_bindings.py` |
| Changement | R1 (entrées lues sur les ticks simulés, verrou étendu à `JOYBUTTONDOWN`), R2 (armement dans `record_contact`), R3 (réinitialisation selon D3). Un commit par correctif. |
| Bénéfice | Combos fiables pendant le gel ; dégâts de contact et de pièges au premier tick ; plus de soin gratuit. |
| Dépendances | Étape 0 |
| Complexité | Faible |
| Risque de régression | Moyen sur le ressenti, faible sur le code |
| Validation | Les `xfail` de l'étape 0 passent (retirer le marqueur) ; la matrice reste verte ; essai manuel clavier **et** manette : enchaîner pendant le gel d'un coup et d'une parade, traverser un pic, toucher un ennemi en courant. |

## Étape 2 — Une seule source pour les valeurs de jeu (P1)

| Champ | Contenu |
|---|---|
| Problème | C4 |
| Fichiers | `src/entities/enemies/factory.py`, `src/entities/enemies/configs.py`, `src/entities/enemies/types/*.py`, `src/data/provider.py`, `src/core/level/world_builder.py`, `src/core/level/systems/spawn_system.py`, `src/core/level/level.py`, `src/entities/player_config.py`, tests qui importent les configurations |
| Changement | R4 : la table des ennemis vient de `GameplayData` partout ; repli Python retiré ; les tests chargent le JSON par une fixture. |
| Bénéfice | Un réglage d'équilibrage change tous les ennemis, banc de debug compris ; un ennemi ajouté au JSON existe. |
| Dépendances | Aucune |
| Complexité | Faible à moyenne |
| Risque de régression | Faible (valeurs identiques aujourd'hui, vérifié) |
| Validation | Suite ; test « ennemi ajouté au seul JSON » ; banc de debug (`--debug`, touches de spawn). |

## Étape 3 — Rollback vérifié (P1, D4 : conservé pour le multijoueur)

| Champ | Contenu |
|---|---|
| Problème | §3.16, C3 |
| Fichiers | `src/entities/player.py`, `src/entities/entity.py` ; nouveau test `tests/headless/test_rollback_invariant.py` |
| Changement | R7-B : `Player.save_state` complète `extra` au lieu de le remplacer ; test d'invariant : sur un niveau avec joueur et ennemis, enregistrer, avancer N ticks avec des entrées scriptées, revenir, rejouer les mêmes entrées, comparer l'état complet. |
| Bénéfice | Le rollback reste correct en attendant le multijoueur ; tout nouvel état oublié dans les instantanés fait échouer la CI. |
| Dépendances | Aucune |
| Complexité | Faible à moyenne |
| Risque de régression | Nul en jeu (rollback désactivé) |
| Validation | Le test d'invariant échoue avant la correction de C3 et passe après. |

## Étape 4 — Résolution des coups en un seul endroit (P1)

| Champ | Contenu |
|---|---|
| Problème | §3.9 |
| Fichiers | `src/combat/hit_resolver.py`, `src/combat/combatant_protocol.py`, `src/entities/entity.py`, `src/entities/player.py`, `src/entities/components/reaction.py`, `src/entities/player_controllers.py` (`GuardController`), `src/core/level/systems/contact_system.py` |
| Changement | R5, en cinq commits à comportement constant : (1) direction du knockback unique ; (2) étourdissement par parades dans le résolveur, sans `isinstance(Enemy)` ; (3) décision de garde et de parade dans le résolveur via un protocole `Defender` ; (4) choix de la réaction écrit une fois ; (5) retrait des `getattr` du résolveur sur des champs déclarés. |
| Bénéfice | Une règle de combat se place à un seul endroit ; l'ordre est lisible ; plus de duplication. |
| Dépendances | Étape 0 (matrice), étape 1 terminée (ne pas mélanger), étape 3 (le rollback doit suivre les états déplacés) |
| Complexité | Élevée |
| Risque de régression | Moyen, couvert par la matrice |
| Validation | Matrice identique après chaque commit ; tests de garde, parade, jonglage, armure ; partie manuelle contre gobelins et slimes, garde et parade comprises. |

## Étape 5 — Retour de combat et nommage du tick (P2)

| Champ | Contenu |
|---|---|
| Problème | §3.5 |
| Fichiers | `src/core/level/systems/physics_system.py`, nouveau `src/core/level/systems/feedback_system.py`, `src/core/level/systems/gameplay_loop.py`, `src/core/level/level.py`, `src/entities/player.py` (`dash_started_this_frame`), `src/core/sprite_groups.py`, `src/core/level/world_builder.py`, `src/core/level/systems/spawn_system.py` |
| Changement | R6 (étape `FeedbackSystem`), R11.1 (`add_fighter`), R11.2 (fin de tick unique), `GameplayLoop` à systèmes obligatoires (partie de R8). |
| Bénéfice | La physique se trouve dans le système qui porte son nom ; un son de coup s'ajoute à un seul endroit. |
| Dépendances | Étape 4 (les faits du tick sont alors stables) |
| Complexité | Moyenne |
| Risque de régression | Faible |
| Validation | Tests FX et secousses, captures de référence, essai visuel (poussière, arcs de garde, secousses). |

## Étape 6 — Tests sur les vrais types, puis retrait des tolérances (P2)

| Champ | Contenu |
|---|---|
| Problème | §3.20 |
| Fichiers | Tests de `contact_system`, `hit_resolver`, `gameplay_scene`, `gameplay_loop` ; puis `src/core/level/systems/contact_system.py`, `contact_damage.py`, `hazard_damage.py`, `src/application/scenes/gameplay_scene.py` |
| Changement | R8 : réécrire les tests sur `tests/fakes.py` / `helpers.make_entity`, puis retirer les `getattr` « pour les stubs » ; remplacer les tests qui lisent le texte source. |
| Bénéfice | mypy vérifie les contrats du combat ; un faux objet ne peut plus cacher un bug. |
| Dépendances | Étape 4 |
| Complexité | Moyenne (volume de tests) |
| Risque de régression | Faible |
| Validation | Suite, mypy ; décompte des `getattr`/`hasattr` hors overlay de debug et évènements pygame. |

## Étape 7 — Finitions (P3)

| # | Changement | Fichiers | Validation |
|---|---|---|---|
| 7.1 | R9 : prose allégée, identifiants d'audit retirés, règle écrite dans le README | `fx/tuning.py`, `entity.py`, `game.py`, `physics_system.py`, puis au fil de l'eau | `git diff` sans changement de code (vérifiable par `ast` identique) |
| 7.2 | R10 : `MovementComponent` sans relais, états génériques typés, réglages en dataclasses | `entity.py`, `components/movement.py`, `states/*.py` | mypy, suite |
| 7.3 | R11.3 `StrEnum` pour les champs de coup | `frame_data.py`, `data/attacks.py`, `contact_system.py` | Suite, chargement du JSON |
| 7.4 | R11.4 transitions d'IA par valeur de retour | `states/enemy_states.py` | Tests d'IA |
| 7.5 | R11.5 / R11.6 préchargement des clips, invalidation des caches d'animateur | `level.py` ou `world_builder.py`, `animator.py`, `game.py` | Journal du temps de frame à la première minute |
| 7.6 | R11.7 interpolation des entités, selon D5 | `renderer.py`, `entity.py` | Observation à 144 Hz, tests de rendu |

---

## Vue d'ensemble

| Étape | Priorité | Comportement changé | Complexité | Risque |
|---|---|---|---|---|
| 0 Filets | P0 | Non | Moyenne | Nul |
| 1 Correctifs | P0 | **Oui** (D1–D3) | Faible | Moyen (ressenti) |
| 2 Source unique | P1 | Non | Faible–moyenne | Faible |
| 3 Rollback vérifié | P1 | Non | Faible–moyenne | Nul |
| 4 Résolution des coups | P1 | Non | Élevée | Moyen |
| 5 Retour de combat | P2 | Non | Moyenne | Faible |
| 6 Tests et tolérances | P2 | Non | Moyenne | Faible |
| 7 Finitions | P3 | Non (sauf 7.6) | Faible chacune | Faible |

Ordre conseillé : 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Les étapes 2 et 3 sont
indépendantes entre elles et peuvent être faites dans l'ordre inverse.

Le fichier `docs/audit/final-report.md` sera créé pendant l'étape B, après la
mise en œuvre.
