# Audit codebase — Knightrock (Pygame CE / PyTMX / Tiled)

> **Date :** 2026-10-08 · **Commit :** `5b2b9cd` · **Mode :** lecture seule, aucun fichier modifié
> **Périmètre :** 172 modules / 36 937 LOC `src` · 143 fichiers de test / ~2 490 tests · 4 benchmarks
> **Auteur :** audit senior game programming (Python / Pygame CE)
>
> **Avertissement de méthode.** Les finds 1 à 12 sont **vérifiés directement**
> (lecture + exécution). Les finds 13+ proviennent d'explorations parallèles mais
> sont **adossés à du code relu** ; ce qui n'a pas été re-vérifié est signalé.
> Aucun fichier du dépôt n'a été modifié.
>
> **Prérequis de relecture.** `assets/data` et `assets/graphics` sont absents d'un
> clone (§D1) : sans eux, `tests/unit/test_levels_manifest.py` **casse la collecte**
> (§D1 aggravant 1) et la suite entière s'interrompt. Sur un checkout sans assets,
> `pytest` donne ~106 échecs au lieu des 7 de §K — ce n'est pas le même projet.
> Les mesures de §E et les censeurs de §I/§G ne sont reproductibles qu'avec eux.
> Les chiffres de *performance* n'ont pas été rejoués lors de la relecture ; ils
> sont laissés tels quels, marqués « mesuré » et non « re-vérifié ».

---

## Sommaire

- [A. Executive Summary](#a-executive-summary)
- [B. Architecture actuelle](#b-architecture-actuelle-observée-pas-supposée)
- [C. Points positifs](#c-points-positifs--ne-pas-refactorer)
- [D. Critical Issues](#d-critical-issues)
- [E. Performance Audit](#e-performance-audit)
- [F. Game Programming Audit](#f-game-programming-audit)
- [G. Architecture & Maintainability](#g-architecture--maintainability)
- [H. Python Code Quality](#h-python-code-quality)
- [I. Tiled / PyTMX Audit](#i-tiled--pytmx-audit)
- [J. Bugs / Edge Cases](#j-bugs--edge-cases--scénarios-concrets)
- [K. Testing](#k-testing)
- [L. Prioritized Action Plan](#l-prioritized-action-plan)
- [M. Quick Wins](#m-quick-wins)
- [N. Long-Term Risks](#n-long-term-risks)
- [Annexe](#annexe--fichiers-dinspectés)

---

## A. Executive Summary

Le code est **nettement au-dessus de la moyenne** pour un projet « from scratch ». Ce n'est pas
une démo : il y a un timestep fixe déterministe, un système de rollback avec checksum géométrique
quantifié, un pipeline de contact unifié melee/projectiles/hazards, une caméra à transform unique,
un banc de debug complet, et 2 490 tests. La rigueur est réelle, pas cosmétique.

**Mais le projet n'est pas livrable en l'état, et l'audit ne peut pas le dire autrement :**

> **Tout le contenu du jeu — les 9 cartes Tiled, les 11 tilesets, et 100 % des sprites — est
> exclu du contrôle de version** (`.gitignore:39-40`). Trois fichiers `.mp3` sont les seuls assets
> commités. Un clone frais ne contient **aucune map et aucun sprite** : `LEVEL_PATHS` pointe sur
> `assets/data/levels/1.tmx`, qui n'existe pas. Le bundle PyInstaller construit en CI
> (`knightrock.spec`) est donc un jeu sans contenu.
>
> **Relecture : la CI n'est pas verte, elle est rouge — et c'est pire que « un test qui
> skip ».** `test_levels_manifest.py:32-36` ne peut pas skipper : le
> `@pytest.mark.parametrize(path, _tmx_files())` de la ligne **61** évalue son argument **au
> chargement du module**, et `_tmx_files()` (`:39-41`) lève un `assert` quand le dossier est
> vide. Le `pytestmark` de la ligne 32 n'arrive jamais à s'appliquer. Mesuré sur un checkout
> sans `assets/` :
>
> ```
> collected 2480 items / 1 error
> tests/unit/test_levels_manifest.py:41: in _tmx_files
>     assert files, f"no .tmx found under {LEVELS_DIR}; ..."
> !!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!!
> ```
>
> Exit 2, **toute la session avorte** — aucun test ne s'exécute. Introduit par `82dde22`
> (2026-09-26, sur `master`). La conclusion de l'audit tient — aucune validation de contenu
> n'atteint la CI — mais la mécanique est un arrêt de collecte, pas un skip silencieux.

Deux constats de même nature s'ajoutent :

> **Aucun ennemi n'a jamais existé en jeu.** Les niveaux Tiled autort `shell` (×7) et `tooth` (×5),
> mais `ENEMY_CONFIGS` ne contient que `goblin`, `dummy`, `slime`. Vérifié :
> `is_enemy_type('shell') is False`. Les 12 objets tombent en `Sprite` décoratif inerte
> (`world_builder.py:360-361`). Conséquence : **tout le système de combat, ses 40+ tests et son
> rollback n'ont jamais été exercés contre le contenu réel d'un niveau.**

Et la suite **n'est pas verte** : `7 failed, 2478 passed, 5 skipped` (2490 tests). Le README
annonce « 2491 tests passing » ; `notes/ecarts_ouverts.md:109` annonce « 1273 passed » avec
« la première fois que les deux sont vertes ». Aucun de ces chiffres n'est vrai aujourd'hui.

**Ce qui va bien est réellement bon** et ne doit pas être refactoré : le game loop, la séparation
update/render, le culling avant travail coûteux, le pipeline de combat, la caméra, et la discipline
de tests. Le problème n'est **pas** la complexité — c'est la **traçabilité du contenu** et **trois
bugs de gameplay réels**.

---

## B. Architecture actuelle (observée, pas supposée)

```
main.py ──dictConfig──> Game (700 l.)  ── owns: pygame, SceneManager, AssetLibrary,
 AudioBus, SaveGame, RollbackSystem, Settings │
   └── SceneManager ── pile de Scene (switch/push/pop)
         ├── MenuScene / OptionsScene / ControlsScene / VideoScene / LevelSelectScene
         └── GameplayScene (317 l.) ── possède Level │
                └── Level (446 l.) = FAÇADE ──> GameplayLoop (319 l.) = ORCHESTRATEUR
                     │
                     └── GameplayLoop.update(dt) — ordre porteuse de sens :
                          1. spawn.process(raw)          debug spawner
                          2. begin_tick(raw)            hit-stop -> effective_delta
                          [si suspended: camera+notif+tick, return]
                          3. capture_sweep_origin × N frontière de tick
                          4. platform.process           plateformes movibles
                          5. hazard.process             saws / orbites
                          6. physics.process            carry + Entity.update × N
                          7. combat + separation         grille O(n) + hit detection
                          8. projectile.process
                          9. contact.process            dégâts de momentum
                         10. hazard_damage.process      dégâts de hazards
                         11. remove_dead_entities
                         12. respawn -> progression
                         13. camera.process(raw)
                         14. notifications.process
                         15. tick.process               snapshot rollback + tick += 1
```

Le pattern dominant est **système injecté** : `GameplayLoop` ne connaît que des `Protocol`
(`TickOwner`) ou des classes concrètes via `TYPE_CHECKING` ; chaque système est instanciable seul
dans un test. C'est la bonne décision et elle est tenue.

**Ordre observé dans `Entity.update` (`entity.py:1123-1156`) :**

```
is_dead → old_hitbox.copy → vitals.tick_timers → _pre_update (INPUT)
→ _update_state_machine (C/accélération) → combat.update (frames d'attaque)
→ move() (PHYSIQUE COMPLÈTE) → _tick_juggle → combat.sync_attack_box
→ _post_update → _update_animator
```

Point notable : **l'accélération horizontale n'est pas dans `Entity.update`**, elle est appelée
depuis *chaque état* (`player_states.py:108,179,193,…`). Un état qui oublie l'appel n'accélère pas.

**Ordre réel de `move_entity` (`movement.py:290-342`) :**

```
sub-step X (résolution horizontale) → GRAVITÉ → sub-step Y (résolution verticale)
→ _snap_to_ground → _revert_carry_crush → update_contact_state
```

— la gravité est **entre** les deux axes, pas avant. Une seule requête au spatial hash
(`movement.py:301`) est réutilisée pour tous les sub-steps des deux axes : bonne décision.

### Comparaison avec l'ordre canonique attendu

| Étape attendue | Réel | Verdict |
|---|---|---|
| Input | `_pre_update` (dans `Entity.update`) | OK |
| Game state / IA | `_update_state_machine`, **après** l'input | OK — l'état lit l'input du tick |
| Physique (intégration) | `move()` — X, puis **gravité**, puis Y | OK, gravity placement argumentable |
| Collision | **dans** `move()`, par axe, sub-steppé | OK |
| Gameplay (dégâts) | après la séparation, en fin de tick | OK |
| Animation | `_update_animator`, **dernier** | OK |
| Caméra | `camera.process(raw_delta)`, queue du pipeline | OK |
| Rendu | hors pipeline, dans `Game.step` | OK |

Le seul écart notable : la caméra reçoit `raw_delta` alors que le monde reçoit `effective_delta`.
C'est délibéré (la caméra doit continuer pendant le hit-stop) et c'est correct.

---

## C. Points positifs — ne pas refactorer

| Domaine | Preuve |
|---|---|
| **Game loop** | `game.py:489` clamp `MAX_FRAME_TIME=0.1`, `game.py:521-527` cap `MAX_TICKS_PER_FRAME=6` **et remets l'accumulateur à zéro**. Les deux moitiés du garde-fou anti-spirale sont présentes, et `test_frame_pacing.py:217-263` le prouve y compris en reconstruisant l'arithmétique d'avant le cap. |
| **Pacer unique** | `game.py:434-461`. Le double-pacage (clock + vsync) est diagnostiqué, expliqué et évité. Le plafond est *dérivé* de `Display.FPS`, pas codé en dur. |
| **Update/render séparés** | `Game.step` : events → ticks → `scene_manager.draw()` → `_present()`. Aucun accès mutuel simulation/rendu. |
| **Transform caméra unique** | `Camera.begin_frame` (`camera.py:150-178`) calcule shake/blend/offset/viewport **une fois** ; `apply_snapped` (`camera.py:342-364`) applique l'unique règle d'arrondi. `test_frame_coherence.py:130-154` mesure un écart ≤1 px sur tous les sprites — là où l'interpolation par sprite donnait un whole-camera-step. |
| **Culling avant travail coûteux** | `renderer.py:598-603` : rect → `colliderect` → *puis* `apply_snapped` → *puis* `_scaled_image`. Le cache de scaling n'est jamais touché pour un sprite cullé. Les trois plans cullent, tous correctement. |
| **Overdraw** | 0.49× — la frame peint **moins d'un écran** de pixels, à toute densité. |
| **Surface de rendu** | Exactement 2 surfaces plein écran. Cible = rect de letterbox, présentation **1:1 sans resampling** (`presentation.py:177`). `density` est fonction pure de la cible, donc la caméra ne peut pas en disagreed. |
| **Pipeline de contact** | Un seul moteur (`ContactSystem`) pour melee / projectiles / hazards / contact damage. Tampons réutilisés partout ; mesuré à **31 octets/tick** sur un passage 4v4. `OffensiveBox` dégelé délibérément parce que les producteurs hazard le réécrivent — et l'invariant d'identité est testé. |
| **Déterminisme** | `determinism.py` : SHA-256 sur géométrie **quantifiée** (1/1024 px). Ordre des cibles stabilisé, parité grille/sans-grille vérifiée, hit-vs-hit vérifié sur les 6 permutations. `level.py:380-384` traite correctement le `id()` recyclé. |
| **Ordering des dégâts** | Détection **entièrement achevée** avant toute application de dégâts. `_resolve_hit_vs_hit` n'appelle que `cancel_attack()` (clear la hitbox), jamais `receive_damage`. C'est la propriété de déterminisme clé, et elle tient. |
| **Suppression d'entités en itération** | Vérifié partout : `tuple(...)` ou `list(...)` systématiquement. `pygame.Group.update` itère une copie. **Aucune instance trouvée.** |
| **Contrôle des couches** | `Level._install_static_culls` (`level.py:202-227`) refuse d'installer l'index si un sprite mobile est dans le plan figé. Ce genre de garde est rarement écrit. |
| **Profondeur de tests** | 41 502 LOC de tests pour 36 937 de source (**1.12×**), 34 s contre 15 min de budget CI. Les tests de perf comptent des **opérations**, pas du temps — bonne discipline. Goldens par digest quantifié (`test_simulation_golden.py`), insensible aux pixels. |
| **Pas d'allocation par frame côté combat** | Pools, tampons réutilisés, géométrie mise en cache. Vérifié. |
| **Documentation des décisions** | `settings.py` documente ses invariants (`SWEEP_MAX_DISPLACEMENT_PX` : « invariant at fixed sim dt »), `spatial_hash.py:52-54` justifie `QUERY_MARGIN_PX`, `hitbox_manager.py:288-290` explique pourquoi `_scaled_cache` retient sa source. |

---

## D. Critical Issues

### D1 — CRITICAL · Tout le contenu du jeu est hors contrôle de version

| | |
|---|---|
| **Localisation** | `.gitignore:39-40` · `src/core/level/level_manager.py:11-13` · `tests/unit/test_levels_manifest.py:32-36` · `knightrock.spec:12-15` |
| **Constat** | `git ls-files assets` → **3 fichiers** (les `.mp3` d'UI). `assets/data/` (les 9 `.tmx`, 11 `.tsx`) et `assets/graphics/` (tous les `.png`) sont ignorés. |
| **Pourquoi c'est grave** | Le contenu est la donnée la plus fragile d'un jeu (format binaire propriétaire pour les cartes). Le seul moyen de le versionner est de le commiter. En l'ignorant : aucun historique, aucune revue, aucun diff, et **une régression de map est indétectable**. |
| **Scénario** | `git clone` → `uv sync` → `python main.py` → `LevelManager.get(0)` → `FileNotFoundError` → écran FATAL ERROR. Le cloneur ne peut même pas voir le jeu. |
| **Aggravant 1** | `test_levels_manifest.py` est censé **skip** quand `assets/` est absent, ce qui est le cas de la CI. Il ne skip pas : il **erreur à l'import** (voir §A). Le `skipif` de `:32` est inatteignable, le `parametrize` de `:61` déclenche l'`assert` de `:41` au chargement du module, et la session s'interrompt en codes de sortie 2. Depuis `82dde22`. |
| **Aggravant 2** | `build.yml:76` construit PyInstaller. Le bundle publié part sans un seul sprite ni une seule carte. |
| **Recommandation** | Supprimer les deux lignes du `.gitignore`. Si les `.png` posent un problème de taille, utiliser **git-lfs** — pas l'exclusion. |
| **Effort** | SMALL (minutes) · **Risque** LOW · **Bénéfice** maximal de tout l'audit |

---

### D2 — CRITICAL · Aucun ennemi n'a jamais existé

| | |
|---|---|
| **Localisation** | `src/entities/enemies/configs.py:5-9` · `src/core/level/world_builder.py:334-363` · `assets/data/levels/1.tmx:433-472` |
| **Constat** | `ENEMY_CONFIGS = {"goblin", "dummy", "slime"}` (et `data/gameplay/enemies.json` identique). Les niveaux TMX autort `shell` (×7) et `tooth` (×5). |
| **Vérifié** | `is_enemy_type('shell') → False`, `is_enemy_type('tooth') → False`. |
| **Mécanisme** | `world_builder.py:341-363` dispatche sur `obj.name`. Nom inconnu + `obj.image is not None` → `Sprite` figé dans `all_sprites` (`world_builder.py:360-361`). Silencieux. |
| **Pourquoi c'est grave** | Le jeu est un *hack and slash*. Il n'a aucun ennemi. Toute la machinerie combat — 752 lignes de `combat_component`, 585 de `contact_system`, le rollback, les 40+ tests combat — n'a jamais tourné contre le contenu d'un niveau. Les tests passent contre des doubles ; le contenu réel n'existe pas. |
| **Scénario** | Lancer `1.tmx`. Le joueur traverse un niveau vide. Les 12 ennemis sont des sprites décoratifs qui ne recoivent ni IA, ni PV, ni hitbox. |
| **Second problème** | La propriété custom `reverse` est autort sur les 12 (×7 dans `1.tmx`) et **lue par rien** dans `src/`. `EnemyConfig` n'a pas ce champ. |
| **Note** | L'art **existe** : `assets/graphics/enemies/shell/` et `tooth/` sont présents. Seule la déclaration Python manque. |
| **Recommandation** | Décider explicitement : soit ajouter `shell`/`tooth` à `ENEMY_CONFIGS` + `enemies.json`, soit renommer les objets TMX vers des types enregistrés. Puis **ajouter un test qui charge un vrai `.tmx` et asserte que le compte d'ennemis > 0** (voir D1 : impossible aujourd'hui en CI). |
| **Effort** | MEDIUM · **Risque** MEDIUM |

---

### D3 — CRITICAL · Le `.gitignore` rend la CI incapable de valider quoi que ce soit

Ci-dessus, D1. Je le sépare car c'est le point qui fait échouer toute garantie future : tant que
`assets/` est ignoré, **aucun test d'intégration de contenu ne peut être ajouté**, donc D2 restera
invisible. C'est la cause racine ; D1 et D2 en sont les symptômes.

**Relecture — la formulation d'origine était trop douce.** L'audit disait « la CI est verte parce
que le manifeste skip ». La réalité mesurée est pire : la collecte **échoue** et pytest avortent
la session entière. Ce n'est plus une garantie absente, c'est une garantie qui **retourne le code
de sortie 2** — donc un build rouge, pas un build mensonger. Les deux versions disent la même
chose sur le fond (rien n'est validé), mais il faut corriger la mécanique avant d'écrire le plan.

---

## E. Performance Audit

**Verdict global : la performance n'est pas un problème de ce projet.** Mesures (pilote SDL
logiciel, ratios = ce qui compte) :

| Poste | 720p | 4K | Budget |
|---|---|---|---|
| Monde entier (draw) | 1.27 ms | — | 16.7 ms |
| Fill plein écran | 0.21 ms | 1.9 ms | — |
| Present (blit 1:1) | 0.34 ms | 3.2 ms | — |
| Overdraw | **0.49×** | 0.49× | — |
| Frame complète, `DEBUG=1` | 10 % du budget | 62 % | — |

Aucune optimisation micro n'est justifiée ici. Les vrais finds :

### E1 — HIGH · `_SHEAR_CACHE` recyclage d'`id()` → surface de mauvaise taille

`renderer.py:124,181` : clé `(id(image), skew)`, **ne retient pas la source**.
`renderer.py:288-290` explique précisément pourquoi `_scaled_cache` doit la retenir.
`_SHEAR_CACHE` commet exactement l'erreur que le fichier documente contre lui-même.

Démontré : une source 32×40 met en cache `(38,40)` ; `id()` recyclé sur une surface 70×60 →
`_sheared` renvoie `(38,40)`. Puis `turn_frame` (`renderer.py:114-118`) construit le rect de blit
depuis la surface *cisaillée* alors que `apply_snapped` l'a dimensionné depuis la surface *non
cisaillée* → `pygame.blit` recadre silencieusement. Le chemin flash (`renderer.py:641-651`)
construit une surface **neuve chaque frame** et l'alimente : 60 frames = 60 entrées pour 60
sources transitoires.

**Fix :** retenir la source dans la valeur cachée, comme `_scaled_cache:364`.
**Effort SMALL · Risque LOW.**

### E2 — HIGH · `_scaled_cache` / `_flash_cache` croissent sans borne

`renderer.py:291,294`. Mesuré sur 200 cycles spawn+destroy : **200 entrées, 3,1 Mo + 2,76 Mo
retenus**, soit **~29 Ko par ennemi**. Aucun éviction hormis `set_surface`
(`renderer.py:337-338`). Les touches de spawn debug `G`/`P`/`T` sont sur un cooldown de 0,5 s
(`settings.py:2084`) → **~1,9 Mo/minute** en maintenant une touche. Chaque `create_enemy` crée
une `Surface` neuve (`entity.py:190`) donc un nouvel `id` et une entrée permanente. La mort d'un
ennemi ne libère rien : le cache tient la surface en vie.

Second cache non borné par-dessus : `Animator._display_cache` (`animator.py:77`), **une instance
par ennemi** (`enemy.py:210`) et par hazard (`hazards.py:27`).

Le pattern d'éviction existe déjà dans le fichier : `_SHEAR_CACHE` utilise une demi-éviction
(`renderer.py:198-221`). **Effort SMALL · Risque LOW.**

### E3 — HIGH · Le plan statique disparaît silencieusement quand l'index est refusé

`renderer.py:564-565` :

```python
if static_index is None:
    return ()          # ← pas de repli linéaire
```

La docstring `renderer.py:299-302` affirme « keeps the linear scan ». Le code ne le fait pas.
Mesuré : **107 blits avec index, 21 sans** — les 839 tuiles de terrain ne sont pas dessinées.

Le chemin est atteignable : `level.py:222-225` refuse délibérément l'index et journalise
*« the linear cull is kept »* — un message qui ment. Un niveau avec un sprite mobile dans le plan
figé donne **un monde vide**.

**Fix :** restaurer le scan linéaire dans `_static_plane` (le commentaire promet déjà ce
comportement). **Effort SMALL · Risque LOW.**

### E4 — MEDIUM · La cible de rendu n'est jamais convertie au format d'affichage

`presentation.py:42` : `convert: bool = False`, et `game.py:252-254` ne le passe pas →
`viewport.py:48-49` (`surface.convert()`) **n'est jamais exécuté en production**.

Les *sources* sont converties (`asset_library.py:55`), donc : 88 surfaces opaque déjà converties
blittant dans une cible **non convertie**. Sur cette machine cela ne coûte rien (masques
identiques : `0xff0000/0xff00/0xff/0x0` des deux côtés), donc l'affirmation de `viewport.py:45-47`
est *non vérifiée* plutôt que fausse. Sur une plateforme où le format par défaut diffère,
**chaque blit (~115) et le present paient une conversion par pixel** (mesuré en 24 bits : present
0.34 → 0.49 ms).

**Fix :** passer `convert=True` à `game.py:252`. Le chemin existe déjà, il est gardé.
**Effort SMALL · Risque LOW.**

### E5 — MEDIUM · `velocities` paie pour `debug_reference` même désactivé

`world_ui.py:152` construit la référence de debug **avant** le dispatch de couche à `:155-159`.
Mesuré : 88 µs avec *n'importe quelle* couche active, 12.7 µs avec aucune. Le coût partagé de
76 µs est un travail que la couche désactivée jette. C'est exactement la classe de correctif que
`statics` a déjà reçu (`notes/perf_debug_overlay.md`). **Effort SMALL · Risque LOW.**

### E6 — LOW · `TileChunkIndex.candidates` alloue 3 conteneurs par frame par plan

`tile_chunk_index.py:148-155`. 10.3 µs à 720p. Un set scratch réutilisé (comme
`AnnotationSink.clear` le fait déjà, `world_overlay_shared.py:177-185`) en retire deux.
**Non urgent.**

### Points de performance explicitement **non** problèmes (à ne pas « optimiser »)

- **Allocs par frame** : 127 `Rect` + 110 `FRect` (≈9 Ko C-side), transitoires, absorbés par les
  free-lists CPython. 4 blocs Python / 144 octets nets. **Non méritant.**
- **TileChunkIndex** : mesuré **7 % plus lent** que le scan linéaire sur le niveau livré
  (0.264 vs 0.246 ms) — mais **plat** quand le scan est linéaire. 839 tuiles est le point de
  basculement. **C'est le bon choix à livrer**, il ne faut pas le débrancher.
- **Aucun chargement d'image en jeu**, aucun `Surface` alloué par frame en régime établi, aucune
  donnée statique recalculée.
- **FX** : `_scaled_image_once` correct et bon marché (68 µs pour un plan complet).
- **Terrain blits à destination alignée 4 octets** : ~6× plus lents que non alignés. C'est un
  artefact du rasteriseur logiciel SDL sous le dummy driver ; **ne pas optimiser contre ça.**
- `Debug.is_enabled()` fait un `os.getenv` par appel (0.69 µs, 14 sites) — le comportement
  « env-var au moment de l'appel » est ce qui fait marcher `main_debug()`. **Ne pas mettre en cache.**

---

## F. Game Programming Audit

### F1 — Game loop : excellent. (Le bémol annoncé initialement était erroné.)

Voir §C. **Relecture : le bémol annoncé ici est faux, et il a été recopié sans relire.** L'audit
reprise l'item R-1 de `notes/audit_consolide.md:91-95` (« `settings.py:14-16` commente encore
"rendering at 120 FPS" alors que `FPS = 60` »). À `5b2b9cd` cette phrase n'existe plus : `grep
"120 FPS" src/core/settings.py` ne renvoie rien, et la docstring de `Display` (lignes 10-26) a
été réécrite — elle explique maintenant que `FPS` est la base du plafond anti-emballement
(`game.DISPLAY_SAFETY_CEILING_FPS`) et le distingue de la limite de frames choisie par le joueur.
`FPS = 180` est ligne 28.

Le drift est donc **corrigé**, et le reliquat R-1 de l'audit précédente peut être clos. Ce que
reste vrai de F1 : le game loop lui-même est excellent (§C), sans réserve.

### F2 — Physics : `HIGH` — le budget de tunneling n'est ni observé ni testé

Pas de test continu : la résolution est **discrète**, avec sub-stepping comme mitigation :

```
steps = min(MAX_SUBSTEPS_PER_AXIS=8, ceil(|move| / SUB_STEP_SIZE=16))
```

Mesuré : le résolveur est exact jusqu'à **128 px/tick = 7 680 px/s**. Au-delà il se dégrade
silencieusement — `steps_x` est un `min(...)`, sans avertissement, sans drapeau, sans test.
Vitesse max livrée = 900 px/s de knockback (×2.0 charge = 1 800), soit 1–2 sub-steps :
**marge ×4, non exploitable aujourd'hui**, mais le plafond est muet.

**Le vrai danger est la marge de requête** — `spatial_hash.py:52-54` :

```python
#: 32 px — MAX_FALL_SPEED 1500 / 60 Hz ≈ 25 px, plus a little headroom.
QUERY_MARGIN_PX = 32.0
```

C'est une **hypothèse à 60 Hz**, écrite en prose, **appliquée nulle part dans le code et testée
nulle part**. Mesuré : un gap de **90 px est manqué à 60 Hz** et rattrapé à 30 Hz ; un
déplacement horizontal à 40 000 px/s tunnel à travers la grille.

**Recommandation :** ajouter une assertion (et son test) que
`QUERY_MARGIN_PX >= MAX_FALL_SPEED * Simulation.TIMESTEP`. C'est un test de constante, la bonne
forme de test — exactement comme `test_camera.py:289-299` le fait déjà pour `MAX_SPEED_PX_S`.
**Effort SMALL · Risque LOW.**

### F3 — Physics : `HIGH` — `_snap_to_ground` désynchronise collisionneur et hurtbox

`movement.py:376-377` :

```python
if best is not None:
    entity.hitbox.bottom += best
    entity.velocity.y = 0.0
```

**Aucun `sync_rects()`.** Après l'ajustement, `rect`, `hurtbox` et `contact_shape` restent
périmés pour le reste du tick. Mesuré sur une `Entity` réelle atterrissant dans la fenêtre de
snap : `hitbox.bottom = 200.0` mais `rect.bottom = 197.4` et `hurtbox.bottom = 197.4` —
**désaccord de 2,6 px entre le collisionneur et ce que la détection de coup lit**. Auto-corrigé
au tick suivant. La hitbox d'attaque est sauve (`sync_attack_box`, `entity.py:1154`, lit `hitbox`
directement).

**Effort SMALL · Risque LOW.**

### F4 — Physics : `MEDIUM` — `_revert_carry_crush` annule sur n'importe quel crush

`movement.py:378-389` lit `entity.crushed`, que `_flag_crushed` positionne dès qu'une correction
dépasse `MAX_RESOLVE_PX=16` (`collisions.py:169-175`) — **y compris un simple choc de mur**. Le
drapeau et la sauvegarde ne sont pas causalement liés. Mesuré : un combattant porté par une
plateforme ascendante qui percute un mur qu'il chevauchait déjà se retrouve téléporté à sa
position pré-porte avec **les deux vitesses mises à zéro**. `test_collision_robustness.py:112-127`
teste la réversion isolément et passe.

### F5 — Physics : `MEDIUM` — friction de dash décrue deux fois le dt

`player_states.py:472-473` :

```python
friction = max(0.0, 1.0 - self.entity.dash.friction * delta_time)  # déjà un facteur par tick
apply_velocity_friction(self.entity, friction, delta_time)           # qui multiplie par dt ENCORE
```

`apply_velocity_friction` calcule `alpha = 1 - exp(-friction*dt)`. Décroissance effective :
`exp(-(1-f*dt)*dt)`.

**Vérifié directement :** `DASH_FRICTION = 25`, départ 800 px/s, après 1 s →
**30 Hz : 677.2 / 60 Hz : 446.4 / 120 Hz : 362.5**. Avec l'usage correct
(`friction = DASH_FRICTION`) on obtient 0.0 aux trois.

**Nuance importante et à ne pas mal rapporter :** la simulation est à timestep fixe 60 Hz
(`Simulation.TIMESTEP`), donc **ceci ne se manifeste pas comme une dépendance au FPS en jeu**.
C'est un **bug d'équilibrage** : le dash perd sa vitesse bien trop lentement (446 px/s restants au
lieu de ~0). À corriger comme tel.

**Effort SMALL · Risque MEDIUM** (change le feel du dash — c'est la mécanique signature ;
`test_knockback_feel.py` existant ne couvre pas le dash).

### F6 — Physics : frame-rate independence — bien fait, sauf le noted ci-dessus

`alpha = 1 - exp(-k*dt)` partout (`movement.py:204,218,222`, `velocity.py:11,17`), gravité en
`accel*dt` avec terme de traînée (`gravity.py:63-65`), animateur en `while` sur dt accumulé
(`animator.py:112-127`) — **indices de frame identiques vérifiés à 30/60/120 Hz**. Coyote time
(0.12 s), jump buffer (0.10 s) et hauteur de saut variable (`velocity.y /= 2.5`, un scaling
instantané donc indépendant du dt) sont tous en dt.

**`LOW`** : le coyote rend **133 ms au lieu des 120 ms configurés** —
`JumpController.update` (`player_controllers.py:87-95`) remplit *avant* de décrémenter, et
`update_timers` tourne dans `_pre_update` **avant** `move()` (`entity.py:1143` vs `1148`), donc la
presse est toujours évaluée contre le flag de contact du tick précédent.

**`MEDIUM`** : `src/physics/` ne dit nulle part que `move_entity` est une fonction de dt à
appeler à 1/60 seulement. `src/combat/sweep.py:12-14` le fait correctement ; la physique non.
C'est un invariant porté uniquement par la documentation du game loop.

### F7 — Combat : `HIGH` — les dégâts de hazard n'ont aucun cooldown

`hazard_damage.py:41-64` réémet la même box **à chaque tick**, avec `can_contact=_always_contact`
(ligne 61). `Entity.receive_damage` n'accorde des i-frames que si
`invincibility_duration > 0` (`vitals.py:102-105`) — **et `Enemy` ne le configure jamais**.

**Vérifié directement :**

```
enemy invincibility_duration = 0.0
after set_invincibility, timer = 0.0    ← no-op
```

Un saw à 20 dégâts tue un ennemi de 100 PV en **5 ticks (83 ms)**. Le joueur est immunisé
uniquement grâce à sa fenêtre de 0.18 s.

Même défaut dans le contact damage : `MomentumGate` (`contact_damage.py:44`) teste
`other.combat.is_hurt`, mais le producteur passe `interrupt=False` (ligne 112) et `receive_damage`
n'entre en état hurt que via `_handle_heavy_knockback`/`on_hit` — **la porte ne peut jamais se
déclencher**. Vérifié : 8 ticks consécutifs, 5 dégâts chacun, `b_hurt` jamais True.

Le `remove_dead_entities` tourne après les quatre producteurs de dégâts, donc le cadavre est
récolté au même tick — mais le burst est instantané. `test_hazard_damage.py` n'appelle
`process()` qu'**une fois** par test : le cas multi-tick n'est couvert par rien.

Il existe un gating équivalent pour le contact damage (`MomentumGate`) mais **aucun pour les
hazards**. **Effort MEDIUM · Risque MEDIUM** (introduit une mémoire par cible ; à faire
carefully pour ne pas casser les hazards balayants legitimately).

### F8 — Combat : `HIGH` — `stagger_timer` décru deux fois pendant le dizzy

`Vitals.tick_timers` (`vitals.py:109-110`, appelé par `entity.py:1131`) décrue inconditionnellement.
`EnemyDizzyState.update` (`enemy_states.py:455-456`) et `PlayerDizzyState.update`
(`player_states.py:517-518`) décruent **encore**.

**Vérifié directement** sur le chemin : `1.0 → 0.98333` (un tick) `→ 0.96667` (le dizzy décruit
encore). **Toutes les fenêtres dizzy / parry-stun sont exactement la moitié de leur durée
configurée.** `StaggerState` (`reaction_states.py:153-178`) lit le timer sans le décruire — donc
stagger est correct, seul dizzy est affecté. Le commentaire `reaction_states.py:19-22` *constate*
l'exception sans la réconcilier.

**Effort SMALL · Risque MEDIUM** (double l'effet d'un stun — c'est un changement de game feel,
mais dans le sens d'un bug évident).

### F9 — Combat : `HIGH` — un attaquant déjà annulé continue d'annuler un troisième

`combat_system.py:218-252`, **relu ligne à ligne** : la boucle teste `if id(...) in clashed`
(ligne 227) et rien d'autre. **`losers` n'est pas consulté *dans cette boucle*** — ce n'est
cependant pas du code mort : `_produce_boxes` (`:194`) le consomme pour ne pas produire de box
d'un attaquant déjà annulé. Ce qui est réel, c'est qu'un attaquant annulé **reste dans la boucle**
et peut gagner un nouveau clash. Puisque `_ReadyAttacker` détient un **snapshot des objets
`FRect`** pris dans `_collect_ready` (`combat_system.py:54-55`) et que `cancel_attack()` →
`hitbox.clear()` vide `_pool` **sans muter les rects** (`hitbox_manager.py:109-116`), la géométrie
de l'attaquant mort survit dans le snapshot et continue de gagner les comparaisons.

**Fix :** ajouter `or id(...) in losers` à la ligne 227. **Effort SMALL · Risque MEDIUM** (modifie
qui gagne un clash — mais le comportement actuel est manifestement non intentionnel).

### F10 — Combat : `MEDIUM` — l'échelle de juggle est globale à l'attaquant, pas par cible

`hit_resolver.py:24-29` décrue les dégâts par `air_combo_count * 0.1`. Vérifié : frapper A puis B
applique le scaling de B au follow-up sur A. `ComboTracker.air_count` (`combo_tracker.py:132-133`)
n'a pas de clé de cible. De plus `ComboTracker.reset()` (`:94-98`) **omet `air_count = 0`**,
incohérent avec `restore`.

### F11 — Combat : `MEDIUM` — le crédit de dégâts dépend de l'ordre du groupe après un rollback

La santé est identique dans tous les cas testés, mais `targets_hit` diffère. `Level.load_state`
(`level.py:380-384`) réinscrit les entités ressuscitées dans l'ordre du snapshot, qui n'est
**pas** l'ordre d'insertion original — vérifié avec un vrai `pygame.Group` : kill-and-readd
déplace le sprite en fin de liste. **Rayon d'impact limité** : ne se manifeste que quand un coup
létal et un second attaquant atteignent la même cible dans la même frame.

### F12 — Combat : `MEDIUM` — 3 blocs `getattr`/`hasattr` dans `hit_resolver.py`

L'item R-3 de `notes/audit_consolide.md:123-127` exigeait zéro `getattr`. **Non fait** — les trois
blocs sont aux lignes citées (80-86 exact ; 158-159 et 164 après croissance du fichier).
`grep -c` = **7**. Le pire : `target: Combatant` **déclare** `state_machine`
(`combatant_protocol.py:179`), donc le `getattr` de 158-159 est une tolérance sans justification, et
le commentaire du protocol (`:161-164`) dit lui-même que c'est « optionnel » tout en le déclarant.

**Et le test de garde a été élargi au lieu du code corrigé** — `test_combat_contracts.py:59-69` :

```python
def test_resolver_uses_typed_access_without_getattr_fallbacks() -> None:
    getattr_count = text.count("getattr")
    assert getattr_count <= 8, ...     # le nom promet 0, l'assertion en tolère 8
```

**C'est un défaut d'intégrité de test**, pas un défaut de code : un garde dont le nom et
l'assertion se contredisent.

Duck-typing plus large dans le même pipeline, hors périmètre R-3 mais à consigner :
`contact_system.py:119,172,185,198,208-213,276-281,501,522`. `_is_valid_target`
(`:202-215`) assume « Duck-typed on purpose » en référence à des *stubs de test* — c'est-à-dire
que **les doubles de test, et non le contrat de production, dictent la signature de production**.

### F13 — Combat : `LOW` — l'accumulateur d'attaque conserve le surplus

`attack_state.py:274-279` avance **au plus une frame par tick** et conserve le surplus (`-=`).
Déterministe, mais après un hitch l'attaque occupe **plus de temps réel** que ses frame-data ne
l'impliquent. Le commentaire (`:275-276`) explique le choix ; le `-=` en contredit la moitié de
l'intention.

### F14 — `LOW` — `metrics.overlaps` compté deux fois

`combat_system.py:231` incrémente, puis `_merge` (`:174`) **additionne**
`outcome.metrics.overlaps`. Vérifié : 5 chevauchements hit-vs-hit + 2 contacts → `overlaps`
rapporte 7. Cosmétique, mais le panneau de debug ment.

### F15 — `LOW` — `_resolve_generic` compte un contact quand `receive_damage` n'a rien fait

`contact_system.py:540-546` appelle `target.receive_damage(...)` et **ignore la valeur de retour**,
puis incrémente inconditionnellement `self.metrics.contacts` (`:546`). Une cible i-framed ou déjà
morte compte quand même. `_resolve_melee` (`:493`) vérifie correctement
`result.applied or result.guarded`.

### F16 — Entités : `entity.py` n'est **pas** une god class

1238 lignes, dont **110 commentaires + 369 docstrings + 154 vides ≈ 605 lignes de code**, et
**21 propriétés dont la plupart sont de la délégation**. La logique lourde a été extraite
(`MovementComponent`, `Vitals`, `ReactionComponent`, `CombatComponent`, `HitboxManager`), et
`tests/unit/test_entity_composition.py:1-22` documente la décision. **Verdict : pas de god class ;
c'est une façade large.** Une seule responsabilité n'est pas déléguée et mérite peut-être ailleurs :
`is_at_ledge` / `find_landing_ahead` (74 lignes) — requêtes de navigation sans état d'entité.

**`LOW`** : crouch — `crouch_posture.py:118-124` redimensionne `hitbox.height` 56 → 33.6 et
appelle `sync_rects`, qui ne touche que `rect.midbottom` (`entity.py:645`) — `rect.size` n'est
jamais modifié. **L'image de 56 px reste donc dessinée** : un combattant accroupi est dessiné
debout. Il n'y a pas non plus d'art `crouch/`, donc `AssetLibrary` retombe sur `player/idle`.
**Le crouch est invisible** (hitbox rétréci, image identique).

### F17 — `HIGH` — le champ des branches d'état est zéro couverture

`movement.py:193-206` — **toute la branche lock/damping du wall-jump** : non couverte par la suite
complète (unitaire + headless). Vérifié par couverture. `DASH_WALL_BOUNCE` et `DASH_AIR_CONTROL`
n'apparaissent dans **aucun** fichier de test. `PlayerWallSlideState`
(`player_states.py:201-214`) non testé.

Le dash est la mécanique signature du jeu ; ces trois chemins n'ont aucun filet.

### F18 — `MEDIUM` — un état machine se verrouille (charge)

`PlayerChargeState` (`player_states.py:217-232`) n'a pas d'`exit()`, et rien n'annule
`combat.charging` sur changement d'état. Vérifié : maintenir `ATTACK_2` → `charge`, puis `DASH` →
`dash` avec `charging == True` et le multiplicateur qui grossit encore. Relâcher `ATTACK_2`
ensuite ne fait rien, car `_handle_charging` (`player_input.py:98-112`) court-circuite sur
`charging.is_charging`. `start_attack` refuse pendant la charge
(`combat_component.py:284-285`). **Le heavy devient inatteignable tant que le combattant n'a pas
été touché.**

### F19 — `MEDIUM` — états enregistrés inatteignables

`EnemyState.TURN` est enregistré mais `PROFILES["enemy"]` hérite de `default` avec
`enabled=False` → `request_turn` renvoie False pour tout ennemi. `EnemyState.CHARGE` enregistré,
jamais entré. **2 des 11 états ennemis sont du code mort.**

`StateMachine.update` (`state_machine.py:132-142`) **ignore silencieusement** un nom non
enregistré — ni raise, ni log, ni compteur. Une faute de frappe dans une valeur de retour gèle le
combattant sans signal.

### F20 — `MEDIUM` — guard + attaque le même tick

`state_machine.py:127-130` : la boucle `return` au premier interrupt qui matche, donc
**`update()` de l'état courant ne tourne pas ce tick**. Priorités :
`hurt(100) → dash(80) → guard(60) → attack(40) → crouch(30)`. Vérifié : presser `ATTACK_1` en
maintenant `GUARD` donne tick 0 = état `GUARD` avec `is_attacking == True` et phase `STARTUP` ;
tick 1 = `ATTACK`. **Le combattant garde en frappant**, une frame.
`test_priority_clash.py` ne couvre pas cette paire.

### F21 — Caméra : excellent, un invariant porté par convention

`Camera.begin_frame` calcule tout une fois (§C). Le smoothing est `min(1, RATE*dt)` avec un
plafond `MAX_SPEED_PX_S * dt` sur la discontinuité — exponentiel, indépendant du dt. Le shake est
`trauma² * MAX_PX` sur un `sin`/`cos` déterministe du temps de tick accumulé → mêmes pixels pour
les mêmes ticks. `hold()` (`camera.py:239-275`) referme l'écart d'interpolation, et **age le shake**
(corrigé en `7f3643b`).

`LOW` : `Camera.follow` est le seul appelant d'`advance_shake` avec `hold`. Un tick qui ne passe
par ni l'un ni l'autre gèlerait **les deux** silencieusement. Aujourd'hui impossible
(`gameplay_loop.py:211` appelle `camera.process` même en hit-stop) — c'est un invariant porteur tenu
par convention, pas par le code.

`LOW` : les barres de vie et les sprites concordent au pixel (`world_overlay_bars.py:132` utilise
`camera.apply` float contre `apply_snapped` flooré) — **0/500 désaccords mesurés**,
`health_bar_rect` à `:86` absorbe. Le bug attendu n'existe pas.

### F22 — `LOW` — changement de tier de locomotion relance le clip

`Animator.play` (`animator.py:103-110`) remet `_frame = 0, _timer = 0` à chaque changement de nom.
`walk`, `walk_slow` et `run` sont trois `AnimationSpec` distinctes sur le **même** répertoire
`run/` avec des durées différentes (`player_animation.py:12-16`) — franchir une frontière de tier
relance le cycle au frame 0 en pleine foulée.

---

## G. Architecture & Maintainability

### G1 — `HIGH` — le dispatch par nom échoue en `logger.debug` sous une racine à INFO

`LevelData.from_tmx` indexe les couches **par nom** (`level_data.py:114,117`) ;
`world_builder.py:296-297` dispatche par nom ; `level_registry.py:60-63` :

```python
handler = self._handlers.get(name)
if handler is None:
    logger.debug("%s: no handler for '%s', ignored", self._kind, name)   # invisible : main.py:29 = INFO
```

Les noms enregistrés sont codés en dur : `"Terrain"`, `"BG"`, `"Platforms"`, `"FG"`
(`world_builder.py:82-85`) ; `"helicopter"`, `"boat"`, `"saw"`, `"spike"`, `"floor_spike"`,
`"flag"` (`:255-260`).

**Scénario :** renommer `Terrain` → `Ground` dans Tiled. Le niveau se charge, affiche un fond, et
a **zéro géométrie de collision** — le joueur traverse le sol. Aucun message.

**Recommandation :** passer ces deux `logger.debug` en `warning`, ou (mieux) **échouer au
chargement** avec une liste des noms attendus. Le comportement par défaut d'un éditeur de niveaux
devrait être *fail loudly* sur un nom inconnu. **Effort SMALL · Risque LOW.**

### G2 — `HIGH` — la visibilité Tiled et l'ordre z sont ignorés

**Visibilité** : `level_data.py:112-119` copie les couches sans lire le drapeau.
`TiledTileLayer` le parse (`pytmx.py:1370`), et `4.tmx` masque **cinq** couches (`BG` `:11`,
`BG details` `:45`, `FG` `:114`, `Water` `:337`, `Data` `:338`). Un level designer qui masque
une couche de décor **n'a aucun retour** et elle continue d'être dessinée. `opacity`,
`offsetx/offsety` et l'attribut `class=` sont également ignorés.

**Ordre z** : détruit deux fois. (1) pytmx réordonne (`pytmx.py:592-608`) — *tous* les `<layer>`
d'abord, puis *tous* les `<objectgroup>`, indépendamment de l'ordre du document ; l'ordre de
`1.tmx` est `BG, BG details, Terrain,…` mais `m.layers` est `BG, Terrain, Platforms, FG,
BG details, …`. (2) Le builder met **tout** le plan objet dans `all_sprites` (le plan *moving*),
rendu **après** les 839 tuiles statiques (`renderer.py:534-539`). Résultat : `BG details` — 45
props de fond autortes **entre** `BG` et `Terrain` — est dessiné **au-dessus** du terrain. Mesuré :
95 des 133 sprites d'`all_sprites` sont des `Sprite` figés, cullés linéairement chaque frame.

**Effort MEDIUM · Risque MEDIUM.**

### G3 — `MEDIUM` — propriétés Tiled autortées 106 fois, lues par rien

Census : `speed` 79 (**lu**), `inverted` **45 (jamais lu)**, `platform` **44 (jamais lu)**, `flip`
33 (lu **uniquement pour `saw`**, `:176`), `reverse` **17 (jamais lu)**.

Le cas `inverted` est le plus vicieux : les 45 `floor_spike` déclarent `inverted="true"`,
`_build_static_hazard` (`:231-247`) ne lit que `damage`, et l'orientation visuelle vient en fait
du **bit de flip du GID** — présent sur **un seul** spike sur 25 (`1.tmx:213`). **24 spikes
"inverted" se dessinent non-inversés, sans rien le signaler.**

`flip` sur les plateformes movibles : `_build_moving_platform` (`:131-164`) ne lit jamais `flip` ;
seul `_build_span_hazard` (`:176`) le fait. Un designer mettant `flip=true` sur un `helicopter`
obtient une plateforme identique.

### G4 — `MEDIUM` — une propriété mal typée plante tout le niveau

`world_builder.py:141,175,213` et `level_data.py:152-156` font `float()` / `int()` **non
gardés**. Le type par défaut d'une nouvelle propriété Tiled est *string* : un `"speed"` en string
→ `ValueError` brut hors de `LevelManager.get` → écran FATAL ERROR. Inverse :
`bool(obj.properties.get("flip", False))` (`:176`) — une string `"false"` est truthy, donc
**`flip` s'inverse silencieusement, sans erreur du tout**.

### G5 — `MEDIUM` — `bg=""` devient la chaîne littérale `"None"`

`pytmx.py:363` fait `subnode.get("value") or subnode.text` ; `"" or None` → `None`. Puis
`level_data.py:151` : `str(props.get("bg", ""))` → `"None"`. Confirmé à l'exécution pour `1.tmx`,
`0.tmx`, `6.tmx`, `omni.tmx` : `LevelConfig(bg='None', …)`. Inoffensif **aujourd'hui** seulement
parce que `renderer.py:428` retombe sur `sky_blue` — mais le sentinelle est détruit et le défaut
documenté `bg: str = ""` est **injoignable** pour tout niveau Tiled.

### G6 — `MEDIUM` — 8 des 9 niveaux sont inatteignables

`level_manager.py:11-13` : `LEVEL_PATHS = {0: "assets/data/levels/1.tmx"}`. `data/gameplay/levels.json`
identique, et gagne à `game.py:95-97`. `1.tmx:484` déclare `level_unlock = 2` ; `game.py:137`
écrit l'id `2` dans la sauvegarde **sans vérifier le registre** — un id que `LevelSelectScene` ne
peut jamais rendre et qui lèverait `UnknownLevelError`. `LevelManager.next_id(0)` renvoie `None`
→ `VictoryScene` direct.

`overworld.tmx` est par ailleurs **structurellement incompatible** : ses couches `main`/`top` ne
sont dans aucun handler (`world_builder.py:82-85`) et il n'a aucun objet `player` →
`world_builder.py:300-304` lève `ValueError`.

### G7 — `MEDIUM` — `LevelManager._cache` retient des surfaces liées au format d'affichage

`level_manager.py:54` : `_cache: dict[int, LevelData]`, écrit `:92`, lu `:93`, **jamais
invalidé** — aucun `clear()` dans le fichier, appelé nulle part.

pytmx convertit chaque tuile **au chargement** contre le display *courant*
(`util_pygame.py:106,110`). `Game._invalidate_assets` (`game.py:342-351`) couvre exactement ce
risque — et traite `shared_library()` et `fx.clear_frame_cache()` mais **pas**
`LevelManager._cache`. Après un changement de résolution, chaque blit de tuile passe par une
conversion alpha logicielle, **pour le reste de la session**.

### G8 — `MEDIUM` — le chemin hash et le chemin linéaire désignent des endowments différents

`platforms.py:33-46` :

```python
spatial_hash = getattr(platform, "spatial_hash", None)
if spatial_hash is not None:
    return (s for s in spatial_hash.get_nearby(candidate) if s is not platform)   # ne filtre PAS one_way
return (s for s in static_sprites
        if not hasattr(s, "waypoints") and not getattr(s, "one_way", False))      # filtre
```

Le chemin linéaire filtre `one_way` ; le chemin grille **seulement `self`**. Les tuiles one-way
sont des membres ordinaires de `collision_sprites` et donc bucketisées (`level.py:136`). **Les
deux chemins ne sont pas d'accord sur où une plateforme a le droit de s'arrêter.** La docstring
`:26-32` s'inquiète précisément de ce désaccord et ne corrige que la moitié « auto-blocage ».

### G9 — `MEDIUM` — `GameplayLoop` : 12 systèmes optionnels

`gameplay_loop.py:60-74` : douze paramètres à `None` par défaut, donc un assemblage invalide
n'échoue qu'à `update()`, pas à la construction. C'est l'item R-4 ouvert. `update()` valide
effectivement tout le câblage **avant toute mutation** via `_require` (`:149-159`) — c'est bien
pensé, et `combat_only()` reste la seule construction partielle. Il ne manque qu'une
justification écrite pour clore le sujet, pas une réécriture.

### G10 — `LOW` — `tile_size` du TMX est lu mais ignoré

`level_data.py:124` enregistre `tile_size=tmx_map.tilewidth`, mais tous les placements multiplient
par `World.TILE_SIZE` (`world_builder.py:44,60,75`), de même que `TileChunkIndex.__init__`
(`tile_chunk_index.py:99`). Re-tiler un niveau à 32 px en Tiled fait que `LevelData.pixel_width`
(qui utilise bien la valeur TMX) rapporte des unités 32 px pendant que le monde est posé en unités
64 px — caméra, index et sprites divergent, **sans assertion nulle part**.

### G11 — `LOW` — `LevelConfig` porte trois champs que rien ne lit

`level_data.py:52-62` le dit lui-même pour `top_limit`/`bottom_limit`/`horizon_line`. Parsés à
`:152-154` de propriétés que chaque niveau définit (8 occurrences chacune), sans consommateur.

### G12 — `LOW` — un hazard orbite le coin haut-gauche, pas le centre

`world_builder.py:218-219` passe `(obj.x, obj.y)` ; `hazards.py:67-71` fait `rect.center = (x,y)`.
Mesuré pour `1.tmx:377` (`x=1472 y=896 w=54 h=54`) : centre à `[1472, 842]` — **27 px en
haut-à-gauche** de là où Tiled l'a placé.

### G13 — `LOW` — la zone d'exit est un carré 64×64 au-dessus du drapeau

`world_builder.py:250-252` + `sprites.py:99` (`Surface((TILE_SIZE, TILE_SIZE))`). Mesuré pour le
drapeau de `1.tmx:195` (68×186) : `exit rect FRect(1856, 326, 64, 64)` — le joueur doit toucher
une boîte 186 px **au-dessus** du haut du drapeau.

### G14 — `LOW` — les couches `Items` et `Water` sont des no-op décoratifs

Les 27 objets `Items` de `1.tmx:403-431` ont des gid → `Sprite` statique, sans ramassage, sans
collision, sans état. `world_builder.py:239-240` code en dur le répertoire d'animation des
hazards dans Python ; aucun niveau ne porte de propriété `damage` (la valeur 20.0 est un défaut
Python dupliqué).

### G15 — `LOW` — doubles `firstgid` dans chaque fichier de niveau

`1.tmx:5-6` déclare `firstgid="72"` **deux fois** (`enemies.tsx` et `grass.tsx`) ; même chose dans
`2.tmx:9-10` (252) et `4.tmx:8-9` (224). Benin **seulement** parce que `enemies.tsx` est vide
(`tilecount="0" columns="0"`). Ajouter une tuile et les deux tilesets partagent silencieusement
une plage de GID (`pytmx.py:671-686`, le dernier gagne `self.images[gid]`).

### G16 — `LOW` — métadonnées de tileset dans chaque dict de propriétés d'objet

pytmx copie les propriétés de tuileset sur l'objet (`pytmx.py:625-628`) — `id`, `source`, `trans`,
`width`, `height`, `frames` atterrissent dans chaque `properties` (`level_data.py:144`). Une
propriété custom nommée `source` est **rejetée au chargement** (`pytmx.py:429-435`).

### G17 — `LOW` — `_build_player` balaie aussi la couche `Data`

`world_builder.py:317-318` itère *toutes* les couches objets pour `obj.name == "player"`, y
compris la couche `Data` que `build()` saute délibérément à `:307`.

### G18 — `INFORMATIONAL` — points d'entrée des assets

`load_pygame(absolute_path)` avec **aucun drapeau** (`level_manager.py:91`). pytmx 3.32 ne
reconnaît que `optional_gids`, `load_all`, `invert_y`, `allow_duplicate_names` —
**`load_layer_objects` et `load_tilesets` n'existent pas dans cette version** (vérifié : passé en
`**kwargs`, silencieusement avalé). Tous les drapeaux réels prennent donc leurs défauts :
`load_all=True` (chaque tuile de chaque sheet décodée et convertie), `invert_y=True`,
`allow_duplicate_names=False`. Mesuré : `get(0)` à froid **12,6 ms**, en cache **0,001 ms**.

**Per-frame : aucune structure PyTMX accédée.** `LevelData.from_tmx` copie tout dans des
dataclasses purs et des `dict`s simples ; `_object_from_tmx` (`:131-145`) matérialise
`points`, `image` et `properties` immédiatement. Le `TiledMap` est un local de
`level_manager.py:91` et devient garbage immédiatement. C'est une **bonne** décision structurelle,
à préserver.

---

## H. Python Code Quality

Le code est propre, typé strictement (`disallow_untyped_defs` global, `mypy src` clean), `ruff`
avec `C901` actif et propre, formaté. Les magic numbers sont **centralisés** dans `settings.py` —
40 classes de constantes, bien nommées et commentées.

Points relevés :

- **Aucun import inutile**, aucune dépendance superflue (`pygame-ce` + `pytmx` seulement).
- **Aucune dépendance circulaire** — les cycles potentiels sont tranchés par `TYPE_CHECKING` +
  `Protocol` (`tick_system.py:20-26` `TickOwner` est l'exemple canonique).
- **`settings.py` à 2108 lignes** est un module de constantes, pas un god object. Volumineux mais
  cohérent ; aucune raison de le scinder. *(Subjectif :* la granularité est devenue irrégulière —
  `Dust` seul pèse 579 lignes — mais ce n'est pas un problème tant que ce sont des constantes.*)
- **Tests qui scrapent le source** : `test_reaction_ownership.py:49-54`
  (`"hasattr(" not in getsource(...)`), `test_world_overlay_bars.py:105-107`
  (`body.count("pygame.draw") == 0`), 9 fichiers parsent l'AST. Ce sont des gardes
  d'architecture — utiles — mais ils cassent sur tout refactor de formatage, et leur valeur est
  commerciale plus que technique. *(Subjectif :* je les laisserais, mais il faut savoir qu'ils sont
  un coût de maintenance assumé.*)
- **Assertions tautologiques** (4 cas), suivis de leur sort :
  - `test_parry_stun.py:228` : `assert True` littéral. **Traité** — remplacé par un garde de
    source (`parries_taken` absent de `projectile_system`), qui échoue si le mot y apparaît.
  - `test_world_overlay_shapes.py:126` : `assert x0 == x1 or y0 == y1` — **l'audit se trompe**.
    Un segment diagonal produit par `dashed_edges` aurait `x0 != x1` **et** `y0 != y1`, donc
    l'assertion échoue. Le garde est faible mais pas vacuous ; laissé tel quel.
  - `test_camera.py:563` : `assert pixel[:3] == (7,9,11) or pixel[:3] == (255,0,0)`. **Traité** —
    le `or` est retiré, et un garde affirme d'abord que le sprite 16×16 du test ne couvre pas le
    pixel lu (1100, 600). Une couleur fausse fait désormais échouer le test.
  - `test_debug_overlay.py` : assertions de couleur de pixel dans une boîte dimensionnée par la
    police. **Traité** — la lecture porte maintenant sur le padding de la carte et non sur un
    pixel qu'un glyphe peut couvrir (voir §K, relecture du golden).
- `test_rf6_branches.py:20-23` : les deux branches testaient la même valeur via un roundabout
  `Vector2`. **Traité** — une seule assertion `pytest.approx(0.3)`, et le commentaire dit ce qui
  est réellement épingué : l'absence de clamp à zéro, pas un clamp.
- **`test_type_annotations.py:237-262`** n'est **pas** vacuous, contrairement à ce que dit
  l'audit : `ControllerView.__getattr__` lève `AttributeError` pour un nom non délégué
  (sa docstring le dit), donc `hasattr` **peut** échouer. Laissé tel quel.
- `test_type_annotations.py:197-201` : un `or` de deux sous-chaînes, qui passe sur à peu près
  n'importe quoi. **Non traité** — pas de valeur à clarifier ici sans décider ce que
  l'annotation doit être ; à faire avec le propriétaire du test.
- `SpyStateMachine` (`helpers.py:234-240`) **n'a pas `has_tag`**, alors que
  `Entity.is_invincible` (`entity.py:900-906`) l'appelle — toute future installation du spy qui
  touche `is_invincible` lèvera `AttributeError`. Fragile, pas faux aujourd'hui.

Contre-exemples à citer comme **le bon pattern** : `test_source_conventions.py:129-139`
(« le détecteur de parenthèses détecte vraiment ») et `test_readme_claims.py:54-56`
(« le garde de collecte n'est pas vacuous ») sont des tests *de* leurs propres gardes. C'est la
bonne discipline et elle est présente.

---

## I. Tiled / PyTMX Audit

Synthèse (le détail est dans G et D) :

| Domaine | État |
|---|---|
| Chargement | Un seul point d'entrée, cache par id, 12,6 ms à froid / 0,001 ms en cache. **Jamais invalidé** (G7). |
| Où chargé | **Dans un tick de simulation** (`GameplayScene.update → _advance_level → switch → enter → _load_level`), pas à une frontière de transition. Pas de thread, pas de fade, pas d'écran de chargement. Parse ~10 ms + build ~13 ms = **~26 ms de frame bloquée** au premier niveau ; **~13 ms** sur un rejeu en cache (le build `Level` n'est jamais cachée). |
| Périmètre | L'architecture est saine (une seule source de vérité, pas d'accès PyTMX par frame). Le manque est un **écran de chargement**, qui est une feature — donc **hors périmètre** de cet audit. Je le note sans le recommander. |
| Culling | `TileChunkIndex` (chunk de 4 tuiles), 839 sprites → 166 cellules, `get_nearby` → **2 candidats en 22,6 µs**. Conservateur par construction, ordre de build préservé, straddlers enregistrés partout, coordonnées négatives floquées. |
| Collision | **Pas de lookup par tuile.** Chaque tuile est son propre `pygame.sprite.Sprite` (460 en collision), bucketisé une fois. Par entité par tick : **une** requête grille réutilisée pour tous les sub-steps des deux axes — bonne décision. |
| Chemins | `paths.py` : CWD-independent et PyInstaller-aware. Faiblesses : `parents[2]` est une hypothèse de profondeur ; `.resolve()` suit les symlinks ; le chemin du niveau est hardcodé **deux fois** (`level_manager.py:12` et `levels.json`) sans validation ; `data/` et `assets/data/` sont deux répertoires différents tous deux appelés « data ». |
| Validation | `test_levels_manifest.py` **interrompt la collecte** en CI (§A, §D1) et ne compare que `width*height*tilewidth*tileheight` quand il tourne. **Noms de couches, noms d'objets, noms de propriétés, chevauchement de `firstgid`, comptes d'objets : rien ne les valide.** |
| `firstgid` | Doublons dans 3 fichiers de niveau — bénins seulement parce que `enemies.tsx` est vide (G15). |
| Exceptions | pytmx lève un `Exception` **nu** pour une map infinie (`pytmx.py:1424-1426`) et pour un `.tsx` manquant (`:1234-1240`), contournant le contrat d'erreur du jeu (`level_manager.py:84-90` ne protège que le `.tmx`). |
| `ObjectData.gid` | Sa docstring (`level_data.py:23-24`) est **fausse** : pytmx le remappe (`pytmx.py:1547-1548`), donc `gid="229"` se charge comme `92`. |
| Métadonnées tileset | Voir G16. |
| Structure des maps | Chaque niveau a **4 couches de tuiles** (`BG`, `Terrain`, `Platforms`, `FG`) et **7 groupes d'objets** (`BG details`, `Objects`, `Moving Objects`, `Items`, `Enemies`, `Water`, `Data`). Pour `1.tmx` : BG 379, Terrain 455, Platforms 5, FG 0 → 839 sprites. |

### Propriétés réellement consommées

| Objet | Traitement | Site |
|---|---|---|
| `player` | `Player(...)`, premier match gagne | `world_builder.py:319-331` |
| `shell`, `tooth` (et tout nom dans `ENEMY_CONFIGS`) | `create_enemy(...)` | `:343-357` |
| `helicopter`, `boat` | `_build_moving_platform` | `:255-256`, `:131-164` |
| `saw` | `_build_span_hazard` | `:257`, `:167-205` |
| `spike` | `_build_orbiting_hazard` | `:258`, `:208-228` |
| `floor_spike` | `_build_static_hazard` | `:259`, `:231-247` |
| `flag` | `_build_exit` | `:260`, `:250-252` |
| autre **avec gid** | `Sprite` figé dans `all_sprites` | `:360-361` |
| autre sans gid (`water`) | ignoré, `logger.debug` | `:362-363` |

---

## J. Bugs / Edge Cases — scénarios concrets

| # | Sév | Localisation | Scénario de reproduction |
|---|---|---|---|
| J1 | CRIT | `.gitignore:39-40` | `git clone` → `python main.py` → FATAL ERROR, aucune map. |
| J2 | CRIT | `configs.py:5-9` / TMX | Ouvrir `1.tmx` → aucun ennemi, 12 sprites décoratifs. |
| J3 | HIGH | `hazard_damage.py:41-64`, `enemy.py` | Ennemi de 100 PV sur un saw à 20 dégâts → mort en 5 ticks (83 ms), aucun i-frame possible. |
| J4 | HIGH | `contact_damage.py:44,112` | 8 ticks de contact damage à 5 dégâts : `is_hurt` jamais True, la porte ne peut pas se déclencher. |
| J5 | HIGH | `vitals.py:109-110` + `enemy_states.py:455` / `player_states.py:517` | Timer dizzy 1,0 s → sortie après 30 ticks (0,5 s). |
| J6 | HIGH | `combat_system.py:227,247,250` | `a`(prio 5) annule `b`(prio 3) ; `b` chevauche `c`(prio 0) → **`c` est annulé par un attaquant déjà mort**. |
| J7 | HIGH | `renderer.py:124,181` | 60 frames de flash → `id()` recyclé → surface cisaillée de mauvaise taille → blit recadré silencieusement. |
| J8 | HIGH | `renderer.py:564-565` + `level.py:222-225` | Un sprite mobile dans le plan figé → index refusé → log dit « linear cull is kept » → **839 tuiles non dessinées, monde vide**. |
| J9 | HIGH | `movement.py:376-377` | Atterrissage dans la fenêtre de snap : `hitbox.bottom=200.0` mais `hurtbox.bottom=197.4` pendant le tick. |
| J10 | HIGH | `spatial_hash.py:52-54` | Chute à 1500 px/s sur un sol à 90 px : **le gap est manqué à 60 Hz**, rattrapé à 30 Hz. Déplacement horizontal à 40 000 px/s : tunnel. |
| J11 | HIGH | `level_manager.py:54` | Changer la résolution → `_cache` non invalidé → toutes les surfaces de tuiles en conversion alpha logicielle pour le reste de la session. |
| J12 | HIGH | `platforms.py:33-46` | Grille liée : une plateforme est arrêtée net par une tuile one-way qu'elle devrait traverser par le bas. |
| J13 | HIGH | `world_builder.py:296` + `level_registry.py:62` | Renommer `Terrain` → `Ground` dans Tiled → log à `debug` sous racine `INFO` → **zéro collision, aucun message**. |
| J14 | HIGH | `player_states.py:217-232` | Charge + dash → le heavy est inaccessible jusqu'à être touché. |
| J15 | MED | `level_data.py:112-119` | Masquer une couche dans Tiled → elle est **quand même construite, affichée et collisionne**. |
| J16 | MED | `pytmx.py:592-608` + `world_builder.py:360` | `BG details` est dessinée **au-dessus** du terrain qu'elle précède dans Tiled. |
| J17 | MED | `world_builder.py:141,175,213` | Propriété `speed` passée en string dans Tiled → `ValueError` brut → FATAL ERROR. |
| J18 | MED | `world_builder.py:176` | `flip="false"` (string) → truthy → **inversion silencieuse, aucune erreur**. |
| J19 | MED | `level_data.py:151` | `bg=""` → `LevelConfig(bg='None')` sur 4 niveaux. |
| J20 | MED | `player_states.py:472-473` | Dash à 800 px/s : 446 px/s restants après 1 s au lieu de ~0. |
| J21 | MED | `state_machine.py:132-142` | Faute de frappe dans un nom d'état → **ignoré silencieusement**, combattant gelé. |
| J22 | MED | `state_machine.py:127-130` | `GUARD` + `ATTACK` le même tick → `state=GUARD, is_attacking=True` pendant une frame. |
| J23 | MED | `level_data.py:114,117` | Deux couches nommées `Terrain` dans Tiled → **la première disparaît sans log**. |
| J24 | MED | `world_builder.py:237` vs `1.tmx` | 24 spikes sur 25 déclarent `inverted="true"`, aucun ne le lit, un seul a le flag GID → **se dessinent non-inversés**. |
| J25 | LOW | `movement.py:378-389` | Combattant porté par une plateforme ascendante qui percute un mur → téléporté en arrière, deux vitesses à zéro. |
| J26 | LOW | `player_controllers.py:87-95` | Coyote : **133 ms** au lieu des 120 ms configurés. |
| J27 | LOW | `entity.py:645` / `crouch_posture.py:118` | Accroupi : hitbox 33,6 px, image 56 px, même clip → **crouch invisible**. |
| J28 | LOW | `combat_system.py:174,231` | Panneau debug : `overlaps` rapporte 7 pour 5+2. |
| J29 | LOW | `enemy_states.py` / `PROFILES["enemy"]` | `EnemyState.TURN` et `EnemyState.CHARGE` enregistrés et inatteignables. |
| J30 | LOW | `level_manager.py:12` + `game.py:137` | `level_unlock=2` écrit dans la sauvegarde alors que l'id 2 n'existe pas au registre. |

**Non trouvés** (vérifiés explicitement) : aucune entité détruite en itération ; aucune
double-application de coup ; un attaquant mort ne peut pas frapper ; pas de tunneling
exploitable aux vitesses livrées (marge ×4) ; pas de dépendance au FPS dans la physique (hormis
J20, masqué par le timestep fixe).

### Edge cases physiques examinés

| Cas | Résultat |
|---|---|
| Vitesse élevée | Sub-stepping exact jusqu'à 128 px/tick (7 680 px/s) ; tunneling vertical à −20 000 px/s, horizontal à 30 000 px/s. Non atteignable aujourd'hui. |
| Coins de plateforme | 3 assists présents et testés : `_try_step_up` (8 px, `collisions.py:178-196`), `_try_corner_correct` (12 px, `:199-218`), `_snap_to_ground` (3 px, `movement.py:345-375`). |
| Collision multiple / axes simultanés | Séparation X/Y correcte ; l'ordre est X → gravité → Y. `Entity.update` capture `was_grounded` **avant** `move()` (`:1146`) et relit après (`:1149`) — `landed_impact` et l'octroi OTG se basent sur un vrai front. |
| Entités superposées | `SeparationSystem` : poussée par axe dominant, Y quand les deux sont en l'air et `overlap_y < overlap_x * 0.4`. Invincibles (dash) ignorés. 77 % couvert. |
| Plateforme movible | `apply_moving_platform` tourne **avant** l'intégration (`physics_system.py:136-137`) et utilise `old_hitbox` pour le test de montage ; `_sticky_snap` rattrape une plateforme qui descend vite. Testé. |
| Pentes | Non implémentées (pas de détection de pente). Choix de design, pas un manque. |

---

## K. Testing

**État mesuré :** `7 failed, 2478 passed, 5 skipped` (2490 tests) en ~39 s. **Le README annonce
« 2491 tests passing » (badge `:10`, tableau `:64`, baseline `:656`) et
`notes/ecarts_ouverts.md:109-110` annonce « 1273 passed » — aucun n'est vrai.**

> **Relecture — l'état ci-dessus a bougé depuis la première passe.** L'audit annonçait
> `8 failed, 2477 passed`, avec `test_menu_performance` et `test_panel_layout` en échec et une
> seule erreur dans `test_debug_overlay`. Mesuré à `5b2b9cd` : ces deux fichiers **passent**, et
> `test_debug_overlay` en a **deux**. Le total de tests (2490) et le nombre de skips (5) sont
> inchangés ; seule la répartition des échecs diffère, ce qui pointe une dépendance d'ordre ou
> d'environnement, pas un travail de code.

Commande de reproduction :

```bash
uv run pytest -q    # 7 failed, 2478 passed, 5 skipped
```

**Les 7 échecs ont une seule cause racine : `Consolas` n'est pas installé.** La machine de relecture
n'a pas Consolas : `pygame.font.match_font("consolas")` retombe sur
`LiberationMono-Regular.ttf`, alors que le défaut de pygame est `freesansbold.ttf`.
`panel_renderer.py:567-582` construit les cinq polices de debug via `pygame.font.SysFont("Consolas", …)`.

| Échec | Cause |
|---|---|
| `test_world_overlay_golden.py` × 4 | Le golden est *une fonction de la police* — et la docstring du module (`:9-13`) affirme le contraire (« geometry only, never pixels »). **Relecture :** l'audit décrivait un écart de *largeur* (158 vs 100) ; l'écart réel est en **hauteur** — `Ectoplasm` attendu `(400, 251, 158, 31)` contre `(400, 250, 158, 32)` mesuré, `Slime` attendu `(420, 251, 158, 31)` contre `(420, 250, 158, 32)`, et les cartes placées `(680, 504, 80, 53)` contre `(680, 500, 80, 57)`. Les largeurs sont identiques des deux côtés. |
| `test_debug_overlay.py` × 2 | `test_label_card_renders_header_divider_and_accent_edge` et `test_labels_beyond_all_slots_are_dropped` : couleur de pixel à un offset fixe dans une boîte dimensionnée par la police. |
| `test_readme_claims.py` | README 2491 vs 2490 collectés. |

> **Relecture :** l'audit annonçait aussi « 691 warnings `pygame/sysfont.py:494` ». La passe de
> relecture en compte **74**. La cause racine est bien la police ; le décompte, non.

`test_readme_claims.py:59-79` vérifie que badge / tableau / baseline **sont d'accord entre eux**,
explicitement *pas* contre une mesure — d'où le drift « 82 % branch » (mesuré **86,1 %**) qu'il
ne peut pas voir. Son frère `:42-51` **échoue**, lui.

### Zones à risque réel (au-delà des polices)

1. **`CRITICAL` — l'indépendance au frame rate n'est jamais testée.** 280 occurrences de `1 / 60`
   dans 53 fichiers de test ; **zéro** de `1/30`, `1/120` ou d'un balayage paramétré.
   Conséquence directe : J20, le verrouillage d'attaque de `attack_state.py`, et l'hypothèse
   `QUERY_MARGIN_PX` (J10) sont **tous invisibles**. *Un seul* test
   `for dt in (1/120, 1/60, 1/30): assert checksum(dt) == checksum(1/60)` sur la fixture
   `build_level` existante couvrirait les trois.
2. **`CRITICAL` — le chargement de niveau réel n'est pas testé.** `LEVEL_PATHS` → `1.tmx`, absent
   d'un checkout propre (§D1) : **aucun test ne peut charger un vrai `.tmx` en CI.** Vérifié de
   plus : un `.tmx` corrompu lève un `pytmx.ParseError` **brut**, et une map `width=0 height=0`
   est **acceptée** — le joueur tombe indéfiniment (`y=4034.2` après 180 ticks) sans mourir, car
   `death_border_bottom <= 0` désactive la règle.
3. **`HIGH`** — `movement.py:193-206` (wall-jump lock) : couverture **suite complète zéro**.
   `DASH_WALL_BOUNCE` / `DASH_AIR_CONTROL` : **absents de tout fichier de test**.
4. **`HIGH`** — fenêtres coyote / jump buffer : seule l'arithmétique de refill/decay est testée,
   jamais la **fenêtre** (mesurée : 8 ticks = 133 ms contre 120 ms configurés).
5. **`MEDIUM`** — `test_hazard_damage.py` n'appelle `process()` qu'**une fois** par test : J3 est
   hors couverture. `separation_system.py:103-118` (empilement vertical, `pushable` unilatéral)
   non testé. `EnemyChaseState` : les lignes non couvertes (`:249,318,321,352`) sont exactement
   les refus de saut risqué.
6. **`MEDIUM`** — ordre des tests : ~25 modules unitaires appellent `pygame.display.set_mode()`
   au scope module et **ne restaurent jamais l'état global** (tailles 64×64 à 1920×1080).
   `helpers.py:375` `make_card_layer()` lit `pygame.display.get_surface()`. **Vérifié : aucune
   dépendance d'ordre vivante aujourd'hui** (suite relue en ordre inverse → résultat identique),
   mais le couplage est **structurel**.
7. **Positif** — `test_simulation_and_config.py:222-245` teste `resolve_jump` sur un
   `SimpleNamespace` mais jamais la *conséquence* du lock. `enemy.py:254-279` :
   `jump_apex`/`jump_range` sont assertés contre des valeurs **en forme close ignorant le drag**
   (formule 140,8 px, réel simulé 136,4 px) — le test épingle la formule, pas le comportement.
8. **Positif** — seuls 15 fichiers importent `unittest.mock`, 32 utilisent `monkeypatch`, 55 des
   `SimpleNamespace` — **chaque module qui touche le rendu tourne contre une vraie
   `pygame.Surface`**. Aucun test n'assert sur un mock : chaque `Mock()` est un espion sur une
   vraie étape. `test_gameplay_loop.py:156-199` asserte l'ordre exact des 13 étapes — la bonne
   façon d'épingler un pipeline. Aucun test de performance à base de timing (une seule exception,
   `test_menu_performance.py:276-290`, marge ×50) : les gardes comptent des **opérations**, et le
   disent.

### Modules sans fichier de test dédié

`physics/velocity.py` (11 lignes, **aucun import depuis un test**), `entities/player_animation.py`,
`entities/enemies/types/{dummy,goblin,slime}.py`, `core/fx/{spawners,particles}.py`,
`core/level/level_registry.py`, `core/level/systems/{tick_system,notification_system}.py`,
`core/rollback/{rollback,snapshots}.py` — tous importés transitivement, jamais nommés.

La couverture est large ; les trous sont dans les **branches**, pas dans les fichiers.

---

## L. Prioritized Action Plan

*Ordonnancement par ratio bénéfice/effort. Aucun item n'ajoute de feature ni ne change le
comportement voulu du jeu.*

> **Statut après traitement** — branche `fix/remediation`, 30 commits au-dessus de `5b2b9cd`.
> Chaque item ci-dessous porte une marque : **fait**, **refusé** (décision de l'auteur du
> projet), ou **reste** (non traité). Les marques sont posées sur la colonne « # », pour que
> le tableau se lise comme un état des lieux et non comme une liste de courses.
>
> **fait** : 0.0, 0.2, 0.3, 0.4, 0.5, 1.1 à 1.6, 2.1 à 2.9, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7,
> 4.1, 4.2, 4.3, 4.4, 4.7 — plus les LOW de la section G qui valaient une ligne de code
> (G10, G12, G13, G17). 0.4 et 0.5 ont livré `shell` et `tooth`, qui passent le nombre
> d'ennemis du niveau livré de 0 à 12, et la propriété `reverse` que 17 shells sur 17
> portent est enfin lue.
>
> **refusé** : **0.1** — la décision d'exclure `assets/data` et `assets/graphics` du contrôle
> de version est celle de l'auteur du projet, pas un oubli de cet audit. Le reste du plan a
> été traité en la respectant, et 0.2 couvre ce que 0.1 aurait apporté : le manifeste échoue
> dès que les cartes sont là.
>
> **reste** : **3.5**, **4.5**, **4.6**, **4.8**, et **G6** (les sept salles enregistrées).
> G6 est **volontairement** laissé de côté : le système de niveaux part sur une matrice
> Metroidvania, et les brancher en chaîne linéaire construirait le système qu'on remplace.
> Voir `notes/design_matrice_niveaux.md`. Les trois autres sont des manques réels, pas des
> choix : aucun `firstgid` dupliqué détecté, les 3 blocs `getattr` de `hit_resolver.py`
> toujours là, `DASH_AIR_CONTROL`/`DASH_WALL_BOUNCE` toujours non couverts, et une carte
> `0×0` toujours acceptée.

### Lot 0 — Débloquer la reproductibilité (à faire en premier, tout le reste en dépend)

| # | Action | Fichiers | Problème | Difficulté | Risque | Bénéfice |
|---|---|---|---|---|---|---|
| **0.0 ✅** | **Réparer la collecte du manifeste TMX** — sortir `_tmx_files()` du `parametrize` de module (guard `pytest.importorskip`-like, ou fixture paramétrée) pour qu'un checkout sans `assets/` **skip au lieu d'avorter la session** | `tests/unit/test_levels_manifest.py:39-61` | J1, D1/D3 | **SMALL** | LOW | La suite redevient exécutable en CI ; aujourd'hui elle sort en code 2 |
| **0.1 ❌ refusé** | Retirer `assets/data` et `assets/graphics` du `.gitignore` | `.gitignore:39-40` | J1 | **SMALL** | LOW | Le projet devient clonable, buildable, et le bundle CI a enfin du contenu |
| **0.2 ✅** | Faire échouer le manifeste TMX quand `assets/` est présent mais vide | `tests/unit/test_levels_manifest.py:32-41` | J1, J2 | SMALL | LOW | La CI peut enfin voir le contenu |
| **0.3 ✅** | Faire échouer au chargement un nom de couche/objet inconnu, ou au minimum `logger.warning` | `level_registry.py:62`, `world_builder.py:363` | J13 | SMALL | LOW | Fin des niveaux silencieusement cassés |
| **0.4 ✅** | Résoudre `shell`/`tooth` vs `ENEMY_CONFIGS` | `configs.py`, `enemies.json`, TMX | J2 | MEDIUM | MEDIUM | Le jeu a enfin des ennemis |
| **0.5 ✅** | Test d'intégration : un vrai `.tmx` se charge et contient ≥1 ennemi | `tests/unit/` | J2 | SMALL | LOW | Empêche la régression de contenu |

> **0.1 et 0.2 sont la condition préalable à toute garantie future.** Tant que `assets/` est
> ignoré, J2 et les tests d'intégration sont structurellement impossibles.
>
> **Relecture — 0.0 a été ajouté.** L'action 0.2 d'origine était écrite comme « faire échouer le
> manifeste au lieu de skipper », en supposant que le test *skip* et que seule la validation
> manquait. Le test ne skip pas : il casse la collecte et interrompt toute la session (§A, §D1
> aggravant 1). Le correctif est donc inverse — il faut d'abord que l'absence d'assets **saute**,
> et seulement ensuite que le contenu soit validé. `0.0` est donc à faire avant `0.1`.

### Lot 1 — Bugs de gameplay avérés (comportement actuel manifestement non intentionnel)

| # | Action | Fichiers | Problème | Difficulté | Risque | Bénéfice |
|---|---|---|---|---|---|---|
| **1.1 ✅** | Ne décruer `stagger_timer` qu'à un seul endroit (retirer des états dizzy) | `enemy_states.py:455-456`, `player_states.py:517-518` | J5 | SMALL | MEDIUM | Les fenêtres de stun durent enfin leur durée configurée |
| **1.2 ✅** | Exclure les attaquants déjà annulés des comparaisons hit-vs-hit | `combat_system.py:227` | J6 | SMALL | MEDIUM | Un attaquant mort n'annule plus un tiers |
| **1.3 ✅** | Cooldown par cible pour les dégâts de hazard | `hazard_damage.py` | J3 | MEDIUM | MEDIUM | Un ennemi ne meurt plus en 83 ms sur un saw |
| **1.4 ✅** | Faire réellement porter le `is_hurt` au gate de contact damage | `contact_damage.py:44,112` | J4 | SMALL | MEDIUM | Symétrie avec le correctif 1.3 |
| **1.5 ✅** | `sync_rects()` après `_snap_to_ground` | `movement.py:376-377` | J9 | **SMALL** | LOW | Collisionneur et hurtbox d'accord à la frame d'atterrissage |
| **1.6 ✅** | Ne conserver le surplus que si c'est voulu, ou le documenter | `attack_state.py:274-279` | F13 | SMALL | LOW | Levée d'ambiguïté sur le timing des attaques |

### Lot 2 — Corrections de robustesse à faible risque, fort bénéfice

| # | Action | Fichiers | Problème | Difficulté | Risque | Bénéfice |
|---|---|---|---|---|---|---|
| **2.1 ✅** | Retenir la source dans `_SHEAR_CACHE` | `renderer.py:181` | J7 | **SMALL** | LOW | Supprime une classe entière de bugs de rendu |
| **2.2 ✅** | Restaurer le scan linéaire dans `_static_plane` | `renderer.py:564-565` | J8 | **SMALL** | LOW | Supprime un monde vide possible + rend le log vrai |
| **2.3 ✅** | Éviction bornée sur `_scaled_cache` / `_flash_cache` (demi-éviction déjà présente à `:198-221`) | `renderer.py:291,294` | E2 | SMALL | LOW | Finit ~1,9 Mo/min en fuite |
| **2.4 ✅** | Invalider `LevelManager._cache` dans `_invalidate_assets` | `game.py:342-351` | J11 | **SMALL** | LOW | Plus de conversion alpha après un changement de résolution |
| **2.5 ✅** | Passer `convert=True` à la présentation | `game.py:252` | E4 | **SMALL** | LOW | Le chemin existe déjà, il est gardé |
| **2.6 ✅** | Réserver `losers` **et** filtrer `one_way` dans le chemin grille | `platforms.py:36-41` | J12 | SMALL | LOW | Les deux chemins d'accord |
| **2.7 ✅** | Fixer la friction de dash | `player_states.py:472-473` | J20 | SMALL | **MEDIUM** | Le dash décélère enfin (changement de feel — tests requis) |
| **2.8 ✅** | Test d'invariant `QUERY_MARGIN_PX >= MAX_FALL_SPEED * TIMESTEP` | `tests/unit/` | J10 | **SMALL** | LOW | Rend une hypothèse à 60 Hz explicite et vérifiée |
| **2.9 ✅** | `exit()` sur `PlayerChargeState` / annuler `charging` sur changement d'état | `player_states.py:217-232` | J14 | SMALL | MEDIUM | Débloque le heavy après un dash |

### Lot 3 — Fiabiliser Tiled (après 0.1/0.3, sinon sans effet)

| # | Action | Fichiers | Problème | Difficulté | Risque | Bénéfice |
|---|---|---|---|---|---|---|
| **3.1 ✅** | Honorer `visible` ; au minimum `logger.warning` | `level_data.py:112-119` | J15 | SMALL | LOW | Le level designer voit ce qu'il masque |
| **3.2 ✅** | Conserver l'ordre z de Tiled au lieu du plan figé/moving | `world_builder.py`, `renderer.py` | J16 | MEDIUM | MEDIUM | `BG details` derrière le terrain |
| **3.3 ✅** | Garde-fous sur les conversions de propriétés (`float`/`int`) | `world_builder.py:141,175,213` | J17, J18 | SMALL | LOW | Plus de FATAL ERROR sur une propriété mal typée |
| **3.4 ✅** | `bg` : distinguer `None` de `""` | `level_data.py:151` | J19 | **SMALL** | LOW | Restaure le sentinelle |
| **3.5 ⏳ reste** | Détecter les `firstgid` dupliqués + valider noms/objets/propriétés | `tests/unit/` | G15, §I | MEDIUM | LOW | Attrape la corruption de map avant le lancement |
| **3.6 ✅** | Envelopper les `Exception` nus de pytmx | `level_manager.py:84-90` | §I | SMALL | LOW | Contrat d'erreur cohérent |
| **3.7 ✅** | Corriger la docstring de `ObjectData.gid` | `level_data.py:23-24` | §I | **SMALL** | LOW | Le champ dit le contraire de ce qu'il contient |

### Lot 4 — Qualité de test

| # | Action | Fichiers | Problème | Difficulté | Risque | Bénéfice |
|---|---|---|---|---|---|---|
| **4.1 ✅** | Rendre les goldens indépendants de la police, **ou** livrer la police | `test_world_overlay_golden.py`, `panel_renderer.py:567` | K | MEDIUM | LOW | 4 des 7 échecs |
| **4.2 ✅** | Idem pour `test_debug_overlay` | `test_debug_overlay.py` | K | MEDIUM | LOW | 2 des 7 échecs |
| **4.3 ✅** | Balayage dt (1/120, 1/60, 1/30) sur la fixture existante | `tests/headless/` | K1 | **SMALL** | LOW | Couvre J10, J20, le verrouillage d'attaque — **le meilleur rapport valeur/effort de l'audit** |
| **4.4 ✅** | Retirer `assert True` et les `or` tautologiques | 4 fichiers (§H) | K | **SMALL** | LOW | 4 tests qui passent avec le code cassé |
| **4.5 ⏳ reste** | Rendre `test_combat_contracts.py:59-69` honnête (nom ↔ assertion), ou corriger les 3 blocs `getattr` | `test_combat_contracts.py`, `hit_resolver.py` | F12 | MEDIUM | LOW | Clôt l'item R-3 de l'audit précédente |
| **4.6 ⏳ reste** | Couvrir `movement.py:193-206`, `DASH_AIR_CONTROL`, `DASH_WALL_BOUNCE` | `tests/unit/` | F17 | SMALL | LOW | La mécanique signature a enfin un filet |
| **4.7 ✅** | Tests de cas multi-ticks pour hazards et contact damage | `test_hazard_damage.py` | J3, J4 | SMALL | LOW | Empêche la régression de J3/J4 |
| **4.8 ⏳ reste** | `.tmx` corrompu / `0×0` → erreur claire | `tests/unit/` | K2 | SMALL | LOW | Empêche le joueur de tomber indéfiniment |

---

## M. Quick Wins

Cinq actions, **effort total < 1 heure**, bénéfice immédiat :

1. **`.gitignore:39-40`** — retirer deux lignes. *Débloque tout le reste.*
2. **`renderer.py:181`** — retenir la source dans `_SHEAR_CACHE`. *Copier ce que
   `_scaled_cache:364` fait déjà, dans le même fichier.*
3. **`renderer.py:564-565`** — restaurer le scan linéaire. *La docstring promet déjà ce
   comportement ; c'est du code qui manque, pas une nouveauté.*
4. **`movement.py:377`** — ajouter `sync_rects()`. *Une ligne, corrige un désaccord de 2,6 px
   entre collisionneur et hurtbox.*
5. **`combat_system.py:227`** — ajouter `or id(...) in losers`. *Une condition ; `losers` est
   déjà calculé et ignoré.*

Bonus, également une ligne : **`level_registry.py:62`** — `logger.debug` → `logger.warning`.

---

## N. Long-Term Risks

1. **Le contenu est le seul poste à ne pas être versionné.** Tout le reste est très bien tenu ;
   `assets/` est le point faible unique et il est structurel, pas accidentel.

2. **La suite de tests surpasse la source (1,12×) mais ne teste pas ce qui compte le plus.**
   ~2 490 tests, 93,7 % de couverture d'instructions — et pourtant **aucun test ne charge un vrai
   `.tmx`, aucun ne tourne à un dt autre que 1/60, et 4 tests passent avec le code cassé.** Le
   ratio LOC est devenu un indicateur de confort, pas de couverture du risque. Le risque réel
   (contenu, physique, timing) est précisément celui que la suite ne touche pas.

3. **`settings.py` va continuer de croître.** 40 classes, 2 108 lignes, avec `Dust` (579 l.) et
   `FootstepDust` (545 l.) en tête. C'est sain tant que ce sont des constantes, mais la granularité
   est devenue irrégulière. Le jour où quelqu'un ajoute de la *logique* ici, la vérification de
   types et la lisibilité se dégradent d'un coup. **Recommandation :** garder des constantes,
   refuser la logique ; ne pas scinder pour l'esthétique.

4. **Le dispatch par nom de chaîne est une dette qui ne s'amortit pas.** Sept noms de couches, six
   noms d'objets, hardcodés en Python, indexés par nom, échouant en `debug`. Chaque niveau ajouté
   augmente la surface. Le passage à un `class=` ou un registre déclaré à l'import ne coûte
   presque rien **maintenant** ; dans un an, il coûtera un inventaire.

5. **Les caches non bornés vont croître avec le temps de session.** E2 montre ~29 Ko par ennemi.
   Un menu ou un mode qui apparaît/disparaît beaucoup (le banc de debug le fait déjà) finira par
   consommer mémoire. Un LRU borné est une demi-journée.

6. **`GameplayLoop` a 12 systèmes optionnels.** Le jour où quelqu'un ajoute un 13ᵉ système, il faut
   penser à `update()`, à `_require`, à `combat_only()`, à `Level`, et aux tests d'ordre. C'est un
   coût marginal croissant — pas un problème aujourd'hui.

7. **Le clamp de hitbox à 8 sub-steps / 128 px par tick est un plafond muet.** Inatteignable
   aujourd'hui (marge ×4). Il le deviendra si un `charge` multi-niveau, une attaque à longue
   portée, ou un projectile rapide est un jour ajoutés. **Documenter le plafond ou le rendre
   visible maintenant coûte bien moins cher que le diagnostiquer plus tard.**

---

## Synthèse

| Domaine | Verdict |
|---|---|
| **Game loop, pacing, update/render** | **Excellent.** Ne pas y toucher. |
| **Caméra, culling, rendu** | **Excellent.** Trois bugs de cache à corriger (§E), pas de problème de performance. |
| **Pipeline de combat, déterminisme** | **Bien conçu.** Cinq bugs de gameplay (§F7-F11). |
| **Physique** | **Correcte et dt-indépendante.** Deux vrais bugs (§F2, F3) + une hypothèse 60 Hz non testée. |
| **Architecture** | **Bonne.** Une god class évitée, une façade assumée, des systèmes injectés testables. Le problème est le *dispatch par nom*, pas la structure. |
| **Qualité Python / outillage** | **Au-dessus de la moyenne.** mypy strict, ruff + C901, 4 benchmarks, discipline de tests mesurée. |
| **Contenu (Tiled + assets)** | **Le point faible du projet.** Non versionné, contenu inerte, propriétés mortes, z-order et visibilité ignorés. |
| **Tests** | **Volume excellent, ciblage insuffisant.** Couvrent tout sauf ce qui casse. |

**Le projet n'a pas un problème d'architecture ni de performance.** Il a un problème de
**traçabilité du contenu** et **cinq bugs de gameplay de quelques lignes chacun**.

---

## Note de relecture

Une passe de vérification a été faite sur ce document au même commit (`5b2b9cd`). Six points
n'ont pas tenu et sont corrigés ci-dessus, chacun annoté « Relecture » :

| Point | Ce que l'audit affirmait | Ce qui est vrai |
|---|---|---|
| §A, D1, D3 | le manifeste TMX *skip* quand `assets/` est absent, **la CI est verte** | il **erreur à l'import** et pytest interrompt la session entière (exit 2) |
| §A, §K | `8 failed, 2477 passed`, dont `test_menu_performance` et `test_panel_layout` | `7 failed, 2478 passed` ; ces deux fichiers passent, `test_debug_overlay` en a deux |
| §K | 691 warnings `sysfont.py` ; golden en écart de *largeur* (158 vs 100) | 74 warnings ; l'écart est en *hauteur* (31/53 attendus, 32/57 mesurés), largeurs identiques |
| §H | `test_debug_overlay.py:146`, un `or density == 1.0` | aucun `density` dans ce fichier ; les deux échecs réels sont des assertions de pixel en boîte police-dimensionnée |
| F1 | `settings.py` commente « rendering at 120 FPS » | la docstring a été réécrite, le drift R-1 est **corrigé** ; F1 est sans objet |
| F9 | `losers` « n'est jamais consulté » | il est consommé ligne 194 ; c'est la boucle de clash qui ne le teste pas |

**Ce qui a été re-vérifié et tient** : les métadonnées du périmètre (172 modules, 36 937 LOC,
143 fichiers de test, 2 490 tests), D1, D2 (census `shell`/`tooth` inclus), E1-E5, F3, F5, F7, F8,
F12-F19, G1-G3 (census de propriétés exact), G5, G7, G15, K1, et les cinq assertions tautologiques
de §H. Les trois constats les plus lourds — contenu hors VCS, aucun ennemi, niveau de test non
reproductible — sont confirmés sans réserve.

**Non rejoué** : les mesures de §E (timings, overdraw, budget de cache) et le taux de couverture de
branches. Elles restent marquées « mesuré » et n'ont pas été re-vérifiées.

---

## Annexe — Fichiers inspectés

### Lu intégralement (noyau)

`main.py` · `pyproject.toml` · `.gitignore` · `knightrock.spec` · `.github/workflows/build.yml`

`src/core/game.py` · `src/core/settings.py` · `src/core/paths.py` · `src/core/asset_library.py` ·
`src/core/sprite_groups.py` · `src/core/sprites.py` · `src/core/hazards.py` ·
`src/core/animation/animator.py` · `src/core/audio.py`

`src/core/level/level.py` · `level_data.py` · `level_manager.py` · `level_registry.py` ·
`world_builder.py` · `scene_host.py`

`src/core/level/systems/` — `gameplay_loop.py` · `tick_system.py` · `physics_system.py` ·
`platform_system.py` · `hazard_system.py` · `hazard_damage.py` · `contact_system.py` ·
`contact_damage.py` · `combat_system.py` · `projectile_system.py` · `separation_system.py` ·
`spawn_system.py` · `respawn_system.py` · `progression_system.py` · `camera_system.py` ·
`notification_system.py`

`src/core/rendering/` — `renderer.py` · `camera.py` · `overlay.py` · `tile_chunk_index.py`

`src/core/display/` — `presentation.py` · `viewport.py` · `letterbox.py` · `framing.py` ·
`stage.py` · `mode.py` · `detection.py`

`src/core/rollback/` — `rollback.py` · `snapshots.py`

`src/core/input/` — `input_manager.py` · `input_provider.py` · `input_actions.py` ·
`input_bindings.py` · `input_state.py` · `event_router.py` · `bindings_repository.py`

`src/physics/` — `movement.py` · `collisions.py` · `gravity.py` · `velocity.py` · `platforms.py` ·
`spatial_hash.py` · `entity_grid.py`

`src/entities/` — `entity.py` · `player.py` · `player_controllers.py` · `player_input.py` ·
`player_animation.py` · `player_config.py` · `vitals.py` · `crouch_posture.py` ·
`hurtbox_zones.py` · `controller_view.py` · `attack_moves.py` · `projectile.py` ·
`components/movement.py` · `components/reaction.py` ·
`enemies/enemy.py` · `enemies/factory.py` · `enemies/configs.py` · `enemies/schema.py` ·
`enemies/types/{dummy,goblin,slime}.py`

`src/combat/` — `attack_data.py` · `attack_loading.py` · `attack_state.py` · `charge_handler.py` ·
`combatant_protocol.py` · `combat_component.py` · `combo_tracker.py` · `damage_types.py` ·
`determinism.py` · `frame_data.py` · `hitbox_manager.py` · `hit_resolver.py` · `knockback.py` ·
`refusal.py` · `shapes.py` · `sweep.py`

`src/states/` — `state_machine.py` · `null_state_machine.py` · `player_states.py` ·
`enemy_states.py` · `reaction_states.py` · `turn_state.py` · `ledge_state.py`

`src/application/` — `scene.py` · `scene_manager.py` · `events.py` · `input_dispatcher.py` ·
`save_game.py` · `settings_store.py` · `attack_authoring.py` · `scenes/*`

`src/ui/` — `hud.py` · `ui_manager.py` · `world_ui.py` · `player_ui.py` · `panel_renderer.py` ·
`metrics.py` · `scale.py` · `styles.py` · `world_overlay_*.py` (9 fichiers)

`src/data/` — `provider.py` · `roots.py` · `levels.py` · `attacks.py` · `enemies.py` · `player.py` ·
`errors.py`

### Données inspectées

`data/gameplay/{attacks,enemies,player,levels}.json` · `data/levels_manifest.json` ·
`assets/data/levels/{0..6,omni,overworld}.tmx` · `assets/data/tilesets/*.tsx` (11) ·
`assets/data/overworld/overworld.tmx`

### Tests inspectés

`tests/conftest.py` · `tests/headless/conftest.py` · `tests/unit/helpers.py` ·
`tests/unit/test_readme_claims.py` · `test_frame_pacing.py` · `test_frame_coherence.py` ·
`test_combat_contracts.py` · `test_hazard_damage.py` · `test_collision_robustness.py` ·
`test_player_controllers.py` · `test_priority_clash.py` · `test_world_overlay_golden.py` ·
`test_menu_performance.py` · `test_panel_layout.py` · `test_debug_overlay.py` ·
`test_levels_manifest.py` · `test_runtime_and_paths.py` · `test_asset_library.py` ·
`test_simulation_golden.py` · `test_camera.py` · `test_parry_stun.py` ·
`test_rf6_branches.py` · `test_type_annotations.py` · `test_world_overlay_shapes.py` ·
`test_source_conventions.py` · `test_gameplay_loop.py` · `test_simulation_and_config.py` ·
`test_save_game.py` · `test_settings_store.py` · `test_video_settings_persistence.py`
+ les 13 tests headless et 4 benchmarks (`contact`, `render`, `ui`, `fx`)

### Documentation existante lue

`README.md` (37 669 o.) · `notes/audit_consolide.md` · `notes/ecarts_ouverts.md` ·
`notes/audit_ui.md` · `notes/perf_debug_overlay.md` · `notes/perf_shatter_arc.md`

---

*Fin de l'audit. Aucun fichier du dépôt n'a été modifié.*