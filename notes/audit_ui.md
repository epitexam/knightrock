# Audit UI — Interface, navigation et paramétrage

> Audit réécrit le 2026-09-24 contre `master` au commit `afe044f`.
> L’historique des versions précédentes reste conservé dans Git.

## 1. Verdict exécutif

Le codebase possède un socle UI technique sain (`SceneManager`, panneaux, interactions debug, HUD joueur), mais l’interface de jeu reste volontairement minimale :

- les menus principal, pause et game over sont clavier-only ;
- il n’existe pas encore de modèle de focus/hover menu ;
- il n’existe pas de scène Options, Level Select ou Victory ;
- il n’existe pas de réglages vidéo/audio persistés ;
- il n’existe pas de rebinding ;
- l’audio n’est pas implémenté.

Le HUD joueur et le gating des panneaux debug sont désormais livrés et ne doivent pas être réimplémentés.

**État au 2026-09-24 (branche `feat/audit-ui-implementation`) :** les lots 0 à 4 sont
livrés et vérifiés — navigation clavier / souris / manette, `MenuModel`/`MenuView`,
Options, Level Select, Victory, `ui.scale`, bindings persistés, écran Contrôles
(rebinding clavier et manette) et redimensionnement utilisateur.  Restent ouverts :
l’audio (lot 5, optionnel) et un tutoriel de contrôles gameplay (UI-8, partiel).

## 2. Base vérifiée

- **HEAD :** `afe044f` (`master`)
- **Historique UI :** `4f8b025` → `1f5e3fa` → état courant
- **Périmètre :** `src/application/`, `src/ui/`, `src/core/game.py`, `src/core/input/`, `src/core/settings.py`, tests associés.
- **Validation de référence :** suite complète à 910 tests ; Ruff et mypy propres.
- **Mise à jour d’état :** 2026-09-24, branche `feat/audit-ui-implementation` —
  981 tests verts avec et sans `DEBUG`, 89 % instructions / 86 % branches,
  Ruff et mypy (138 fichiers) propres.

Les références de lignes de l’ancienne version ne sont pas reproduites telles quelles : elles sont remplacées par les chemins de fichiers et les tests qui définissent désormais le contrat.

## 3. Matrice d’état

| Domaine | État actuel | Statut | Preuve |
|---|---|---|---|
| Menus clavier | Touches par défaut + actions `ui_*` routées | **Clos** | `event_router.py`, `menu_model.py`, tests headless |
| Menus souris | Hover, clic gauche, clic droit = retour | **Clos** | `MenuModel.hover`, `test_scenes.py` (pointeur) |
| Menus manette | Boutons, hat et stick (repeats inclus) | **Clos** | `event_router._route_hat/_route_axis`, `test_menu_navigation_supports_stick_and_hat` |
| Modèle focus/hover | `MenuModel` + `MenuView` (rects, wrap, items désactivés) | **Clos** | `src/ui/menu_model.py`, `src/ui/menu_view.py` |
| Scène Options | UI scale, plein écran, vsync, stick Y, contrôles | **Clos** | `options_scene.py`, `test_options_scene.py` |
| Rebinding/persistance | Écran Contrôles + `settings.json` versionné | **Clos** | `settings_store.py`, `controls_scene.py`, `test_controls_scene.py` |
| Réglages vidéo | Fenêtre `RESIZABLE`, plein écran, vsync, redimensionnement | **Clos** | `game.py` (`_configure_display`, `_resize_display`) |
| Audio | Absent (asset de navigation fourni) | Ouvert | lot 5 optionnel : aucun mixer / `Sound` |
| HUD joueur | Vie, posture, dash et combo | **Clos** | `src/ui/hud.py`, `GameplayScene.draw` |
| Panneau COMBAT hors debug | Gaté | **Clos** | `WorldUI.draw_metrics_panel`, tests debug |
| Aide aux contrôles joueur | Écran Contrôles listant les bindings | Partiel | `controls_scene.py` ; pas de tutoriel gameplay |
| Level Select | Livré (progression `SaveGame`) | **Clos** | `level_select_scene.py`, tests headless |
| Victory Scene | Livrée (fin du dernier niveau) | **Clos** | `victory_scene.py`, tests headless |
| `ui.scale` | 0.8 / 1.0 / 1.2, persisté, appliqué au rendu | **Clos** | `settings_store.py`, `MenuView.set_scale` |
| Debug panels interactifs | Souris close/drag, F1–F10 | Clos | `panel_renderer.py`, `GameplayScene` |
| Sauvegarde progression | JSON avec fallback | Clos | `save_game.py`, tests save |

## 4. Capacités existantes à préserver

### 4.1 Architecture des scènes

`SceneManager` fournit déjà `switch()`, `push()` et `pop()`. Les futures Options, Level Select et Victory doivent utiliser cette API sans refonte du manager.

### 4.2 HUD joueur

`src/ui/hud.py` fournit un HUD screen-space avec vie, posture, dash, combo, seuils de couleur, layout responsive et rects dirty. `GameplayScene.draw()` le dessine après le niveau, même sans `DEBUG`.

**Ne pas recréer un HUD ni ajouter une barre world-space au joueur.**

### 4.3 Debug UI

Le debug conserve déjà hitboxes, hurtboxes, vecteurs, labels, timeline, panels, métriques, F1–F10, fermeture de panels au clic, drag-and-drop, export F9 et rejeu F8. Ces capacités sont hors scope de l’UI joueur.

## 5. Constats : état de livraison

| Constat | Statut | Preuve |
|---|---|---|
| UI-1 Navigation souris | **Clos** | `MenuModel.hover`, `MenuView.item_rects`, parcours pointeur headless |
| UI-2 Navigation manette | **Clos** | `event_router` (boutons, hat, stick, repeats), tests headless |
| UI-3 Modèle de sélection | **Clos** | `src/ui/menu_model.py`, `src/ui/menu_view.py`, tests unitaires |
| UI-4 Options | **Clos** | `options_scene.py`, accessible depuis menu et pause |
| UI-5 Rebinding et settings | **Clos** | `settings_store.py` + `controls_scene.py` (capture touche/bouton + persistance) |
| UI-6 Vidéo | **Clos** | `game.py` : `RESIZABLE`, `FULLSCREEN|SCALED`, vsync, `VIDEORESIZE` |
| UI-8 Aide aux contrôles | Partiel | l’écran Contrôles liste les bindings ; pas de tutoriel gameplay |
| UI-9 Parcours de progression | **Clos** | `level_select_scene.py`, `victory_scene.py`, tests headless |
| UI-10 Audio | Ouvert | lot 5 optionnel : aucun mixer / `Sound` (asset de navigation fourni) |
| UI-13 Accessibilité UI | **Clos** | `ui.scale` persisté, `MenuView` recalculé à chaque dessin |

Comportements de retour verrouillés par des tests (toute modification demande une
décision explicite et la mise à jour des deux documents) :

- pause : bouton B / clic droit / ESC = **reprise** (`PauseScene` → `pop`) ;
- menu principal : ESC / bouton B = **quitter** (`MenuScene` → `running = False`) ;
- gameplay : bouton B / clic droit = **pause** (`GameplayScene` → `push(PauseScene)`).

### UI-1 — Navigation souris

Les scènes de menu filtrent `KEYDOWN`. La souris existe uniquement pour les panneaux debug via `MOUSEMOTION` et `MOUSEBUTTON*`.

**Manque :** position de curseur, hover d’item, clic sur Rect et propagation vers le modèle de menu.

### UI-2 — Navigation manette

Le joystick est géré pour le gameplay, mais aucune action `ui_up`, `ui_down`, `ui_confirm` ou `ui_back` n’est routée vers les scènes menu.

**Manque :** boutons, hat et stick vertical avec seuil dans le routeur d’entrée.

### UI-3 — Modèle de sélection

Il n’existe pas de `MenuModel` ou `menu_view.py`.

**Manque :** index partagé entre clavier, manette et souris ; hover ; wrap ; item désactivé ; rectangles de rendu.

### UI-4 — Options

Il n’existe pas de scène Options. Elle doit être accessible depuis le menu principal et la pause, avec retour par `pop()`.

### UI-5 — Rebinding et settings

`InputBindings` ne possède pas de contrat de persistance et `settings.json` n’existe pas.

**Manque :** store versionné, valeurs par défaut, fichier corrompu sans crash, section bindings et sections vidéo/audio/ui.

### UI-6 — Vidéo

`Game._initialize()` appelle :

```python
pygame.display.set_mode((Display.WIDTH, Display.HEIGHT))
```

Il n’y a pas de `RESIZABLE`, `FULLSCREEN`, `SCALED` ou vsync. L’ancien audit indiquait `FPS = 180` : la valeur actuelle est `FPS = 60`, tandis que le commentaire mentionne 120 FPS. Le problème courant est l’absence de réglages vidéo et l’incohérence commentaire/valeur.

### UI-8 — Aide aux contrôles

Le panneau actuel est une aide debug (`1-6`, V/B, G/P/T, F1–F10), pas un écran de contrôles joueur généré depuis les bindings.

### UI-9 — Parcours de progression

`SaveGame.unlocked_levels` existe, mais aucun menu ne permet de choisir un niveau. La fin du dernier niveau retourne directement au menu.

### UI-10 — Audio

Aucun système audio n’existe : pas de mixer, pas de sons, pas de volumes persistés.

### UI-13 — Accessibilité UI

Il n’existe pas de réglage `ui.scale` (`small`, `normal`, `large`). Les tailles de police sont fixes.

## 6. Points explicitement hors scope

- Grab/throw et gameplay ;
- niveaux, attaques, physique ou combat ;
- rollback réseau ;
- refonte de `SceneManager` ;
- suppression des outils debug ;
- ajout d’un framework UI externe.

## 7. Dépendance obligatoire : audit contrôles

`notes/audit_controles.md` reste le prérequis pour les entrées UI. Avant le lot navigation UI, il faut traiter ou valider :

- C-1 : routeur d’événements commun ;
- C-2 : migration massive de l’API gameplay et retrait de la façade d’edges ;
- C-3 : actions de menu ;
- C-4 : souris hors simulation ;
- C-5/C-6 : mapping manette et deadzones ;
- C-7 : bindings persistés.

La séparation responsibilities doit rester :

```text
audit_controles : provider, bindings, routeur, événements et seuils
audit_ui        : MenuModel, MenuView, scènes, HUD, options et feedback
```

## 8. Plan d’implémentation futur

### Lot 0 — Valider le socle contrôles — **Livré**

- terminer C-2 : migration massive de l’API gameplay, parité et retrait de la façade d’edges ;
- routeur `KEYDOWN`, `MOUSE*`, `JOYBUTTON*`, `JOYHAT*`, `JOYAXIS*` ;
- actions `ui_*` ;
- seuils et deadzones ;
- hot-plug et tests headless.

### Lot 1 — Navigation clavier et modèle de menu — **Livré**

Créer :

- `src/ui/menu_model.py` ;
- `src/ui/menu_view.py` ;
- `tests/unit/test_menu_model.py` ;
- `tests/unit/test_menu_view.py`.

Convertir les trois scènes menu sans toucher au gameplay.

### Lot 2 — Souris et manette — **Livré**

Brancher le routeur sur `MenuModel` :

- `MOUSEMOTION` → hover ;
- clic → activation ;
- hat/stick → déplacement ;
- bouton confirmer/back → activation/retour.

Ajouter les parcours headless des trois périphériques.

### Lot 3 — Persistance et Options — **Livré**

Créer :

- `src/application/settings_store.py` ;
- `src/application/scenes/options_scene.py` ;
- tests settings/options.

Implémenter vidéo, audio UI, scale et lecture des bindings. Ne pas réimplémenter la couche bindings si `audit_controles` la fournit.

Livré en complément (vérification 2026-09-24) :

- **écran Contrôles** (`controls_scene.py`, UI-5) : rebinding clavier et boutons
  manette, paire gauche/droite pour `move_x`, raccourci nouvelle partie, annulation
  par ESC / clic droit / bouton B. La capture est neutralisée côté routeur par
  `EventRouter.would_route_key` / `would_route_button` : l’appui qui termine la
  capture ne déclenche pas l’action qu’il route ;
- **redimensionnement** (`Game._resize_display`) : `VIDEORESIZE` recrée la surface,
  clampe la taille aux bornes de `settings_store` et la propage aux scènes ; la
  taille reste en mémoire et sera persistée au prochain `apply_settings` ;
- **nettoyage** : `src/application/scenes/menu_panel.py` supprimé (code mort, plus
  aucun appelant de production) ; tous les écrans passent par `MenuView`.

### Lot 4 — Parcours joueur — **Livré**

Créer :

- `src/application/scenes/level_select_scene.py` ;
- `src/application/scenes/victory_scene.py` ;
- tests associés.

Brancher la sélection de niveau et la victoire sur la progression.

### Lot 5 — Audio et polish optionnels — **Ouvert (optionnel)**

Créer `AudioBus`, hooks EventBus, fades et sons de navigation. Ce lot reste optionnel tant que l’audio n’est pas requis par le produit.

Asset déjà fourni pour la navigation :
`assets/sounds/universfield-computer-mouse-click-02-383961.mp3` (le dossier réel
est `assets/sounds/`, il n’y a pas de dossier `assets/audio/`). Cible du lot :
`pygame.mixer`, un `AudioBus` abonné à l’EventBus, un son de déplacement et un son
de validation dans les menus, plus une section volume persistée dans
`settings.json` (à valider avec les bornes du store).

## 9. Réception globale — état

- [x] Menu clavier, souris et manette produisent les mêmes transitions.
- [x] Options accessible depuis menu et pause.
- [x] `settings.json` round-trip et fichier corrompu sans crash.
- [x] Vidéo : fenêtre, plein écran, vsync et redimensionnement.
- [x] Rebinding clavier / manette persisté depuis l’écran Contrôles.
- [x] Level Select et Victory fonctionnels.
- [x] HUD présent sans `DEBUG`.
- [x] Aucun panneau COMBAT/clash visible sans `DEBUG`.
- [x] Tests UI, Ruff, format, mypy et suite complète verts.
- [ ] Audio : mixer, sons de navigation, volumes (lot 5).

## 10. Commandes de vérification

```bash
env -u DEBUG uv run pytest -q
DEBUG=1 uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
```

Recherche d’absence audio :

```bash
grep -rnE 'pygame\\.mixer|Sound\\(|music\\.' src/
```

Recherche des scènes UI prévues :

```bash
ls src/application/scenes/
test -e src/ui/menu_model.py
test -e src/ui/menu_view.py
test -e src/application/settings_store.py
```

## 11. Historique et validation

- Audit initial : `4f8b025`.
- Mise à jour UI/debug/HUD : `1f5e3fa`.
- Réécriture courante : 2026-09-24 contre `afe044f`.
- Vérification d’implémentation : 2026-09-24, branche `feat/audit-ui-implementation` —
  lots 0–4 clos, écran Contrôles et redimensionnement livrés, `menu_panel.py` supprimé,
  matrice §3 et réception §9 mises à jour.
