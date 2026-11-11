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

**Effet sur l'architecture**, mesuré par le graphe d'imports :

- `core` n'importe plus rien de `application` ni de `ui`. Il importait
  `application` depuis 4 modules et `ui` depuis 1.
- Les cycles d'import à l'exécution passent de 2 à 1. Celui qui reste est la
  navigation entre scènes, normale et cassée par un import local.
- `test_layer_boundaries.py` n'a plus aucune exception : la règle
  « `core` n'importe ni `application` ni `ui` » vaut pour tous les fichiers.

**Aucun comportement de jeu n'a changé.** Seule la correction de B0 en
changerait un ; elle attend une décision.

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
| `pytest` (hors `test_levels_manifest`, qui exige les `.tmx`) | **3 244 réussis**, 100 échecs et 16 erreurs, identiques à la base, tous dus aux assets absents. Aucun test qui passait n'échoue. |
| `mypy src main.py tools` | Aucune erreur sur 187 fichiers (il y en avait 3 au début de l'audit). |
| `ruff check` / `ruff format --check` | Propres. |
| Captures de référence des menus | Identiques au pixel. |
| `import main` | OK. |
| Tests ajoutés ou modifiés | Le test de couches est resserré (plus d'exemption, plus d'import de `application` toléré). Les tests de persistance des contrôles passent par `SettingsStore`. Deux doubles de test complétés. |

**Non vérifié sur ce poste**, à faire sur une machine qui a les assets :

- lancer `uv run pytest` complet : les 116 tests qui dépendent des sprites et
  des cartes ;
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

1. **B0 — corrigé.** Reste à ressentir en jeu (voir F).
2. **B7 — Moyen.** `ControllerView` (`__getattr__`/`__setattr__` sur `Player`)
   est la cause racine de B0 : ses attributs sont invisibles pour mypy et pour
   `inspect`. Remplacer la table `CONTROLLER_VIEWS` par des propriétés
   générées sur la classe (ou un accès explicite `player.jump.x`) rendrait les
   attributs réels. Ensuite, un `Protocol` `Collider` pour le décor dans
   `physics/collisions.py`.
3. **B1.2 — Moyen.** Extraire l'affichage de `Game` dans un objet dédié
   (`stage`, `presentation`, `window`, plein écran, suivi des écrans). `Game`
   garderait `game.presentation` et `game.stage` comme attributs, donc les
   87 références des tests resteraient valides.
4. **B5 — Moyen.** Sortir l'état de rendu d'`Entity` (`RenderHints`) et
   l'état de virage (`TurnTuning`). À faire avec la suite complète.
5. **B6 — Moyen.** Prédicats d'état (`is_dashing`, `in_knockback`) au lieu
   de comparer `current_state_name` à des chaînes.
6. **B8 — Faible.** `Entity.__init__` (174 lignes) et `Level.__init__`
   (110 lignes) suivront naturellement B5.

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
