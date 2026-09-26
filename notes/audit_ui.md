# Audit UI — Interface, navigation et paramétrage

> Audit réécrit le 2026-09-24 contre `master` au commit `afe044f`, mis à jour le
> 2026-09-26 contre `40ca5a9` (lot 6, cohérence de frame et cadence).
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

**État au 2026-09-26 (`40ca5a9`) :** le lot 6 est livré — une seule transform de
frame (le blend est porté par la caméra), `Camera.apply_covering()` pour tout ce que
le renderer blitte, les barres HP ancrées sur les rects réellement blittés, les
rectangles overlay déclarés au renderer, et une boucle cadencée une seule fois. La
section 3 et le lot 6 de la section 8 portent les preuves. Restent ouverts : l’audio
(lot 5), le tutoriel gameplay (UI-8), le réglage de limite de frames (lot 7,
planifié dans `notes/plan_limit_frames_video.md`) et l’écart O10 consigné dans
`notes/ecarts_ouverts.md` (la suite n’est pas verte avec `DEBUG=1`).

## 2. Base vérifiée

- **HEAD :** `40ca5a9` (`master`)
- **Historique UI :** `4f8b025` → `1f5e3fa` → `afe044f` (état du 2026-09-24) → `40ca5a9`
- **Périmètre :** `src/application/`, `src/ui/`, `src/core/game.py`, `src/core/input/`, `src/core/settings.py`, `src/core/rendering/`, tests associés.
- **Validation de référence (2026-09-26) :** suite complète à **1117 tests** verts
  (`env -u DEBUG uv run pytest -q`) ; 89 % instructions / 86 % branches, Ruff et
  format propres, `mypy src` (142 fichiers) et `mypy src main.py tools` (144
  fichiers, la commande CI) propres.
- **Réserve connue :** `DEBUG=1 uv run pytest -q` est **rouge sur 1 test**,
  `test_frame_presentation.py::test_level_draw_presents_the_health_bar_rects`. Le
  chemin debug fait toujours un refresh complet, donc `Level.draw` renvoie `None`
  et rien n’est présenté partiellement. Le même test échoue aussi **isolé**, avec ou
  sans `DEBUG` : il dépend d’un test précédent qui agrandit l’écran, sans quoi la
  barre de l’ennemi est cullée. Consigné comme O10 dans `notes/ecarts_ouverts.md`,
  non corrigé.

Les références de lignes de l’ancienne version ne sont pas reproduites telles quelles : elles sont remplacées par les chemins de fichiers et les tests qui définissent désormais le contrat.

## 3. Matrice d’état

| Domaine | État actuel | Statut | Preuve |
|---|---|---|---|
| Menus clavier | Touches par défaut + actions `ui_*` routées | **Clos** | `event_router.py`, `menu_model.py`, tests headless |
| Menus souris | Hover, clic gauche, clic droit = retour | **Clos** | `MenuModel.hover`, `test_scenes.py` (pointeur) |
| Menus manette | Boutons, hat et stick (repeats inclus) | **Clos** | `event_router._route_hat/_route_axis`, `test_menu_navigation_supports_stick_and_hat` |
| Modèle focus/hover | `MenuModel` + `MenuView` (rects, wrap, items désactivés) | **Clos** | `src/ui/menu_model.py`, `src/ui/menu_view.py` |
| Scène Options | Hub de navigation (Video settings, Controls) | **Clos** | `options_scene.py`, `test_options_scene.py` |
| Rebinding/persistance | Écran Contrôles + `settings.json` versionné | **Clos** | `settings_store.py`, `controls_scene.py`, `test_controls_scene.py` |
| Réglages vidéo | Résolutions prédéfinies (écran de sélection), plein écran `SCALED` (letterbox), vsync | **Clos** | `game.py` (`_configure_display`), `video_scene.py`, `resolution_scene.py` |
| Audio | Absent (asset de navigation fourni) | Ouvert | lot 5 optionnel : aucun mixer / `Sound` |
| HUD joueur | Vie, posture, dash et combo | **Clos** | `src/ui/hud.py`, `GameplayScene.draw` |
| Panneau COMBAT hors debug | Gaté | **Clos** | `WorldUI.draw_metrics_panel`, tests debug |
| Aide aux contrôles joueur | Écran Contrôles listant les bindings | Partiel | `controls_scene.py` ; pas de tutoriel gameplay |
| Level Select | Livré (progression `SaveGame`) | **Clos** | `level_select_scene.py`, tests headless |
| Victory Scene | Livrée (fin du dernier niveau) | **Clos** | `victory_scene.py`, tests headless |
| `ui.scale` | 0.8 / 1.0 / 1.2, persisté, appliqué au rendu | **Clos** | `settings_store.py`, `MenuView.set_scale` |
| Debug panels interactifs | Souris close/drag, F1–F10, F4 statics **off par défaut** | Clos | `panel_renderer.py`, `world_ui.py:319`, `GameplayScene` |
| Sauvegarde progression | JSON avec fallback | Clos | `save_game.py`, tests save |
| Cohérence de frame | Une seule transform : le blend est dans la caméra | **Clos** | `Camera.begin_frame`, `test_frame_coherence.py` |
| Arrondi écran sortant | `apply_covering()` : floor/ceil, arêtes lointaines depuis `apply` | **Clos** | `camera.py:166-197`, `test_camera_zoom.py` |
| Rectangles overlay | HUD et barres HP déclarés au renderer pour l’erase et le present | **Clos** | `level.py:340`, `gameplay_scene.py:231`, `test_no_stale_pixels.py` |
| Présentation partielle | Une frame portant des overlay rects ne prend jamais le chemin partiel | **Clos** | `test_frame_coherence.py` |
| Cadence de boucle | Present = seul pacer sous vsync, plafond dérivé de `Display.FPS` | **Clos** | `game.py:40,250-277`, `test_frame_pacing.py` |
| Limite de frames (menu vidéo) | Absente, planifiée | Ouvert | lot 7, `notes/plan_limit_frames_video.md` |

## 4. Capacités existantes à préserver

### 4.1 Architecture des scènes

`SceneManager` fournit déjà `switch()`, `push()` et `pop()`. Les futures Options, Level Select et Victory doivent utiliser cette API sans refonte du manager.

### 4.2 HUD joueur

`src/ui/hud.py` fournit un HUD screen-space avec vie, posture, dash, combo, seuils de couleur, layout responsive et rects dirty. `GameplayScene.draw()` le dessine après le niveau, même sans `DEBUG`.

**Ne pas recréer un HUD ni ajouter une barre world-space au joueur.**

### 4.3 Debug UI

Le debug conserve déjà hitboxes, hurtboxes, vecteurs, labels, timeline, panels, métriques, F1–F10, fermeture de panels au clic, drag-and-drop, export F9 et rejeu F8. Ces capacités sont hors scope de l’UI joueur.

Deux règles ont été ajoutées le 2026-09-25 et sont à considérer comme du contrat :

- **`F4` statics est off par défaut** (`world_ui.py:319`). Un niveau porte ~970
  tuiles de terrain dont le contour n’apprend rien, et `_debug_reference` — le
  poste le plus lourd de la frame — leur coûtait 2.8 ms. Le gate `statics` passe
  maintenant **avant** la construction de la référence : le test de type exact qui
  précédait (`type(sprite) is pygame.sprite.Sprite`) ne matchait jamais, les tuiles
  étant des sous-classes, donc chaque tuile payait l’allocation avant que le
  toggle puisse l’éviter. Mesuré sur le niveau 0 (972 sprites) en `DEBUG=1` :
  p50 6.0 → 4.3 ms, p95 7.3 → 6.2 ms, pire 15.0 → 12.8 ms.
- **L’overlay lit la même transform que le monde.** Il ne se punit plus lui-même à
  `alpha = 1.0` : c’est la caméra qui interpole, une fois par frame, et l’overlay
  passe par le même `camera.apply`. Conséquence : plus aucun debug ne se détache
  du sprite qu’il annote, et les deux contournements construits autour de l’ancien
  split (la map des rects blittés pour les barres, le pin à 1.0) ont disparu.

## 5. Constats : état de livraison

| Constat | Statut | Preuve |
|---|---|---|
| UI-1 Navigation souris | **Clos** | `MenuModel.hover`, `MenuView.item_rects`, parcours pointeur headless |
| UI-2 Navigation manette | **Clos** | `event_router` (boutons, hat, stick, repeats), tests headless |
| UI-3 Modèle de sélection | **Clos** | `src/ui/menu_model.py`, `src/ui/menu_view.py`, tests unitaires |
| UI-4 Options | **Clos** | `options_scene.py` : hub sans réglage propre, chaque valeur dans l'écran qui la possède (Video / Controls) |
| UI-5 Rebinding et settings | **Clos** | `settings_store.py` + `controls_scene.py` (capture touche/bouton + persistance) |
| UI-6 Vidéo | **Clos** | `game.py` : fenêtre **non redimensionnable** (viewport logique stable), `FULLSCREEN|SCALED` avec letterbox, vsync, `VIDEORESIZE` ignoré ; cadence livrée (voir UI-14) |
| UI-8 Aide aux contrôles | Partiel | l’écran Contrôles liste les bindings ; pas de tutoriel gameplay |
| UI-9 Parcours de progression | **Clos** | `level_select_scene.py`, `victory_scene.py`, tests headless |
| UI-10 Audio | Ouvert | lot 5 optionnel : aucun mixer / `Sound` (asset de navigation fourni) |
| UI-13 Accessibilité UI | **Clos** | `ui.scale` persisté, `MenuView` recalculé à chaque dessin |
| UI-14 Cohérence de frame et cadence | **Clos** | `Camera.begin_frame` / `apply_covering`, `add_overlay_rects`, `Game._frame_delta`, `test_frame_coherence.py`, `test_frame_pacing.py`, `test_no_stale_pixels.py` |
| UI-15 Limite de frames (menu vidéo) | Ouvert, planifié | lot 7, `notes/plan_limit_frames_video.md` ; `UserSettings` n’a pas encore `fps_limit` |

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

Avant l’implémentation de la UI, `Game._initialize()` appelait `pygame.display.set_mode((Display.WIDTH, Display.HEIGHT))` en dur, sans `RESIZABLE`, `FULLSCREEN`, `SCALED` ni vsync. L’état livré expose désormais un menu **Video** (résolutions prédéfinies, plein écran letterbox, vsync) et une fenêtre **non redimensionnable**, afin que la résolution choisie reste le viewport stable du jeu (culling caméra, budget de rendu).

La cadence appartient au même écran, et a été reprise le 2026-09-25 :

- la boucle est cadencée **exactement une fois**. `clock.tick(Display.FPS)` dort
  pour tenir la cadence, alors que sous vsync le present bloque déjà jusqu’au
  blanc vertical : faire les deux cadencent deux fois, et les deux attentes ne
  s’additionnent pas — une frame arrive juste après le blanc, le present attend
  alors le *suivant*, et la frame d’après trouve son sommeil déjà écoulé. La
  cadence alterne entre à l’heure et un refresh de retard, ce qui se lit comme un
  micro-saccade ;
- `Game._frame_delta()` (:250) laisse donc le present être le seul pacer sous
  vsync, et ne tique l’horloge que contre un plafond anti-emballement. Ce plafond
  est **dérivé** (`DISPLAY_SAFETY_CEILING_FPS = Display.FPS * 4`, `game.py:40`),
  jamais codé en dur : un 125 fixe passait sous une cible de 240 et coupait
  silencieusement la cadence demandée, vsync actif et sans rien à l’écran pour le
  dire. Le multiplicateur dégage tout taux de rafraîchissement réel (4.2 ms à
  240 Hz pour un present), donc le seul cas qu’il attrape est un present qui ne
  bloque pas du tout ;
- le compteur FPS a été rétabli sur le chemin vsync : un `pygame.time.Clock` ne
  met son propre chronomètre à jour que si on appelle `tick()`, et un
  `pygame.time.wait` manuel se place hors de la fenêtre que le Clock mesure, donc
  le compteur ne le voyait pas. Le garde-fou est désormais exprimé comme une cadence
  confiée à l’horloge, dans la même unité que ce qu’elle garde ;
- le réglage de limite de frames reste absent : `Display.FPS` est ignoré sous
  vsync (c’est la fréquence de l’écran qui décide), donc un curseur « FPS » serait
  inerte. Le lot 7 le nomme *Frame limit* et le plan est
  `notes/plan_limit_frames_video.md`.

### UI-8 — Aide aux contrôles

Le panneau actuel est une aide debug (`1-6`, V/B, G/P/T, F1–F10), pas un écran de contrôles joueur généré depuis les bindings.

### UI-9 — Parcours de progression

`SaveGame.unlocked_levels` existe, mais aucun menu ne permet de choisir un niveau. La fin du dernier niveau retourne directement au menu.

### UI-10 — Audio

Aucun système audio n’existe : pas de mixer, pas de sons, pas de volumes persistés.

### UI-13 — Accessibilité UI

Il n’existe pas de réglage `ui.scale` (`small`, `normal`, `large`). Les tailles de police sont fixes.

### UI-14 — Cohérence de frame et cadence — **Clos (2026-09-25)**

Ce constat n’est pas né d’une demande UI : il est apparu en mesurant le niveau 0
pendant l’audit, et il touche directement ce que le joueur voit — le HUD et les
barres HP. Les sept défauts constatés et leur contrat livré :

| Défaut constaté | Contrat livré | Preuve |
|---|---|---|
| Bandes horizontales pendant le scroll | le blend est **dans la caméra** (`Camera.begin_frame`) : une seule transform par frame, tous les sprites se déplacent du même amount | `test_frame_coherence.py::test_scrolling_never_exposes_the_background`, `::test_every_sprite_moves_by_the_same_amount` |
| Le debug s’éloigne des pixels qu’il annote | l’overlay passe par la même transform ; plus de pin à `alpha = 1.0` | `::test_the_bar_and_the_overlay_read_the_same_transform` |
| Barre HP à moitié de tick en retard sur son sprite | la passe de barres reçoit les rects **blittés** (`Renderer.draw_health_bars` → `WorldUI.draw_health_bars(..., screen_rects)`) | `::test_the_hp_bar_stays_on_its_sprite`, `test_no_stale_pixels.py` |
| HUD et barres jamais effacés (bandes de pixels périmés) | les deux passes déclarent leurs rects au renderer (`Level.draw`, `GameplayScene.draw` → `add_overlay_rects`) ; une frame qui porte des overlay rects ne prend jamais le chemin partiel | `::test_a_frame_carrying_the_hud_never_presents_partially`, `::test_a_frame_without_overlays_still_uses_the_partial_path`, `test_no_stale_pixels.py::test_a_moving_frame_leaves_no_stale_pixel` |
| Dernière colonne / dernière ligne de fenêtre jamais peinte | `Camera.apply_covering()` : `floor` des arêtes proches, `ceil` des lointaines, ces dernières **prises depuis le résultat de `apply`** | `test_camera_zoom.py::test_a_screen_rect_covers_the_pixels_it_was_meant_to_cover` (fuzz : 3 cas sur 129 600 avant, 0 après) |
| Traînée du dash clouée à la fenêtre | un ghost retient son rect **monde** et le remappe à chaque frame | `test_frame_coherence.py::test_a_dash_ghost_stays_anchored_to_the_world_while_the_camera_moves` |
| Compteur FPS à 0 sous vsync, cadence alternée | `_frame_delta()` : un seul pacer, plafond dérivé, horloge toujours tiquée | `test_frame_pacing.py` (9 tests, invariant plutôt que constante) |

Deux invariants de suite, à ne pas réintroduire :

1. **une constante partagée a un seul home**, celui du module qui agit. La
   géométrie de la barre HP est définie dans `world_ui.py`, qui la dessine, et le
   renderer l’importe pour sa tête d’effacement au lieu d’en garder une copie ;
2. **une frame qui porte des overlay rects ne présente jamais partiellement**,
   puisque ces rects sont peints *après* que le renderer ait choisi quoi présenter.

La vérification de non-régression est la comparaison pixel à pixel du chemin
incrémental contre une repinte complète de la même séquence de 40 frames : 0
divergence en alpha 0 et 0.5, jusqu’à 40 px/frame sans le correctif.

### UI-15 — Limite de frames (menu vidéo) — **Ouvert, planifié**

`UserSettings` porte `width`, `height`, `fullscreen`, `vsync`, `ui_scale` et rien
d’autre : il n’existe aucun plafond de frames réglable. Le plan (valeurs, bornes,
persistance, tests) est dans `notes/plan_limit_frames_video.md`. Ne pas nommer ce
réglage « FPS » : sous vsync, `Display.FPS` ne contrôle rien.

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
- **vidéo** (`Game._configure_display`) : la fenêtre n'est **pas** redimensionnable.
  La résolution vient de la liste prédéfinie du menu vidéo (`VideoScene.RESOLUTIONS`)
  et constitue le viewport logique stable du jeu (culling caméra, budget de
  rendu). En plein écran, `pygame.FULLSCREEN | pygame.SCALED` conserve le ratio et
  remplit l'écart avec des barres noires. `VIDEORESIZE` est ignoré : il ne peut
  plus modifier les réglages (ce qui interdit aussi toute boucle
  `set_mode()` / `VIDEORESIZE`) ;
- **viewport caméra** (`Level`) : la caméra est dimensionnée depuis la surface
  réelle, plus depuis les constantes `Display` — sinon un changement de
  résolution laisserait la caméra plus grande que la fenêtre et le culling
  écarterait des sprites visibles ;
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

### Lot 6 — Cohérence de frame et cadence — **Livré (2026-09-25)**

Ce lot n’était pas au plan initial : il est né des mesures de frame du niveau 0,
et il est livré (détail et preuves en §5, UI-14). Il a touché :

- `src/core/rendering/camera.py` : `begin_frame` porte le blend, `apply_covering`
  arrondit vers l’extérieur ;
- `src/core/rendering/renderer.py` : une seule transform lue par tous les
  consommateurs, `add_overlay_rects`, suppression du cache de position par sprite
  (60 lignes) et des deux contournements qu’il nourrissait ;
- `src/core/game.py` : `_frame_delta()` et le plafond dérivé de `Display.FPS` ;
- `src/ui/world_ui.py` : barres ancrées sur les rects blittés, gate `statics` avant
  la construction de la référence, `F4` statics off par défaut ;
- `src/ui/ui_manager.py`, `src/core/level/level.py`,
  `src/application/scenes/gameplay_scene.py` : déclaration des overlay rects.

Tests : `tests/unit/test_frame_coherence.py` (nouveau), `test_frame_pacing.py`
(nouveau), `test_no_stale_pixels.py` (nouveau), `test_camera_zoom.py` (13 tests
ajoutés), `test_renderer_dirty_rects.py`. Les cinq tests d’interpolation par
sprite de `test_world_render_perf.py` ont été retirés : le cache de position par
sprite a disparu, donc ils testaient une API qui n’existe plus ; l’équivalent est
désormais couvert au niveau caméra.

### Lot 7 — Limite de frames dans le menu vidéo — **Ouvert, planifié**

Réglage *Frame limit* (`Uncapped, 20, 30, 60, 120, 144, 240`), valeur par défaut
`Display.FPS`, appliqué à chaud sans recréer la fenêtre, avec le taux réel de
l’écran affiché quand le vsync est actif. Plan, bornes et tests :
`notes/plan_limit_frames_video.md`. Contrainte à respecter : ne pas nommer ce
réglage « FPS », ne pas toucher `_mode_signature`, ne pas bumper
`SETTINGS_FORMAT_VERSION`.

## 9. Réception globale — état

- [x] Menu clavier, souris et manette produisent les mêmes transitions.
- [x] Options accessible depuis menu et pause.
- [x] `settings.json` round-trip et fichier corrompu sans crash.
- [x] Vidéo : fenêtre, plein écran, vsync et redimensionnement.
- [x] Rebinding clavier / manette persisté depuis l’écran Contrôles.
- [x] Level Select et Victory fonctionnels.
- [x] HUD présent sans `DEBUG`.
- [x] Aucun panneau COMBAT/clash visible sans `DEBUG`.
- [x] Une seule transform par frame ; sprites, barres HP et overlay debug se
      déplacent du même amount.
- [x] Aucun pixel périmé : chemin incrémental vs repinte complète, 0 divergence.
- [x] Une frame portant des overlay rects ne présente jamais partiellement.
- [x] Boucle cadencée une fois ; compteur FPS juste sur les deux chemins
      (vsync off 62,1 sur 62,1 mesuré ; vsync on 125,0 sur 124,1).
- [x] Tests UI, Ruff, format, mypy et suite complète verts **sans `DEBUG`**
      (1117 tests au 2026-09-26).
- [ ] `DEBUG=1 uv run pytest -q` : 1 test rouge
      (`test_frame_presentation.py::test_level_draw_presents_the_health_bar_rects`,
      écart O10 de `notes/ecarts_ouverts.md`).
- [ ] Audio : mixer, sons de navigation, volumes (lot 5).
- [ ] Limite de frames réglable (lot 7, planifié).

## 10. Commandes de vérification

```bash
env -u DEBUG uv run pytest -q          # 1117 passed
DEBUG=1 uv run pytest -q               # 1 failed : écart O10 connu, non corrigé
uv run ruff check src tests main.py tools
uv run ruff format --check src tests main.py tools
uv run mypy src                        # 142 fichiers
uv run mypy src main.py tools          # 144 fichiers (commande CI)
git diff --check
```

Un test n’est pas exécutable isolément, et cela ne doit pas être lu comme une
régression : `test_frame_presentation.py::test_level_draw_presents_the_health_bar_rects`
dépend d’un test précédent qui agrandit l’écran, faute de quoi la barre de
l’ennemi de test est cullée par la caméra. C’est le même écart que O10.

`ruff format --check .` n’est pas dans cette liste : il échoue sur deux blocs de
code des notes (`audit_controles.md`, `hitbox_amelioration.md`), état antérieur à
cette mise à jour et hors de la commande CI, qui ne couvre que `src`, `tests`,
`main.py` et `tools/`.

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
- Mise à jour : 2026-09-26 contre `40ca5a9` — lot 6 livré (§5 UI-14, §8), lot 7
  planifié, `F4` statics off par défaut et transform unique en §4.3, cadence en
  §5 UI-6. Base §2 rafraîchie : 1117 tests, 89 % / 86 %, mypy 142 (`src`) et 144
  (CI), Ruff propre. La réception §9 ne peut plus afficher une suite verte « avec et
  sans `DEBUG` » : l’écart O10 est consigné et non corrigé.
