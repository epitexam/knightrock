# Architecture actuelle — Knightrock

Audit du 2026-11-12, branche `fix/remediation`, commit `d718a8c`.
Python 3.14, pygame-ce 2.5.7, PyTMX.

Ce document décrit le jeu **tel qu'il est**, avant toute recommandation. Les
jugements sont dans `comprehensive-audit.md`.

> **Note (après l'étape B).** Ce document décrit l'état de départ (`d718a8c`).
> Ce qui a changé depuis (entrées lues par le niveau, `FeedbackSystem`, source
> unique des combattants, états typés…) est dans `final-report.md`.

## 0. Méthode et état de départ

- Lecture du code de production, en suivant les chemins d'exécution d'un module
  à l'autre (boucle, scènes, niveau, systèmes, entités, combat, états, physique,
  animation, rendu, entrées, données). Les modules d'UI de menu et de l'overlay
  de debug ont été lus en surface (structure, dépendances, taille), pas ligne à
  ligne.
- Mesures faites par script : graphe d'imports, proportion code/prose, appels
  dynamiques (`getattr`/`hasattr`).
- Quatre comportements suspects ont été **reproduits par script** avant d'être
  consignés (voir `comprehensive-audit.md`, constats C1 à C4). Les scripts sont
  hors du dépôt et ne modifient rien.

| Mesure | Valeur |
|---|---|
| Modules dans `src/` | 187 |
| Lignes dans `src/` | 40 335, dont 22 668 de code (56 %), 9 901 de docstrings (25 %), 1 852 de commentaires (5 %) |
| Fichiers de test | 161, environ 47 400 lignes |
| `pytest` | **3 408 réussis**, 1 ignoré, en 26 s (headless) |
| `mypy src main.py tools` | aucune erreur (190 fichiers) |
| `ruff check` | propre |
| Cycles d'import au niveau module (imports de tête) | aucun |

## 1. Structure physique

Tailles en lignes (code et prose compris).

```
main.py                      point d'entrée : logs, --debug, Game().run()
data/gameplay/*.json         attaques, ennemis, joueur, niveaux (versionnés)
assets/                      graphismes, sons, cartes .tmx, polices
src/
├── application/   4 683     Game (boucle), Screen (fenêtre), SceneManager, scènes,
│                            réglages utilisateur, sauvegarde
├── core/
│   ├── settings.py  850     constantes de simulation et de rendu (classes-espaces de noms)
│   ├── events.py            bus d'événements typé et synchrone
│   ├── audio.py             AudioBus (sons d'interface uniquement)
│   ├── asset_library.py     chargement paresseux et cache des images
│   ├── sprites.py, hazards.py, sprite_groups.py   objets du monde et groupes
│   ├── display/   1 522     fenêtre, écrans, letterbox, présentation
│   ├── input/     1 533     routeur d'événements, bindings, providers, InputManager
│   ├── level/     4 274     Level (façade), WorldBuilder, LevelData (TMX)
│   │   └── systems/         15 systèmes du tick + GameplayLoop
│   ├── rendering/ 1 545     Camera, Renderer, index des tuiles, RenderHints
│   ├── fx/        4 175     particules décoratives (poussière, arcs, sueur…)
│   ├── animation/           Animator
│   └── rollback/            instantanés et retour arrière (désactivé en jeu)
├── combat/        3 880     frame data, machine d'attaque, hitboxes, résolution
├── entities/      4 282     Entity, Player, Enemy, composants, contrôleurs
├── states/        1 871     StateMachine, états joueur/ennemi/réactions
├── physics/       1 525     mouvement, collisions, gravité, spatial hash
├── data/          1 243     lecteurs JSON stricts
└── ui/            7 398     HUD, menus, overlay de debug (≈ 4 400 lignes)
tests/             unit/, headless/, golden/ (captures de référence), benchmarks/
tools/             outils manuels (inventaire manette, recette d'affichage)
```

## 2. Architecture logique

### 2.1 Les couches réelles

Le dossier `core/` regroupe deux choses distinctes :

1. une **fondation** sans logique de jeu : `settings`, `events`, `colors`,
   `paths`, `asset_library`, `display/`, `input/`, `animation/` ;
2. le **monde du jeu** : `level/` (et ses systèmes), `rendering/`, `fx/`,
   `rollback/`, `sprites.py`, `hazards.py`.

La seconde partie dépend de `entities`, `combat` et `states`. En pratique, les
couches sont donc :

```
application  (Game, Screen, SceneManager, scènes)
     │
     ├──► ui  (HUD, menus, overlay de debug)
     │
     └──► core.level / core.rendering / core.fx     « le monde »
              │
              ├──► entities ──► combat ──► states
              │        └──────► physics
              │
              └──► fondation : core.settings, core.events, core.input,
                   core.display, core.animation, core.asset_library
```

Graphe mesuré entre paquets (imports à l'exécution, `TYPE_CHECKING` exclu) :

```
application    -> combat, core, core.display, core.input, core.level, data, ui
ui             -> combat, core, core.display, core.input, core.level, core.rendering, entities, states
core.level     -> combat, core, core.fx, core.input, core.rendering, core.rollback, data, entities, physics, states
core.rendering -> core, core.display, core.level, states
core.rollback  -> core, core.input, entities
entities       -> combat, core, core.animation, core.input, core.rendering, data, physics, states
combat         -> core, data, states
states         -> combat, core, physics
physics        -> core, states
data           -> combat, core, core.level, entities
core (racine)  -> combat, physics, core.level        (sprites.py, hazards.py)
```

`test_layer_boundaries.py` garantit que `core` n'importe ni `application` ni
`ui`. Il n'y a aucun cycle entre modules au chargement ; les quelques imports
réciproques (`combat` ↔ `states`, `data` ↔ `core.level`) passent par des
imports locaux ou `TYPE_CHECKING`.

### 2.2 Responsabilités des classes principales

| Classe | Fichier | Rôle réel |
|---|---|---|
| `Game` | `application/game.py` | Racine de composition (réglages, entrées, audio, bus, sauvegarde, scènes) et boucle à pas fixe. Délègue la fenêtre à `Screen`. |
| `Screen` | `application/screen.py` | Fenêtre, cible de rendu, présentation (letterbox), suivi des écrans. |
| `SceneManager` | `application/scene_manager.py` | Pile de scènes : seule la scène du haut est mise à jour, toute la pile visible est dessinée ; fondu de transition. |
| `GameplayScene` | `application/scenes/gameplay_scene.py` | Charge un `Level`, lit les entrées à chaque tick, gère pause, mort, sortie, touches de debug. |
| `Level` | `core/level/level.py` | Façade : construit le monde (groupes, caméra, spatial hash, systèmes), délègue le tick à `GameplayLoop`, dessine. |
| `GameplayLoop` | `core/level/systems/gameplay_loop.py` | **Ordre** des systèmes d'un tick ; hit-stop ; déclenchement des FX de garde et des secousses. |
| `WorldBuilder` | `core/level/world_builder.py` | Construit tuiles, plateformes, pièges, ennemis et joueur depuis `LevelData`, via deux registres (couches, objets). |
| `Entity` | `entities/entity.py` | Base de tout combattant : boîtes (pushbox, zones de hurtbox, balayage), mouvement (par `MovementComponent`), vie (`Vitals`), réactions (`ReactionComponent`), combat (`CombatComponent`), machine à états, animateur ; méthode `update` en patron (hooks). |
| `Player` | `entities/player.py` | Entité jouable : contrôleurs saut/garde/dash, posture accroupie, `PlayerInputHandler`, garde et parade dans `receive_damage`. |
| `Enemy` | `entities/enemies/enemy.py` | **Une seule classe** configurée par `EnemyConfig` ; machine à états d'IA commune ; aucun sous-type. |
| `CombatComponent` | `combat/combat_component.py` | Par entité : `AttackStateMachine`, `HitboxManager`, `ComboTracker`, `ChargeHandler`, état « blessé », cooldowns ; seul point où une attaque peut être refusée (`Refusal`). |
| `AttackStateMachine` | `combat/attack_state.py` | Phases startup / active / recovery comptées en frames à 60 Hz. |
| `HitboxManager` | `combat/hitbox_manager.py` | Positionne les formes offensives (AABB, capsules…) image par image depuis les keyframes, garde l'origine du balayage. |
| `CombatSystem` | `core/level/systems/combat_system.py` | Attaquants prêts, priorité et clash entre coups simultanés, minuteur global de hit-stop. |
| `ContactSystem` | `core/level/systems/contact_system.py` | Pipeline commun aux quatre producteurs (mêlée, projectiles, pièges, contact) : broadphase, narrowphase balayée par zone, résolution. |
| `HitResolver` | `combat/hit_resolver.py` | Formule de dégâts et effets d'un coup (jonglage, OTG, finisher, armure, stagger). |
| `StateMachine` | `states/state_machine.py` | Machine à états générique : états-classes, interruptions à priorité, tags, tampon d'entrées. |
| `Renderer` / `Camera` | `core/rendering/` | Rendu du monde avec culling, cache de mises à l'échelle, images rémanentes ; caméra à zone morte, secousse, interpolation. |
| `EventBus` | `core/events.py` | Faits pour l'application (niveau commencé, mort, niveau fini, retour d'interface), isolés par abonné. |

## 3. Cycle de vie d'exécution

### 3.1 Démarrage

1. `main.py` configure les logs (`dictConfig`), active le debug si `--debug`,
   puis `Game().run()`.
2. `Game.__init__` : variables SDL, `Screen`, `SettingsStore.load()`,
   `EventRouter` + `LocalInputProvider` + `InputManager`,
   `load_gameplay_data()` (JSON stricts), `AudioBus`, `LevelManager`,
   `SaveGame.load`, `EventBus` (abonnements audio et progression),
   `SceneManager`.
3. `Game._initialize` (dans `run`) : `pygame.init()`, manettes, mixer (jamais
   fatal), fenêtre et présentation, `Clock`, premier `tick(0)` pour ne pas
   facturer le chargement, puis `MenuScene`.

Les images sont chargées **à la demande** (`AssetLibrary`), après création de
l'affichage, ce qui permet `convert_alpha`.

### 3.2 Une frame (`Game.step`)

```
frame_delta = clock.tick(...)                     pacing : limite de FPS ou vsync
accumulator += min(frame_delta, 0.1 s)
si la fenêtre a changé de taille : recadrer, redessiner la pile
_handle_events()        QUIT, Alt+Entrée, fenêtre, manettes ; le reste va à la scène du haut
_poll_displays()        écran débranché / ajouté
poll_held_repeats()     répétition des sticks dans les menus
flush_settings()        écriture groupée des réglages
_run_ticks()            0 à 6 ticks de 1/60 s ; au-delà, le surplus est abandonné
scene_manager.draw()    toute la pile visible, dans la cible de rendu
screen.present()        mise à l'échelle letterbox et flip
```

- **Pas fixe** : 60 ticks/s (`Simulation.TICK_RATE`), accumulateur borné à
  0,1 s, au plus 6 ticks par frame.
- **Rendu découplé** : `render_alpha()` (fraction du tick suivant) est passé au
  rendu ; il vaut 1 quand une scène fige le monde, pour éviter le tremblement.
- **Pause** : `PauseScene` est empilée ; seule la scène du haut reçoit `update`,
  donc le niveau ne tique plus. Perte de focus → pause (hors debug).

### 3.3 Un tick de jeu

`GameplayScene.update(dt)` lit d'abord les entrées (`input_manager.update()`),
puis `Level.update(dt)` → `GameplayLoop.update(...)`. Ordre exact :

| # | Étape | Code |
|---|---|---|
| 1 | Banc de debug (spawns, attaques de démonstration) — actif seulement avec `DEBUG` | `SpawnSystem.process` |
| 2 | Hit-stop : si un gel est en cours, le delta simulé devient 0 | `begin_tick` |
| — | *Si gel : seules les étapes 15 à 17 tournent.* | |
| 3 | Capture des origines de balayage (hurtboxes, hitboxes) | `capture_sweep_origin`, `capture_attack_origin` |
| 4 | Plateformes mobiles | `PlatformSystem` |
| 5 | Pièges (animation, origine du balayage) | `HazardSystem` |
| 6 | Transport par plateforme, puis `Entity.update` de chaque entité, puis FX de mouvement | `PhysicsSystem` |
| 7 | Grille d'entités, séparation des corps, attaques de mêlée | `process_combat_and_separation` |
| 8 | Secousse si impact lourd | `camera.add_trauma` |
| 9 | Projectiles | `ProjectileSystem` |
| 10 | FX de garde, parade, bris, étourdissement | `_emit_guard_fx` |
| 11 | Dégâts de contact entre corps | `ContactDamageSystem` |
| 12 | Dégâts des pièges | `HazardDamageSystem` |
| 13 | Trace de combat (debug) puis retrait des morts (sauf le joueur) | `remove_dead_entities` |
| 14 | Réapparition du joueur, mort par chute | `PlayerRespawnSystem` |
| 15 | Sortie atteinte | `ProgressionSystem` |
| 16 | Caméra (delta brut, même pendant le gel) | `CameraSystem` |
| 17 | Événements du bus, compteur de tick, instantané de rollback (désactivé) | `NotificationSystem`, `TickSystem` |

À l'intérieur de l'étape 6, `Entity.update` suit un patron fixe :

```
old_hitbox ← hitbox
vitals.tick_timers, render_hints.tick
_pre_update            Player : lecture des entrées, contrôleurs ; Enemy : se tourner vers le joueur
state_machine.update   interruptions à priorité, puis l'état courant (qui applique l'accélération)
combat.update          blessure, cooldowns, combo, charge, avance d'une frame d'attaque
move()                 axe X par sous-pas, gravité, axe Y par sous-pas, collage au sol
_tick_juggle           jonglage et protection OTG
combat.sync_attack_box hitboxes recalées sur la position finale
_post_update
_update_animator       choix du clip, avance, image mise à l'échelle et retournée
```

### 3.4 Transitions et arrêt

- Sortie atteinte → `GameplayScene` remplace la pile par le niveau suivant, ou
  `VictoryScene`. `MAX_DEATHS` morts → `GameOverScene` empilée.
- `LevelCompleted` → `Game` déverrouille et écrit la sauvegarde.
- Arrêt : `run()` mémorise taille et écran de la fenêtre, écrit les réglages,
  `pygame.quit()` dans un `finally`. Une exception non gérée est journalisée
  avec sa pile et affichée sur un écran d'erreur.

## 4. Flux de gameplay

### 4.1 Déplacement du joueur

```
pygame.key.get_pressed / manette
   └─ LocalInputProvider.poll()        une fois par tick ; un appui plus court
                                        qu'une frame est verrouillé par note_event
       └─ InputManager                  état courant + précédent → held / just_pressed
           └─ PlayerInputHandler        move_axis, *_held, tampon de saut,
                                        jump cut, demande de dash, demi-tour
               └─ états de locomotion   apply_horizontal_movement :
                                        accélération exponentielle, freinage
                                        dédié au demi-tour, verrou après saut mural
                   └─ move_entity       sous-pas de 16 px max (8 par axe),
                                        gravité (montée / chute / glissade / jonglage),
                                        résolution AABB par axe, marche, correction
                                        de coin, plateformes à sens unique,
                                        collage au sol, détection d'écrasement
                       └─ update_contact_state   on_surface {floor, left, right}
                           └─ hooks _on_floor_contact / _on_wall_contact
```

Le saut est résolu par `resolve_jump` (coyote time, tampon, saut mural, sauts
en l'air). La géométrie physique (`hitbox`, appelée pushbox) est distincte de
l'image : `rect` est dérivé de la pushbox par `sync_rects`.

### 4.2 Cycle de vie d'une attaque

```
Appui (ATTACK_1..4, SPECIAL)
 └─ PlayerInputHandler._start
     ├─ Player.may_attack_now()                 seul garde-fou propre au dash
     ├─ move_for_button(bouton, stance)         Stance : WALL > AIR > CROUCH > GROUND
     ├─ ATTACK_2 → start_charge (état CHARGE), relâché → release_charge
     └─ CombatComponent.start_attack(move)      refus typé : BUSY, CHARGING, UNKNOWN,
                                                STANCE, COOLDOWN, NO_CANCEL
         ├─ refus « réessayable » → tampon (StateMachine.buffer_input)
         └─ AttackStateMachine.start            STARTUP, frame 0
 └─ StateMachine : interruption ATTACK (combat.is_attacking)
     └─ PlayerAttackState.enter                 élan au sol ou impulsion verticale en l'air
 └─ chaque tick : AttackStateMachine.update     une frame par tick (60 Hz) :
                                                STARTUP → ACTIVE → RECOVERY → phase suivante
     └─ HitboxManager                           formes interpolées par keyframes,
                                                ancrées (hanche, torse, centre), miroir
 └─ GameplayLoop étape 7 : CombatSystem.process_attacks
     ├─ attaquants prêts (phase ACTIVE, boîtes vivantes)
     ├─ coups simultanés : priorité ; égalité + « clash » → les deux annulés, hit-stop
     └─ ContactSystem.resolve
         ├─ broadphase  EntityGrid (indexée à partir de 8 entités) ou liste complète
         ├─ filtre      vivant, pas le propriétaire, faction opposée, pas déjà touché
         ├─ narrowphase première zone de hurtbox vulnérable touchée par le volume balayé
         └─ HitResolver.resolve
             ├─ dégâts = base × charge × zone × type × jonglage (× étourdi)
             ├─ invincibilité (tag d'état), OTG, finisher sous 20 %
             └─ cible.receive_damage(...)
                 ├─ Player : parade par dash, garde (posture, chip, parade, bris)
                 └─ Entity : Vitals, flash, knockback, i-frames,
                            knockback lourd → état KNOCKBACK
             └─ effets : bris d'armure, gravité de jonglage, combo, recharge de dash,
                         combat.on_hit (état HURT), stagger
         ├─ record_contact → targets_hit       un seul coup par cible et par phase
         └─ hit-stop global = base + dégâts + knockback (parade : 0,14 s min)
 └─ fin de la dernière phase → IDLE → PlayerAttackState consomme le tampon
    (enchaînement) ou revient à la locomotion
```

Les phases (startup, active, recovery) sont **explicites et comptées en
frames**, définies dans `data/gameplay/attacks.json` et validées au chargement
(`attack_loading.validate_attacks`). Les annulations se déclarent par phase
(`cancel_into`).

### 4.3 IA des ennemis

- **Création** : `WorldBuilder` (objets Tiled nommés comme un type d'ennemi) ou
  `SpawnSystem` (debug) → `create_enemy(nom)` → `Enemy(config)`.
- **États** : `IDLE → PATROL ↔ CHASE → ATTACK → IDLE`, plus `TURN`, `LEDGE`,
  `CHARGE` et les réactions `HURT`, `KNOCKBACK`, `STAGGER`, `DIZZY`.
- **Perception** : distance au joueur (`vision_range`, `attack_range`), sans
  ligne de vue.
- **Déplacement** : sonde de bord (`is_at_ledge`), saut vers un mur ou vers le
  joueur, saut de trou calculé à partir de la physique (`jump_range`), saut
  risqué, descente.
- **Attaque** : une seule attaque par type (`attack_name`), lancée à l'entrée
  de `EnemyAttackState`.
- **Dégâts et mort** : mêmes chemins que le joueur ; étourdissement après N
  parades parfaites (déclenché depuis `ContactSystem`). Les morts sont retirées
  par `GameplayLoop.remove_dead_entities` ; un ennemi tombé sous la limite meurt
  (`PlayerRespawnSystem`).
- **Sans IA** (`has_ai=False`, le mannequin) : friction passive seulement.

### 4.4 Animation

- `Animator` (un par entité) : clips = dossiers de PNG numérotés, durée de frame
  fixe par clip, boucle ou non.
- **Sélection** : `Entity._animation_name()` traduit l'état courant en clip
  (`Player` : table état → clip, clip déclaré par l'attaque ; `Enemy` : nom
  d'état = nom de clip s'il existe).
- **Cadence** : avancée dans le tick de simulation, indépendante de la frame data
  de l'attaque.
- **Affichage** : l'image est mise à l'échelle à la taille de `rect` et
  retournée selon `facing_right`, avec un cache par entité
  (clip, frame, sens, taille).
- Les états sans art (garde, charge, stagger) gardent le clip précédent ; `dash`
  et `crouch` retombent sur `run` et `idle`.

### 4.5 Rendu

`Level.draw` → `Renderer.draw` : `camera.begin_frame(alpha)` (seule la caméra
est interpolée), remplissage, collecte des sprites visibles (index par blocs
pour les tuiles statiques, culling pour le reste), mise à l'échelle mise en
cache, afterimages du dash, flashs de coup, puis barres de vie, panneaux de
debug et HUD par `UIManager`. Tout est redessiné à chaque frame, dans une cible
de taille fixe, puis mis à l'échelle par `Presentation`.

## 5. Dépendances, état partagé et communication

### 5.1 État global

| État | Où | Remarque |
|---|---|---|
| `_SHARED_LIBRARY` | `core/asset_library.py` | Cache d'images unique, vidé quand le format d'affichage change. |
| Cache de frames FX | `core/fx` | Vidé avec le précédent. |
| `_ENTITY_ID_SEQUENCE` | `entities/entity.py` | Compteur d'identifiants jamais remis à zéro entre niveaux. |
| `_compact_panels`, `_language` | `ui/panel_renderer.py`, `ui/text.py` | Préférences de l'overlay de debug. |
| `DEBUG` | variable d'environnement, lue à chaque appel de `Debug.is_enabled()` | 12 points de lecture. |
| Classes de `settings.py` | constantes | Lues partout, jamais modifiées en jeu. |

### 5.2 État mutable partagé

`SpriteGroups` est le registre du monde, partagé par `Level`, les systèmes, le
`WorldBuilder` et le `Renderer`. Une entité est ajoutée « à la main » à
plusieurs groupes (`all_sprites`, `entity_sprites`, `combat_sprites`), à trois
endroits.

### 5.3 Communication entre systèmes

- **Appels directs**, dans l'ordre fixé par `GameplayLoop`. C'est le mode
  principal.
- **Listes par tick** : `CombatSystem.guard_events`, `ProjectileSystem.guard_events`,
  `ContactSystem.zone_contacts`, `CombatSystem.impact`, vidées par
  `GameplayLoop`.
- **Drapeaux posés sur les entités** : `RenderHints` (flash, impact
  d'atterrissage, virage), `Player.dash_started_this_frame`.
- **`EventBus`** : uniquement simulation → application (début, mort, fin de
  niveau) et interface → audio. Les abonnés ne doivent pas modifier la
  simulation.
- **Protocoles** (`Combatant`, `CombatPort`, `MovableEntity`…) : décrivent ce
  que chaque fonction lit. Aucun n'est vérifié par `isinstance` (interdit par
  `test_source_conventions.py`).

## 6. Forces existantes

Constat avant tout jugement critique : cette base est **au-dessus de la
moyenne** pour un jeu Pygame de cette taille.

1. **Boucle à pas fixe correcte** : accumulateur borné, surplus abandonné (pas
   de spirale de la mort), rendu découplé, pause sans dérive.
2. **Ordre du tick explicite** dans un seul fichier (`GameplayLoop`), avec des
   systèmes injectés et testables un par un.
3. **Combat modélisé comme un jeu de combat** : frame data à 60 Hz, phases
   explicites, annulations déclarées, priorité et clash, coups balayés (pas de
   traversée à grande vitesse), hurtboxes par zone, refus typé
   (`Refusal`) depuis un point unique.
4. **Données de jeu externes et validées** : attaques, ennemis, joueur et
   niveaux en JSON, erreurs de chargement localisées.
5. **Ennemis pilotés par la configuration** : une classe, aucun sous-type
   inutile.
6. **Physique de plateforme soignée** : sous-pas, marche, correction de coin,
   coyote time, tampon de saut, plateformes à sens unique et mobiles,
   écrasement.
7. **Adaptateur Tiled propre** : le gameplay ne voit jamais PyTMX ; registres de
   fabriques pour les couches et les objets.
8. **Ressources en cache, rien n'est chargé dans la boucle** (sauf au premier
   usage de chaque clip, voir l'audit).
9. **Outillage strict** : mypy strict bloquant, ruff avec complexité, 3 408
   tests, captures de référence au pixel, test de couches, CI qui construit
   l'exécutable.
