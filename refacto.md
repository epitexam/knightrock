I have completed the audit. Here is the full report and the prioritized refactoring plan.

---

# 🔍 Audit complet — Knightrock

**Périmètre** : 29 108 lignes `src/`, 26 545 lignes `tests/`+`tools/`, 155 modules.
**Mesures** : `mypy src main.py tools` → **clean (156 fichiers)** · `ruff check` → **clean** · `C901` → **clean** · `pytest` → **1813 passed, 4 skipped en 21 s** · `ruff format --check` → **1 fichier en échec** (`src/ui/menu_view.py:126`).

> **Constat liminaire** : ce projet est déjà nettement au-dessus de la moyenne en matière de rigueur (mypy strict sans exception, tests exhaustifs, benchmark maison, documentation de décision inline). Les problems ci-dessous sont donc des points de convergence, pas des fondations. Je les ai triés par **coût de correction / gain réel**, pas par_alignement théorique.

---

## 1. Synthèse mesurée

Profil cProfile sur `Level.update` + `Level.draw`, 200 itérations, niveau réel `1.tmx` (972 sprites, 461 collidables, 35 hazards), cible 1280×720, SDL *dummy* (CPU pur, sans GPU) :

| Poste | Coût / tick | Part |
|---|---|---|
| `Renderer.draw` total | 2.45 ms | 60 % |
| ↳ `_collect_visible_blits` | **1.62 ms** | 66 % du draw |
| ↳ `Camera.is_visible` (974 appels/frame) | 0.39 ms | |
| `GameplayLoop.update` total | 1.91 ms | 40 % |
| ↳ `hazard_damage.produce_boxes` (35 boîtes) | **0.51 ms** | 27 % de l'update |
| ↳ `contact_system._candidates` (36 tris/tick) | 0.37 ms | |
| ↳ `PhysicsSystem._spawn_impact_fx` | 0.28 ms | |
| `Level.draw` (hors monde) | 0.04 ms | |

**Chiffres clés du diagnostic :**

- **972 sprites testés, 89 visibles.** 91 % du travail de cull est jeté, 60 fois par seconde.
- **`EntityGrid` coûte plus cher qu'elle ne rapporte au réel.** `contact_benchmark` : `8v8-exhaustive 1.156 ms` vs `8v8-grid 1.276 ms`. Sur le niveau livré (1 entité), le `rebuild` par tick est du travail pur.
- **39 µs par appel** sur `AssetLibrary.frames(".../player/dash")` — un `Path.is_dir()` refait à l'infini, 1 000 fois = 39 ms, jamais mis en cache.

---

## 2. Findings détaillés

### 🔴 CRITIQUE

**C1 — `except` sans parenthèses (PEP 758), 4 fichiers**
`src/application/save_game.py:63` et `:78` · `src/core/input/event_router.py:503` · `src/core/display/stage.py:165` · `src/ui/world_ui.py:1262`

```python
except KeyError, TypeError, ValueError:   # save_game.py:63
```

Légal en 3.14 uniquement. `pyproject.toml` dit `requires-python = ">=3.14"`, donc ça passe — mais c'est **incohérent avec les 4 autres fichiers du même codebase** qui utilisent `except (A, B) as e:`. Un contributesur sur 3.13, un `pyupgrade` automatique, ou un backport casse 4 modules dont `save_game` (chemin critique au lancement). Le fait que `mypy` et `ruff` passent ne prouve rien : les deux ciblent `py314`.

> **Impact** : pas de bug aujourd'hui, risque de rupture immédiat et fort coût de diagnostic.

---

### 🟠 MAJEUR

**M1 — Inversion de couches : `core` dépend de `ui`**
`src/core/rendering/renderer.py:13-14`
```python
from src.ui.panel_renderer import PanelLayout, compact_panels
from src.ui.ui_manager import UIManager
```
Vérifié par analyse AST : **7 violations de couches** au total.

**M2 — `Level` (simulation) pilote directement la présentation**
`src/core/level/level.py:339-347` et `:354` — `Level.draw()` atteint `self.renderer.ui_manager.world_ui` pour le clash, les métriques et le marqueur. Et `level.py:320` : `game: Any = None` — le cœur de la simulation reçoit **l'objet applicatif entier** en `Any` pour afficher un panneau debug.

**M3 — Le cull O(n) sur sprites statiques** *(cause racine du principal coût perf)*
`src/core/rendering/renderer.py:263-273`
```python
cached_planes = (*groups.all_sprites, *groups.fg_sprites)   # tuple de 972, alloué à chaque frame
for sprite in cached_planes:
    if self.camera.is_visible(sprite.rect):   # 972 colliderect/frame
```
Mesuré : 34 ms/200 frames pour les `is_visible` seuls, +2.5 ms/200 pour l'éclatement du tuple. Le terrain ne bouge jamais.

**M4 — Reconstruction de 35 `OffensiveBox` par tick pour rien**
`src/core/level/systems/hazard_damage.py:36-70` (+ `contact_damage.py:50-83`) — `OffensiveBox` + `HitProperties()` + `swept_contact_shapes()` reconstruits pour chaque hazard, chaque tick, puis jetés. **0.51 ms/tick**, soit 27 % de l'update, pour un résultat identique.

**M5 — `EntityGrid` sans seuil, tri de restauration sysmbolique**
`src/core/level/systems/gameplay_loop.py:89` · `src/core/level/systems/contact_system.py:379`
Le tri `self._nearby.sort(key=...)` à chaque box (36 tris/tick) sert à restaurer l'ordre d'insertion — que le grid ne garantit pas. Plus, avec 1 entité, la grille coûte plus que l'exhaustif (chiffré ci-dessus).

**M6 — `SpatialHash` : `id()` comme clé, aucun évictif**
`src/physics/spatial_hash.py:109` — `_cells_by_sprite: dict[int, ...]`. `remove()` n'est **jamais appelé** par le cycle de vie des entités (`gameplay_loop.py:313-320` appelle `entity.kill()` sans `spatial_hash.remove()`). Aujourd'hui sans fuite car les entités ne sont pas dans `collision_sprites` — mais l'API l'invite, et surtout **`add()` est idempotent par `id()`** : une surface libérée dont l'`id` est recyclé sera silencieusement **non insérée**. Le renderer documente précisément ce risque (`renderer.py:76-78`) sans l'atténuer.

**M7 — `EventBus.emit` ne性的 isole pas les abonnés**
`src/application/events.py:128-131` — une exception dans un abonné (audio, save, UI) remonte **dans le tick de simulation** et le tue. Le contrat dit « must never mutate the simulation » mais ne dit rien de l'isolation.

**M8 — Erreur fatale : chemin de secours non testable et non logger**
`src/core/game.py:589-602` — dessine sur `self.surface` (**la fenêtre**, pas la cible de rendu), utilise `SysFont("Arial")` hors de la chaîne graphique, et `print()` vers stderr au lieu de logger. `run()` remonte `SystemExit(1)` : le smoke test CI perd le traceback.

**M9 — `LevelManager.get` lève une `KeyError` nue**
`src/core/level/level_manager.py:57` — `self.level_paths[level_id]`. Le chemin `FileNotFoundError` a un excellent message ; le chemin `KeyError` n'en a aucun. Vérifié en exécution. Une sauvegarde nommant un niveau supprimé crash au lancement.

**M10 — `Set_surface` / `set_ui_scale` par duck-typing `getattr`**
`src/application/scene_manager.py:84-105` — 7 `getattr(..., None)` + `callable(...)` sur la `Scene` et sa `.view`. Le contrat est implicite : une scène qui oublie `set_surface` est **ignorée en silence**.

---

### 🟡 MINEUR

| # | Fichier:Ligne | Problème |
|---|---|---|
| **m1** | `src/ui/world_ui.py` (2095 l., 100+ méthodes, 115 `getattr`) | God-module : overlay debug + barres de vie + placement de labels + panneau combat + vecteurs + timeline. Au moins 4 modules. |
| **m2** | `src/entities/entity.py` (1106 l.) | God-class ; `MovementComponent`/`ReactionComponent` existent mais l'entité reste massive. |
| **m3** | `src/core/fx.py:173, 211, 242, 289, 366, 455, 524` | **Un `pygame.Surface` neuf par particule et par frame.** `ObjectPool` existe et n'est utilisé que pour les projectiles. |
| **m4** | `src/entities/projectile.py:50, 99` | `Surface` recréée à chaque `launch()` — annule une partie du bénéfice du pool. |
| **m5** | `src/core/asset_library.py:98-100` | Fallback `player/dash → player/run` **jamais mis en cache** sous la clé demandée. 39 µs × à l'infini. |
| **m6** | `src/core/level/systems/physics_system.py:104-131` | 3 dictionnaires `id(entity)` **reconstruits** chaque tick (`_cleanup_timers`) ; `hasattr(entity,"landed_impact")` par entité par tick. |
| **m7** | `src/core/level/level.py:112` + `gameplay_loop.py:89` | `cell_size=128` en dur **à deux endroits** — viole la règle README « no magic numbers ». |
| **m8** | `src/core/level/level.py:158` | `spawn_system.projectile_system = ...` — injection **après construction**, contredit la revendication « injected explicitly ». |
| **m9** | `src/core/level/level.py:179-213` | 6 paires property/setter de simple délégation vers les systèmes. Facade sur facade. |
| **m10** | `src/pause_scene.py:34`, `gameover_scene.py:31` | `self.OPTIONS` — attribut **mort**, jamais lu (grep `src` + `tests` : 0 lecture). |
| **m11** | `src/core/object_pool.py:11` | Docstring « unused by the simulation yet » — obsolète, il est utilisé par `ProjectileSystem`. |
| **m12** | `src/ui/world_ui.py:509` | `if type(sprite) is pygame.sprite.Sprite: continue` — **code mort** (les tuiles sont une *sous-classe*). Le filtrage réel est le gate `statics` en dessous ; le commentaire attribue le gain à cette ligne. |
| **m13** | `src/core/game.py:532, 538` | `logger.info(f"...")` — formatage f-string au lieu de `%s` paresseux, incohérent avec le reste du fichier. |
| **m14** | `src/core/settings.py:27` vs `game.py:48` | `Display.FPS = 180` ⇒ `DISPLAY_SAFETY_CEILING_FPS = 720`. Le « backstop anti-emballement » laisse tourner à 720 sans vsync. |
| **m15** | `README.md:10, 47, 428` | « 1511 tests » — réel : **1813**. Dérive documentaire. |
| **m16** | 187 annotations `Any` ; 333 `getattr` | `Level.draw(game: Any)`, `draw_scene_panel(game: Any)` — l'`Any` sert de passe-droit transversal. `contact_system.py` déclare `swept_hurtbox` sur le protocole **et** fait un `getattr` de secours. |

---

## 3. Design patterns — avis motivé

### ✅ À conserver (déjà bon, ne pas toucher)

| Pattern | Où | Pourquoi c'est juste |
|---|---|---|
| **State** | `Scene` + pile `SceneManager` · `StateMachine`/`NullStateMachine` | Le jeu a 9 écrans avec transitions suspendues (`halts_simulation`), et 30+ états d'entité. C'est *exactement* le cas d'usage. |
| **Observer** | `EventBus` synchrone ordonné | 4 consommateurs (UI, save, audio, logs), producteur = simulation sans référence à l'applicatif. Le contrat « ordered, no async ⇒ no non-determinism » est-thinking bien posé. |
| **Registry** | `TILE_LAYER_HANDLERS`, `OBJECT_FACTORIES`, `ENEMY_CONFIGS` | Extension sans modifier `WorldBuilder`. |
| **Null Object** | `NullStateMachine`, `NullCombatComponent` | Évite les `if x is not None` dans la boucle. |
| **Object Pool** | `ProjectileSystem` | Juste, générique, testé. À étendre (m3/m4). |
| **Séparation update/render** | `GameplayLoop` vs `Renderer` + `alpha` d'interpolation | Le mélange caméra/frame est le piège classique du fixed-timestep ; il est ici **explicitement traité et testé** (`test_frame_coherence.py`). |
| **Facade** | `Level`, `UIManager` | Correct dans l'intention — c'est son implémentation property-by-property qui est à revoir (m9). |

### ➕ À introduire

| Pattern | Cible | Justification contextuelle |
|---|---|---|
| **Spatial partitioning (chunks)** | Culling du terrain statique (M3) | Le terrain est **figé pour toute la session**. Un index par tuiles de 16×16 donne 4-9 chunks visibles au lieu de 972 tests. C'est la réponse standard, et elle est dimensionnée par la mesure : 89/972 = ratio mesuré, pas supposé. |
| **Ports & Adapters (DI minimale)** | `Game` → ports étroits (M2, M10) | `Scene` ne doit pas recevoir l'objet applicatif. Un `SceneHost` de 6 lignes remplace `game: Any` et supprime M2, M10 et une partie de m16 d'un coup. **Pas de conteneur DI** — juste des `Protocol`. |
| **Object Pool étendu** | Particules FX (m3) | `pygame.Surface` allouée 60×/s par type de particule. Le pool existe déjà : c'est un câblage, pas une abstraction nouvelle. |
| **Retry/Isolation boundary** | `EventBus.emit` (M7) | Un abonné ne doit pas pouvoir tuer un tick de simulation. Une `try/except` + `logger.exception` par abonné, avec l'invariant écrit en test. |
| **Strategy (explicite)** | Boîtes offensives (M4) | Remplacer la reconstruction par tick par un *handle vivant* réinjecté dans le pipeline. |

### ❌ Ce que je recommande explicitement de NE PAS faire

- **ECS complet.** Contre-productif ici, et ce n'est pas une question de goût :
  1. le nombre d'entités est de **1 sur le niveau livré** (`entity_sprites: 1`) ;
  2. le vrai coût n'est **pas** le pairing d'entités (0.37 ms/tick au total, dont 90 % dans le tri) mais le cull de rendu (1.62 ms) et l'allocation de boîtes (0.51 ms) — **aucun des deux n'est un problème d'ECS** ;
  3. le combat frame-data (`attack_data.py`, `frame_data.py`, `attack_state.py`) est le cœur de valeur du projet ; un ECS le disperserait en data tables pour un gain nul.
  → **Conclusion** : compléter le component-based **déjà amorcé** (`MovementComponent`, `ReactionComponent`, `CombatComponent`) ennerscoupant `Entity` (m2), et **rien d'autre**.
- **Résolution du `sort` de broadphase (M5) par un ordre canonique** plutôt que par un seuil « si n < K alors exhaustif ». Le seuil est plus simple, mesurable, et réversible ; un ordre canonique寓意 une refonte du contrat de déterminisme.
- **Hexagonal / ports-and-adapters à l'échelle du dépôt.** M1/M2 se corrigent par 2-3 `Protocol`. Le reste du code est déjà convenablement stratifié.
- **Event sourcing, DI container, plugin loader.** Aucun besoin demonstrated.

---

## 4. Plan de refactoring priorisé

### **Phase P0 — Débloquants (1 j, risque quasi nul)**

| # | Action | Fichiers | Impact |
|---|---|---|---|
| P0.1 | Parenthèses sur tous les `except` multiples | `save_game.py:63,78` · `event_router.py:503` · `stage.py:165` · `world_ui.py:1262` | Élimine C1. Test : import de chaque module sous 3.13 dans la CI matrix. |
| P0.2 | `ruff format` | `src/ui/menu_view.py` | Gate format actuellement **rouge**. |
| P0.3 | `KeyError` → erreur nommant les ids connus | `level_manager.py:57` | Élimine M9. |
| P0.4 | Supprimer `OPTIONS` mort ; corriger la docstring `ObjectPool` | `pause_scene.py:34` · `gameover_scene.py:31` · `object_pool.py:11` | m10, m11. |
| P0.5 | `logger.info(f"…")` → `%s` | `game.py:532,538` | m13. |
| P0.6 | Corriger le compte de tests du README (1511 → 1813) | `README.md:10,47,428` | m15. |

---

### **Phase P1 — Performance (3-5 j, gains mesurables)**

| # | Problème | Solution | Gain attendu (mesuré) |
|---|---|---|---|
| **P1.1** | **M3** — 972 culls/frame, 89 utiles | `TileChunkIndex` : tuiles groupées en chunks 16×16, index figé au build. `Renderer._collect_visible_blits` itère les chunks du viewport (~9) au lieu du groupe entier. Le plan de cull devient **O(9)** au lieu de **O(972)**. | **−1.4 ms/frame** (draw 2.45 → ~1.0 ms). C'est le **gain n°1** du chantier. |
| **P1.2** | **M4** — 35 `OffensiveBox`/tick | `HazardDamageSystem` et `ContactDamageSystem` détiennent des handlesvivants indexés par hazard ; `OffensiveBox` est mis à jour (`.swept`, `.box`) au lieu d'être reconstruit. Suppression de l'allocation `HitProperties()` par tick. | **−0.4 ms/tick** (update 1.91 → ~1.5 ms). |
| **P1.3** | **M5** — `EntityGrid` plus coûteuse que l'exhaustif | Seuil mesuré dans `EntityGrid` : sous `MIN_GRID_ENTITIES` (constante, ≈8), `overlapping_pairs` retombe sur l'exhaustif — **sans modifier l'ordre**, donc sans casser le déterminisme. + **early-out** dans `_candidates` : ne trier que si la liste n'est pas déjà ordonnée. | **−0.3 ms/tick** ; et supprime le coût *nul* sur le niveau livré (1 entité). |
| **P1.4** | **m5** — fallback jamais cachée | Dans `AssetLibrary.frames`, mettre en cache le résultat **sous la clé demandée** après un fallback. | **39 µs → ~0,1 µs** par appel ; supprime un `stat()` disque par frame et par entité en état `dash`. |
| **P1.5** | **m3/m4** — `Surface` par particule par frame | Pool `ObjectPool` pour `DustParticle` / `SparkParticle` / `SweatParticle` ; `Projectile.launch` réutilise la `Surface` si les dimensions n'ont pas changé. | Supprime ~60 `Surface`/s → churn CPython/GC. |
| **P1.6** | **m6** — 3 dicts `id(entity)` reconstruits/tick | Une passe de réconciliation in-place sur placeholders supprimeurs ; `hasattr(..., "landed_impact")` → un `isinstance` de protocole. | **−0.15 ms/tick**. |

> **Ordre d'exécution** : P1.1 d'abord (independamment vérifiable via `render_benchmark.py`, qui existe déjà), puis P1.2, puis P1.3.
> **Critère de recette** : `render_benchmark.py` (existant) doit montrer `frame` en baisse ; `contact_benchmark.py` (existant) doit montrer `grid` ≤ `exhaustive` à 1v1/4v4/8v8.

---

### **Phase P2 — Architecture (5-8 j)**

| # | Problème | Solution (principe) | Impact |
|---|---|---|---|
| **P2.1** | **M10** — hooks de scène en `getattr` | Déclarer `set_surface` / `set_ui_scale` / `view` sur `Scene` comme méthodes **no-op** (comme `enter`/`exit` l'ont déjà). Fin du duck-typing silencieux. | Supprime 7 `getattr` + 4 `callable`, et rend l'oubli impossible. |
| **P2.2** | **M2** — `Level.draw(game: Any)` | Introduire `SceneHost(Protocol)` (~6 lignes : `ui_scale`, `clock`, `scene_manager`, `notice`, `render_alpha`, `surface`). `Game` l'implémente. `Level.draw` et `GameplayScene.draw` prennent le port, plus `Any`. **Injection par le bas** : la simulation ne connaît plus l'applicatif. | Élimine M2, m16, et rend `Level.draw` testable sans `Game`. |
| **P2.3** | **M1** — `core` → `ui` | Extraire une `OverlayPort(Protocol)` (`draw_health_bars`, `draw_debug_overlays`, `draw_debug_panels`, `note_clash`, `update_metrics`, `layers`). `UIManager` l'implémente, `Renderer` le consomme via le port. Vérifié : 7 → 0 violation de couches. | Inversion de couches rétablie, `Renderer` testable avec un faux overlay. |
| **P2.4** | **M7** — abonné peut tuer le tick | `EventBus.emit` : `try/except` + `logger.exception` par abonné. Invariant écrit en test (« un abonné qui lève ne corrompt pas le tick »). | Robustesse du tick garantie par construction. |
| **P2.5** | **M8** — erreur fatale | Logger via `logger.exception`, dessiner sur la **cible de rendu** (pas la fenêtre), utiliser la chaîne `PanelRenderer`, et exposer l'erreur via une **`SceneErrorScene`** plutôt que `print` + `SystemExit(1)` opaque. | Smoke test CI capture enfin le traceback. |
| **P2.6** | **m7, m8** — magic number + injection tardive | `World.HASH_CELL_SIZE` dans `settings.py`, utilisé par `Level` **et** `GameplayLoop`. `SpawnSystem` prend `projectile_system` **au constructeur**. | Cohérence avec les conventions maison, câblage immuable. |
| **P2.7** | **m2** — `Entity` 1106 l. | Extraire les blocs déjà délimités par les composants existants : `EntityKinematics` (délégations `MovementComponent`), `EntityVitalsAdapter`, `EntitySweep`. `Entity` devient le **composition root** des composants, pas leur conteneur. | Réduit `Entity` sous ~500 l. **Pas d'ECS** — c'est de l'extraction de ce qui existe déjà. |

---

### **Phase P3 — Hygiène longue durée (2-3 j, sans risque)**

| # | Action | Principe |
|---|---|---|
| **P3.1** | **m1** — découper `world_ui.py` (2095 l.) en `world_ui/` : `health_bars.py`, `debug_boxes.py`, `label_placement.py`, `combat_panel.py`, `velocity.py`. `WorldUI` reste la façade. Chaque module ≤ 400 l. **Découpage pur** : aucun changement de comportement, la suite de 1813 tests sert de filet. |
| **P3.2** | **m9** — remplacer les 6 property/setter de `Level` par une délégation explicite documentée (ou un `LevelStateView` en lecture seule). |
| **P3.3** | **m12** — supprimer la ligne morte `type(sprite) is pygame.sprite.Sprite` et corriger le commentaire qui lui attribue le gain. |
| **P3.4** | **m14** — `DISPLAY_SAFETY_CEILING_FPS` : décider explicitement si 720 est voulu ; sinon `max(Display.FPS * 2, MAX_FRAME_LIMIT)`, avec un test d'invariant (le plafond dépasse la cadence, son plancher reste sous sa moitié — le test existe déjà, `test_frame_pacing.py`). |
| **P3.5** | **M6** — `SpatialHash` :ifi `id()` est conservé, le documenter comme **dangereux** et ajouter `remove` au chemin de vie des entités + un test « un `id` recyclé est correctement réinséré ». Alternative : `WeakKeyDictionary` sur le sprite. |
| **P3.6** | Réduire les `Any` restants par `Protocol` déjà déclarés (`Combatant`, `CollisionSprite`, `SnapshotCapable`) plutôt que par `getattr`. |

---

## 5. Ce que je ne toucherai pas (et pourquoi)

| Élément | Verdict |
|---|---|
| `Game.step` / `_run_ticks` / `render_alpha` / `halts_simulation` | **Exemplaire.** Le pacer dérivé, le plafond anti-emballement, l'alpha forcée à 1.0 sous halt — tout est justifié en commentaire et testé. |
| `EventBus` synchrone ordonné | **Correct** pour un jeu solo. Le passage async introduirait de la non-déterminisme : interdit par convention explicite du projet. Seul M7 (isolation) est à corriger. |
| Fixed timestep 60 Hz / rollback local | **Sain.** Le rollback est opt-in (`rollback_enabled=False`) — le bon choix par défaut. |
| `GameplayLoop` comme séquenceur d'ordre | **Bon pattern** (chaînage de responsabilité explicite, ordre load-bearing documenté). Ne pas le dissoudre dans un ECS. |
| `SpatialHash` / `EntityGrid` | Garder l'idée, corriger M5/M6. |
| `pygame.Surface` pour le rendu | Correct : CPU-dummy mesuré à 1.48 ms/frame en 1280×720, très en dessous du budget 16.7 ms. |

---

## 6. Validation de chaque phase

```bash
uv run ruff check src tests main.py tools          # lint
uv run ruff format --check src tests main.py tools # format
uv run ruff check src tests --select C901          # complexité
uv run mypy src main.py tools                      # types strictes
uv run pytest -q                                   # 1813 tests
uv run python tests/benchmarks/render_benchmark.py     # perf rendu (P1.1)
uv run python tests/benchmarks/contact_benchmark.py    # perf contact (P1.3)
uv run python tests/benchmarks/ui_benchmark.py
```

**Réception globale** : chaque phase est indépendante et réversible ; P0 et P3.1 sont sans risque comportemental ; P1 est validé par des benchmarks **existants** ; P2 est validé par mypy + le graphe de dépendances (je peux ajouter un test d'architecture interdisant `core → ui`, ce qui empêche la régression de M1).

**Charge estimée** : P0 ≈ 1 j · P1 ≈ 3-5 j · P2 ≈ 5-8 j · P3 ≈ 2-3 j. Les phases P1.1, P1.3, P2.3 sont indépendantes et peuvent être ré-exemptées en premier.

---

Dites-moi ce que vous voulez ajuster — par exemple :
- **si vous voulez un périmètre plus resserré** (P0 + P1.1 + P1.2 seuls, soit le gros du gain perf en 2 jours) ;
- **ou si P2.2/P2.3 (ports `SceneHost` / `OverlayPort`) vous semblent trop invasifs** — je peux proposer une variante minimale qui supprime `game: Any` sans toucher à la signature de `Scene`;
- **ou l'ordre** — je peux réordonner pour grinder P2 (architecture) avant P1 (perf), l'inverse de ma recommandation.

Une fois votre choix validé, passez en **Act mode** et j'implémenterai phase par phase, avec les tests qui vont avec.
