L'audit est complet. Toutes les informations ont été collectées : structure, modules, tests (156 verts), pipeline CI, assets, et comportements runtime. Voici le rapport final.

---

# 🔍 Rapport d'audit — Knightrock (Pygame / hack'n'slash 2D)

**Périmètre audité :** branche `feature/hitbox` (HEAD `c2815c0`), ~11 900 lignes de code source (`src/`), 23 fichiers de tests.
**Méthode :** lecture intégrale des modules, analyse du flux d'exécution (game loop → level → systems → entities), exécution de la suite de tests (`156 passed in 0.47s`), inspection du CI, comptage d'occurrences (`getattr`, code mort, événements, assets).
**Aucune modification de code effectuée** — rapport uniquement.

---

## 1. Résumé exécutif

La base de code est **d'un niveau nettement supérieur à la moyenne junior** : elle a déjà traversé plusieurs refactors lourds (git log : `ARCH-01`→`ARCH-08`, `BUG-01`→`BUG-06`, `PERF-01/02`) et en porte les bénéfices.

**Forces remarquables :**
- Fixed timestep 60 Hz avec accumulateur, hit-stop, snapshots sérialisables et entités déterministes (`entity_id` séquentiel, `rng` injectable) — orientation netcode déjà prise en compte.
- Architecture par **systèmes découplés** (`CombatSystem`, `SeparationSystem`, `ContactDamageSystem`, `HazardDamageSystem`, `GameplayLoop`) et **composants** (`Vitals`, `CombatComponent`, `JumpController`/`Block`/`Dash`, état machine).
- Utilisation systématique des **Protocols** (`Combatant`, `CombatPort`, `JumpEntity`, `HorizontalMovementEntity`, `WallJumpLock`) → bonne application du DIP côté physique/combat.
- **Data-driven combat** solide : frame data, phases startup/active/recovery, `Factory`/`Registry`, `EnemyConfig`/`PlayerConfig` en dataclasses immuables.
- 156 tests unitaires rapides (0.47 s), ci multi-plateforme PyInstaller avec smoke test, ci avec gate de coverage.

**Faiblesses structurelles restantes :**
1. **`Player` (698 l.) et `Level` (~180 l., 18 dépendances) restent des God Objects** — le refactor a déplacé les responsabilités mais pas terminé la décomposition au niveau agrégat.
2. **Aucun AssetManager** : les entités affichent des rectangles de couleur (`image.fill(color)`) alors qu'une centaine d'artworks animés est livrée et inutilisée, aucune surface `.convert_alpha()`, rendu full-screen 180 FPS sans dirty rects.
3. **Pas de système de scènes / sauvegarde / audio / event bus** — la boucle `Game.run()` est infinie, seul le level 1 est enregistré (`game.py:29`).
4. **56 `getattr()`/8 `hasattr` de duck-typing** non typés qui fragilisent LSP et la testabilité.
5. Du code mort/vestigial (attributs `_space_held` etc., snapshots rollback jamais invoqués, `MAX_PREDICTION_FRAMES`/`ROLLBACK_FRAMES`).

**Note de maturité estimée : 7,5/10** (très bon socle senior en logique métier ; la dette restante se concentre sur le rendu, l'agrégation et la gestion des ressources).

---

## 2. Findings détaillés par axe

### Axe 1 — Architecture générale

**F1.1 — [MAJEUR] God Class `Player` et pléthore de délégations plates**
`src/entities/player.py` (698 lignes). Après les extractions `ARCH-02/03`, `Player` conserve ~40 `@property` de délégation "flat" vers ses controllers (`player.py:286-488`), la lecture d'input (`get_input`, `_handle_attack_input`, `512-563`) et des règles de jeu. C'est un agrégat légitime, mais trop de surface.
**Solution :** factoriser le boilerplate de délégation via un petit mixin générique :
```python
class ControllerView:
    """Achémine les attributs vers les controllers (contient le DIP)."""
    _controllers: tuple[tuple[str, Any], ...] = ()

    def __getattr__(self, name: str) -> Any:
        for prefix, ctrl in self._controllers:
            flat = name[len(prefix):] if name.startswith(prefix) else ""
            if flat and hasattr(ctrl, flat):
                return getattr(ctrl, flat)
        raise AttributeError(name)
```
Et extraire la gestion des entrées dans un `PlayerInputHandler` pur (sans `pygame`, testable) qui émet des "intents d'action" consommés par la state machine.

**F1.2 — [MAJEUR] God Object `Level**
`src/core/level/level.py` : `__init__` construit 18 dépendances (groups, camera, renderer, gameplay_loop, spatial_hash, 2 systèmes de dégâts, world_builder, player, debug_controller) et `update()` (l.84-143) enchaîne plateformes, hazards, combat, contact damage, respawn, death border, exit detection.
**Solution :** déplacer les responsabilités dans des systèmes dédiés et faire de `Level une simple façade :**
```python
class Level:
    def __init__(self, ...):
        self.world = WorldBuilder(level_data).build(...)
        self.systems = [
            PlatformSystem(self.groups, self.spatial_hash),
            HazardsSystem(self.groups),
            PlayerRespawnSystem(self.player, self.level_data),
            ProgressionSystem(self.exit_sprites),
        ]
        self.gameplay = GameplayLoop()

    def update(self, dt):
        self.gameplay.update(dt, self.groups)   # tout est délégué
```

**F1.3 — [MOYEN] Packages incohérents (namespace packages implicites)**
`src/core/`, `src/states/`, `src/ui/`, `src/entities/` n'ont **pas** de `__init__.py` alors que `src/combat/` et `src/physics/` en ont (certains avec ré-exports soignés). Travaille en Python 3.14 (namespace packages OK), mais c'est fragile pour PyInstaller et les outils.
**Solution :** créer les `__init__.py` (vides ou avec `__all__` comme `combat/__init__.py`).

**F1.4 — [MOYEN] Boucle de jeu : 180 FPS de rendu pour une simulation à 60 Hz**
`src/core/settings.py:12` (`Display.FPS = 180`) vs `Simulation.TICK_RATE = 60` (l.106). Avec l'accumulateur (`game.py:71-86`), **2 frames sur 3 redessinent un état strictement identique**.
**Solution :** passer le rendu à 60–120 FPS (ou en mode "low latency" optionnel), et prévoir une interpolation de rendu + `pygame.display.set_allow_screensaver(False)` si l'inertie de la caméra doit rester fluide.

**F1.5 — [MOYEN] Absence de système de scènes**
`Game.run()` est une boucle infinie ; ni menu, ni pause, ni game over (respawn automatique sans écran, `level.py:119-123`). Et `_advance_level` au dernier niveau enregistré ne fait **rien** (silencieux) faute de `next_id`.
**Solution :** voir Axe 8 (F8.1).

**F1.6 — [MINEUR] Coordination duplicate `Level` ↔ `GameplayLoop`**
`GameplayLoop.process_combat_and_separation` (gameplay_loop.py:23-36) fait déjà séparation + combat + récupération des morts ; `Level.update` ré-applique du damage (contact/hazard) en dehors du loop. **Solution :** étendre `GameplayLoop` à tous les systèmes et laisser `Level` ne faire que `gameplay_loop.update(...)`.

---

### Axe 2 — Principes de conception (SOLID, DRY, composition)

**F2.1 — [MAJEUR] 56 `getattr` / 8 `hasattr` de duck-typing non typé**
Répartis dans `collisions.py:36-37,94`, `hazard_damage.py:21-26`, `world_ui.py:26-29,105-110`, `movement.py:223-228`, `contact_damage.py`, `gameplay_loop.py:44`, `debug_controller.py`, `entity.py`. C'est le **principal point de friction typage/testabilité** — chaque `getattr(entity, "is_dead", False)` est un contrat implicite et échoue silencieusement en silence (`world_ui` continue au lieu d'afficher).
**Solution : des Protocols `runtime_checkable` (pattern déjà utilisé) partout** :
```python
@runtime_checkable
class Routable(Protocol):
    @property
    def is_dead(self) -> bool: ...
# …
if isinstance(ent, RemoveAble):
    ent.kill()  # au lieu de getattr(entity, "is_dead", False)
```

**F2.2 — [MOYEN] `Entity` reste une base "fat" à responsabilités multiples**
`src/entities/entity.py` (640 lignes) : hitbox ou physiques, knockback (`470-495`), heavy knockback (`497-534`), stagger (`584-607`), state machine config, contact/proximité, moving plat.`. C'est un agrégat légitime mais bordé par le numéro de Template Method (`_pre_update`/`_post_update`) et beaucoup de délégations vers `vitals` (bon signe) MAIS une logique encore monolithique.
**Solution progressive :** extraire un `ReactionController (hurt/knockback/stagger) et un MovementIntegration, injectés en composition comme `combat` / `vitals`.

**F2.3 — [MOYEN] State strings magiques côté enemis vs Enum côté player**
`states/enemy_states.py` et `entity.py:443,525` utilisent `"idle"`, `"patrol"`, `"knockback"` en chaînes brutes, alors que `states/player_states.py` dispose de `PlayerState(Enum)`. Incohérence DRY/typage.
**Solution : `EnemyState(Enum)` partagé, et `entity.py` référence `EnemyState.KNOCKBACK`.**

**F2.4 — [MOYEN] Null object pattern éclaté en 4 classes internes**
`combat_component.py:506-552` : `_NullHitboxManager`, `_NullChargeHandler`, `_NullAttackState`, `_NullComboTracker`. Correct conceptuellement mais dupliqué et encapsulé dans un module qui grossit. **Solution : consolidater dans `src/combat/null_objects.py` et les rendre testables ; ou générer via `__getattr__` no-op sur un mixin.**

**F2.5 — [MINEUR] Netcode "ready" codé mais jamais branché**
`save_state()`/`load_state()` (`combat_component.py:303-335`), `AttackStateSnapshot`, `MAX_PREDICTION_FRAMES`/`ROLLBACK_FRAMES` (`settings.py:109-110`) sont **du code mort (aucun appel externe). Décision claire à prendre : soit brancher un vrai rollback + test E2E, soit retirer le code "netcode-ready" et documenter. Laisser le code mort dans une codebase senior n'est pas souhaitable.

**F2.6 — [AMÉLIORATION] caches de textes non bornés**
`ui/panel_renderer.py:19-26` : `_text_cache` ne purge jamais → croissance infinie en debug prolongé. Ajouter `cache_clear()` ou cache LRU par taille.

---

### Axe 3 — Entités et gameplay

**Positif notable :** double-pass de détection/résolution déterministe des contacts (`combat_system.py:38-56`, "trades" possibles), hitbox/hurtbox distincts, input buffering + coyote time, hit-stop global, séparation des états de réaction partagés (`reaction_states.py`).

**F3.1 — [MOYEN] Magic numbers physiques en dur dans les collisions**
`collisions.py:133` `+ 4` (t. olerance sol), `139-146` heuristiques axis-nearest ; `movement.py:274` `-2 <= vertical_dist <= 4` (monture de plateformes) ; `enemy_states.py:74` `< 10` (détection à 1 px) ; `level.py:121` `2.0` (respawn). Ces "fudge factors méritent des constantes nommées : `ContactProbe.MARGIN_PX`, `PlatformRider.EPSILON_VERTICAL`, etc., centralisées dans `settings.py`, et un commentaire sur l'heuristique `was_overlapping`.

**F3.3 — [MOYEN] `SeparationSystem` et `ContactDamageSystem` en O(n²)/tick**
`separation.py:19-56`, `contact_damage.py:20-42` tester chaque paire d'entités, documenté comme accepté (populations actuelles faibles). `ContactDamageSystem` passe aussi par `velocity` (momentum) — cohérent. **Solution aval : un hash spatial *des entités elles-mêmes** (grid des entités par cellule, 1 seul passage par tick, « PERF-02 » est déjà annoté dans le code ») → passer à O(n) ammortisé, avec un object pool de `HitCandidate`/rect réutilisables.

**F3.4 — [MOYEN] Substeps de mouvement non bornés par tick**
`movement.py:230-256` : nombre de substeps = `ceil(step/SUB_STEP_SIZE=16)`. En dash (1500 px/s, ~94 px/tick) → ~94 itérations ; c'est correct mais coûteux. **Solution : clamps (`max_velocity_per_substep), early-break avec `velocity==0` (déjà fait) — ajouter un compteur de garde et un `substep-max configurable pour éviter le spiral.

**F3.5 — [MINEUR] Double mécanisme de buffering d'attaque**
`player.py:552-554` pré-buffer via la state machine (`buffer_input("attack")`) **et** `_buffered_attack_name` — deux sources de vérité. Centraliser sur un seul (le buffer de la `StateMachine` avec payload dans le kwargs).

**F3.6 — [MINEUR] Attributs vestigiaux morts**
`player.py:140-143,598-601` : `_space_held`, `_left_held`, `_right_held`, `_block_held` sont écrits mais jamais lus ailleurs (les states lisent les attributs publics sans underscore), à part `space_held`. Supprimer (vestiges `ARCH-03`).

**F3.7 — [MINEUR] Collision Axis `+4` du sol** (déjà couvert F3.1) ; et **`KnockbackConfig(power=(0,0))` re-créé par paire dans `contact_damage.py:46`** → constante module-level `NULL_KNOCKBACK`.

---

### Axe 4 — Gestion des ressources

**F4.1 — [MAJEUR] Rendu sans `.convert_alpha()` ni rects sales, aucune asset library**
Confirmé par grep (`convert`, `convert_alpha`, `pygame.image.load` absents de `src/`). Les entités remplissent des `pygame.Surface(size)` et `fill(color)` (`entity.py:156-157`, `enemy.py`, `sprites.py:26-30`). Les 3 spritesheets d'ennemis animés + items (diamond/gold/potion/…), bullet, player/idle/run/jump/wall, spikes/saw — livrés mais **jamais chargés par le runtime.
**Impact réel :** rendu à 1440x900 @180 FPS en blit brut full-screen (`game.py:86`).
**Solution — `AssetLibrary`** :
```python
class AssetLibrary:
    def image(self, path, *, alpha=True) -> pygame.Surface:
        surf = self._cache.get(path)
        if surf is None:
            surf = pygame.image.load(resource_path(path)).convert_alpha()  # format display
            self._cache[path] = surf
        return surf
```
+ `SpriteSheet.load()`/`Animator` par état, + `pygame.display.update(rects)` avec calculé par le renderer.

**F4.2 — [MOYEN — cache immuable `LevelManager`** : cache par niveau chargé une seule fois, jamais évicté (`level_manager.py:24`) — acceptable à 5 niveaux ; documenter un budget simple (LRU si >N niveaux.

**F4.3 — [MINEUR — chemins centralisés incomplets : `LevelManager.register()`, `register"assets/data/... "` hardcodée à `game.py:29` — `resource_path` (paths.py) n'est utilisé que par `LevelManager.get`. Centraliser dans un `PATHS.yml` (assets registry JSON) pour les assets référencés par les TMX, eux aussi hardcodés via références `.tsx`.

---

### Axe 5 — Qualité du code

**F5.1 — [MAJEUR] Nombreuses valeurs magiques restantes** (déjà listées F1.4, F3.1) : `level.py:121 2.0`, `debug_controller.py:50 0.5`, `hazard`, `separation` (8e settings), `collisions.py +4`, `movement.py -2..4`, `player_states.py abs(vel.x)<0.1`, etc. Une passe de sweep `# TODO(sweep): centraliser les constantes` + un `Settings.groupe dédié les résoudrait en 1/2 journée.

**F5.2 — [MOYEN] Incohérences de nommage**
`renderer.py:43 draw_debug_panels` (pluriel) vs `ui_manager.draw_state_panel` ; `Colors` vs couleurs inline dans `world_ui.py:32-46` et `panel_renderer.py` ; `max_wall_jumps: int | float = math.inf` (borne "infini" fragile dans `player_config.py:105`) ; `.gitignore` commence par une backtick artificielle `` ``` `` (fichier malformé depuis un export chat, seule la ligne finale `assets/` compte).

**F5.3 — [MINEUR] Sur-commentaire/docstrings système**
`player_states.py` : chaque classe/état a une docstring mécanique («Represent the PlayerIdle state»). Remplacer par 1–2 lignes d'intention.

**F5.4 — [MINEUR] `verify_audit.py` : assertions par sous-chaînes**
373 lignes de vérifications `"class Goblin(Enemy)" in enemy_file` qui donnent une **fausse confiance** (un renommage innocent fabriquerait des faux positifs ; les vrais contrats ne sont pas vérifiés). **Solution :** remplaçable par pytest-structure + `mypy --strict`/ruff, ou une batterie de tests de contracts (cf. Axe 7).

**F5.5 — [AMÉLIORATION] Aucun outil qualité dans `pyproject.toml`**
Pas de section `[tool.ruff]`, pas de `[tool.mypy]`, CI sans lint ni mypy. Ajouter ruff (lint+format, règles flake8-bugbear + isort) et mypy with `disallow_untyped_defs` — le code est déjà très typé, le retour sera immédiat.

---

### Axe 6 — Performance

**F6.1 (déjà F1.4 / F4.1) — [MAJEUR]** 180 → 60-120 FPS + `convert_alpha` + rects sales + `SDL_VSYNC`. Gain mesurable le plus important.

**F6.2 — [MOYEN] O(n²) combos pairs tests** (`combat_system.py:46-48` documenté, `separation`, `contact_damage`) : le `SpatialHash` ne bucket que l'environnement. Ajouter un grid pour entités (cf. F3.3) + pré-filtrage faction sur la boucle (`if attacker.faction==target.faction: continue` est bien là — bon).

**F6.3 — [MOYEN] Allocations par tick** : `Vector2(...)` dans `can_see_player`/`distance_to`, `list` subs­steps, `HitCandidate` (OK immutables, c'est voulu pour le determinisme), `KnockbackConfig` null par paire (`contact_damage.py:46`). Pour un jeu en 60Hz avec ~20 spprites : anecdotique, MAIS dès que vous ajouterez projectiles/particules → **Object Pool obligatoire** (prévoir un `ObjPool[T]` générique générique dès maintenant).

**F6.4 — [MINEUR] `spatial_hash.py`** : `update_all` fait `remove`+`add` pour chaque sprite — pour des plateformes (peu nombreuses c'est parfait du moment qu'elles bougent ; OK.

**F6.5 — [MINEUR – amuel] `is_visible` + blit boucle directe** = culling par rect (bon). Amélioration : itérer `LayeredUpdates` trié si les z-order multi-FG sont requis (actuellement FG dessiné à part — correct pour le passe).

---

### Axe 7 — Testabilité et maintenabilité

**Positif fort.** 156 tests verts en 0.47 s, scope unitaire ciblé, conftest avec fixtures, mocks d'interface (`SpyCombat`/`SpyStateMachine`/`InputStub` — excellents), determinisme (rng, entity_id). CI : pytest --cov --cov-fail-under=50 + build multi-OS + smoke test headless (`SDL_VIDEODRIVER=dummy`).

**F7.1 — [MOYEN] Couverture 50 % insuffisante et zones non testées**
Aucun test sur : `Level`/`WorldBuilder` (build TMX), `Renderer`/`Camera`, `InputProvider` (keyboard/gamepad polling réel, deadzones), `InputManager` mapping, `GameplayLoop` end-to-end (hit-stop suspendu), `HazardDamage` en contexte world, `separation` multi-entités. **Action : package-level test coverage ≥ 70 % ; ajouter un fixture « SDL dummy » avant pygames dans un `tests/conftest.py` pour tester l'orchestration.**

**F7.2 — [MOYEN] Helpers de test dupliqués**
`make_entity`/`phase`/`attack` redéfinis dans `test_hitbox_pipeline.py`, `test_damage_resolution.py`, `test_combat_behaviors.py`… Factoriser dans `tests/unit/helpers.py + fixtures conftest (DRY des tests eux-mêmes).

**F7.3 — [MINEUR] Logging non centralisé**
`logging.basicConfig` global dans `game.py:17-20` (niveau INFO, format, module-level → config exécutée à l'import, interfere avec les tests). **Solution : `logging.config.dictConfig` dans `main.py` uniquement, les modules utilisent `getLogger(__name__)`** (pattern déjà présent dans `level_registry`/`world_builder`).

**F7.4 — [MINEUR] Nombreuses `type: ignore[assignment]` dans les tests**
(ex. `test_damage_resolution.py:66-67`) — signe sain — on remplace des interfaces ; passez à des fixtures typés pour éviter les `# type: ignore`.

---

### Axe 8 — Gestion d'état globale du jeu

**F8.1 — [MAJEUR] Absence de state machine d'application, de sauvegarde, d'event bus** (3 trous majeurs pour features futures) :
- `game.py` : pas de `MenuScene/PauseScene/GameOver` → rien ne s'interrompt, et dans `_advance_level` à la fin des niveaux → blocage muet.
- `LevelConfig.level_unlock` (`level_data.py:47`) **défini mais jamais lu nulle part** → progression sans suite.
- `pygame.event` custom jamais utilisé (grep vide), les systèmes communiquent par appels directs à travers `Level` (rappels implicites).

**Solution commune (architecture cible, cf. §4)** — `SceneManager`, `SaveGame` neutre (JSON), `EventBus` minimal :
```python
events = EventBus()
events.emit(PlayerDied())               # GameplayLoop → UI·Audio·Save
events.emit(LevelCompleted())           # Progression.next() · SaveGame
```
et remplacer `level_manager.register(0, ...)` par un `LevelRegistryConfig` (map id → path) déclaratif.

---

## 3. Roadmap de refactoring priorisée

**Phase 1 — Quick wins (< 2 jours, sans risque, haute valeur)**
| # | Action | Sévérité |
|---|---------|----------|
| 1 | `__init__.py` pour packages manquants + README non vide (README.md est vierge) | Moyen |
| 2 | Supprimer code mort vestigiel (`_space_held` etc., `space_held` innécessaire) | Mineur |
| 3 | FPS rendu 60-120 + `convert_alpha()` à l'AssetLibrary naissante | Majeur |
| 4 | Déplacer magic numbers du résiduel (F3.1/F3.3) vers `settings.py` groupés | Moyen |
| 5 | `EnemyState(Enum)` + cleaner `.gitignore`/nommages incohérents | Moyen |
| 6 | Centraliser `KnockbackConfig.NULL_KNOCKBACK` constant, `collisions` constants nommés | Mineur |
| 7 | ruff + mypy configurés (pyproject) et lancés en CI, remplacer `verify_audit.py` par des tests | Amélioration |
| 8 | Logger via `dictConfig`, `getLogger(__name__)` partout | Mineur |
| 9 | Factoriser helpers de test + fixtures (F7.2) | Moyen |
| 10 | Tests d'orchestration headless (GameplayLoop, Level, InputManager⏎) | Moyen |

**Phase 2 — Chantiers courts (1–2 semaines)**
| # | Chantier | Bénéfice |
|---|---------|----------|
| 1 | **AssetLibrary + Animator + sprite sheets enemies/player/items** (débloque tout l'artiste existant) | Majeure — impact graphique immédiat |
| 2 | **Rendu dirty-rects** (`display.update(rects)` + culling itératif déjà bon) | Perf |
| 3 | **Réduction de `Player`** (mixin `ControllerView`, `PlayerInputHandler`) — objectif < 400 l. | Maintenabilité |
| 4 | **SceneManager minimal** (Menu/Play/Pause/GameOver) + `LevelConfig` data-driven complet (id→path) | Features futures |
| 5 | **EventBus** câblé par-dessus les systèmes existants sans toucher au déterminisme ; écouter `events.emit(PlayerDied)` → UI | Découplage UI/combat |
| 6 | **SaveGame JSON** + progression `level_unlock | Feature |
| 7 | Tests couvrant les systèmes manquants (cip ≥ 70 %) | Confiance |

**Phase 3 — Chantiers lourds (3–6 semaines, à décider au besoin feature)**
1. **SpatialHash des entités** (élimine les O(n²) `Separation`/`Contact`/`Combat`) + **ObjectPool générique** pour projectiles/particules.
2. **Refactor `Entity → composition** complète** : `MovementComponent` + `ReactionComponent` branchés comme `Vitals/Combat (LevelS. de F1.2) ; `Level` n'est plus qu'une façade de systems.
3. **Rollback netcode réel** (on tire enfin les snapshots existants) **ou** suppression du code mort associé.
4. Externalisation finale des données de gameplay en **JSON data-driven** (attaques, enemies, levels) — actuellement en dataclasses Python, très bien pour l'instant ; JSON optionnel quand l'éditeur/designers arrivent.

---

## 4. Architecture cible recommandée

```
main.py                     # bootstrap : pygame.init, dictConfig, run(scene_manager)
└── application/
   ├── scene_manager.py     # State<Scene> — Menu/Play/Pause/GameOver + transitions
   ├── event_bus.py         # EventBus<T>, typed Signal (+ POST_TYPES in EventBus)
   ├── asset_library.py     # lazy cache convert_alpha + SpriteSheet + Animator
   ├── save_game.py         # dataclass + JSON store (progression, settings)
   ├── settings.py          # constantes centralisées (déjà dense, on l'étend)
   └── paths.py             # resource_path (existant) + registry PATHS
   └── scenes/
        ├── menu_scene.py / pause_scene.py / gameover_scene.py
        └── gameplay_scene.py  # contient level + hud + pause via overlay
└── core/
   ├── game.py              # = Application (iojit, Game.run → scene_manager)
   └── level/ level.py      # façade : level_data + groups + spatial_hash
       └── systems/  (GameplayLoop étendu)
            platform_system / hazard_system / spawn_system
            physics_system / combat_system / separation_system
            contact_damage / hazard_damage / progression_system
   └── input/ (provider/bindings/manager – déjà propre)
   └── rendering/ (camera + renderer dirty-rects + world_ui)
└── entities/
   ├── entity.py            # Sprite + components (thin)
   ├── components/ (vitals, combat, movement, reaction, controllers)
   ├── player.py (Player(states + PlayerInputHandler + Controllers)
   └── enemies/ (factory, configs, types/*.py — déjà propre)
└── physics/  (collisions, movement, separation, spatial_hash, gravity… — RAS)
└── combat/   (frame_data, combat_system, assets validés ; purger netcode mort)
└── states/   (state_machine + reaction states ; EnemyState(Enum))
└── ui/       (ui_manager, panel_renderer, styles, player_ui, world_ui)
tests/
   unit/ (systemes, entities, states, physics, helpers.py)
   headless/ (gameplay loop E2E sous SDL_VIDEODRIVER=dummy)
```

---

## 5. Points de vigilance pour le futur

- **Le socle est très bon sur le fond (déterminisme, types, states, frame data, CI).** Les deux vrais trous à combler avant d'ajouter des features : **rendu/ressources** (AssetLibrary + convert_alpha + FPS) et ****scènes + event bus + save**.
- Les constantes «netcode » existantes sont un investissement payé *mais seulement si un rollback arrive réellement* : décision à prendre tôt (brancher ou retirer, pour ne pas maintenir du code mort).
- Lors de l'ajout de projectiles/particules/ennemis : **ObjectPool** et **SpatialHash entités** obligatoires à ce moment-là, sinon un retour arrière O(n²) à résoudre illico.
- Examiner `hasattr` pour les comportements de `DeathBorder`/`Falling` — la limite `death_border_bottom > 0` condition l'utilisation (ligne 128-132) : prévoir d'activer par niveau.

**Conclusion** — base de code mature pour un projet indépendant : la dette restante est bien identifiée, isolée, et chaque chantier de la roadmap est segmenté sans risque. Les quick wins (Phase 1) suffisent déjà à remonter la note de maturité de 7,5 → 8,5/10 dès la prochaine itération.