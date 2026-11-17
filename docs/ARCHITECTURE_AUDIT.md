# Audit architectural et de qualité logicielle — Knightrock

Branche `fix/remediation`, commit `6a98588` (« feat(fx): speed lines that linger, a clap of
air, and a dark step you can see »), audit réalisé en lecture seule.

> **Portée de ce document** : état initial de la codebase et recensement complet des
> problèmes. L'architecture cible est dans [`ARCHITECTURE.md`](ARCHITECTURE.md), les
> règles de qualité dans [`ENGINEERING_STANDARDS.md`](ENGINEERING_STANDARDS.md) et la
> roadmap d'exécution dans [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md). Ce document ne
> décrit pas une architecture implémentée au-delà de ce qui existe aujourd'hui.

---

## 1. Méthode et limites de l'audit

### 1.1 Ce qui a été fait

- Inspection intégrale de l'arborescence : `src/` (8 couches, ~180 modules, ~43 000
  lignes), `tests/` (unit, headless, benchmarks, goldens), `data/gameplay/*.json`,
  `data/levels_manifest.json`, `assets/` (fonts, sounds ; les TMX sont git-ignorés et
  matérialisés au build), `tools/`, `.github/workflows/build.yml`, `.pre-commit-config.yaml`,
  `pyproject.toml`, `knightrock.spec`, `main.py`, `README.md`, `docs/audit/*`.
- Lecture ciblée des modules structurants : `application/game.py`, `application/save_game.py`,
  `application/settings_store.py`, `core/events.py`, `core/paths.py`, `core/settings.py`,
  `core/level/level_manager.py`, `core/level/world_builder.py`, `core/level/systems/gameplay_loop.py`,
  `entities/entity.py`, `combat/determinism.py`, `core/fx/particles.py`, `ui/text.py`,
  `ui/panel_renderer.py`, `core/display/stage.py`, `data/provider.py`, `data/roots.py`.
- Analyses statiques non destructives : imports de `pytmx`, directions d'imports entre
  couches, `global`, `except Exception` / `except:`, écritures dans `os.environ`, `getattr`,
  `Any`, `eval`/`exec`/`pickle`/réseau, TODO/FIXME.
- Étude de l'historique git (branches, commits, introductions de motifs) et de l'historique
  d'audit existant (`docs/audit/`, six rapports antérieurs).

### 1.2 Limites explicites

1. **Aucun test n'a été exécuté.** Le projet exige Python ≥ 3.14 (`.python-version`) et
   pytest/mypy/ruff ne sont pas installés dans l'environnement d'audit ; la mission interdit
   d'installer des dépendances ou de modifier l'environnement du projet. La baseline
   d'exécution est donc **statique** ; les chiffres d'exécution cités (3 674 tests, 92 %
   de couverture, 1,9 ms/tick) proviennent du README, de `test_readme_claims.py` et des
   rapports d'audit antérieurs, pas d'une reproduction locale.
2. **Python ≤ 3.13 ne peut pas parser le code** (voir F2) : les analyses AST locales ont dû
   être menées par lecture et par motifs textuels plutôt que par compilation.
3. Les cartes Tiled (`assets/data/levels/*.tmx`) sont absentes du clone (git-ignorées) ;
   leur audit s'appuie sur `data/levels_manifest.json`, `LevelData.from_tmx`, `world_builder.py`
   et les tests de manifeste.
4. Aucun run CI n'existe pour la branche `fix/remediation` (voir F13) : l'état « vert »
   revendiqué par les derniers commits n'a pas été vérifié par GitHub Actions.

### 1.3 Contexte : un projet déjà audité et remédié

`docs/audit/` contient six rapports d'un cycle d'audit/refactoring antérieur (2026-11-12),
clos par `final-report.md` : trois défauts de gameplay corrigés (C1, C2, C5), un bug de
rollback (C3), une source unique pour les données combattants (C4), une matrice de
caractérisation de 421 issues de coups (`tests/golden/hit_outcomes.json`), et une liste de
dette restante (prose 30 %, `getattr`, `GameplayLoop` optionnel, interpolation, tuiles non
reconverties). Le présent audit repart de la tête de branche **après** ces remédiations et
après les ajouts de gameplay récents (dash retravaillé, charge, boucle No More Heroes 2,
FX). Les constats ci-dessous sont donc pour l'essentiel **neufs ou résiduels**, et le
niveau de départ est élevé.

---

## 2. État initial : ce qui est solide (constaté, pas supposé)

| Domaine | Evidence |
|---|---|
| **Game loop** | Accumulateur 60 Hz dans `application/game.py` (`_accumulator`, `Simulation.TIMESTEP`, `MAX_TICKS_PER_FRAME`, fraction d'interpolation `frame_fraction`), pacing unique (vsync ou `Clock`), plafond dérivé `DISPLAY_SAFETY_CEILing_FPS = max(Display.FPS * 4, MAX_FRAME_LIMIT)`. |
| **Séparation des couches** | `application / combat / core / data / entities / physics / states / ui`, direction `core → ui/application` interdite et **vérifiée par AST** dans `tests/unit/test_layer_boundaries.py` (allowlist explicite). `grep` de confirmation : zéro import de `src.ui`/`src.application` sous `core/`, `combat/`, `physics/`, `entities/`, `data/`, `states/`. |
| **Encapsulation PyTMX** | Deux modules seulement : `core/level/level_manager.py` (`load_pygame`, wrap des erreurs en `LevelLoadError`) et `core/level/level_data.py` (`LevelData.from_tmx`). Aucun autre module n'importe `pytmx`. |
| **Communication** | `core/events.py` : bus synchrone, ordre de souscription, itération sur copie, isolation par abonné (`except Exception` + log + `SubscriberFailure` listée), familles « faits de simulation » / « feedback d'interface ». L'audio est un consommateur pur (`core/audio.py` n'importe ni scènes ni vues). |
| **Données** | `data/provider.py` : JSON obligatoires, erreurs strictes (`GameplayDataError`), une seule source de vérité (les copies Python ont été supprimées, audit C4), `KNIGHTROCK_DATA_DIR` pour les tests/moddeurs. |
| **Déterminisme** | IDs d'entités séquentiels (`_ENTITY_ID_SEQUENCE`), checksums de géométrie SHA-256 quantifiés (`combat/determinism.py`), snapshots de rollback + test d'invariant à 392 valeurs (`tests/headless/test_rollback_invariant.py`). |
| **Ressources** | `AssetLibrary` partagée, caches bornés (`SCALE_CACHE_MAX = 512` avec éviction), caches FX invalidés au changement de format d'affichage (`clear_frame_cache`), préchargement des clips au chargement du niveau. |
| **Écritures disque** | `SettingsStore.save` : écriture atomique (`tempfile.NamedTemporaryFile` + `replace`) + sauvegarde `.json.bak` best effort + migrations v1→v4. |
| **Tests** | ~3 674 tests (unit + headless + goldens d'interface + matrice de combat + invariants de rollback), CI bloquante : `ruff check`, `ruff format --check`, `mypy` strict, `pytest --cov-fail-under=80`, actions GitHub épinglées par SHA, `timeout-minutes: 15`, builds multi-plateformes. |
| **Sécurité de surface** | Aucun `eval`/`exec`/`pickle`/réseau dans `src/` ; chemins résolus via `resource_path` (PyInstaller `_MEIPASS`) ; overrides d'environnement documentés (`KNIGHTROCK_DATA_DIR`, `KNIGHTROCK_SAVE_DIR`) ; XML délégué à pytmx sur des assets locaux de confiance. |

---

## 3. Constats

Chaque constat porte un identifiant `F<n>` réutilisé par le plan. Gravité : critique /
majeure / moyenne / mineure. Classification : `IN_SCOPE` (amélioration interne autorisée),
`OUT_OF_SCOPE` (gameplay / comportement), `REQUIRES_INVESTIGATION` (à instruire avant toute
décision).

---

### F1 — Écriture de sauvegarde non atomique (incohérence avec les réglages)

1. **Identifiant** : F1.
2. **Catégorie** : robustesse / persistance.
3. **Description** : `SaveGame.save` écrit le JSON directement dans le fichier final, alors
   que `SettingsStore.save` du même paquet applique le protocole complet (fichier temporaire,
   `replace`, backup `.bak`). Un crash ou une coupure pendant l'écriture laisse un JSON
   tronqué ; la progression du joueur est alors perdue (le chargement retombe sur une
   sauvegarde neuve, par conception).
4. **Preuves** : `src/application/save_game.py:67-70` —
   `path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")` sans fichier
   temporaire ni `replace`. Comparer `src/application/settings_store.py:509-516`
   (`tempfile.NamedTemporaryFile(... dir=self.path.parent, delete=False)` puis
   `temporary_path.replace(self.path)`) et `_keep_backup` (518-527).
5. **Fichiers concernés** : `src/application/save_game.py`.
6. **Classes/fonctions** : `SaveGame.save`.
7. **Principe** : robustesse, gestion des erreurs, DRY (un seul protocole d'écriture durable).
8. **Conséquences** : perte de progression possible ; deux politiques de persistance pour
   deux fichiers du même dossier `~/.knightrock/`.
9. **Gravité** : moyenne.
10. **Priorité** : haute (petit changement, bénéfice direct, aucun risque comportemental).
11. **Recommandation** : répliquer le protocole de `SettingsStore.save` (tempfile même
    répertoire + `Path.replace` + backup `.bak` best effort), idéalement en factorisant un
    petit utilitaire d'écriture atomique partagé.
12. **Risques de régression** : quasi nuls ; `test_save_game.py` couvre le module, un test
    d'échec d'écriture est à ajouter.

**Classification : `IN_SCOPE`.**

---

### F2 — Syntaxe PEP 758 : compatibilité outillage restreinte à Python ≥ 3.14

1. **Identifiant** : F2.
2. **Catégorie** : outillage / portabilité.
3. **Description** : cinq modules utilisent la clause `except A, B:` sans parenthèses
   (PEP 758, valide uniquement en Python 3.14+). C'est un choix délibéré et documenté
   (commit `fdf7e2c6` « style: make the PEP 758 except spelling the house style », après
   `26c3816c` qui les avait parenthésés). Conséquence : tout outillage basé sur un
   interpréteur ≤ 3.13 (ruff/mypy anciens, IDE, scripts d'analyse, notebooks) échoue à la
   parse — c'est arrivé à cet audit lui-même.
4. **Preuves** : `src/core/input/event_router.py:525`
   (`except TypeError, ValueError:`), `src/core/display/stage.py:223`
   (`except pygame.error, AttributeError, TypeError, ValueError:`),
   `src/ui/world_overlay_velocity.py:70` (`except AttributeError, TypeError:`),
   `src/application/save_game.py:63,78`, `tools/display_acceptance.py:173`. `pyproject.toml`
   : `target-version = "py314"`, `requires-python = ">=3.14"`, `.python-version` = `3.14`.
5. **Fichiers concernés** : les cinq ci-dessus ; `README.md` (section Conventions).
6. **Classes/fonctions** : sans objet (syntaxe).
7. **Principe** : import hygiene, outillage reproductible.
8. **Conséquences** : contributeur·rice sur Python 3.12/3.13 ne peut ni parser ni lancer
   quoi que ce soit, avec un message (`SyntaxError: multiple exception types must be
   parenthesized`) qui ne dit pas que la version de Python est en cause.
9. **Gravité** : mineure (le projet épinglé 3.14 fonctionne).
10. **Priorité** : moyenne.
11. **Recommandation** : ne pas réécrire les clauses (le style est assumé) ; documenter la
    contrainte « Python 3.14 strict, y compris pour lire le code » dans le README/les
    conventions, et garder `.python-version` + `uv` comme voie d'entrée unique.
12. **Risques de régression** : aucun (documentation).

**Classification : `IN_SCOPE`** (documentation uniquement).

---

### F3 — `core/settings.py` : module de configuration fourre-tout (faible cohésion)

1. **Identifiant** : F3.
2. **Catégorie** : architecture / cohésion.
3. **Description** : 1 055 lignes, ~36 dataclasses de domaines sans rapport — affichage
   (`Display`, `World`), physique (`Physics`, `Collision`, `PlatformRide`), combat
   (`Combat`, `Stun`, `Guard`, `Clash`, `Slot`, `Finisher`, `Throw`, `Battery`, `Fury`,
   `Rush`), caméra (`CameraShake`, `CameraFollow`, `HitFlash`, `ParryFlash`,
   `ReactionMark`, `Afterimage`), IA (`AI`, `Turn`, `TurnProfile`, `resolve_turn_profile`),
   entrées (`Input`), audio (`Audio`), animation (`Animation`), simulation (`Simulation`),
   debug (`Debug`), gameplay (`Gameplay`, `Locomotion`, `Ledge`, `EnemyJump`,
   `Separation`, `Respawn`, `StateMachineConfig`). Tout importe ce module (c'est permis
   et vérifié), donc chaque retouche d'un domaine touche le même fichier : conflits
   d'édition, navigation difficile, tentation d'y ajouter « encore un champ ».
4. **Preuves** : liste des définitions de `src/core/settings.py` (classes aux lignes 9 à
   1052, cf. audit : `class Display` l.9 … `class Gameplay` l.1052). Imports de
   `src.core.settings` présents dans toutes les couches (`entities/entity.py` en importe
   onze noms, `core/level/world_builder.py`, `physics/*`, `states/*`, `ui/*`).
5. **Fichiers concernés** : `src/core/settings.py` (+ tous ses importeurs si on déplace).
6. **Classes/fonctions** : toutes les classes listées ci-dessus ; `resolve_turn_profile`.
7. **Principe** : Single Responsibility au niveau module, High Cohesion, Low Coupling.
8. **Conséquences** : coût de maintenance croissant, historique git illisible sur ce
   fichier, frontières de domaines invisibles.
9. **Gravité** : moyenne.
10. **Priorité** : moyenne.
11. **Recommandation** : convertir en **package** `core/settings/` avec un module par
    domaine (`display.py`, `physics.py`, `combat.py`, `camera.py`, `ai.py`, `input.py`,
    `audio.py`, `simulation.py`, …) et un `settings/__init__.py` qui ré-exporte les noms
    actuels : les ~centaines d'imports `from src.core.settings import X` restent valides,
    zéro changement d'appelant, zéro changement de valeurs. Ruff/mypy verrouillent
    l'équivalence.
12. **Risques de régression** : faibles (déplacement pur) ; risque principal = oublier un
    nom dans le ré-export → attrapé par mypy et la suite de tests.

**Classification : `IN_SCOPE`.**

---

### F4 — `Entity` : résidu de god-object (géométrie, sweep, turn, snapshot dans la base)

1. **Identifiant** : F4.
2. **Catégorie** : architecture des entités.
3. **Description** : `Entity` reste une classe de 1 373 lignes et 102 méthodes qui cumule :
   identité/rollback, vitals, combat (délégé à `CombatComponent`), réactions
   (`ReactionComponent`), locomotion (`MovementComponent`), **plus** toute la géométrie
   hitbox/hurtbox/zones multiples, la capture de sweep (`capture_sweep_origin`,
   `swept_pushbox`, `swept_contact_shapes`, `swept_hurtboxes`), le réglage de turn
   (`_init_turn_tuning`, `resolve_turn_profile`), le câblage de la machine à états et des
   interruptions, et les render hints. La composition existe (quatre composants) mais la
   base garde les responsabilités géométriques et de snapshot.
   NB : l'audit précédent a **volontairement** arrêté là (frontière « le défenseur décide
   s'il se défend » dans `receive_damage`, déplacement de la garde refusé pour ne pas
   changer le comportement des pièges/contact). Toute extraction doit respecter ces
   décisions.
4. **Preuves** : `src/entities/entity.py` (1 373 lignes ; 102 `def` ; imports de 30+
   symboles en tête de fichier, l.1-65) ; `EntitySnapshot` l.72-102 avec `entity: Any`,
   `groups: list[Any]`, `extra: dict[str, Any]`.
5. **Fichiers concernés** : `src/entities/entity.py`, éventuellement
   `src/entities/hurtbox_zones.py`, `src/combat/shapes.py`, `src/core/rollback/snapshots.py`.
6. **Classes/fonctions** : `Entity` (méthodes de géométrie l.519-620, snapshot l.72-102),
   `EntitySnapshot`.
7. **Principe** : Single Responsibility, composition over inheritance, testabilité.
8. **Conséquences** : chaque retouche de combat/physique/rendu passe par la même classe ;
   les tests d' `Entity` doivent monter beaucoup d'état ; le typage `Any` du snapshot
   affaiblit le futur chemin réseau.
9. **Gravité** : moyenne.
10. **Priorité** : moyenne.
11. **Recommandation** : extraction **incrémentale** et sans changement de comportement :
    (a) un fournisseur de géométrie de hurtbox (zones, multiplicateurs, tags) ;
    (b) un constructeur de snapshot typé (remplacer les `Any` de `EntitySnapshot` par des
    types concrets) ; (c) à terme, déplacer la capture de sweep vers `combat/shapes.py`.
    Ne pas toucher à `receive_damage`, à l'ordre des mises à jour ni aux timings.
12. **Risques de régression** : moyens — `Entity` est au cœur de la simulation ; la matrice
    de 421 issues de coups, les goldens de simulation et l'invariant de rollback (392
    valeurs) sont les garde-fous obligatoires.

**Classification : `IN_SCOPE` pour (a) et (b) ; `REQUIRES_INVESTIGATION` pour (c) et pour
toute extraction touchant `receive_damage` / les états.**

---

### F5 — `getattr` résiduels (214 → 206 depuis le dernier audit)

1. **Identifiant** : F5.
2. **Catégorie** : qualité logicielle / typage.
3. **Description** : ~206 `getattr` restent dans `src/`. Un tiers dans l'overlay de debug,
   ~20 légitimes sur les évènements pygame ; le reste lit des attributs « peut-être
   absents » d'objets hétérogènes. L'audit précédent a démontré le danger concret
   (`getattr(target, "is_invincible", False)` avalait une `AttributeError` levée *dans* la
   propriété — §7 du `final-report.md`).
4. **Preuves** : comptage `grep -c getattr` sur `src/` = 206 ; répartition documentée dans
   `docs/audit/final-report.md` §9 (P2).
5. **Fichiers concernés** : surtout `src/ui/world_overlay_*.py`, `src/core/level/systems/*`,
   `src/combat/*`.
6. **Classes/fonctions** : à relever fichier par fichier lors de l'exécution.
7. **Principe** : encapsulation, contrats explicites (Protocols), fail-fast.
8. **Conséquences** : erreurs silencieuses (valeur par défaut au lieu de l'exception),
   contrats invisibles, faux positifs de tests avec des faux objets incomplets.
9. **Gravité** : moyenne.
10. **Priorité** : moyenne.
11. **Recommandation** : poursuivre la méthode de l'étape 6 : donner aux faux objets la
    forme réelle (`tests/fakes.py` épinglé par `test_fakes.py`), puis lire directement ;
    traiter par lots (overlay de debug d'abord, où la densité est la plus forte).
12. **Risques de régression** : faibles ; chaque lot vérifié par la suite complète.

**Classification : `IN_SCOPE`.**

---

### F6 — `GameplayLoop` accepte encore des systèmes optionnels

1. **Identifiant** : F6.
2. **Catégorie** : architecture / lifecycle.
3. **Description** : `GameplayLoop` déclare `contact_system: ContactSystem | None = None`
   et `feedback_system: FeedbackSystem | None = None`, puis instancie un défaut à la volée
   ; `reaper_feedback` reste `Optional`. L'audit précédent a classé ce point P3 (coût de
   réécriture des montages de test jugé supérieur au gain) ; il reste ouvert.
4. **Preuves** : `src/core/level/systems/gameplay_loop.py:56-58,64,73,121`.
5. **Fichiers concernés** : `src/core/level/systems/gameplay_loop.py`, montages de tests.
6. **Classes/fonctions** : `GameplayLoop.__init__`, `CombatLoop`.
7. **Principe** : dépendances explicites, fail-fast (le `_require` existant montre l'intent).
8. **Conséquences** : un montage incomplet peut sembler valide ; deux chemins de
   construction (injection ou défaut implicite).
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : rendre les deux systèmes requis en position/keyword obligatoire et
    mettre à jour les montages de tests qui s'appuient sur les défauts ; conserver
    `CombatLoop` (sous-ensemble volontaire pour les tests).
12. **Risques de régression** : faibles (échecs de construction bruyants, pas de changement
    d'exécution).

**Classification : `IN_SCOPE`.**

---

### F7 — Prose : ~30 % des lignes de `src/` sont des docstrings/commentaires historiques

1. **Identifiant** : F7.
2. **Catégorie** : qualité logicielle / maintenabilité.
3. **Description** : la proportion de prose narrative (récits d'audit, histoire des
   décisions) reste ~30 % après retrait des références orphelines. Exemples : `core/fx/tuning.py`
   (602 lignes dont ~190 de code), `entities/entity.py` (1 373 lignes), docstrings de
   `settings_store.py`. La règle d'écriture est désormais dans le README, mais le stock
   existant n'a pas été réécrit (décision : relecture humaine fichier par fichier).
4. **Preuves** : `docs/audit/final-report.md` §6 (R9 « en partie ») et §9 (P2) ;
   comptages locaux (tuning.py 602 lignes, 504 non-commentaires — la prose est dans les
   docstrings).
5. **Fichiers concernés** : `src/core/fx/tuning.py` en premier, puis les gros modules.
6. **Classes/fonctions** : sans objet.
7. **Principe** : KISS, lisibilité, coût de recherche.
8. **Conséquences** : signal utile noyé dans le récit ; revues plus lentes.
9. **Gravité** : mineure.
10. **Priorité** : basse (hygiène continue).
11. **Recommandation** : réécriture éditoriale par lots, en ne conservant que le « pourquoi »
    du code vivant ; jamais mélangée à un changement de comportement.
12. **Risques de régression** : aucun si et seulement si l'AST est inchangé (le précédent
    audit a utilisé un diff AST pour le prouver).

**Classification : `IN_SCOPE`.**

---

### F8 — Tuiles du niveau en cours non reconverties après un changement de format d'affichage

1. **Identifiant** : F8.
2. **Catégorie** : rendu / gestion des ressources.
3. **Description** : après un changement de format d'affichage (plein écran, changement
   d'écran), les surfaces de tuiles du niveau affiché ne sont pas reconverties : les blits
   passent par une conversion à la volée (lenteur seulement, aucune erreur). Les caches FX
   et l'`AssetLibrary` s'invalident correctement (`clear_frame_cache`), pas les tuiles
   déjà découpées.
4. **Preuves** : `docs/audit/final-report.md` §9 point 6 et §11 (B4 « non corrigé, faible ») ;
   mécanisme d'invalidation existant dans `src/core/fx/particles.py:1433-1441`
   (`clear_frame_cache`) et `core/asset_library.py`.
5. **Fichiers concernés** : `src/core/rendering/renderer.py`, `src/core/rendering/tile_chunk_index.py`,
   `src/core/display/*` (point d'appel du changement de format).
6. **Classes/fonctions** : renderer (cache de tuiles), `TileChunkIndex`.
7. **Principe** : resource lifecycle, surface reuse.
8. **Conséquences** : coût de rendu majoré après un changement de format, jusqu'au
   rechargement du niveau.
9. **Gravité** : mineure.
10. **Priorité** : basse (à traiter avec F9, même mécanisme).
11. **Recommandation** : pré-rendre les calques de tuiles statiques par blocs à partir de
    `TileChunkIndex`, invalidé au changement d'échelle/format — cela règle F8 et apporte
    le gain de dessin estimé à 30-40 % (mesure de l'audit précédent).
12. **Risques de régression** : moyens côté visuel (un pixel faux sur un bord de bloc se
    voit) ; exiger une comparaison au pixel contre le rendu actuel (le dépôt a déjà des
    goldens et `test_no_stale_pixels.py`).

**Classification : `IN_SCOPE`** (optimisation de présentation, aucun changement de
simulation).

---

### F9 — Pistes de performance documentées mais non justifiées aujourd'hui

1. **Identifiant** : F9.
2. **Catégorie** : performance.
3. **Description** : les mesures de l'audit précédent (§11) donnent 5,7 ms de tick et 3,0 ms
   de dessin à 53 entités sur un budget de 16,7 ms, coût linéaire (~0,08 ms/entité),
   aucune fuite mémoire sur 12 000 ticks. Les pistes (voisinage `get_nearby` calculé une
   fois par entité et par tick ~10 % du tick ; `sync_rects` ; pas d'échantillonnage
   `draw_arc_stroke`) ne sont **pas** justifiées à la charge actuelle.
4. **Preuves** : `docs/audit/final-report.md` §11 (tableaux de mesures) et §11 « Pistes ».
5. **Fichiers concernés** : `src/physics/collisions.py` (`get_nearby_sprites`),
   `src/entities/entity.py` (`sync_rects`), `src/core/fx/draw.py` (`draw_arc_stroke`).
6. **Classes/fonctions** : idem.
7. **Principe** : pas d'optimisation prématurée ; mesurer d'abord.
8. **Conséquences** : aucun aujourd'hui ; devient réel si les niveaux grossissent
   (voir `docs/design/matrice-niveaux.md`).
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : garder les pistes écrites avec leurs seuils de déclenchement
    (« si le tick médian dépasse ~8 ms au pire scénario visé ») ; ne planifier que F8/F9-pré-rendu,
    qui a une seconde justification (F8).
12. **Risques de régression** : moyens pour le voisinage (sémantique exacte du
    « proche » à préserver) ; tests de collision existants + benchmarks
    (`tests/benchmarks/*`) comme garde-fous.

**Classification : `IN_SCOPE` (pré-rendu tuiles uniquement, via F8) ; le reste
`REQUIRES_INVESTIGATION`** (à ne rouvrir qu'avec une mesure motivante).

---

### F10 — Objets `water` de six niveaux ignorés par le world builder

1. **Identifiant** : F10.
2. **Catégorie** : données de niveau / design.
3. **Description** : six niveaux contiennent des objets `water` ; aucune fabrique n'existe,
   `world_builder` les journalise comme ignorés. Décision de design requise (comportement
   de nage/dégâts/ralentissement) ou retrait des objets des cartes.
4. **Preuves** : `docs/audit/final-report.md` §12 (« Encore ouverts ») ;
   `src/core/level/world_builder.py` (journalisation des objets sans fabrique).
5. **Fichiers concernés** : `assets/data/levels/*.tmx` (absents du clone),
   `src/core/level/world_builder.py`.
6. **Classes/fonctions** : `OBJECT_FACTORIES` (registre), `_build_*` de `world_builder`.
7. **Principe** : data-driven design cohérent (pas de données mortes).
8. **Conséquences** : contenu de carte silencieusement inerte.
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : arbitrer côté design ; si « rien », retirer les objets des cartes
    ; si « comportement », spécifier avant d'implémenter une fabrique.
12. **Risques de régression** : hors périmètre du refactoring interne.

**Classification : `OUT_OF_SCOPE` tant que le design n'est pas tranché**
(les cartes et le gameplay ne se modifient pas dans un refactoring). Recensé ici pour
mémoire.

---

### F11 — Interpolation des entités (décision D5) en attente d'observation

1. **Identifiant** : F11.
2. **Catégorie** : rendu / game feel.
3. **Description** : la fraction d'interpolation existe (`Game.frame_fraction`,
   `settings.Interpolation`) mais l'interpolation des entités n'est pas appliquée ;
   décision D5 du développeur : attendre une observation réelle à 120/144 Hz avant de
   trancher.
4. **Preuves** : `docs/audit/final-report.md` §6 (R11.7 « Non »), §9 point 4 ;
   `src/application/game.py:412-433` (`frame_fraction`).
5. **Fichiers concernés** : `src/core/rendering/*`, `src/application/game.py`.
6. **Classes/fonctions** : `Game.frame_fraction`, renderer.
7. **Principe** : simulation/présentation ; ne pas toucher sans preuve visuelle.
8. **Conséquences** : potentiel micro-judder à des taux de rafraîchissement non multiples
   de 60 Hz.
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : campagne d'observation à 120/144 Hz (manuel), puis décision
    d'implémenter ou de clore.
12. **Risques de régression** : élevés si implémenté sans garde-fous (dédoublement
    d'entités, incohérences hitbox visuelle) — d'où le statut.

**Classification : `REQUIRES_INVESTIGATION`.**

---

### F12 — Changements de gameplay récents de la branche (constat d'inventaire, pas un défaut)

1. **Identifiant** : F12.
2. **Catégorie** : périmètre.
3. **Description** : les commits récents de `fix/remediation` sont explicitement des
   changements de gameplay assumés (« a gameplay change » dans les messages : dash
   retravaillé, charge qui grossit les coups, boucle No More Heroes 2, dark step, FX).
   Ils constituent la **référence comportementale actuelle** que tout refactoring futur
   doit préserver, mais ne font pas partie d'un plan de refactoring.
4. **Preuves** : `git log origin/master..fix/remediation` (commits `7e5ffd8`, `6d508e9`,
   `25c1301`, `d01baae`, `6a98588`, etc.).
5. **Fichiers concernés** : `src/combat/*`, `src/entities/player*.py`, `src/core/fx/*`,
   `data/gameplay/*.json`.
6. **Classes/fonctions** : sans objet.
7. **Principe** : préservation du gameplay (section 4 de la mission).
8. **Conséquences** : la matrice de caractérisation (`tests/golden/hit_outcomes.json`) et
   les goldens de simulation doivent être **regénérés une fois** si ce n'est déjà fait
   après ces changements, puis gelés comme référence du refactoring.
9. **Gravité** : sans objet.
10. **Priorité** : sans objet.
11. **Recommandation** : avant le premier jour de refactoring, vérifier que les goldens
    correspondent à la tête de branche (regénération volontaire + lecture du diff), puis
    geler.
12. **Risques de régression** : sans objet.

**Classification : `OUT_OF_SCOPE`** (recensement).

---

### F13 — Aucun run CI sur la branche `fix/remediation`

1. **Identifiant** : F13.
2. **Catégorie** : qualité / intégration continue.
3. **Description** : le workflow `build.yml` se déclenche sur push de tags, push de
   `master`, PRs vers `master` et `workflow_dispatch`. La branche `fix/remediation` — qui
   diverge fortement de `master` (~57 900 insertions, 367 fichiers) — n'a aucun run
   associé : les portes ruff/mypy/pytest n'ont jamais tourné sur GitHub pour son état
   actuel. Les commits se disent « vert » sur exécution locale, mais rien n'est vérifié
   côté dépôt (multi-plateforme inclus).
4. **Preuves** : `gh run list --branch fix/remediation` = vide ;
   `.github/workflows/build.yml` (déclencheurs, l.2-9).
5. **Fichiers concernés** : `.github/workflows/build.yml` (éventuellement), ou simple PR.
6. **Classes/fonctions** : sans objet.
7. **Principe** : intégration continue réelle, risque multi-plateforme (le jeu cible
   Linux/Windows/macOS).
8. **Conséquences** : une régression qui ne casse que sur Windows/macOS, ou un conflit
   futur coûteux avec `master`.
9. **Gravité** : moyenne.
10. **Priorité** : haute (zéro code à écrire).
11. **Recommandation** : ouvrir une PR (draft) de `fix/remediation` vers `master` pour
    faire tourner la CI sur l'état de la branche, ou déclencher `workflow_dispatch`.
    Aucune fusion n'est proposée : c'est la branche de travail du développeur.
12. **Risques de régression** : aucun.

**Classification : `IN_SCOPE`** (opérationnel, pas de code).

---

### F14 — État global de module résiduel (caches et options process-wide)

1. **Identifiant** : F14.
2. **Catégorie** : qualité logicielle / état global.
3. **Description** : quelques états globaux de module subsistent, tous justifiés par le
   mono-fenêtrage mais à connaître : `_SHARED_LIBRARY` (`core/asset_library.py:159`),
   `_vortex_cache` et caches FX (`core/fx/particles.py:925,1395-1441`), `_language`
   (`ui/text.py:170`), `_compact_panels` (`ui/panel_renderer.py:403`), `_bindings_cache`
   (`core/display/sdl_probe.py:256`). Les caches FX ont un hook d'invalidation
   (`clear_frame_cache`) ; `_language` et `_compact_panels` sont des options de process
   sans hook de reset explicite pour les tests (ils sont réinitialisés par les tests au
   cas par cas).
4. **Preuves** : occurrences listées ci-dessus (motif `global` : 6 sites dans `src/`).
5. **Fichiers concernés** : les cinq modules listés.
6. **Classes/fonctions** : `shared_library`, `vortex_frames`, `clear_frame_cache`,
   `set_language`, `compact_panels`, `set_compact_panels`.
7. **Principe** : état global maîtrisé (le projet les assume et les documente).
8. **Conséquences** : fuite d'état entre tests si un test oublie de réinitialiser ;
   documentation dispersée.
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : ne pas ré-architecturer (aucun problème réel mesuré) ; ajouter
    une section « état process-wide » aux standards et, si un fuite de test apparaît, un
    fixture de reset.
12. **Risques de régression** : aucun.

**Classification : `IN_SCOPE`** (standards + fixture au besoin).

---

### F15 — Snapshot de rollback partiellement typé `Any`

1. **Identifiant** : F15.
2. **Catégorie** : qualité logicielle / déterminisme.
3. **Description** : `EntitySnapshot` porte `entity: Any`, `groups: list[Any]`,
   `extra: dict[str, Any]`. Les champs scalaires (la partie sérialisable réseau) sont
   bien typés ; les références locales ne le sont pas. Le test d'invariant (392 valeurs)
   compense à l'exécution, mais le compilateur ne protège pas l'ajout d'un champ.
4. **Preuves** : `src/entities/entity.py:72-102` (`EntitySnapshot`), docstring explicitant
   la frontière local/réseau.
5. **Fichiers concernés** : `src/entities/entity.py`, `src/core/rollback/snapshots.py`,
   `src/core/rollback/rollback.py`.
6. **Classes/fonctions** : `EntitySnapshot`, `RollbackSystem`.
7. **Principe** : typage des contrats, préparation multijoueur (décision D4 : rollback
   conservé pour le multijoueur prévu).
8. **Conséquences** : un nouveau champ de simulation oublié dans le snapshot n'est vu que
   par le test d'invariant, pas par mypy.
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : typer `entity` par un protocole minimal (ce que le restore lit)
    et documenter le schéma réseau attendu ; ne pas sérialiser plus aujourd'hui.
12. **Risques de régression** : faibles ; l'invariant de rollback reste le garde-fou.

**Classification : `IN_SCOPE`.**

---

### F16 — Outils de sécurité absents de la chaîne (Bandit), surface d'attaque faible

1. **Identifiant** : F16.
2. **Catégorie** : sécurité.
3. **Description** : la surface d'attaque est objectivement faible : pas de réseau, pas
   d'`eval`/`exec`/`pickle` dans `src/`, parsing XML délégué à pytmx sur des fichiers
   locaux de confiance, chemins résolus et overrides d'environnement documentés, sauvegarde
   et réglages dans le dossier utilisateur. Aucun scanner statique de sécurité (Bandit)
   n'est présent dans la chaîne pre-commit/CI ; ce n'est pas une vulnérabilité, c'est une
   absence de filet.
4. **Preuves** : greps `eval|exec|pickle|subprocess|urllib|requests|socket` sur `src/` =
   aucun hit de production ; `.pre-commit-config.yaml` (ruff + mypy + pytest seulement) ;
   `build.yml` (ruff, mypy, pytest, coverage).
5. **Fichiers concernés** : `.pre-commit-config.yaml`, `.github/workflows/build.yml`
   (éventuellement).
6. **Classes/fonctions** : sans objet.
7. **Principe** : défense en profondeur proportionnée.
8. **Conséquences** : une régression future (ex. un import réseau, un `pickle`) ne serait
   signalée par aucun outil.
9. **Gravité** : mineure.
10. **Priorité** : basse.
11. **Recommandation** : ajouter Bandit (profil par défaut, exclusions tests) en
    non-bloquant d'abord, bloquant après tri des faux positifs ; ne rien installer pendant
    l'audit.
12. **Risques de régression** : aucun (outil d'analyse).

**Classification : `IN_SCOPE`.**

---

## 4. Récapitulatif et classification

| ID | Résumé | Gravité | Priorité | Classification |
|---|---|---|---|---|
| F1 | Sauvegarde non atomique (`SaveGame.save`) | moyenne | haute | `IN_SCOPE` |
| F2 | PEP 758 : outillage limité à Python ≥ 3.14 | mineure | moyenne | `IN_SCOPE` (doc) |
| F3 | `core/settings.py` fourre-tout (1 055 lignes, ~36 classes) | moyenne | moyenne | `IN_SCOPE` |
| F4 | `Entity` : résidu de god-object (géométrie, sweep, snapshot) | moyenne | moyenne | `IN_SCOPE` partiel / `REQUIRES_INVESTIGATION` partiel |
| F5 | ~206 `getattr` résiduels | moyenne | moyenne | `IN_SCOPE` |
| F6 | `GameplayLoop` à systèmes optionnels | mineure | basse | `IN_SCOPE` |
| F7 | Prose ~30 % de `src/` | mineure | basse | `IN_SCOPE` |
| F8 | Tuiles non reconverties après changement de format | mineure | basse | `IN_SCOPE` |
| F9 | Optimisations non justifiées à la charge actuelle | mineure | basse | `IN_SCOPE` (pré-rendu) / `REQUIRES_INVESTIGATION` |
| F10 | Objets `water` ignorés (6 niveaux) | mineure | basse | `OUT_OF_SCOPE` (design) |
| F11 | Interpolation des entités (D5) | mineure | basse | `REQUIRES_INVESTIGATION` |
| F12 | Changements de gameplay récents = référence à geler | — | — | `OUT_OF_SCOPE` |
| F13 | Aucun run CI sur la branche | moyenne | haute | `IN_SCOPE` |
| F14 | État global de module résiduel | mineure | basse | `IN_SCOPE` |
| F15 | `EntitySnapshot` partiellement `Any` | mineure | basse | `IN_SCOPE` |
| F16 | Pas de scanner sécurité (Bandit) | mineure | basse | `IN_SCOPE` |

**Aucun constat critique ou majeur.** Le déficit le plus concret (F1) est un défaut de
robustesse localisé ; le reste est de la dette d'entretien déjà largement cartographiée
par l'audit précédent, confirmée à la tête de branche actuelle.

### Bugs de gameplay recensés (explicitement exclus du plan de refactoring)

- Aucun nouveau bug de gameplay identifié à la tête de branche. Les défauts de gameplay
  historiques (C1, C2, C5, géométrie des pièges, B1, B2) sont corrigés et documentés dans
  `docs/audit/final-report.md`.
- Points de gameplay en attente d'une décision du développeur (exclus du plan) :
  la direction de la projection lourde en mode `fixed` (§7 du rapport final, corrigée
  depuis par B2 — à confirmer en jeu), les objets `water` (F10), l'interpolation (F11),
  le ressenti des derniers changements de combat (F12).

---

## 5. Baseline des diagnostics exécutés

| Diagnostic | Commande | Résultat |
|---|---|---|
| État git | `git status`, `git branch -a`, `git log` | arbre propre, branche `fix/remediation` = `origin/fix/remediation`, aucun fichier non suivi |
| CI de la branche | `gh run list --branch fix/remediation` | aucun run (F13) |
| PRs ouvertes | `gh pr list --head fix/remediation` | aucune |
| Analyse syntaxique Python 3.12 | `ast.parse` sur 300+ fichiers | 5 fichiers non parsables en ≤ 3.13 (PEP 758, F2) — attendu et voulu |
| Imports PyTMX | grep | 2 modules seulement (`level_manager`, `level_data`) |
| Frontières de couches | grep + lecture `test_layer_boundaries.py` | aucune violation `core → ui/application` |
| `except Exception` / `except:` | grep | 12 sites, tous justifiés en bordure (bus, joystick, pytmx, stage, dernier recours), 8 avec `# noqa: BLE001` explicite |
| `global` | grep | 6 sites (F14) |
| `eval/exec/pickle/réseau` | grep | aucun en production |
| TODO/FIXME | grep | 0 |
| pytest / mypy / ruff | — | **non exécutés** (installation interdite par la mission ; Python 3.14 requis) — voir §1.2 |
