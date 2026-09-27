# Audit Contrôles — Socle clavier / manette / souris (prérequis de `audit_ui.md`)

> Audit réécrit le 2026-09-24 contre `master` au commit `afe044f`, base de
> validation rafraîchie le 2026-09-26 contre `40ca5a9`.
> L’historique des versions précédentes reste conservé dans Git.
> Ce document décrit l’état vérifié et les décisions futures ; il ne présente pas les lots comme livrés.

## 1. Verdict exécutif

Le socle de gameplay est fonctionnel et suffisamment découplé pour être conservé :

- `InputBindings` décrit les codes physiques par défaut ;
- `LocalInputProvider` traduit clavier et manette en `InputState` ;
- `InputManager` conserve les états précédent/courant et calcule les edges ;
- `set_provider()` et `apply_remote_state()` offrent une surface d’injection ;
- `Game` gère l’ajout et la suppression d’une manette.

Le socle n’est pas encore prêt pour les menus multi-périphériques et le rebinding. Les écarts réels sont :

- aucun vocabulaire d’actions `ui_*` ;
- aucun routeur commun pour les événements de menu ;
- pas de navigation souris/manette dans les scènes de menu ;
- hat Y et `down` non alimentés par la manette ;
- seuils provider dispersés et deadzone appliquée en deux endroits ;
- SOCD non documenté ni testé ;
- bindings sans persistance ;
- doublons de doubles d’input dans les tests.

Ces écarts sont à traiter avant les lots de navigation de `notes/audit_ui.md`. Le gameplay ne doit pas être remplacé par un routeur d’événements : ses entrées restent échantillonnées par le tick fixe.

## 2. Base vérifiée et limites

- **HEAD :** `afe044f` pour le constat ; `40ca5a9` pour la base de validation (`master`).
- **Périmètre :** `src/core/input/`, `src/core/game.py`, `src/entities/player_input.py`, `src/core/settings.py`, scènes de menu et tests input/runtime.
- **Validation de référence :** **82 tests ciblés passés** (la commande du §11 ; 52 lors de la réécriture) ; `ruff check src tests`, `mypy src` (142 fichiers) et `git diff --check` passés.
- **Limite :** les périphériques physiques et la lecture réelle d’un contrôleur ne sont pas simulés par cette validation.
- **Fixe depuis le 2026-09-24 :** aucun fichier de `src/core/input/` n’a été modifié. Le seul fichier de ce périmètre touché est `src/core/game.py`, sur la cadence de la boucle (`_frame_delta`, plafond dérivé de `Display.FPS`) — sans rapport avec les entrées. Aucun constat de la matrice §3 n’a donc évolué.

## 3. Matrice d’état

| Capacité | État actuel | Statut | Preuve |
|---|---|---|---|
| Clavier gameplay | Polling et edges fonctionnels | **Vérifié** | `input_manager.py`, `player_input.py`, tests input |
| Manette : connexion/déconnexion | Réassignement après retrait | **Partiel** | `game.py`, `input_provider.py` |
| Axes et hat X | Axe X + hat X, deadzone codée en dur | **Partiel** | `input_provider.py` |
| Hat Y / `down` | Non branchés | **Ouvert** | `input_provider.py` |
| Deadzone/seuils | Valeurs `0.1`, `0.2` et `0.5` dispersées | **Ouvert** | `settings.py`, `input_provider.py` |
| Combos clavier/manette | `special_attack` fonctionnel | **Vérifié** | bindings et provider |
| SOCD | `droite - gauche = 0`, mais non documenté | **Ouvert** | `input_provider.py` |
| Souris | Panels debug uniquement | **Ouvert pour UI** | `panel_renderer.py`, `gameplay_scene.py` |
| Actions `ui_*` | Absentes | **Ouvert** | `input_bindings.py`, `src/core/input/` |
| Routeur menu | Absent ; scènes filtrent principalement `KEYDOWN` | **Ouvert** | scènes de menu |
| Persistance/rebind | Absente | **Ouvert** | `input_bindings.py` |
| API d’action générique | Absente ; propriétés edges manuelles | **Ouvert, chantier obligatoire** | `input_manager.py` |
| Test provider local | Couverture réduite, sans faux joystick dédié | **Ouvert** | tests input |
| Injection réseau/replay | `set_provider`/`apply_remote_state` présents | **Partiel** | `input_manager.py` |
| Doublons de doubles input | Plusieurs motifs historiques | **Ouvert** | tests input |

## 4. Constats détaillés

### C-1 — Deux canaux distincts, mais aucun adaptateur commun pour l’UI — **Ouvert**

Le gameplay utilise le polling `InputManager`, tandis que les menus reçoivent les événements Pygame bruts par `Game._handle_events()` puis `SceneManager.handle_event()`. Les scènes filtrent encore les événements selon `KEYDOWN` et ne partagent pas de contrat d’action.

Ce découpage n’est pas une erreur : il faut garder le gameplay déterministe. L’écart est l’absence d’un adaptateur unique pour les événements UI.

**Cible :** créer un routeur simple dans `src/core/input/event_router.py`, appelé une fois par `Game` ou `SceneManager`, qui retourne des résultats structurés (`action`, `position`, `device`) ou `None`. Le routeur couvre clavier, souris, boutons, hat et axes. Le polling gameplay reste inchangé.

**Réception :** événements headless injectés → actions UI attendues ; aucun filtre `KEYDOWN` comme unique porte d’entrée dans les trois scènes ; parcours clavier historique inchangé.

### C-2 — API gameplay fermée et répétitive — **Ouvert, chantier structurant obligatoire**

`InputState` contient les champs de gameplay et `InputManager` expose des propriétés `held` et des edges répétées manuellement. Ajouter une action de gameplay demande aujourd’hui de modifier plusieurs couches.

La migration doit être massive et canonique : toutes les actions gameplay doivent être déclarées dans un vocabulaire typé `InputAction`, lues par une API uniforme `held/just_pressed/just_released`, et consommées par `PlayerInput` et les systèmes de gameplay. Les propriétés existantes ne sont pas conservées indéfiniment : elles constituent une façade de compatibilité temporaire pendant la migration.

Les actions UI ne doivent pas entrer dans `InputState` : elles ne font pas partie de la simulation. Elles utiliseront le même vocabulaire d’actions via le routeur UI, mais un canal d’événements distinct.

**Cible :** définir `InputAction`, faire de `InputManager` l’unique façade gameplay, migrer les appels de `PlayerInput`, les combos, le rollback, les tests et les scripts, puis mesurer la parité avant de supprimer les anciennes propriétés.

**Réception :** aucune nouvelle action gameplay n’utilise une propriété manuelle ; les parcours clavier, manette, combos et rollback passent par l’API générique ; la façade historique est testée pendant la transition puis retirée dans un lot dédié ; `InputState` ne contient aucun événement souris ou UI.

#### C-2.1 — Contrat de données final

Le contrat ci-dessous est normatif pour l’implémentation. L’agent ne doit pas conserver la structure par champs `_held` comme interface finale.

```python
class InputAction(StrEnum):
    MOVE_X = "move_x"
    MOVE_DOWN = "move_down"
    JUMP = "jump"
    DASH = "dash"
    GUARD = "guard"
    RESET = "reset"
    ATTACK_1 = "attack1"
    ATTACK_2 = "attack2"
    ATTACK_3 = "attack3"
    ATTACK_4 = "attack4"
    SPECIAL_ATTACK = "special_attack"

    UI_UP = "ui_up"
    UI_DOWN = "ui_down"
    UI_LEFT = "ui_left"
    UI_RIGHT = "ui_right"
    UI_CONFIRM = "ui_confirm"
    UI_BACK = "ui_back"
    UI_CANCEL = "ui_cancel"
    UI_POINTER_MOVE = "ui_pointer_move"
    UI_POINTER_DOWN = "ui_pointer_down"
    UI_POINTER_UP = "ui_pointer_up"
```

`MOVE_X` est la seule action analogique de gameplay. `MOVE_LEFT` et `MOVE_RIGHT` ne sont pas des actions de touches distinctes : ce sont des projections directionnelles dérivées de `MOVE_X` dans `PlayerInput`, avec le seuil documenté.

`InputState` final est un snapshot gelé du tick :

```python
@dataclass(frozen=True)
class InputState:
    move_axis: float = 0.0
    held_actions: frozenset[InputAction] = frozenset()
```

Règles :

- `held_actions` contient uniquement les actions gameplay discrètes ;
- `move_axis` contient la valeur analogique de `MOVE_X` dans `[-1, 1]` ;
- `SPECIAL_ATTACK` est une action logique produite par la stratégie de combo du provider ;
- aucun événement souris, focus, menu, position de pointeur ou edge ne se trouve dans `InputState` ;
- `InputState` doit pouvoir être construit par les providers, fixtures, replay et tests sans dépendre de Pygame ;
- les anciennes assertions `InputState(attack1_held=True)` sont interdites dans la version finale.

`InputManager` expose l’API canonique :

```python
def axis(self, action: InputAction) -> float: ...
def held(self, action: InputAction) -> bool: ...
def just_pressed(self, action: InputAction) -> bool: ...
def just_released(self, action: InputAction) -> bool: ...
```


#### C-2.2 — Politique de parité et de retrait de la façade

La migration suit obligatoirement cet ordre :

```text
contrats → nouvelle API → tests API → PlayerInput → consommateurs → fixtures → parité → suppression façade
```

Avant la suppression, chaque ancien appel doit avoir son équivalent nouveau :

| Ancien contrat | Nouveau contrat |
|---|---|
| `move_axis` | `axis(InputAction.MOVE_X)` |
| `jump_just_pressed` | `just_pressed(InputAction.JUMP)` |
| `jump_just_released` | `just_released(InputAction.JUMP)` |
| `guard_just_pressed` | `just_pressed(InputAction.GUARD)` |
| `attack1_held` | `held(InputAction.ATTACK_1)` |
| `attack1_just_pressed` | `just_pressed(InputAction.ATTACK_1)` |
| `attack1_just_released` | `just_released(InputAction.ATTACK_1)` |
| `attack2_*` | `* (InputAction.ATTACK_2)` |
| `attack3_just_pressed` | `just_pressed(InputAction.ATTACK_3)` |
| `attack4_just_pressed` | `just_pressed(InputAction.ATTACK_4)` |
| `reset_just_pressed` | `just_pressed(InputAction.RESET)` |
| `special_attack_just_pressed` | `just_pressed(InputAction.SPECIAL_ATTACK)` |

La suppression de la façade n’est acceptée qu’après :

- recherche exhaustive des anciennes propriétés dans `src/` et `tests/` ;
- aucun consommateur actif de l’ancienne API ;
- tests de parité clavier/manette ;
- tests des edges, combos, reset et rollback ;
- suite complète, Ruff et mypy verts.

La recherche finale doit notamment être exécutée avec :

```bash
grep -RInE \
  '\.(left_held|right_held|jump_just_pressed|jump_just_released|dash_just_pressed|guard_just_pressed|down_held|attack[1-4]_(held|just_pressed|just_released)|reset_just_pressed|special_attack_just_pressed)' \
  src tests
```

Les seules occurrences autorisées avant retrait sont celles de la façade compatibility explicitement identifiée. Après le lot de retrait, elles doivent être absentes.

#### C-2.3 — Bindings et stratégie de résolution

La forme cible de `InputBindings` est un agrégat explicite de contextes :

```python
@dataclass(frozen=True)
class GameplayBindings:
    keyboard: Mapping[InputAction, int]
    gamepad_buttons: Mapping[InputAction, int]
    gamepad_axes: Mapping[InputAction, int]
    keyboard_combos: Mapping[InputAction, tuple[int, ...]]
    gamepad_combos: Mapping[InputAction, tuple[int, ...]]


@dataclass(frozen=True)
class MenuBindings:
    keyboard: Mapping[InputAction, int]
    gamepad_buttons: Mapping[InputAction, int]
    gamepad_hats: Mapping[InputAction, int]
    gamepad_axes: Mapping[InputAction, int]


@dataclass(frozen=True)
class InputBindings:
    gameplay: GameplayBindings
    menu: MenuBindings
```

Règles :

- les mappings sont des `Mapping` immuables ou remplacés atomiquement ;
- un binding peut pointer vers plusieurs sources, mais une action ne doit pas être écrite par une scène ;


- `gameplay` alimente le polling ; `menu` alimente le routeur UI ;
- `special_attack` reste une action logique ; ses combinaisons sont définies dans `GameplayBindings` ;
- le provider applique la même logique de combo pour clavier et manette et place `SPECIAL_ATTACK` dans `held_actions` ;
- `PlayerInput` ne connaît pas les codes physiques, les touches du clavier ou les numéros de bouton ;
- les liaisons analogiques utilisent une clé d’action explicite (`MOVE_X`, `DASH`) et non une liste magic.

La résolution de direction est une policy documentée :

```text
clavier → stick analogique → hat
oppositions gauche/droite → neutral (0.0)
oppositions clavier/manette → neutral
```

Les seuils sont définis dans `settings.Input` : `AXIS_DEADZONE`, `DASH_AXIS_THRESHOLD`, `UI_AXIS_TRIGGER_THRESHOLD` et les seuils de répétition UI. Le provider normalise l’axe une seule fois ; l’`InputManager` ne réapplique pas de deadzone.

`axis()` accepte uniquement `MOVE_X` et retourne `current_state.move_axis`. Pour les autres actions, `axis()` lève une erreur de contrat explicite ; il ne doit pas inventer une conversion implicite. `held()`, `just_pressed()` et `just_released()` utilisent `held_actions` et les snapshots précédent/courant. `MOVE_X` n’est pas considéré comme une action booléenne par ces trois méthodes.

`PlayerInput` calcule les projections `left_held` et `right_held` à partir de `im.axis(InputAction.MOVE_X)` et du seuil de gameplay ; il ne les demande plus à `InputManager` comme propriétés d’edges historiques.

#### C-2.4 — Portée de la migration obligatoire

Sont migrés avant suppression de la façade :

- `PlayerInputHandler` ;
- les consommateurs de `InputManager` dans les états, contrôleurs et scripts de gameplay ;
- les helpers de doubles de tests ;
- `ScriptedProvider` et les tests de rollback ;
- les éventuels providers replay/network ;
- les tests qui construisent `InputState` ou lisent les anciennes propriétés.

Ne sont pas migrés vers `InputState` : souris, hover, focus, position de menu et sons. Ils restent dans le canal UI.

### C-3 — Actions de menu absentes des bindings — **Ouvert**

`InputBindings` ne contient que des mappings de gameplay. Il n’existe pas d’actions `ui_up`, `ui_down`, `ui_confirm` ou `ui_back`.

**Cible :** bindings séparés par contexte (`gameplay`, `menu`) ou structure équivalente, avec mapping clavier et manette documenté. Le contexte menu doit alimenter le routeur, pas créer une seconde logique de lecture physique.

**Réception :** mappings menu présents par défaut, testés et accessibles au routeur ; mapping Xbox/Standard Gamepad documenté.

### C-4 — Souris absente du chemin menu commun — **Ouvert pour UI**

`InputState` ne contient pas de position ou de bouton souris, ce qui est correct pour la simulation. La souris est déjà traitée par les panneaux debug. Les menus n’ont ni hover ni clic.

**Cible :** traiter `MOUSEMOTION` et `MOUSEBUTTONDOWN` dans le routeur UI, sans ajouter la souris à `InputState`. Focus et rectangles restent la responsabilité de `audit_ui.md`.

### C-5 — Deadzone et seuils dispersés — **Ouvert**

Le provider utilise une deadzone par défaut de `0.2`, tandis que `InputManager` applique `InputSettings.AXIS_DEADZONE = 0.1`. Le dash compare directement l’axe à `0.5`.

**Cible :** centraliser dans `settings.Input` une deadzone et des seuils explicites (`DASH_AXIS_THRESHOLD`, seuil menu futur). Éviter un double filtrage avant le manager.

**Réception :** un test modifiant la deadzone observe un seul point d’application ; aucun littéral fonctionnel de seuil dans `input_provider.py`.

### C-6 — Hat Y et `down` non implémentés — **Ouvert**

Le provider lit l’axe X et le hat X, mais ignore l’axe Y du hat et `down_held` ne reçoit que la touche clavier.

**Cible :** alimenter `down_held` avec clavier, hat Y et stick vertical selon une politique de priorité documentée. Ajouter un faux joystick pour tester les deux directions.

### C-7 — Rebinding et persistance absents — **Ouvert**

La docstring des bindings annonce des mappings personnalisables, mais aucun stockage ou roundtrip n’existe. `SaveGame` ne doit pas être utilisé pour les bindings.

**Cible :** sérialisation versionnée et repository séparé de `savegame.json`, chargement avant la construction du provider, valeurs par défaut et journalisation en cas de fichier absent/corrompu. La capture de touche et l’écran Contrôles restent UI.

### C-8 — Doublons de doubles d’input — **Ouvert**

Plusieurs tests utilisent des doubles proches. Ils ne sont pas tous interchangeables, mais certains peuvent diverger silencieusement.

**Cible :** helper/fixture partagé pour les scénarios de base, avec doubles spécifiques conservés lorsqu’ils testent un contrat particulier. Ne pas supprimer tous les doubles au prix de tests moins lisibles.

### C-9 — SOCD non explicite — **Ouvert**

Le calcul `droite - gauche` donne `0.0` lorsque les deux directions sont pressées, mais cette policy n’est ni nommée, ni documentée, ni testée.

**Cible :** conserver `neutral` et l’implémenter dans une fonction pure ou une petite stratégie testable. Ne pas passer à `last_input_wins` sans décision et tests dédiés.

### C-10 — Contextes de bindings absents — **Ouvert**

Les dictionnaires sont plats et ne distinguent pas gameplay et menu.

**Cible :** contextes nommés, sans dupliquer les codes physiques dans les scènes. Le rebinding écrit dans le contexte approprié.

### C-11 — Plage analogique non bornée explicitement — **Ouvert/optionnel**

Le rescale analogique est borné mathématiquement pour une valeur brute dans `[-1, 1]`, mais aucun `AXIS_RANGE_END` externe n’est défini pour les sticks hors plage.

**Cible :** définir une politique de saturation si du matériel réel le nécessite. Ne pas bloquer le chantier UI sans besoin utilisateur identifié.

## 5. Patterns d’architecture et concepts mobilisés

Les patterns suivants sont des décisions de conception, pas des classes à créer automatiquement. Le code doit rester minimal tant qu’un contrat simple suffit.

| Pattern / concept | État | Décision |
|---|---|---|
| **Ports and Adapters** | Déjà présent implicitement | `InputProvider` est le port de simulation ; `LocalInputProvider` est l’adaptateur Pygame. Conserver la classe actuelle ; n’ajouter un `Protocol` que s’il clarifie les tests. |
| **Injection de dépendances** | Présent | `set_provider()` injecte une source d’état. `apply_remote_state()` est une surface locale de test/replay, pas une fonctionnalité réseau. |
| **Boundary / séparation simulation-UI** | Décision structurante | `InputState` reste réservé au tick fixe. Les événements souris, focus et menu passent par le routeur UI et ne sont jamais ajoutés à `InputState`. |
| **Facade / migration progressive** | Structurant | Les propriétés d’edges existantes sont une façade de compatibilité temporaire, jamais une seconde API concurrente. Elles doivent être retirées après migration vérifiée. |
| **Strangler migration** | À expliciter | Le nouveau chemin d’actions est introduit progressivement, puis `PlayerInput`, les tests et les systèmes sont migrés avant suppression de l’ancien chemin. |
| **Null Object** | Présent | `NullInputProvider` fournit un état neutre. Les consommateurs ne doivent pas gérer `None` comme une source ordinaire. |
| **Adapter Pygame → gameplay** | Présent | `LocalInputProvider` traduit clavier/manette en `InputState`. |
| **Adapter Pygame → UI** | À créer | `EventRouter` traduira clavier/souris/manette en actions UI typées. |
| **Anti-Corruption Layer** | À formaliser | Le routeur empêche les scènes de connaître les codes physiques Pygame et les événements bruts. |
| **Pipeline** | Implicite, à documenter | Événement brut → traduction → contexte → priorité → action structurée. |
| **Strategy / Policy** | Partiel et à cadrer | Une fonction ou petite stratégie suffit pour clavier > analogique > hat et SOCD `neutral`. Éviter une hiérarchie de classes spéculative. |
| **Repository** | À créer pour les bindings | `SaveGame` reste la progression ; un repository séparé gère les préférences. Le premier backend peut être JSON. |
| **Schema versioning / migration** | À formaliser avec la persistance | Valider le schéma, gérer les versions inconnues et falling back vers les valeurs par défaut. |
| **Dispatcher explicite** | À nommer lors de l’intégration | Un composant unique distribue les événements UI à la scène active. Pas d’`EventBus` global. |
| **Registry / table d’actions** | À utiliser avec parcimonie | Une table typée peut remplacer les longues chaînes de tests ; ne pas y cacher la logique gameplay. |
| **Value Object / DTO** | Partiel | `InputState` est un snapshot de données pour la simulation. `RoutedInput` pourra être un objet gelé pour les événements UI. |
| **Immutabilité des configuration** | À spécifier | Bindings et seuils sont remplacés atomiquement et ne sont pas modifiés pendant un tick. |
| **Model / Controller / View** | À traiter dans `audit_ui.md` | `MenuModel` gère l’état ; le contrôleur traduit les actions ; la vue gère rectangles et rendu. |

### 5.1. Contrat de responsabilité recommandé

```text
Pygame / périphérique
        ↓
LocalInputProvider ──polling──→ InputState ──→ InputManager ──→ gameplay
        ↓
     actions typées
        ↓
EventRouter ──RoutedInput──→ InputDispatcher ──→ MenuController ──→ MenuModel
                                                                    ↓
                                                              MenuView / scène
```

- Le provider normalise les périphériques pour la simulation.
- L’`InputManager` conserve les edges et l’état précédent.
- L’`EventRouter` traduit les événements Pygame pour l’UI.
- Le dispatcher possède le point d’entrée unique vers la scène active.
- Le contrôleur UI ne connaît ni les touches physiques ni les événements bruts.
- Le modèle UI ne dépend pas de Pygame.
- La vue ne modifie pas directement les bindings ni le provider.

### 5.2. Contrat de `RoutedInput`

Le futur événement UI doit être un objet structuré et testable, par exemple :

```python
@dataclass(frozen=True)
class RoutedInput:
    action: InputAction
    device: InputDevice
    position: tuple[int, int] | None = None
    value: float | None = None
```

Le contrat doit préciser la représentation des événements répétés, de la position souris, des axes et de la perte d’un périphérique. Le format exact doit être testé avant d’être repris par les scènes.



## 6. Décisions conservées

| ID | Décision |
|---|---|
| C-D1 | Garder `InputState` limité à la simulation ; ne pas y ajouter les événements UI. |
| C-D2 | Utiliser un seul routeur d’événements UI ; aucun `EventBus` global. |
| C-D3 | La souris reste hors simulation ; position et activation sont des résultats UI. |
| C-D4 | Les seuils vivent dans `settings.Input` ; `AXIS_RANGE_END` reste optionnel tant qu’un besoin réel n’est pas démontré. |
| C-D5 | Le hat Y et le stick vertical alimentent `down`, avec priorité clavier > analogique > hat, à tester. |
| C-D6 | Le stockage des bindings est porté par l’audit contrôles ; l’écran de capture reste UI. |
| C-D7 | Conserver `set_provider` et `apply_remote_state` ; formaliser le port avec un `Protocol` seulement si cela clarifie les tests. |
| C-D8 | Réduire les doublons par helper/fixture commun sans supprimer les doubles spécifiques justifiés. |
| C-D9 | L’API d’actions gameplay est le chemin canonique ; la migration de tous les consommateurs est obligatoire avant de considérer le socle terminé. La façade des anciennes propriétés est temporaire. |
| C-D10 | SOCD `neutral` : directions opposées → axe zéro. |
| C-D11 | Bindings par contextes `gameplay` et `menu`. |
| C-D12 | Le dispatcher UI est explicite et injecté à un seul point d’entrée. |
| C-D13 | Les patterns sont documentés comme décisions ; aucune classe n’est créée au seul motif de nommer un pattern. |

## 7. Plan futur, sans implémentation

### C-Lot 0a — Migration massive de l’API gameplay et socle UI

- définir `InputAction` et le contexte `gameplay` ;
- faire de `InputManager` l’unique façade gameplay avec `held/just_pressed/just_released` ;
- migrer `PlayerInput`, les contrôleurs, combos, actions de reset et les scripts ;
- migrer les providers de test, fixtures et helpers vers l’API par actions ;
- vérifier la parité clavier/manette, edges, combos et rollback avant suppression ;
- conserver les anciennes propriétés comme `Compatibility Facade` pendant la transition uniquement ;
- supprimer la façade historique dans un lot final, après grep et suite complète ;
- structurer les bindings par contexte `gameplay`/`menu` ;
- centraliser deadzone et seuil dash dans `settings.Input` ;
- définir le contrat du futur `RoutedInput` et le dispatcher UI.

Ce lot est obligatoire avant la navigation UI. Il n’est pas acceptable de commencer les menus en conservant les propriétés manuelles comme interface principale.

### C-Lot 0b — Routeur et dispatcher UI

- créer `src/core/input/event_router.py` ;
- router clavier, souris, boutons, hat et axes vers des actions UI typées ;
- définir `RoutedInput` et son contrat de données ;
- créer ou nommer le dispatcher qui distribue à la scène active ;
- brancher ce chemin une seule fois dans `Game`/`SceneManager` ;
- faire consommer les résultats par les scènes sans mettre la souris dans `InputState`.

### C-Lot 0c — Hygiène manette

- hat Y et stick vertical ;
- alimenter `down` ;
- tester deadzone, priorités, combo, connexion/déconnexion et SOCD ;
- tester `JOYDEVICEREMOVED` et le reassign ;
- utiliser un faux joystick scriptable pour les tests headless.

Ce lot peut suivre en parallèle, mais il doit être terminé avant de déclarer la manette supportée dans les menus.

### C-Lot 0d — Persistance

- sérialisation versionnée et validation des bindings ;
- repository/config store séparé de `savegame.json` ;
- chargement avant création du provider ;
- fichier absent ou corrompu → valeurs par défaut sans crash ;
- distinguer validation de schéma, migration et fallback.

### Dépendance UI

```text
C-Lot 0a (migration massive + socle UI) → C-Lot 0b → navigation UI
C-Lot 0c peut suivre en parallèle, avant validation de la manette menu
C-Lot 0d → écran Contrôles / rebinding UI
```

`audit_ui.md` garde la responsabilité du `MenuModel`, du focus, des rectangles, du rendu, des options et des scènes. L’audit contrôles porte le provider, les bindings, le routeur, le dispatcher, les événements et les seuils.

## 8. Règles de future implémentation

1. Ne pas router le gameplay via `EventBus` ni remplacer le polling fixe par les événements UI.
2. Ne pas ajouter la souris aux actions de simulation.
3. Garder les propriétés d’edges existantes uniquement comme `Compatibility Facade` pendant la migration ; les supprimer après parité complète.
4. Tester avec `SDL_VIDEODRIVER=dummy`, événements injectés et faux joystick scriptable.
5. Modifier les seuils avec tests avant/après et vérifier l’absence de régression gameplay.
6. Ne pas considérer `apply_remote_state()` comme une fonctionnalité réseau complète : c’est une surface d’injection locale.
7. Toute divergence avec `audit_ui.md` doit être explicitement arbitrée dans les deux documents.
8. Ne pas créer de hiérarchie de patterns spéculative : une fonction, une stratégie ou un objet simple suffit tant que le contrat reste testable.
9. Ne pas modifier les bindings ou les seuils en place pendant un tick.
10. Le routeur doit produire des actions stables et testables ; les scènes ne doivent pas traduire à nouveau les touches physiques.

## 9. Non-objectifs

- ne pas remplacer le polling gameplay par les événements Pygame ;
- ne pas mettre la souris dans `InputState` ;
- ne pas créer d’`EventBus` global ;
- ne pas créer une classe `Command` pour chaque action simple ;
- ne pas créer une hiérarchie de `Strategy` pour chaque périphérique sans variation de politique ;
- ne pas créer un repository générique avant l’existence d’un second backend ;
- ne pas déclarer le support de la manette avant les tests de hat Y, stick vertical, SOCD et connexion/déconnexion ;
- ne pas conserver les anciennes propriétés gameplay comme interface principale après la migration ;

## 10. Réception future

- [ ] actions `ui_*` déclarées dans le vocabulaire commun et routées hors simulation ;
- [ ] `InputAction` et la table des actions gameplay sont livrés ;
- [ ] `InputManager.held/just_pressed/just_released` sont l’API canonique ;
- [ ] `PlayerInput`, contrôleurs, combos, reset et tests utilisent l’API par actions ;
- [ ] l’ancienne façade d’edges est supprimée après parité complète ;
- [ ] bindings `gameplay`/`menu` présents ;
- [ ] contrat `RoutedInput` documenté et testé ;
- [ ] routeur clavier/souris/manette fonctionnel ;
- [ ] dispatcher UI unique et explicite ;
- [ ] parcours clavier historique inchangé ;
- [ ] une seule deadzone et seuils centralisés ;
- [ ] hat Y/stick vertical et SOCD `neutral` testés ;
- [ ] ajout et retrait de manette testés ;
- [ ] helper input partagé et doublons réduits ;
- [ ] roundtrip/rechargement des bindings si C-Lot 0d est livré ;
- [ ] `ruff check src tests`, `mypy src` et suite complète verts.

## 11. Commandes de vérification actuelles

```bash
uv run pytest -q \
  tests/headless/test_input_manager.py \
  tests/unit/test_runtime_and_paths.py \
  tests/headless/test_scenes.py \
  tests/unit/test_player.py \
  tests/unit/test_player_controllers.py

uv run ruff check src tests
uv run mypy src
git diff --check
```

Références utiles :

- `src/core/input/input_bindings.py`
- `src/core/input/input_provider.py`
- `src/core/input/input_manager.py`
- `src/core/input/input_state.py`
- `src/core/game.py`
- `src/entities/player_input.py`
- `src/application/scene_manager.py`
- `src/application/scenes/menu_scene.py`
- `src/application/scenes/pause_scene.py`
- `src/application/scenes/gameover_scene.py`
- `src/ui/panel_renderer.py`
- `tests/headless/test_input_manager.py`
- `tests/unit/test_runtime_and_paths.py`

## 12. Historique et validation

- Audit initial : conservation de l’ancien document dans Git.
- Réécriture : 2026-09-24 contre `master` à `afe044f`.
- Livraisons constatées le 2026-09-24 (branche `feat/audit-ui-implementation`) :
  C-Lot 0d (bindings persistés dans `settings.json`) et l’écran Contrôles /
  rebinding (`src/application/scenes/controls_scene.py`, UI-5). `EventRouter`
  expose `would_route_key` / `would_route_button` (peek sans état) pour que la
  capture de touche ne déclenche pas l’action qu’elle route.
- Arbitrage avec `notes/audit_ui.md` §3/§5 : l’écran Contrôles reste de
  responsabilité UI ; le routeur, les bindings et les seuils restent couverts ici.
- Correction des patterns : 2026-09-24, après fact-check de l’audit réécrit.
- Validation de référence : 82 tests ciblés passés ; Ruff, mypy (142 fichiers) et `git diff --check` passés.
- Les constats et décisions utiles de l’ancienne version sont conservés ; les patterns implicites sont maintenant nommés et les non-objectifs sont explicités.
- Aucun code de contrôle n’a été modifié lors de cette correction documentaire.
- L’implémentation des lots reste volontairement bloquée jusqu’à validation de ce document.
- Rafraîchissement du 2026-09-26 contre `40ca5a9` : **base de validation seulement**
  (HEAD, 52 → 82 tests ciblés, mypy 142 fichiers). Aucun fichier de
  `src/core/input/` n’a bougé depuis le 2026-09-24 ; le seul fichier de ce périmètre
  touché est `src/core/game.py`, sur la cadence de la boucle. La matrice §3, les
  constats C-1 à C-7 et la réception §10 sont donc inchangés — ils décrivent
  l’état *avant* implémentation, ce que le bandeau du document annonce
  explicitement. La remise à jour des livraisons de ces lots ne peut se faire
  qu’après validation de ce document, pas dans le cadre de cette mise à jour.
