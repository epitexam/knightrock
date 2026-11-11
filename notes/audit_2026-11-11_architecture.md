# Audit d'architecture et de qualité — 2026-11-11

Branche `fix/remediation`. Python 3.14, pygame-ce 2.5.8, PyTMX.
Mesures faites en headless (`SDL_VIDEODRIVER=dummy`) dans un venv local.

**Limite de l'audit.** `assets/graphics` et `assets/data` sont exclus par
`.gitignore` et absents de ce poste : aucune vraie carte `.tmx` n'a pu être
chargée et le jeu n'a pas été lancé avec ses sprites. 100 tests échouent et
16 sont en erreur pour cette seule raison (`FileNotFoundError` sur les
animations ou les `.tmx`). Toutes les comparaisons « avant / après » de ce
document se font contre cette base : 3 244 tests passent, et aucun test qui
passait ne doit échouer.

---

## A. Architecture initiale

### Vue d'ensemble

183 modules, environ 40 000 lignes dans `src/`, 160 fichiers de tests.

```
main.py                    point d'entrée : arguments, logs, Game().run()
src/
├── application/           pile de scènes, bus d'événements, sauvegarde, réglages
│   └── scenes/            menu, niveaux, options, vidéo, contrôles, jeu, pause…
├── core/
│   ├── game.py            racine de composition ET boucle ET fenêtre (voir B1)
│   ├── settings.py        2 108 lignes de constantes (voir B3)
│   ├── display/           cadrage, letterbox, fenêtre, présentation
│   ├── level/             Level (façade), WorldBuilder, LevelData (adaptateur TMX)
│   │   └── systems/       15 systèmes ordonnés par GameplayLoop
│   ├── rendering/         caméra, renderer, index des tuiles par blocs
│   ├── input/             routeur d'événements, bindings, providers
│   ├── fx/                particules et émetteurs
│   └── rollback/          instantanés et restauration déterministe
├── combat/                frame data, résolution des coups, knockback
├── entities/              Entity, Player, Enemy, composants, contrôleurs
├── physics/               collisions, gravité, mouvement, spatial hash
├── states/                machines à états (joueur, ennemis, réactions)
├── data/                  chargeurs JSON stricts + valeurs de repli
└── ui/                    HUD, menus, overlay de debug
```

### Les systèmes, tels qu'ils fonctionnent

| Sujet | Implémentation | Appréciation |
|---|---|---|
| Boucle | `Game.step` : fenêtre → événements → ticks fixes (60 Hz, accumulateur borné, surplus abandonné) → dessin → présentation. Interpolation de rendu par `render_alpha`, coupée quand une scène fige le monde. | **Bonne.** Fixed timestep correct, séparation simulation/rendu nette, pas de spirale de la mort. |
| Ordre de la simulation | `GameplayLoop.update` séquence 15 systèmes injectés par `Level` ; chaque système est testable seul. | **Bonne.** Ordre explicite et documenté. |
| Entités | Héritage court (`Sprite` → `Entity` → `Player`/`Enemy`) + composants (`Vitals`, `MovementComponent`, `ReactionComponent`, `CrouchPosture`, contrôleurs du joueur). | **Correcte mais `Entity` reste très gros** (B5). |
| États | `StateMachine` par entité, états en classes, interruptions déclarées. | **Bonne**, sauf les tests d'état par nom de chaîne depuis l'extérieur (B6). |
| Collisions | Résolution par axe, sous-pas, sweep AABB pour le combat, spatial hash pour le décor, grille d'entités pour les paires. | **Solide** : tunneling traité, complexité maîtrisée (voir E). |
| Événements | Bus synchrone typé (`LevelStarted`, `PlayerDied`, `LevelCompleted`, `UiFeedback`), abonnements à vie de l'application, aucun désabonnement manquant. | **Proportionné** : pas de bus pour tout, seulement pour les faits que l'application observe. |
| Ressources | `AssetLibrary` unique et en cache, `convert`/`convert_alpha` au chargement, sons chargés une fois, polices embarquées et mises en cache. | **Bonne.** Aucun chargement dans la boucle. |
| Tiled / PyTMX | `LevelManager` charge, `LevelData.from_tmx` convertit en dataclasses, `properties` valide les propriétés personnalisées avec leur emplacement, `WorldBuilder` construit via deux registres (couches, objets). | **Bonne** : le gameplay ne voit jamais PyTMX. |
| Rollback | Instantanés par entité et contrôleur, sommes de contrôle géométriques. | Hors périmètre des changements ; couvert par les tests. |
| Qualité | Ruff (avec C901), mypy strict, 3 360 tests, contrôle des dépendances entre couches (`test_layer_boundaries.py`). | **Au-dessus de la moyenne** pour un projet de cette taille. |

### Dépendances entre packages (mesurées sur les imports à l'exécution)

```
application ──► ui, core, core.input, core.display, combat, data
ui          ──► core, core.rendering, entities, combat, states
core.level  ──► core, combat, entities, physics, core.rendering, application(!)
entities    ──► combat, core, physics, states, data
combat      ──► core, data, states
core        ──► application(!), ui(!)        ← via core/game.py et core/audio.py
```

Deux cycles d'import à l'exécution :

1. `application.settings_store` ↔ `core.input.bindings_repository`, cassé par
   des imports dans le corps des fonctions (B2).
2. Les scènes entre elles (menu → jeu → pause → menu…), cassé par un import
   local dans `gameplay_scene`. C'est la navigation normale d'un jeu : **acceptable**.

---

## B. Rapport d'audit

Légende : **avéré** = vérifié par exécution ou mesure ; **risque** = plausible,
non démontré ; **opportunité** = amélioration sans défaut actuel.

### B0 — Le verrou de contrôle après un saut mural ne s'applique jamais au joueur — **Critique, avéré**

- **Où :** `src/physics/movement.py:193`, `src/entities/controller_view.py`.
- **Quoi :** `apply_horizontal_movement` teste
  `isinstance(entity, WallJumpLock)`, un `Protocol` `@runtime_checkable`.
  Depuis Python 3.12, ce test utilise `inspect.getattr_static`, qui ne voit pas
  les attributs fournis par `__getattr__`. Or `Player` expose
  `wall_jump_lock_timer` et ses voisins par `ControllerView.__getattr__`.
  Vérifié : `isinstance(player, WallJumpLock)` renvoie `False`, alors que
  `hasattr(player, "wall_jump_lock_timer")` renvoie `True`.
- **Conséquence :** la réduction de contrôle horizontal prévue après un saut
  mural (`wall_jump_lock_duration = 0.18 s`, configurée dans `player.json`) est
  du code mort pour le joueur. Les tests passent parce qu'ils utilisent des
  objets de substitution avec de vrais attributs.
- **Coût annexe :** environ 18 µs par appel, soit 0,18 ms par tick (7 % de la
  frame mesurée) pour un test qui répond toujours non.
- **Corrigé** (décision du propriétaire) : `Player` déclare les trois membres
  du verrou comme de vraies propriétés au lieu de les servir par
  `__getattr__`. **Cela change le ressenti du saut mural** : le verrou conçu
  s'applique désormais. Testé par `tests/unit/test_wall_jump_lock.py` avec le
  vrai `Player` (qui échouait avant la correction).
- **Leçon générale :** `@runtime_checkable` + `__getattr__` est un piège ; voir B7.

### B1 — `Game` est à la fois racine de composition, boucle et gestionnaire de fenêtre — **Élevé, avéré**

- **Où :** `src/core/game.py` (903 lignes, 49 méthodes).
- **Quoi :** la classe construit tout (bus, audio, pile de scènes, réglages),
  fait tourner la boucle, gère la fenêtre, le plein écran, le suivi des écrans,
  la persistance des réglages et l'écran d'erreur fatale. Environ 20 méthodes
  ne concernent que l'affichage.
- **Pourquoi c'est un problème :** c'est le seul module de `core` qui importe
  `application` et `ui`. `test_layer_boundaries.py` doit l'exempter
  explicitement (« named core for historical reasons »). La règle de couches
  « `core` ne dépend pas de l'application » est donc fausse pour le module le
  plus central.
- **Correction :**
  1. déplacer `game.py` dans `application/`, sa vraie couche (faible risque,
     mécanique) ;
  2. extraire l'affichage (stage, présentation, suivi de fenêtre, plein écran)
     dans un objet dédié qui serait la propriété de `Game` (risque moyen :
     87 références de tests à `game.presentation`, qui resteraient valides).

### B2 — `BindingsRepository` : code mort qui crée un cycle et une exception de couche — **Élevé, avéré**

- **Où :** `src/core/input/bindings_repository.py:355`.
- **Quoi :** la classe n'est utilisée par aucun code de production, seulement
  par ses tests. Elle importe `application.settings_store` dans le corps de ses
  méthodes, pour contourner le cycle qu'elle crée. Le test de couches tolère
  `core` → `application.settings_store` uniquement à cause d'elle.
- **Correction :** la supprimer et réécrire ses tests (migration des contrôles,
  fichiers corrompus) contre `SettingsStore`, qui est le vrai chemin de
  production. Le cycle et l'exception disparaissent.

### B3 — `core/settings.py` : 60 % du fichier ne concerne que les effets visuels — **Moyen, avéré**

- **Où :** `src/core/settings.py` (2 108 lignes, 38 classes, importé par 52 modules).
- **Quoi :** `Dust`, `DustGrain`, `DashDust`, `FootstepTier`, `FootstepDust`,
  `FxDecal`, `FxGuard`, `FxDizzy` et `Sweat` font environ 1 250 lignes. Elles ne
  sont lues que par `core/fx` et par `PhysicsSystem`, qui déclenche la poussière.
- **Pourquoi :** un fichier de configuration central doit rester lisible.
  Aujourd'hui, la physique (50 lignes) est noyée entre des centaines de lignes
  de réglages de grains de poussière, et toute retouche d'effet modifie le
  module dont dépendent 52 autres.
- **Correction :** déplacer ces classes dans `src/core/fx/tuning.py`. C'est une
  opération mécanique, sans changement de valeur.

### B4 — `application.events` est un contrat de la simulation rangé dans l'application — **Moyen, avéré**

- **Où :** `src/core/level/level.py`, `src/core/level/systems/notification_system.py`
  et `src/core/audio.py` importent `src/application/events.py`.
- **Quoi :** le niveau émet `LevelStarted`, `PlayerDied` et `LevelCompleted`
  depuis le tick fixe. Le contrat est produit par `core` et consommé par
  l'application. Le placer dans `application` inverse la dépendance, d'où une
  seconde exception dans le test de couches.
- **Correction :** déplacer `events.py` dans `src/core/`. Les dépendances vont
  alors toutes dans le même sens (`application` → `core`), et la règle de couches
  devient simplement « `core` n'importe ni `application` ni `ui` ».
- **Compromis :** le fichier documente l'argument inverse (« la simulation
  posséderait un concept qui ne sert qu'à l'application »). Il ne tient pas : le
  niveau *produit* ces faits, il en est donc le propriétaire naturel.

### B5 — `Entity` : 1 153 lignes, 79 méthodes, un constructeur de 174 lignes — **Moyen, avéré**

- **Où :** `src/entities/entity.py:85`.
- **Quoi :** un mélange de simulation (physique, santé, collisions), de
  présentation (`flash_timer`, `parry_flash_timer`, `turn_ratio`,
  `turn_lead_px`, `landed_impact`, marqués « render-only ») et de nombreuses
  propriétés de délégation vers les composants.
- **Pourquoi :** un objet de simulation qui porte l'état de rendu impose de
  documenter, champ par champ, ce qui est sauvegardé par le rollback et ce qui
  ne l'est pas.
- **Recommandation :** regrouper l'état de rendu dans un composant
  (`RenderHints`) et l'état de virage dans un `TurnProfile` porté par l'entité.
  **Non fait ici** : le joueur ne peut pas être instancié sans les sprites
  absents, donc une centaine de tests de comportement ne tournent pas sur ce
  poste. C'est le refactor le plus risqué de la liste ; il doit être fait avec
  la suite complète.

### B6 — Les systèmes interrogent les états par leur nom en chaîne — **Moyen, avéré**

- **Où :** `physics_system.py:59-104`, `collisions.py:165`, `renderer.py:28`,
  `contact_system.py` (`current_state_name == "dash"`, `"knockback"`…).
- **Pourquoi :** une faute de frappe ou un état renommé échoue en silence ;
  mypy ne peut rien vérifier.
- **Recommandation :** exposer des prédicats sur l'entité (`is_dashing`,
  `in_knockback`) ou utiliser des constantes partagées. Faible risque, à faire
  progressivement.

### B7 — 362 `getattr`/`hasattr` défensifs, dont beaucoup sur des types connus — **Moyen, avéré**

- **Où :** principalement `ui/world_overlay_*` (debug), `physics/collisions.py`,
  `physics/movement.py`, `core/level/systems/*`, `renderer.py`.
- **Quoi :** deux cas distincts.
  - **Justifiés :** les groupes `pygame.sprite.Group` mélangent tuiles,
    plateformes et entités, qui n'ont pas les mêmes attributs.
  - **Injustifiés :** l'accès à des systèmes typés et injectés
    (`getattr(self.combat_system, "impact", 0.0)`,
    `hasattr(camera, "add_trauma")`), et l'accès à un attribut **privé** du
    joueur depuis un autre module
    (`getattr(player, "_dash_started_this_frame", False)` dans `GameplayLoop`).
- **Pourquoi :** chaque `getattr(x, "nom", défaut)` désactive mypy et
  transforme une faute de frappe en valeur par défaut silencieuse, ce qui est
  exactement la famille de B0. Le coût est mesuré (≈ 1 360 appels par tick,
  ≈ 0,3 ms), mais secondaire.
- **Correction :**
  - accès directs et typés là où le type est connu (fait dans `GameplayLoop`) ;
  - un `Protocol` `Collider` (`hitbox`, `old_hitbox`, `one_way`) pour le décor,
    à long terme.

### B8 — Fonctions trop longues — **Faible à moyen, avéré**

`MenuView.layout` (196 lignes, introduite pendant la session précédente),
`Entity.__init__` (174), `Level.__init__` (110), `bindings_from_dict` (100),
`GeoLayer.draw_boxes` (92). Ruff C901 ne les signale pas, car elles ont peu de
branches, mais elles sont difficiles à lire d'un bloc.

### B9 — Exceptions larges — **Faible, avéré**

Dix `except Exception`. Ils sont tous délibérés et commentés : frontière avec le
matériel (manettes), écran d'erreur fatale, isolement des abonnés du bus,
restauration du `Stage`. Aucun ne masque d'erreur de logique. Les trois de
`event_router` pourraient être resserrés en `pygame.error`. **Pas d'action.**

### B10 — Ce qui n'est pas un problème

- **ECS :** non recommandé. Avec 1 joueur et quelques dizaines d'ennemis, le
  coût est dominé par les `blit` (voir E). La composition déjà en place
  (composants et contrôleurs) apporte l'essentiel de la modularité, sans la
  complexité d'un ECS.
- **Quadtree, object pooling :** le spatial hash et la grille d'entités
  suffisent ; les projectiles sont déjà mis en pool.
- **Dirty rects :** non pertinents, l'écran défile et chaque frame est un
  repaint complet (choix documenté et correct).
- **Nouveau bus d'événements :** inutile, l'actuel est proportionné.

---

## C. Architecture cible

La structure par couches existe déjà ; elle n'est faussée qu'à deux endroits
(B1 et B4). La cible corrige la direction des dépendances, sans multiplier les
dossiers :

```
src/
├── application/             composition et navigation
│   ├── game.py              ← core/game.py (racine de composition + boucle)
│   ├── scene.py, scene_manager.py, save_game.py, settings_store.py
│   └── scenes/
├── core/                    simulation et rendu, n'importe ni application ni ui
│   ├── events.py            ← application/events.py (contrat émis par la simulation)
│   ├── settings.py          réglages de simulation (≈ 850 lignes)
│   ├── fx/tuning.py         ← réglages d'effets sortis de settings.py
│   ├── input/               (sans BindingsRepository)
│   └── …                    inchangé
├── combat/ entities/ physics/ states/ data/ ui/   inchangés
```

Règle de dépendance visée, contrôlée par `test_layer_boundaries.py` :

```
application ──► ui ──► core ◄── combat, entities, physics, states, data
      └──────────────────► core
```

`core` n'a plus aucune exception. `core/audio.py` reste dans `core` : il ne
consomme que `core.events`.

---

## Plan de refactorisation (ordre d'exécution)

| # | Étape | Priorité | Risque | Vérification |
|---|---|---|---|---|
| 1 | B2 : supprimer `BindingsRepository`, migrer ses tests vers `SettingsStore` | Élevé | Faible | Tests de migration des contrôles |
| 2 | B4 : `application/events.py` → `core/events.py` | Moyen | Faible | Suite, mypy, test de couches resserré |
| 3 | B1.1 : `core/game.py` → `application/game.py` | Élevé | Faible | Suite, `main.py`, outils, test de couches sans exemption |
| 4 | B3 : réglages FX → `core/fx/tuning.py` | Moyen | Faible | Suite, valeurs identiques (comparaison des attributs) |
| 5 | B7 (partiel) : accès typés dans `GameplayLoop` | Moyen | Faible | Suite, mypy |
| 6 | B8 : découper `MenuView.layout` | Faible | Faible | Captures de référence identiques au pixel |
| — | B0 : verrou du saut mural | Critique | **Change le gameplay** | En attente de décision |
| — | B1.2, B5, B6 : extraction de l'affichage, `Entity`, prédicats d'état | Moyen | Moyen | À faire avec les assets et la suite complète |

Les sections D à G (refactorisation effectuée, performances, validation, état
final) sont complétées à la fin de ce document.

---

## D. Refactorisation effectuée

Sept commits sur `fix/remediation`. Chacun a été vérifié seul : suite
complète, mypy et Ruff.

| Commit | Problème | Changement |
|---|---|---|
| `14b12d3` | mypy en échec (3 erreurs introduites par la session précédente dans `MenuView._wrap_text`) | Une variable ne sert plus à la fois de `str` et de `Surface`. |
| `81f8f58` | B2 | `BindingsRepository` supprimé ; `bindings_repository.py` renommé `bindings_codec.py` (ce qu'il est vraiment) ; ses tests passent par `SettingsStore`, le vrai chemin du jeu, et gardent tous les cas de migration. |
| `5b44361` | B4 | `src/application/events.py` → `src/core/events.py`. |
| `239906e` | B1.1 | `src/core/game.py` → `src/application/game.py` ; l'exemption du test de couches disparaît. |
| `731b66a` | B3 | Réglages d'effets → `src/core/fx/tuning.py`. `settings.py` passe de 2 108 à 847 lignes. Chaque valeur a été comparée avant et après : identiques. |
| `35a2fa5` | B7 (partiel) | `GameplayLoop` lit ses systèmes par leurs types ; l'attribut privé non déclaré `_dash_started_this_frame` devient un attribut public déclaré dans `Player.__init__`. |
| `c21725c` | B8 (partiel) | `MenuView.layout` (196 lignes) découpé en `_bands`, `_content` et `_place`. Captures de référence identiques au pixel. |

**Suite, après la première version de ce rapport :**

| Commit | Problème | Changement |
|---|---|---|
| `93d29e4` | B0 | Le verrou du saut mural s'applique au joueur (**changement de gameplay**, décidé par le propriétaire). |
| `7ac5d7f` | B7 (cause racine de B0) | `ControllerView` supprimé. Les lecteurs passent par `player.jump`/`.guard`/`.dash` ; le verrou est un attribut déclaré `Entity.wall_jump_lock` ; plus aucun `Protocol` testé par `isinstance`. Les faux joueurs des tests deviennent une fabrique unique, `tests/fakes.py:player_shape`. |
| `607f5da` | Régression de la session précédente | Le fondu entre pages (`4468f7e`) faisait échouer `test_a_halted_scene_repaints_identical_pixels`, invisible tant que les assets manquaient. Le test attend désormais la fin du fondu (`SceneManager.transitioning`) avant la même assertion exacte. |
| `2334a09` | README faux | Nombre de tests, couverture et fichiers mypy, mesurés. |
| `d74353e` | Erreur de ma part | `main.py` était resté hors du commit `239906e` : de `239906e` à `d74353e`, le point d'entrée committé importait `src.core.game`, qui n'existait plus. Démarrage vérifié depuis l'état committé, puis chargement du niveau 0 et 3 s de jeu à 60 ticks/s. |

**Chantiers de suite :**

| Commit | Problème | Changement |
|---|---|---|
| `4e8122c` | Documentation dispersée | Les huit anciens audits de `notes/` sont supprimés ; ce rapport les remplace. |
| `b379053` | Bug de menu à la souris | La bande de note des menus suivait la ligne survolée : sur « Back » (sans note), le panneau changeait de taille et la sélection oscillait avec « Reset video settings ». Même défaut dans les listes « Picture fit » et « Frame limit ». Les pages déclarent toutes leurs notes (`MenuPage.notes()`), et la mise en page ne dépend plus de la ligne survolée. Testé par `test_menu_hover_is_still.py` (vrais évènements souris, 3 tailles). |
| `3b652b9` | B1.2 | Fenêtre, présentation et suivi des écrans sortis de `Game` dans `Screen` (`src/application/screen.py`) ; une seule cascade « nouvelle cible » au lieu de trois copies. |
| `f796100` | B6 | Les noms d'états interrogés hors des machines à états sont dans `src/states/state_names.py` ; plus aucune chaîne littérale comparée à un nom d'état hors de `src/states`. |
| `3c922f4` | B7 (partiel) | Une seule `collider_box()` remplace onze copies de `getattr(sprite, "hitbox", getattr(sprite, "rect", None))`. |
| `1bdbac9` | B5 / B8 (partiel) | `Entity.__init__` passe de 174 à 53 lignes, découpé en étapes nommées ; mêmes 61 attributs, valeurs identiques. |

**Reprise de la dette (même jour, seconde session) :**

| Commit | Problème | Changement |
|---|---|---|
| `8c96b95` | B5 | L'état de rendu sort d'`Entity` dans `RenderHints` (`src/core/rendering/render_hints.py`), porté par `entity.render_hints`. `SpriteGroups.entity_sprites` est déclaré `Group[Entity]` : le renderer, la poussière et la passe physique lisent les champs par leur nom. Les faux sprites des tests partent d'une forme unique, `tests/fakes.py:FighterSprite`. |
| `b1a15c3` | `@runtime_checkable` | Retiré des six protocoles (aucun `isinstance` en production). `test_source_conventions.py` interdit d'en remettre sous `src`. |
| `8e80ba1` | B7 (physique) | `move_entity` et `resolve_collisions` lisent `crushed`, `carry_backup`, `move_axis`, `spatial_hash` et le nom d'état par leur nom, déclarés dans les protocoles. `is_one_way()` devient le seul lecteur du drapeau, à côté de `collider_box()`. |
| `d704b65` | B7 (systèmes) | Poussière et sueur, séparation, faucheur de chutes, banc de debug et balayage des morts lisent un `Entity`. `Entity.dash` est déclaré (`None` sauf pour qui sait dasher). |
| `4b81bee` | B7 (états) | Saut des ennemis, locomotion et dash du joueur, dérive du knockback, `Entity.reset` et `is_invincible` lisent leurs propres champs déclarés. |
| `ab2c354` | B7 (HUD) | Les panneaux STATE et STATS prennent un `Player` : dix-sept `getattr` en moins, et les branches « sans combat » et « sans machine à états » disparaissent. |
| `ca878a0` | B7 (scène) | La scène de jeu appelle `level.spawn_system` par son nom. |

`getattr`/`hasattr` dans `src` : 362 au début de l'audit, 336 avant cette
reprise, **239** après. Deux tests ont été supprimés parce qu'ils vérifiaient un
cas que le type exclut (un joueur avec `combat=None`, un joueur avec
`state_machine=None`) ; un test a été ajouté.

**Fenêtrage (même jour, troisième passe).** Verdict : pas de rework, des
correctifs ciblés.

| Commit | Problème | Changement |
|---|---|---|
| `9e2f7e2` | Le plein écran dépendait de `Window.from_display_module`, déprécié | Repli par `set_mode` à la taille du bureau (mesuré sur deux écrans : aucun changement de mode) ; placement par `pygame.display`. Seule la taille minimale n'a pas de repli. |
| `d487154` | Repli sans la sonde SDL2 | Les fréquences sont conservées ; plusieurs écrans connus par leur seule taille ne servent plus à deviner l'écran de la fenêtre ; la sonde refuse un SDL qui n'est pas le 2. |
| `5b2b83d` | L'écran de la fenêtre était toujours déduit de sa position | `WINDOWDISPLAYCHANGED` est écouté et passe avant la position, qui reste le repli. |
| `935d853` | `Monitor.scale` inutilisé et faux (DPI physique, pas l'échelle du bureau) | Supprimé avec sa lecture DPI. |
| `1f73ab9` | Le niveau continuait fenêtre en arrière-plan | Perte de focus ou minimisation ouvre la pause, hors mode debug et hors fenêtre en cours de reconstruction. |
| `30bedb9` | Rebuild raté mal restauré ; `SDL_GetDesktopDisplayMode` lié comme renvoyant un pointeur | La fenêtre précédente est redemandée ; le statut entier est lu. |

Essai réel (pilote `x11`, deux écrans, réglages temporaires) : ouverture,
plein écran avec et sans la poignée `Window`, retour en fenêtre, pause à la
perte de focus. **Non essayé à la main :** glisser la fenêtre d'un écran à
l'autre (l'évènement `WINDOWDISPLAYCHANGED` n'a pas pu être provoqué par
script), débrancher un écran.

**Écran mémorisé (décision du propriétaire, même jour).** Le commit `9966093`
(2026-10-17) avait retiré l'écran choisi et la mémoire de position, pour
qu'un `settings.json` voyageur ne puisse pas faire planter la première frame.
Une partie revient, sous une forme qui garde cette garantie : `window.screen`
est le **nom** de l'écran où la fenêtre a été fermée. Au lancement il
correspond à un écran présent, ou à rien, et la fenêtre s'ouvre alors sur le
principal. Essai réel : ouverture sur le 24 pouces demandé ; nom inconnu ou
vide, ouverture sur le principal.

Toujours absents, volontairement : la position mémorisée, l'état maximisé
(non détectable ici : maximiser n'envoie pas `WINDOWMAXIMIZED`) et une ligne
de choix d'écran dans le menu Vidéo.

**Effet sur l'architecture**, mesuré par le graphe d'imports :

- `core` n'importe plus rien de `application` ni de `ui`. Il importait
  `application` depuis 4 modules et `ui` depuis 1.
- Les cycles d'import à l'exécution passent de 2 à 1. Celui qui reste est la
  navigation entre scènes, normale et cassée par un import local.
- `test_layer_boundaries.py` n'a plus aucune exception : la règle
  « `core` n'importe ni `application` ni `ui` » vaut pour tous les fichiers.

**Comportement de jeu :** un seul changement, la correction de B0 (`93d29e4`).
Tout le reste est de la structure.

---

## E. Performances

Profilage avec cProfile d'un niveau synthétique : 120×30 tuiles, un joueur
qui court, de 0 à 48 ennemis. Cible de rendu 1920×1080. Les sprites sont des
surfaces de substitution, faute des fichiers d'origine.

| Ennemis | Tick + dessin | Part du budget à 60 Hz |
|---|---|---|
| 0 | 1,1 ms | 7 % |
| 12 | 2,5 ms | 15 % |
| 48 | 4,9 à 5,8 ms (bruit entre les lancers) | 30 à 35 % |

- **Mesuré :** le coût croît à peu près linéairement avec le nombre
  d'entités, et il n'y a aucun goulot quadratique (le spatial hash et la
  grille d'entités font leur travail). Les postes principaux sont `fill` et
  `blit` (rendu), puis `resolve_collisions` et `get_nearby`.
- **Mesuré :** `isinstance(entity, WallJumpLock)` (B0) coûte 0,18 ms par tick
  avec 12 ennemis, soit 7 % de la frame, pour une réponse toujours fausse. Sa
  correction réglera aussi ce coût.
- **Mesuré :** environ 1 360 `getattr` par tick, soit 0,3 ms. C'est réel, mais
  le motif à corriger est la lisibilité (B7), pas la vitesse.
- **Avant / après :** les refactorisations de D n'ont pas d'effet mesurable
  (même plage de 4,9 à 5,8 ms à 48 ennemis sur trois lancers de chaque côté).
  C'était l'objectif : ce sont des changements de structure.
- **Pas d'optimisation appliquée.** Rien ne le justifie : le jeu tient
  largement dans son budget, et les gains disponibles sont marginaux à côté du
  risque de toucher la boucle sans les sprites réels pour vérifier.

---

## F. Validation

| Vérification | Résultat |
|---|---|
| `pytest` complet, **avec les assets** (revenus sur le poste en cours de session) | **3 396 réussis, 0 échec**, 1 ignoré. |
| Couverture (pytest-cov) | 94 % des instructions, 86 % des branches. |
| `mypy src main.py tools` | Aucune erreur sur 190 fichiers. |
| `ruff check` / `ruff format --check` | Propres pour le code. `ruff format --check` signale `notes/design_matrice_niveaux.md`, qui l'était déjà avant. |
| Captures de référence des menus | Identiques au pixel. |

**Non vérifié** (demande un écran et une manette) :

- lancer le jeu, charger une carte Tiled, jouer un niveau ;
- `uv run python main.py --debug` : l'overlay de debug ;
- **sauter contre un mur et essayer de revenir tout de suite vers lui** :
  depuis la correction de B0, le contrôle est réduit pendant 0,18 s
  (`wall_jump_lock_duration`, réglable dans `data/gameplay/player.json`) ;
- reconstruire le paquet PyInstaller (`knightrock.spec`), qui ne référence pas
  les modules déplacés mais n'a pas été construit ici.

---

## G. État final et dette restante

**État général :** la codebase était déjà au-dessus de la moyenne : boucle à
pas fixe correcte, systèmes ordonnés et testables, adaptateur Tiled propre,
ressources en cache, outillage strict. Les défauts réels étaient localisés :
la direction des dépendances, un module de configuration fourre-tout, du code
mort, et un usage du typage dynamique qui a fini par cacher un bug de gameplay.

**Dette restante, par priorité :**

1. **B7, overlay de debug — Faible.** `world_overlay_geo.py` (42),
   `world_overlay_cards.py` (36) et leurs voisins portent à eux seuls plus du
   tiers des 239 lectures dynamiques restantes. L'overlay reçoit *tous* les
   sprites du niveau (tuiles, hazards, projectiles, entités) et ses tests
   reposent sur des stand-ins `SimpleNamespace`. La correction propre est un
   aiguillage `isinstance(sprite, Entity)` à l'entrée, suivi d'accès typés ;
   elle demande de réécrire ces tests. Un défaut y est sans effet sur le jeu.
2. **B7, combat et effets — choix assumé, pas une dette à solder d'office.**
   `contact_system.py`, `contact_damage.py`, `hit_resolver.py` et
   `fx/spawners.py` gardent leurs `getattr`. Le code y documente le duck-typing
   comme voulu (hazards et projectiles n'ont ni `id` ni `faction` ; un spawner
   rend une liste vide pour un objet sans `hitbox`) et des tests le
   verrouillent. Une tentative de lecture directe des membres déclarés par
   `Combatant` a cassé 14 tests à base de stubs et a été annulée. À reprendre
   seulement si le propriétaire décide de changer ce contrat.
3. **B7, évènements pygame — à laisser.** `event_router.py` (21),
   `controls_scene.py` et `game.py` lisent des attributs d'évènements pygame,
   qui varient selon le type d'évènement : c'est le bon usage de `getattr`.
4. **B7, colliders — Faible.** Le décor reste un mélange de tuiles (`rect`
   seul) et de plateformes (`hitbox`, `old_hitbox`, `one_way`), lu par
   `collider_box()` et `is_one_way()`. Donner un `hitbox` aux tuiles
   supprimerait ces deux lectures, mais l'overlay et la séparation se servent
   aujourd'hui de la présence de `hitbox` pour reconnaître un fighter.
5. **Contenu — décision de design.** L'objet `water` (un rectangle au bas des
   niveaux 0, 1, 3, 5, 6 et `omni`) n'a pas de fabrique : il est ignoré au chargement,
   avec un avertissement dans les logs. Il faut décider ce que l'eau fait
   (décor, zone mortelle, nage) avant d'écrire quoi que ce soit. Le manifeste
   déclare désormais tous les niveaux ; ce point de la première version du
   rapport est clos.

**Pour garder ce niveau dans le temps :**

- Garder mypy bloquant. Il a attrapé dès cet audit une erreur que la suite de
  tests laissait passer.
- Interdire `@runtime_checkable` sur les protocoles du code de jeu (ou le
  limiter aux tests). Un `isinstance` sur protocole est lent, et il est faux
  avec `__getattr__` : c'est B0.
- Ajouter à `test_layer_boundaries.py` toute nouvelle règle de direction dès
  qu'elle est décidée, plutôt que de la documenter.
- Pour chaque `getattr(x, "nom", défaut)`, se demander si le type est connu.
  S'il l'est, écrire l'accès direct.
