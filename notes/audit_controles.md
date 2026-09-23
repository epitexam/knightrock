# Audit Contrôles — Socle input clavier / manette / souris (prérequis `audit_ui.md`)

- **Commit audité** : `a6d20f821ccb1c4177ee0e3a56d4ebf8b423228a` (branche `hitbox/rework`, HEAD, 2026-09-22) — re-vérifié intégralement contre HEAD le même jour.
- **Périmètre** : `src/core/input/` (`input_bindings`, `input_provider`, `input_manager`, `input_state`), `src/core/game.py` (`_handle_events`, hot-plug manette), consommation gameplay `src/entities/player_input.py`, tests input associés. Seuils : `src/core/settings.py` (`Input`).
- **Hors périmètre** : touches de debug hors bindings (`spawn_system.py` K_g/K_p/…, `gameplay_scene.py` F1-F7, conflit K_g combo/spawn) — noté en fin de document, non planifié ici ; UI des menus et écrans (`audit_ui.md`) ; simulation (`src/core/level/`, `src/combat/`, `src/entities/` hors `player_input`).
- **Méthode** : lecture ligne à ligne des 4 modules input + `_handle_events` + `player_input` ; greps exhaustifs (souris, actions UI, seuils, remapping, stubs de test) ; croisement avec le snapshot `.coverage` et les tests headless/unit input.
- **Verdict** : le socle **gameplay tient la route** — séparation bindings / provider / manager / edges déterministe, hot-plug manette géré, surface d'injection réseau (`set_provider`, `apply_remote_state`). Mais le système **n'est pas extensible en l'état** vers les besoins UI : zéro action de menu dans le vocabulaire, `InputState` fermé (10 actions booléennes et un axe), propriétés d'edges copiées-collées, **9 stubs de test divergents**, aucune souris dans le chemin commun des menus, seuils/deadzones incohérents, SOCD implicite (C-9), bindings sans contexte de map (C-10), réponse analogique sans seuil extérieur (C-11). Ce n'est pas une refonte : c'est **un vocabulaire d'actions et un routeur d'événements à ajouter en amont des lots UI** (C-Lot 0 avant UI lot 1), en privilégiant des patterns simples et adaptés au projet.
- **Lien** : ce document **précède** `notes/audit_ui.md` (les lots UI 1-2 dépendent de C-Lot 0a/0b). Le chantier rebinding (ex-UI-5) est **porté ici** ; l'écran Contrôles reste en UI.

---

## Sommaire

- [1. État des lieux](#1-état-des-lieux)
- [2. Constats](#2-constats) : C-1 à C-11
- [3. Architecture cible](#3-architecture-cible)
- [4a. Décisions figées](#4a-décisions-figées)
- [4b. Plan par lots](#4b-plan-par-lots) : C-Lot 0a, 0b, 0c
- [5. Règles](#5-règles)
- [6. Réception globale](#6-réception-globale)
- [7. Commandes de vérification et croisements](#7-commandes-de-vérification-et-croisements)

---

## 1. État des lieux

Statut : **verifié** = re-vérifié le 2026-09-22 sur `a6d20f8` ; **absent** = capacité non implémentée ; **partiel** = existant mais incomplet ou incohérent.

| Capacité attendue | État actuel | Preuve | Statut |
|---|---|---|---|
| Clavier : edges just pressed / released | Oui — `InputManager` double état prev/cur, 11 propriétés d'edges dédiées | `input_manager.py:62-158`, tests headless | verifié |
| Manette : hot-plug added/removed | Oui — `game.py:133-146` + `connect`/`disconnect`/`reassign` | `game.py:82,133-146`, `input_provider.py:52-82` | verifié (removed non testé) |
| Manette : axes, hat X, deadzone | Partiel — axe X + hat X ; deadzone **0.2** en dur puis **0.1** dans le manager (cumul) | `input_provider.py:156-191`, `settings.py:286` | partiel |
| Manette : hat Y et `down` | Absents — hat Y ignoré ; `down_held` clavier seul | `input_provider.py:104,166` | absent |
| SOCD clavier (gauche+droite simultanés) | Absent — `neutral` implicite via `droite - gauche`, policy non documentée, non testée | `input_provider.py:156` | absent |
| Combos clavier / manette | Oui — `special_attack` (détecté level dans le provider) | `input_bindings.py:66-76`, `input_provider.py:110-120` | verifié |
| Souris dans la stack input | Absente du chemin commun gameplay/menu — la souris existe uniquement dans les panneaux debug (`MOUSEBUTTON*`, `MOUSEMOTION`, `pygame.mouse.get_pos`) | `panel_renderer.py:151-175,468`, `gameplay_scene.py:42,157-176` | absent |
| Actions de menu (`ui_up` / `ui_confirm` / `ui_back`) | Absentes — bindings = gameplay seul | `input_bindings.py:31-76` | absent |
| Structure des bindings en maps de contexte | Absente — 5 dicts plats gameplay ; pas de regroupement `gameplay`/`menu` ni mapping manette standard documenté | `input_bindings.py:31-76` | absent |
| Routage événements multi-périphériques (menus) | Absent — les 3 scènes filtrent `KEYDOWN` à la source ; manette/souris jamais consommées en menu | `menu_scene.py:48`, `pause_scene.py:33`, `gameover_scene.py:34` | absent |
| API d'action générique | Absente — pas de `just_pressed("nom")` ; chaque action = propriété copiée | `input_manager.py:96-158` | absent |
| Persistance / rebind des bindings | Absente — promesse docstring, 0 `to_dict`/`from_dict`, 0 écriture disque | `input_bindings.py:5` | absent |
| Seuils centralisés (`settings.Input`) | Partiel — seulement `AXIS_DEADZONE` + buffer ; dash `0.5` et deadzone provider hors settings | `settings.py:283-287`, `input_provider.py:107,173` | partiel |
| Seuil extérieur analogique (`range_end`) | Absent — rescale vers 1.0 implicite ; un pad fatigué plafonne `move_axis` | `input_provider.py:188-191` | absent |
| Stubs de test input unifiés | Non — au moins **9** copies partielles divergentes | grep §7 | partiel |
| Tests `LocalInputProvider` | Faible — couverture snapshot **54 %** ; hat/combos/deadzone/connect non testés | snapshot `.coverage` | partiel |
| Abstraction réseau / provider swappable | Partiel — `InputProvider` est une classe conventionnelle avec `NotImplementedError`, pas une véritable ABC/Protocol ; `NullInputProvider`, `set_provider`, `apply_remote_state` existent | `input_provider.py:16-29`, `input_manager.py:38-60` | partiel (API inexploitée dans `src/`) |
| `JOYDEVICEREMOVED` testé | Non — chemin hors couverture | `game.py:141-146` | absent |

Base de tests existante : `tests/headless/test_input_manager.py` (5 tests : edges, deadzone manager, axe, remote, indépendance attaques), `tests/unit/test_runtime_and_paths.py:102-118` (hot-plug added), `tests/unit/test_player_controllers.py` (~20 tests timers), `tests/unit/test_player.py:88-147` (consommation via mock).

---

## 2. Constats

Format de chaque constat : **Constat** (fait + preuve), **Impact**, **Cible**, **Réception** (headless, rejouable).

### Axe A — Extensibilité du vocabulaire

**C-1 — Deux canaux d'entrée parallèles, jamais unifiés (priorité haute, effort M)**
- *Constat* : les menus consomment la file d'événements pygame bruts (`game.py:148` → `SceneManager.handle_event` → filtre `!= KEYDOWN → return` dans `menu_scene.py:48`, `pause_scene.py:33`, `gameover_scene.py:34`). Le gameplay consomme le polling `InputManager` (`gameplay_scene.py:76` → `provider.poll()` → edges), cadencé **uniquement** en tick de scène gameplay — hors gameplay, `InputManager.update()` n'est jamais appelé (gelé). Aucune couche ne traduit événements clavier/souris/manette en **actions nommées** communes.
- *Impact* : toute navigation de menu multi-périphérique impose de dupliquer la logique dans chaque scène ; l'UI (UI-1/UI-2 de `audit_ui.md`) n'a pas de point d'entrée unique ; un appui manette sur un menu n'existe tout simplement pas.
- *Cible* : un **routeur d'événements** (C-Lot 0b), appelé une seule fois par `Game` ou `SceneManager`, qui adapte les événements Pygame en résultats structurés (`action`, `position`, `device`) ou en `None`. Il consomme `KEYDOWN` / `MOUSE*` / `JOYBUTTON*` / `JOYHAT*` / `JOYAXIS*` avant le routage vers la scène active ; les scènes ne reçoivent les événements bruts que pour les usages non input (debug). Le gameplay conserve son polling inchangé (déterminisme).
- *Réception* : headless — un `Event(JOYBUTTONDOWN)` injecté sur le routeur produit l'action attendue (`ui_down`, `ui_confirm`) ; un `MOUSEMOTION` produit un résultat de position et un clic produit `ui_confirm` avec position ; les scènes menu ne contiennent plus `if event.type != pygame.KEYDOWN` comme unique porte d'entrée.

**C-2 — `InputState` fermé + edges en copier-coller (priorité haute, effort M — socle de C-3)**
- *Constat* : `InputState` est un dataclass à **10 champs booléens + 1 axe figés** (`input_state.py:41-51`). `InputManager` expose **11 propriétés d'edges** quasi identiques du type `current.X and not prev.X` (`input_manager.py:96-158`), écrites à la main. Ajouter une action de simulation = (1) champ dans `InputState`, (2) déclaration dans la table d'actions, (3) lecture dans `LocalInputProvider.poll` (câblage en dur, `:102-135`, pas de boucle sur les bindings), puis mise à jour de **jusqu'à 9 stubs de test** divergents (`tests/conftest.py:23`, `tests/headless/test_level_events.py:10`, `tests/headless/test_simulation_golden.py:46`, `tests/headless/test_rollback_e2e.py`, `tests/unit/helpers.py:228`, `tests/unit/test_player.py`, `tests/unit/test_reset_position.py:11`, `tests/unit/test_combat_component.py:11`, `tests/unit/test_type_annotations.py:12`).
- *Impact* : coût linéaire et fragile par action ; les stubs divergent silencieusement (signe : `player_input.py:53` utilise `getattr(im, "jump_just_released", False)` alors que la propriété existe réellement). Bloque directement l'ajout de `ui_up` / `ui_confirm` / `ui_back`.
- *Cible* : une **table d'actions déclarative** reliant un identifiant typé (`InputAction`), le champ correspondant de `InputState` et le contexte, consommée par `manager.held(action)`, `manager.just_pressed(action)` et `manager.just_released(action)`. Les propriétés nommées existantes restent pour la compatibilité et délèguent à cette API. `InputState` reste limité à la simulation : les actions UI ne le rejoignent pas. Un **scripted provider/fixture partagé** fournit de vrais `InputState` aux tests au lieu de neuf faux objets partiels.
- *Réception* : tests unitaires purs — déclarer une nouvelle action de simulation dans la table et `InputState` la rend lisible via l'API générique sans ajouter de propriété au manager ; une action UI n'exige aucune modification de `InputState` ; le stub commun remplace progressivement les neuf doublons.

**C-3 — Aucune action de menu dans le vocabulaire (priorité haute, effort S/M)**
- *Constat* : `InputBindings` ne contient que du gameplay (`move_*`, `jump`, `dash`, `attack1-4`, `guard`, `reset`, combos) — `input_bindings.py:31-76`. Grep `ui_confirm|ui_back|ui_up|ui_down` : **0 hit** dans `src/`. `InputState` ne transporte aucune sémantique de navigation.
- *Impact* : l'audit UI ne peut ni mapper manette en menu (UI-2), ni unifier clavier/souris/manette (D5 de `audit_ui.md`) sans d'abord enrichir ce vocabulaire.
- *Cible* : dict `menu` dans `InputBindings` (`ui_confirm`, `ui_back`, `ui_up`, `ui_down` — codes clavier + indices manette, cf. mapping figé UI-2 de `audit_ui.md`) ; transport via l'API générique C-2 **ou** canal dédié du routeur C-1 (décision C-D2) ; persistance avec les autres bindings (C-7).
- *Réception* : headless — `InputBindings` par défaut contient les 4 actions menu ; roundtrip serialization (C-7) les conserve ; routeur (C-Lot 0b) les produit depuis clavier **et** manette.

### Axe B — Périphériques et seuils

**C-4 — Souris hors du chemin commun input/UI (priorité haute pour l'UI, effort M)**
- *Constat* : `InputState` n'a ni position de curseur, ni boutons (`input_state.py:41-51`) et `LocalInputProvider.poll` ne lit que clavier + joystick (`input_provider.py:86-100`). La souris est toutefois déjà traitée par le panneau de debug : `MOUSEBUTTONDOWN`, `MOUSEBUTTONUP`, `MOUSEMOTION` et `pygame.mouse.get_pos()` (`panel_renderer.py:151-175,468`, `gameplay_scene.py:42,157-176`). Elle n'est ni traduite en action commune, ni routée vers les menus.
- *Impact* : hover et clic menu (UI-1) nécessitent un nouveau chemin ; le code debug montre qu'un routeur peut être introduit sans modifier `InputState` de simulation.
- *Cible* : le **routeur C-Lot 0b** traite `MOUSEMOTION` / `MOUSEBUTTONDOWN` comme résultats de position et d'activation UI ; la souris **n'entre pas** dans `InputState` de simulation (décision C-D3). Le panneau debug conserve son traitement brut tant qu'il n'est pas migré.
- *Réception* : headless — `Event(MOUSEMOTION, pos=…)` et `Event(MOUSEBUTTONDOWN, pos=…, button=1)` routés produisent un résultat de survol et `ui_confirm` avec position ; `InputState` gameplay reste inchangé (pas de champ souris).

**C-5 — Seuils et deadzones incohérents, hors `settings` (priorité moyenne, effort S)**
- *Constat* :
  - Deadzone **provider** : `0.2` en dur (`input_provider.py:173` `_apply_deadzone(..., deadzone=0.2)`) ;
  - Deadzone **manager** : `InputSettings.AXIS_DEADZONE = 0.1` (`settings.py:286`, appliquée `input_manager.py:75,80`) — **deux deadzones cumulées et différentes** ;
  - Seuil dash manette : `> 0.5` en dur (`input_provider.py:107`) ;
  - `settings.Input` ne contient que `AXIS_DEADZONE` + `ATTACK_BUFFER_WINDOW` (`settings.py:283-287`) — les autres seuils sont dispersés.
- *Impact* : comportement manette difficile à régler ; violation de la convention « magic numbers centralisés dans `settings.py` » (README / audit consolidé) ; double filtrage qui déforme l'axe (rescale 0.2 puis test 0.1).
- *Cible* : **une seule deadzone** lue depuis `settings.Input` (décision C-D4) appliquée au provider ; seuil dash (`DASH_AXIS_THRESHOLD`) et seuil stick menu (`MENU_STICK_THRESHOLD`, cf. UI-2) également dans `settings.Input` ; le manager ne filtre plus une deuxième fois (ou documente un rôle distinct, mais la cible est unicité).
- *Réception* : headless — `InputSettings.AXIS_DEADZONE` modifié en test → le même changement de comportement est observé une seule fois au provider ; plus aucun `0.2` / `0.5` littéral dans `input_provider.py` (grep §7).

**C-6 — Manette incomplète : hat Y et `down` absents (priorité moyenne, effort S)**
- *Constat* : `_calculate_move_axis` ne lit que `get_hat(0)[0]` (X) — le **Y du hat est ignoré** (`input_provider.py:166`). `state.down_held = keys[kb["move_down"]]` **clavier seul** (`input_provider.py:104`) — aucun bouton/analog/hat manette n'alimente le fast-fall ; `gamepad_buttons` ne contient pas `move_down` (`input_bindings.py:47-57`). Priorité clavier > analog > hat déjà en place (`:156-168`), non testée.
- *Impact* : pas de descente rapide à la manette (incohérent avec le reste du pad) ; hat vertical inutilisé (utile aussi pour la navigation menu en C-Lot 0b).
- *Cible* : mapping `move_down` manette (hat Y `+1` **et/ou** stick Y `> seuil`, décision C-D5) dans `poll` ; lire les deux composantes du hat pour `down` (et plus tard `ui_up`/`ui_down` côté routeur).
- *Réception* : headless — provider avec joystick scripté (ou état joy forcé) : hat Y bas → `down_held` ; hat X → `move_axis` ; mêmes tests pour le routeur menu (`ui_up`/`ui_down` depuis hat Y).

**C-7 — Bindings non persistés, non rebindables (priorité moyenne, effort M — porte le ex-UI-5)**
- *Constat* : `input_bindings.py:5` promet « *These mappings can be customized to support user-defined keybinds* » ; defaults en dur (`:31-76`) ; **aucun** `to_dict` / `from_dict` ; aucune écriture disque. `SaveGame` ne persiste que la progression. L'écran de capture de touche n'existe pas (l'UI est responsable de l'affichage — `audit_ui.md` UI-8 / lot UI-3).
- *Impact* : tout réglage (dont les futures actions `ui_*`) est perdu à chaque lancement ; le schéma de configuration de l'UI n'a pas de source de données pour les bindings.
- *Cible* : `InputBindings.to_dict()` / `from_dict()` avec schéma versionné, puis un `BindingsRepository` ou le futur `SettingsStore` pour une section `bindings` dans le fichier de configuration utilisateur. Le chargement d'un fichier absent ou corrompu retombe sur les defaults avec journalisation ; une action inconnue dans un fichier par ailleurs valide doit être signalée comme erreur de configuration, pas ignorée. `LocalInputProvider` est construit avec les bindings chargés (`input_provider.py:39-47` le supporte déjà). L'écran de capture reste hors périmètre de cet audit.
- *Réception* : headless — roundtrip JSON des 4 dicts (+ `menu`) ; bindings modifiés → rechargés identiques ; fichier corrompu → defaults sans crash ; le routeur et le gameplay voient les mêmes codes.

### Axe C — Tests et santé du code

**C-8 — Stubs dupliqués et `LocalInputProvider` sous-testé (priorité haute pour la stabilité, effort M)**
- *Constat* :
  - **9 stubs** d'`InputManager` partiels et divergents dans les tests (fichiers listés en C-2) ; chaque nouvelle action les dérive silencieusement ;
  - couverture snapshot `LocalInputProvider.poll` ≈ **54 %** : mapping clavier, combo kb, écrêtage attaques (`input_provider.py:116-120`), axes/hat (`:159-168`), rescale deadzone (`:188-191`), boutons joy (`:97-100`), `connect`/`disconnect`/`reassign` (`:60,70-71,81-82`) non exercés ;
  - `game.py:141-146` (`JOYDEVICEREMOVED`) hors couverture ;
  - `test_rf6_branches.py:35-46` asserte l'**ordre des lignes dans le source** via `inspect.getsource` au lieu d'un comportement — test structurel fragile.
- *Impact* : impossible de verrouiller les régressions manette **avant** de brancher les menus dessus ; les refactors C-2/C-6 risquent des casses silencieuses de la simulation.
- *Cible* : (1) **un seul** stub/fabrique d'input de test partagé, fondé sur un `InputProvider`/`ScriptedProvider` conforme au port et de vrais `InputState` ; (2) tests comportementaux `LocalInputProvider` (clavier/joystick via ports injectables ou adaptation minimale) : deadzone, priorité clavier/analog/hat, combo, écrêtage, hat Y, `down` manette ; (3) test `JOYDEVICEREMOVED` (reassign) ; (4) remplacer l'assert `inspect.getsource` par un test de comportement si touché.
- *Réception* : `uv run pytest tests/unit/test_input_provider.py tests/headless/test_input_manager.py tests/unit/test_runtime_and_paths.py` verts ; grep des 9 stubs → **1** emplacement ; couverture provider nettement au-dessus de 54 % (mesurer avant/après).

**C-9 — SOCD clavier implicite, non spécifié, non testé (priorité haute pour le netcode, effort S)**
- *Constat* : la gestion des directions opposées simultanées (Simultaneous Opposing Cardinal Directions) est **implicite** : `_calculate_move_axis` calcule `float(keys[droite]) - float(keys[gauche])` (`input_provider.py:156`) — les deux touches pressées s'annulent (policy `neutral`) sans que cette policy soit nommée, documentée ou testée. Aucun test n'exerce l'état gauche+droite.
- *Impact* : policy de combat critique laissée au hasard d'une implémentation ; avec le rollback (pattern `test_rollback_e2e.py`), toute évolution accidentelle de ce calcul (par ex. un futur `last_input_wins`) diverge sans être détectée → désync. Le clavier étant une entrée de premier rang du jeu (bindings défauts `move_left`/`move_right`), le cas est atteignable en un appui, pas théorique.
- *Cible* : acter la policy `neutral` (décision C-D10), l'expliciter dans le code (docstring du calcul, nommage éventuel `_socd_neutral`) et un test dédié ; documenter l'option `last_input_wins` (standard fightstick) comme évolution possible, hors lot.
- *Réception* : headless — provider avec `move_left` **et** `move_right` pressés → `move_axis == 0.0` ; test vert tant que la policy n'est pas changée ; tout changement de policy exige une révision de C-D10 avant tout code.

**C-10 — Bindings sans structure de contexte (maps) ni mapping manette standard documenté (priorité moyenne, effort S)**
- *Constat* : `InputBindings` est une collection de **5 dicts plats** gameplay (`keyboard`, `gamepad_buttons`, `gamepad_axes`, `keyboard_combos`, `gamepad_combos`, `input_bindings.py:31-76`) sans notion de contexte ; le dict `menu` prévu par C-3 (C-Lot 0a.2) s'ajouterait en 6e sans hiérarchie. Le mapping manette par défaut (`jump:0/A, attack1:1/B, attack2:2/X, attack3:3/Y, guard:4/LB, attack4:5/RB, reset:7`, `input_bindings.py:47-57`) est proche du **Standard Gamepad** (Xbox) mais n'est pas documenté comme tel — l'écran Contrôles (UI-8) n'a pas de référence de mapping à afficher.
- *Impact* : le rebinding (C-7) et l'affichage des libellés (UI-8) doivent deviner la structure ; chaque nouveau contexte (pause, tutoriel, écran de fin) duplique un dict au lieu d'activer une map.
- *Cible* : regrouper les dicts en **maps nommées** (`gameplay`, `menu` — décision C-D11) ; la map `menu` du C-Lot 0b devient « la map activée consomme les événements », pas un nouveau canal ; documenter le défaut manette comme « Standard Gamepad Mapping (Xbox) » dans la docstring de `InputBindings` ; les indices bruts restent acceptables (pygame n'expose pas l'API `SDL_GameController` complète), seule la référence standard est ajoutée.
- *Réception* : headless — `InputBindings` expose les maps `gameplay`/`menu` avec les mêmes codes qu'aujourd'hui (roundtrip C-7 préservé) ; docstring cite le standard ; aucun changement de comportement polling.

**C-11 — Réponse analogique sans seuil extérieur (priorité basse, effort S — optionnel)**
- *Constat* : `_apply_deadzone` rescale la zone active vers `[0, 1]` en supposant que le pad atteint 1.0 (`input_provider.py:188-191`) — un pad usé ou mal calibré plafonne `move_axis` autour de 0.8-0.9 ; aucun seuil extérieur (`range_end`) ni test avec valeur non saturée.
- *Impact* : différé — le gameplay actuel lit l'axe de façon binaire (seuils `AXIS_DEADZONE`), mais toute lecture analogique future (vitesses intermédiaires) rendrait la vitesse max inatteignable selon le matériel.
- *Cible* : `InputSettings.AXIS_RANGE_END` + rescale `(|v| - dz) / (range_end - dz)` borné à 1.0 ; peut rester hors lots tant que le gameplay reste binaire (C-D4 révisée : seuil extérieur optionnel).
- *Réception* : headless — rescale avec valeur > `AXIS_RANGE_END` → 1.0 ; valeur intermédiaire → linéaire dans la plage active.

---

## 3. Architecture cible

```
InputBindings (défauts + contextes gameplay/menu)  ←→  BindingsRepository / SettingsStore (C-7)
        │
        ▼
LocalInputProvider.poll()  ──→  InputState (gameplay uniquement, inchangé côté simulation)
        │                         + table d'actions / edges calculée par InputManager
        ▼
InputManager  ── API générique held(action) / just_pressed(action) / just_released(action)
        │       ── propriétés nommées existantes déléguées (compat player_input)
        ▼
PlayerInputHandler (gameplay)          │
                                       │  (parallèle, même vocabulaire)
InputEventRouter / Adapter (C-Lot 0b)  │
  KEYDOWN | MOUSE* | JOYBUTTON | JOYHAT | JOYAXIS
        │
        ▼
  résultats ui_* / position  ──→  scène active ou MenuModel (audit_ui.md, UI-3)
```

- **Deux canaux assumés** (polling simulation vs file d'événements menus), mais un **vocabulaire d'actions unique** organisé en contextes (`gameplay`, `menu` — C-D11). Un routeur unique est appelé par `Game`/`SceneManager`, pas par chaque scène.
- Les seuils vivent dans `settings.Input` ; les codes matériels dans `InputBindings` (rebindables) ; la persistance dans la configuration utilisateur via un repository, séparée du `savegame.json`.
- `InputProvider` est maintenu comme port (migrer vers `Protocol` si nécessaire) et `apply_remote_state` est conservé pour le réseau, les tests et le replay d'inputs.
- **Patterns retenus** : table/registry d'actions + façade `InputManager`, adapter + routeur d'événements, parameter object `settings.Input`, strategy SOCD explicite, ports et scripted test doubles, repository de configuration. Un vrai Command/Mediator ou une hiérarchie de strategies serait disproportionné ici ; un routeur simple est préférable.
- **Patterns à éviter** : Singleton pour les bindings/provider/routeur, input UI dans `InputState`, gameplay routed par l'`EventBus`, et observabilité par `inspect.getsource`.

---

## 4a. Décisions figées

Ne pas rouvrir sans écrire la nouvelle décision ici **et** la répercuter dans `audit_ui.md` si elle touche un croisement.

| # | Sujet | Décision |
|---|---|---|
| C-D1 | API d'action | Table d'actions typée (`InputAction` + champ/contexte) et API `held(action)` / `just_pressed(action)` / `just_released(action)` **en plus** des propriétés nommées (délégation) ; `InputState` reste limité à la simulation, le manager calcule les edges sans nouvelle propriété manuelle par action |
| C-D2 | Transport des `ui_*` | Un **InputEventRouter/Adapter** (C-Lot 0b), appelé une fois par `Game` ou `SceneManager`, produit des résultats `ui_up/down/confirm/back` et de position pour les menus ; le polling gameplay **ne remplit pas** `InputState` avec les `ui_*`. Une commande ou un médiateur formel n'est pas justifié tant que le routeur reste simple. Les codes matériels sont dans le contexte `menu` d'`InputBindings` (rebindables, persistés) |
| C-D3 | Souris | **Hors** `InputState` de simulation ; le chemin commun UI la traite via le routeur (position + clic → focus menu / activation). Le panneau debug peut conserver son traitement brut jusqu'à sa migration |
| C-D4 | Deadzone et seuils | `settings.Input` sert de **parameter object** : une seule deadzone `AXIS_DEADZONE` appliquée côté provider, sans second filtrage manager ; `DASH_AXIS_THRESHOLD` et les seuils menu sont regroupés dans le même objet. `AXIS_RANGE_END` reste optionnel, hors lots tant que le gameplay reste binaire |
| C-D5 | `down` manette | Hat **Y** (`+1` = bas) **et** stick axe 1 (`> InputSettings.AXIS_DEADZONE` ou seuil dédié) alimentent `down_held` en plus du clavier ; priorité clavier > analog > hat conservée |
| C-D6 | Portage rebinding | **Porté par cet audit** (C-7) : sérialisation versionnée + `BindingsRepository`/`SettingsStore` ; l'écran Contrôles reste UI lot 3 |
| C-D7 | Port réseau (`set_provider`, `apply_remote_state`) | Conservés comme surface publique (tests + futur multi). Migrer `InputProvider` vers un `Protocol` si cela élimine les écarts de type des scripted providers ; ne pas introduire de service locator global |
| C-D8 | Stubs de test | **Un seul** scripted test double/fixture, basé sur le port `InputProvider` et de vrais `InputState` ; variante **replay** : séquence d'`InputState` injectée via `apply_remote_state` (pattern `test_rollback_e2e.py`) ; les 9 copies sont migrées puis supprimées |
| C-D9 | Ordre | **C-Lot 0a → 0b → 0c** ; l'exécution UI (lots `audit_ui.md`) ne démarre qu'après 0a + 0b verts |
| C-D10 | SOCD | Policy **`neutral`** actée et encapsulée dans une petite **strategy** ou fonction pure testable (directions opposées pressées s'annulent = comportement actuel conservé, zéro changement gameplay) ; l'option `last_input_wins` exige une révision de cette décision avant tout code |
| C-D11 | Contextes d'actions | `InputBindings` regroupé en **contextes nommés** (`gameplay`, `menu`) ; le routeur 0b résout le contexte `menu` actif ; rebind = écriture dans le contexte ; mapping manette par défaut documenté « Standard Gamepad (Xbox) » |

---

## 4b. Plan par lots

Chaque lot est livrable et recevable indépendamment. Efforts : S ≈ demi-journée, M ≈ 1-2 j, L ≈ 3-5 j.

| Lot | Contenu | Constats | Effort | Bloque l'UI ? |
|---|---|---|---|---|
| **C-Lot 0a — Socle actions** | Table d'actions + façade générique ; maps de contexte (`gameplay`, `menu`) dans `InputBindings` ; seuils → `settings.Input` (deadzone unique) ; port + scripted test double ; migration des 9 stubs | C-2, C-3 (bindings), C-5, C-8 (stubs), C-10 | M | Oui → UI-3 et fondations |
| **C-Lot 0b — Routeur événements** | `InputEventRouter`/adapter appelé par `Game` ou `SceneManager` : KEYDOWN + MOUSE + JOYBUTTON + JOYHAT + JOYAXIS → actions `ui_*` ou résultat de position ; scènes actives branchées sur le résultat, sans filtre Pygame local **sans** curseur visuel (UI-3/UI-1 = lots UI) | C-1, C-3, C-4 | M | Oui → UI-1, UI-2 |
| **C-Lot 0c — Hygiène manette + tests** | Hat Y + `down` manette ; test SOCD `neutral` (C-D10) ; tests `LocalInputProvider` (deadzone, priorités, combo, hat) ; test `JOYDEVICEREMOVED` ; revue `inspect.getsource` | C-5, C-6, C-8, C-9 | M | Non (recommandé avant UI-2) |
| **C-Lot 0d — Persistance bindings** | `to_dict`/`from_dict` + section `bindings` dans la configuration utilisateur (ex. `settings.json`) ; wiring au boot (`game.py` charge les bindings dans le provider) | C-7 | M | Non (UI lot 3 en dépend pour l'écran) |

### C-Lot 0a — Socle actions et extensibilité

**Ordre**
1. `settings.Input` : documenter/ajouter `DASH_AXIS_THRESHOLD = 0.5` ; **supprimer** le littéral `0.2` de `_apply_deadzone` au profit de `AXIS_DEADZONE` (C-D4) ; le paramètre de configuration est injecté ou centralisé sans créer un singleton.
2. `InputBindings` : regrouper en **contextes** (`gameplay`, `menu` — C-D11) ; `menu` par défaut clavier (`ui_up: K_UP`, `ui_down: K_DOWN`, `ui_confirm: K_RETURN`, `ui_back: K_ESCAPE`) + manette (`ui_confirm: 0`, `ui_back: 1`) — aligné sur D12 de `audit_ui.md` ; documenter le mapping manette gameplay comme « Standard Gamepad (Xbox) » dans la docstring (C-10).
3. Déclarer une **table d'actions** reliant les identifiants typés aux champs de `InputState` ; `InputManager` expose `held(action)`, `just_pressed(action)` et `just_released(action)`. Les 11 propriétés d'edges existantes délèguent à cette API — comportement gameplay inchangé.
4. Définir le port `InputProvider` (de préférence `Protocol`) et un `ScriptedProvider` partagé qui produit de vrais `InputState` ; variante replay via `apply_remote_state` (C-D8 révisée).
5. Migrer les 9 stubs vers le helper ; supprimer les copies.

**Fichiers créés** : éventuellement `tests/unit/test_input_actions.py`.
**Fichiers modifiés** : `input_bindings.py`, `input_manager.py`, `settings.py` (constantes), `tests/unit/helpers.py`, les 9 fichiers de stubs, `player_input.py` seulement si délégation nécessite un ajustement type.

**DoD C-Lot 0a**
```bash
uv run pytest tests/unit/test_input_actions.py tests/headless/test_input_manager.py \
  tests/unit/test_player.py tests/unit/test_player_controllers.py \
  tests/headless/test_gameplay_loop.py -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
```
+ grep : une seule définition de stub input dans `tests/` (§7) ; `just_pressed(InputAction.JUMP)` équivalent à `jump_just_pressed` sur les mêmes états.

---

### C-Lot 0b — Routeur événements multi-périphériques

**Prérequis** : C-Lot 0a (vocabulaire `menu` + API).

**Ordre**
1. Créer `src/core/input/event_router.py` comme **adapter/routeur simple**, réutilisé par l'UI : `route(event, bindings, previous_axes) -> RouterResult | None`, avec `RouterResult(action, position, device)` ; 2. `Game` ou `SceneManager` appelle ce routeur une seule fois avant de distribuer le résultat à la scène active ; 3. `KEYDOWN` → codes du contexte `menu` ; `MOUSEMOTION` → résultat de position ; `MOUSEBUTTONDOWN` bouton 1 → `ui_confirm` avec position ; 4. `JOYBUTTONDOWN` → indices du contexte `menu` ; `JOYHATMOTION` → hat Y ; `JOYAXISMOTION` → seuil d'activation et désactivation avec état précédent, les seuils appartenant à `settings.Input`. Le routeur n'a pas besoin d'un Command ou d'un Mediator tant que son contrat reste ce résultat structuré.
5. Faire consommer le résultat par `MenuScene`, `PauseScene` et `GameOverScene` ; retirer leur filtre Pygame local. ESC/ENTER/Q restent des actions dont la sémantique varie selon la scène.
6. Ne pas ajouter le curseur visuel ni le hit-test des Rects ici ; le modèle de focus et le rendu restent les lots UI. Les événements bruts non transformés peuvent continuer à être transmis uniquement pour le debug.

**Fichiers créés** : `src/core/input/event_router.py`, `tests/unit/test_event_router.py`.  
**Fichiers modifiés** : `menu_scene.py`, `pause_scene.py`, `gameover_scene.py`, `settings.py` (seuils stick menu si pas fait).

**DoD C-Lot 0b**
```bash
uv run pytest tests/unit/test_event_router.py tests/headless/test_scenes.py \
  tests/unit/test_input_manager.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ headless : `Event(KEYDOWN, K_DOWN)` → `"ui_down"` ; `Event(JOYHATMOTION, value=(0,-1))` → `"ui_down"` ; `Event(JOYBUTTONDOWN, button=0)` → `"ui_confirm"` ; `Event(MOUSEBUTTONDOWN, pos=…, button=1)` → `"ui_confirm"` + pos ; parcours clavier ENTER → gameplay **toujours vert** (`test_scenes.py`).

---

### C-Lot 0c — Hygiène manette et tests provider

**Prérequis** : 0a (constantes) ; 0b recommandé pour tester hat Y côté routeur en même temps.

**Ordre**
1. Deadzone unique (C-D4) : `_apply_deadzone` lit `InputSettings.AXIS_DEADZONE` ; `left_held`/`right_held` manager sans second filtre divergent.
2. Seuil dash : `InputSettings.DASH_AXIS_THRESHOLD` remplace `0.5` (`input_provider.py:107`).
3. Hat Y + `down` manette (C-D5) : lecture `get_hat(0)[1]`, combinaison `down_held`.
4. Test SOCD (C-D10) : `move_left` **et** `move_right` pressés → `move_axis == 0.0` (policy `neutral` explicite, docstring du calcul).
5. `tests/unit/test_input_provider.py` **neuf** : monkeypatch `pygame.key.get_pressed`, faux joystick (double `get_numbuttons`/`get_button`/`get_axis`/`get_hat`) — deadzone, priorité clavier/analog/hat, combo special + écrêtage, boutons, hat Y, `down`, SOCD, `connect`/`disconnect`/`reassign`.
6. Test `JOYDEVICEREMOVED` / reassign dans `test_runtime_and_paths.py`.
7. Optionnel : assainir `test_rf6_branches.py` (comportement plutôt que `inspect.getsource`) si le fichier est touché.

**Fichiers créés** : `tests/unit/test_input_provider.py`.  
**Fichiers modifiés** : `input_provider.py`, `settings.py`, `tests/unit/test_runtime_and_paths.py`.

**DoD C-Lot 0c**
```bash
uv run pytest tests/unit/test_input_provider.py tests/unit/test_runtime_and_paths.py \
  tests/headless/test_input_manager.py tests/unit/test_event_router.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ grep §7 : plus de `deadzone=0.2` ni `> 0.5` littéraux dans `input_provider.py` ; `down_held` alimenté par la manette dans les tests provider ; gauche+droite pressés → `move_axis == 0.0` (SOCD `neutral` testé).

---

### C-Lot 0d — Persistance des bindings

**Prérequis** : 0a (`to_dict`/`from_dict`).

**Ordre**
1. Définir un `BindingsRepository` (ou l'intégrer au futur `SettingsStore`) avec schéma versionné, valeurs par défaut, validation des actions/contexte et écriture atomique. Le fichier de configuration utilisateur est distinct de `savegame.json`.
2. `Game.__init__` : charger les bindings avant de construire `LocalInputProvider(bindings)` ; passer le même modèle au routeur.
3. Écran de rebinding : hors périmètre (UI lot 3) — ici seulement la couche données.

**DoD C-Lot 0d**
```bash
uv run pytest tests/unit/test_input_bindings_dict.py tests/unit/test_settings_store.py \
  tests/headless/test_input_manager.py -q   # test_settings_store.py peut être celui de UI-3
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ roundtrip disque ; corrompu → defaults ; modifs en mémoire persistées au prochain `save`.

---

### Dépendances et enchaînement avec l'UI

```
C-Lot 0a  ──→  C-Lot 0b  ──→  UI lot 1 (MenuModel)  ──→  UI lot 2 (souris + manette curseur/clic)
    │              │
    │              └──→  UI lot 2 peut démarrer dès 0b (routeur) + 0a (vocabulaire)
    ├──→  C-Lot 0c  (parallèle possible avec UI lot 1)
    └──→  C-Lot 0d  ──→  UI lot 3 (écran Contrôles qui relit/writ les mêmes bindings)
```

- **Bloquant UI** : 0a + 0b avant UI lot 1-2.  
- **0c** : recommandé avant UI lot 2 (stabilité manette).  
- **0d** : avant ou avec UI lot 3 (sinon l'écran Contrôles n'a rien à persister).  
- UI lot 3 (Options vidéo/audio) et UI lot 4 (HUD) : **non bloqués** par le contrôle, en dehors de 0d pour les bindings.

---

## 5. Règles

1. **Aucun changement de gameplay** : le polling de simulation (`InputState` gameplay, edges attaque/jump/dash) garde son comportement **bit-identique** sauf hygiène explicite C-5/C-6/C-9 (deadzone/hat/SOCD — le SOCD rend explicite la policy actuelle, zéro changement) testée avant/après. Jamais `src/core/level/`, `src/combat/`, `src/states/`, `src/physics/` ; `src/entities/player_input.py` seulement pour délégation compatible.
2. **Un vocabulaire, deux canaux** : polling (tick fixe) pour la simulation ; routeur d'événements pour les menus — pas de troisième canal ad hoc ; pas de `key.get_pressed` supplémentaire hors provider/routeur.
3. **Seuils dans `settings.Input`**, codes matériels dans `InputBindings`, persistance dans la configuration utilisateur (ex. `settings.json`, section `bindings`) séparée de `savegame.json`.
4. **Réception headless uniquement** : `SDL_VIDEODRIVER=dummy`, events injectés, faux joystick scriptable.
5. **Un seul stub d'input dans les tests** après C-Lot 0a (C-D8).
6. **Compatibilité** : `jump_just_pressed` et consorts restent utilisables par `player_input.py` pendant toute la migration (délégation, pas rupture).
7. **Les décisions C-D1 à C-D11 font autorité** ; divergence = mettre à jour le tableau avant le code.

---

## 6. Réception globale

- [ ] API générique : une nouvelle action de simulation est déclarée dans la table et `InputState`, puis lisible via `held` / `just_pressed` sans nouvelle propriété dans `InputManager` ; une action UI ne modifie pas `InputState`.
- [ ] Vocabulaire `menu` (`ui_up`, `ui_down`, `ui_confirm`, `ui_back`) présent dans `InputBindings` par défaut, sérialisable (roundtrip).
- [ ] Routeur : KEYDOWN, MOUSEMOTION, MOUSEBUTTONDOWN, JOYBUTTONDOWN, JOYHATMOTION et JOYAXISMOTION produisent l'action `ui_*` ou le résultat de position attendu en test unitaire.
- [ ] Scènes menu : plus de porte d'entrée exclusive `KEYDOWN` ; parcours clavier historique (ENTER/N/ESC/Q) **identique** (`test_scenes.py` vert).
- [ ] Une seule deadzone `settings.Input` ; grep sans littéral `0.2` / `0.5` dans `input_provider.py`.
- [ ] `down_held` (et `ui_up`/`ui_down`) fonctionnent à la manette (hat Y) — test provider + routeur.
- [ ] Un seul helper de stub d'input ; les 9 copies supprimées.
- [ ] `tests/unit/test_input_provider.py` créé et vert ; `JOYDEVICEREMOVED` / reassign testé ; couverture provider en nette hausse (mesurer).
- [ ] `InputBindings` persisté dans la section `bindings` de la configuration utilisateur (ex. `settings.json`) (si 0d livré) ; corrompu → defaults.
- [ ] SOCD `neutral` : gauche+droite pressés → `move_axis == 0.0` (C-D10), test dédié vert.
- [ ] Maps de contexte `gameplay`/`menu` dans `InputBindings` ; mapping manette standard documenté (C-D11).
- [ ] (Optionnel, C-11) `AXIS_RANGE_END` : rescale borné à 1.0 au-delà du seuil extérieur.
- [ ] `uv run ruff check src tests`, `ruff format --check`, `mypy src`, suite `pytest` verts ; aucun test désactivé.
- [ ] `git diff --stat` : aucune modification sous `src/core/level/`, `src/combat/`, `src/states/`, `src/physics/`.

---

## 7. Commandes de vérification et croisements

### Commandes (racine du dépôt)

```bash
# C-3 / C-2 : actions menu dans les bindings (0 hit avant C-Lot 0a)
grep -rnE 'ui_confirm|ui_back|ui_up|ui_down' src/core/input/

# C-4 : souris : hits debug attendus avant C-Lot 0b ; vérifier l'absence de routeur commun avant, puis les résultats de position/action après
grep -rnE 'MOUSEMOTION|MOUSEBUTTON|pygame\.mouse' src/

# C-1 : filtre exclusif KEYDOWN dans les scènes (hits avant C-Lot 0b)
grep -rn 'event.type != pygame.KEYDOWN' src/application/scenes/

# C-5 : littéraux de seuil dans le provider (0 hit après C-Lot 0c)
grep -nE 'deadzone=0\.2|> 0\.5' src/core/input/input_provider.py

# C-5 : seuils centralisés
grep -n 'AXIS_DEADZONE\|DASH_AXIS\|MENU_STICK' src/core/settings.py

# C-7 : persistance bindings (0 hit avant C-Lot 0a/0d)
grep -rnE 'to_dict|from_dict' src/core/input/input_bindings.py

# C-8 : duplication de stubs d'input dans les tests (9 fichiers avant 0a, viser 1 emplacement après)
grep -rln 'jump_just_pressed\|attack1_held=' tests/ | sort

# C-6 : hat Y / down manette
grep -n 'get_hat\|down_held' src/core/input/input_provider.py

# C-9 : SOCD neutral — policy explicite + test dédié (0 hit test avant C-Lot 0c)
grep -n 'float(keys\[kb\["move_right' src/core/input/input_provider.py
grep -rlni 'socd\|both_directions\|left_and_right' tests/

# C-10 : maps de contexte dans les bindings (0 hit avant C-Lot 0a)
grep -n 'gameplay\|menu' src/core/input/input_bindings.py

# C-11 : seuil extérieur (0 hit tant que non retenu)
grep -n 'AXIS_RANGE_END' src/core/settings.py src/core/input/input_provider.py

# API générique présente
grep -n 'def just_pressed\|def held' src/core/input/input_manager.py

# Comptage de tests input
grep -c 'def test_' tests/headless/test_input_manager.py tests/unit/test_input_provider.py
```

### Croisements

| Point | Audit contrôles | Audit UI | Décision |
|---|---|---|---|
| Rebinding / `InputBindings` persistés | **C-7**, C-Lot 0d (données + disque) | UI-5, UI-8 (écran Contrôles, capture) | **C-D6** : données ici, écran là ; schéma `bindings` de la configuration utilisateur défini par C-7, référencé par UI-5 sans être dupliqué |
| Routeur / actions menu | **C-1**, **C-3**, C-Lot 0b | UI-1, UI-2, D8 (`ui_controller`) | **C-D2** : routeur physique en `src/core/input/event_router.py` ; l'UI l'appelle et gère focus/Rects ; ne pas créer deux routeurs |
| Mapping manette menu (A/B, hat, stick) | indices dans `InputBindings.menu` (C-3), seuils stick dans `settings.Input` | D12, cible UI-2 | Même mapping ; le tableau D12 UI reste la référence UX, ce document porte l'implémentation |
| `MenuModel` / curseur focus | Hors périmètre ici | UI-3, UI-1 | Après C-Lot 0a+0b |
| Écran Options vidéo/audio | Hors périmètre | UI-4, UI-6, UI-10 | Indépendant de C-Lot 0 (sauf 0d pour l'onglet Contrôles) |
| FPS / R-1 | Hors périmètre | UI-6, D2 (lot UI 3) | Inchangé |
| Debug hotkeys (`spawn_system`, F1-F7, conflit K_g) | **Hors-scope** (mention seulement) | Règle 5 UI (panneaux debug) | Non planifié ; à arbitrer dans un audit dédié si douleur |

---

## Hors-scope (mention, non planifié)

- Troisième canal de lecture clavier pour le debug : `spawn_system.py:94` (`pygame.key.get_pressed()` direct) et touches F1-F7 en dur dans `gameplay_scene.py:19-33` — hors `InputBindings`, non remappables.
- Conflit de touche : `K_g` = moitié du combo `special_attack` (`input_bindings.py:68`) **et** spawn goblin (`spawn_system.py:36`).
- Affichage des libellés de touches dans les menus (UI-8) — après rebinding.

---

## Validation du document

- Re-vérification code : 2026-09-22, `a6d20f8` — preuves §1, §2, §7.
- Reprise complète : 2026-09-22 — branche corrigée (`hitbox/rework`), stubs 7→9 (ajout `test_rollback_e2e.py`, `test_player.py`), constats C-9/C-10/C-11 ajoutés, décisions C-D10/C-D11 ajoutées, C-D4/C-D8 révisées, référence pendante « C-10 en annexe » (§3) remplacée par C-D7/C-D8.
- Revue des design patterns : 2026-09-23 — actions registry/facade, routeur adapter, parameter object, strategy SOCD, ports et repository de bindings ; suppression du Command/Mediator formel et correction du traitement souris debug existant.
- Rédaction : 2026-09-22 — périmètre socle input + prérequis UI ; rebinding (ex-UI-5) porté ici (C-D6) ; enchaînement : exécuter ce document (C-Lot 0a → 0b) **avant** les lots 1-2 de `notes/audit_ui.md`.
