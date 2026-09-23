# Audit UI — Interface, navigation, paramétrage (audit_consolide.md complément)

- **Commit audité** : `a6d20f821ccb1c4177ee0e3a56d4ebf8b423228a` (branche `master`, 2026-09-22) — **re-vérifié intégralement contre HEAD** ce jour (audit initial sur `b493d802`, 2026-09-19 ; 28 commits d'écart, dont des dérives constatées ci-dessous). **Document durci le même jour pour exécution autonome par un agent** : décisions tranchées, API figée, fiches de lot §4b.
- **Prérequis** : le socle d'entrée est audité dans `notes/audit_controles.md` (C-Lot 0a + 0b) — **exécuter ce contrôle avant les lots 1-2** de ce document (règle C-D9 du contrôle ; voir §4a dépendances). Le chantier « bindings persistés » (ex-UI-5) est **porté par le contrôle** (C-7 / C-D6) ; UI-5 ici ne garde que l'écran.
- **Périmètre** : `src/application/` (scenes, scene_manager, save_game), `src/ui/`, `src/core/input/` (routes menu via le routeur du contrôle), `src/core/game.py`, `src/core/settings.py` (Display/Debug), `tests/` existants.
- **Méthode** : relecture ligne à ligne des 4 scènes, du pipeline d'événements (`game.py:_handle_events`) et de la chaîne UI ; greps exhaustifs (souris, manette, audio, modèle de sélection, persistance de réglages) — chaque chiffre ci-dessous est rejouable via la section [§7 Commandes de vérification](#7-commandes-de-vérification).
- **Verdict** : le ressenti « tout est à refaire » est **confirmé par le code**. Aucun des 4 usages attendus d'une interface de jeu n'est couvert : navigation souris (0 hit), navigation manette dans les menus (0 hit), sous-menus/réglages (0 scène, 0 fichier), HUD joueur lisible (pas de barre de vie/posture/dash/combo *du joueur* ; les barres de vie d'entités existent hors debug — voir UI-7). Le socle technique (`SceneManager` à pile, `PanelRenderer`, `InputBindings`, `SaveGame`) est sain et réutilisable — c'est le contenu UI qui manque, pas l'architecture. Le **routeur multi-périphériques** et le vocabulaire `ui_*` sont du côté contrôle (audit contrôles) ; ce document couvre le **modèle de focus**, les **scènes**, le **HUD** et les **réglages**.
- **Pour un agent** : commencer par le contrôle C-Lot 0a/0b si pas fait, puis la fiche du lot UI visé (§4b), respecter §5, finir par le *DoD* de la fiche + §6. Les cases « à trancher » de la version pré-durcissement sont **décidées** (§4a décisions, UI-14, §7 croisements) — ne pas rouvrir l'arbitrage sans écrire la nouvelle décision ici.

## 1. État des lieux

Statut : `✅` = re-vérifié le 2026-09-22 sur `a6d20f8` ; `🆕` = constat apparu depuis l'audit initial.

| Capacité attendue | État actuel | Preuve | Statut |
|---|---|---|---|
| Menu navigable clavier | ❌ raccourcis fixes uniquement (`ENTER`/`N`/`Q`/`ESC`), pas de curseur | `menu_scene.py:47-57` | ✅ |
| Menu navigable souris | ❌ aucun (`MOUSEMOTION`/`MOUSEBUTTON` : **0 hit** dans `src/`) | grep §7 | ✅ |
| Menu navigable manette | ❌ menus = `KEYDOWN` only ; manette initialisée mais réservée au gameplay | `game.py:82,133-146`, scènes | ✅ |
| Sous-menus / Options | ❌ 4 scènes plates (menu, gameplay, pause, gameover), aucune scène Options | `src/application/scenes/` | ✅ |
| Réassignation des touches | ❌ defaults en dur, jamais sérialisés | `input_bindings.py:31-76` | ✅ |
| Réglages vidéo (fenêtre/plein écran/vsync) | ❌ `set_mode` fixe, aucun `RESIZABLE`/vsync | `game.py:84` | ✅ |
| Réglages audio (volumes) | ❌ aucun audio du tout (`pygame.mixer`/`Sound`/`music` : **0 hit**) | grep §7 | ✅ |
| Sélection de niveau | ❌ seuls « continue » (dernier niveau) et « new game » ; `unlocked_levels` au-delà du dernier **inaccessibles** | `menu_scene.py:32-55`, `save_game.py:27-28` | ✅ |
| HUD joueur lisible | ✅ **soldé** : `src/ui/hud.py` (vie/posture/dash/combo, ancré écran, hors `Debug`), branché depuis `GameplayScene.draw` (D9) ; barre world-space du **joueur retirée** (gate dans `_has_health_bar`), celle des *entités* reste hors debug (`level.py:316`) | `src/ui/hud.py`, `gameplay_scene.py:156-172`, `tests/unit/test_hud.py` | 🆕 (UI-7) |
| Écran d'aide aux contrôles | ❌ le panneau « aide » liste les touches du banc de debug (F1-F7), pas les contrôles du joueur | `ui_manager.py:59-83` | ✅ |
| Modèle de sélection (focus/hover) | ❌ 0 hit `selected/focused/hover/highlight` (hits `cursor` = curseurs de layout debug : `panel_renderer.py:23,41`, `world_ui.py` timeline/sweep) | greps §7 | ✅ |
| Panneau COMBAT hors debug | ❌ `draw_metrics_panel` + `note_clash` appelés **avant** le gate `Debug` — visibles en mode joueur | `level.py:317-326` vs `level.py:328` | 🆕 (UI-14) |

Base de tests existante réutilisable pour la réception : `tests/headless/test_scenes.py` (14 tests, verts), `tests/unit/test_menu_panel.py` (6), `test_save_game.py` (10), `test_player_ui.py` (12), `test_ui_debug_panels.py` (5), `tests/headless/test_input_manager.py`.

## 2. Constats

### Axe A — Navigation

**UI-1 — Aucune interaction souris (priorité haute, effort M)**
- *Constat* : toutes les scènes filtrent à la source sur le clavier — `menu_scene.py:48` (`if event.type != pygame.KEYDOWN: return`, idem `pause_scene.py:33`, `gameover_scene.py:34`) ; `gameplay_scene.py:101-118` ne traite qu'ESC et F1-F7. Aucun hit-test, aucune zone cliquable : `draw_centered_menu_panel` (`menu_panel.py:20-62`) retourne pourtant un `Rect` (prévu « useful for headless tests », `:39-43`) mais personne ne le réutilise.
- *Impact* : un joueur sans clavier AZERTY/QWERTY connu ne peut ni lancer, ni reprendre, ni quitter proprement.
- *Cible* : chaque item de menu expose son Rect ; clic = activation, survol = focus visuel.
- *Réception* : headless — injecter `pygame.event.Event(MOUSEBUTTONDOWN, pos=…)`, vérifier le changement de scène ; hover change le rendu de l'item.

**UI-2 — Manette inutile dans les menus (priorité haute, effort S/M)**
- *Constat* : la manette est correctement gérée au niveau application (`game.py:82` `joystick.init()`, `:133-146` `JOYDEVICEADDED/REMOVED` avec hot-plug et réassignation), mais `MenuScene/PauseScene/GameOverScene` ne traitent que `KEYDOWN`. `InputBindings.gamepad_buttons` (`input_bindings.py:47-57`) ne couvre que les actions de gameplay (jump/attack/guard), aucune action de menu (`ui_confirm`, `ui_back`, `ui_up/down`).
- *Impact* : joueur manette > obligé de poser la manette pour naviguer. Contradiction directe avec la cible « beat'em up jouable à la manette ».
- *Cible* : actions de menu dédiées (déplacer/valider/retour). **Mapping figé** (standard Xbox / SDL, aligné sur les indices déjà en dur dans `input_bindings.py`) :
  | Action | Manette | Clavier équivalent |
  |---|---|---|
  | `ui_confirm` | bouton **0 (A)** | `ENTER` / `SPACE` |
  | `ui_back` | bouton **1 (B)** | `ESC` / `Q` (selon scène) |
  | `ui_up` / `ui_down` | **hat Y** (`JOYHATMOTION` ±1) **ou** stick gauche `axis 1` si `abs(v) >= 0.5` (edge only, pas de répétition tant que le seuil n'est pas repassé sous 0.3) | `UP` / `DOWN` |
  - Ces 3 actions s'ajoutent à `InputBindings` (dict `menu` — **implémenté par C-Lot 0a du contrôle**) et sont routées par le **routeur d'événements du contrôle** (`src/core/input/event_router.py`, C-Lot 0b), pas par la boucle gameplay.
- *Réception* : headless — `Event(JOYHATMOTION, value=(0,-1))`, `Event(JOYBUTTONDOWN, button=0)`, `Event(JOYBUTTONDOWN, button=1)` simulés changent l'item courant / activent / reviennent.

**UI-3 — Pas de modèle de sélection (priorité haute, effort M — socle de UI-1/UI-2)**
- *Constat* : les options sont des chaînes figées : `self.options: tuple[str, ...]` (`menu_scene.py:34-42`), `"ENTER / ESC: resume"` (`pause_scene.py:23`), dessinées en texte brut (`menu_panel.py:46`). Aucun index d'item courant, aucun état `enabled`, aucun ordre de navigation — greps `selected|focused|hover|highlight` = 0 hit.
- *Impact* : impossible d'ajouter souris/manette/sous-menus sans d'abord inventer ce modèle à chaque scène. C'est la racine de « menu impraticable ».
- *Cible* : **API figée** `src/ui/menu_model.py` (module pur, zéro import pygame obligatoire sauf `Rect` si besoin — préférer un tuple `(x,y,w,h)` ou `pygame.Rect` au choix, documenté) :

  ```python
  @dataclass
  class MenuItem:
      label: str
      callback: Callable[[], None] | None = None  # None => jamais activable
      enabled: bool = True
      rect: pygame.Rect | None = None             # alimenté par menu_view après draw

  class MenuModel:
      items: list[MenuItem]
      index: int                                  # focus clavier/manette/hover (état UNIQUE)

      def rebuild(self, items: list[MenuItem]) -> None   # appelé à chaque enter() de scène
      def move(self, delta: int) -> None   # wrap circulaire ; saute les items !enabled
      def hover(self, pos: tuple[int, int]) -> None  # si rect contient pos => index = i (sinon no-op)
      def point_inside(self, pos: tuple[int, int]) -> bool
      def activate(self) -> bool  # False si !enabled ou callback None ; sinon appelle callback, True
      @property
      def current(self) -> MenuItem
  ```

  - **Wrap** (pas clamp) : `move(+1)` sur le dernier revient au premier *enabled* ; idem `move(-1)` ; si **aucun** item enabled, `move` est no-op.
  - **Un seul état de focus** : clavier, manette et hover partagent `index` ; le survol souris *déplace* le curseur, le clavier/manette le reprend au prochain `UP/DOWN`.
  - **Menu dynamique** : les items sont reconstruits dans `Scene.enter()` (pas seulement `__init__`) — `MenuScene` a 2 ou 3 options selon `has_progress` (`menu_scene.py:33-42`).
  - Rendu du curseur (flèche `▶` ou surlignage) dans `src/ui/menu_view.py` : `draw_menu(renderer, surface, model, ...) -> list[pygame.Rect]` (Rects par item, alimentés dans `model.items[i].rect`).
- *Réception* : `tests/unit/test_menu_model.py` pur (wrap, skip désactivé, activate désactivé → False, hover, rebuild) + `tests/unit/test_menu_view.py` (curseur rendu, Rects renseignés) + headless ↑/↓/Enter sur les 3 scènes menu.

### Axe B — Paramétrage

**UI-4 — Aucun sous-menu, aucune scène Options (priorité haute, effort M)**
- *Constat* : `src/application/scenes/` contient exactement `menu_scene.py`, `gameplay_scene.py`, `pause_scene.py`, `gameover_scene.py`. `SceneManager` (`scene_manager.py:34-51`) expose `switch/push/pop` — la pile supporte nativement un sous-menu — mais jamais utilisée autrement que pause/game-over.
- *Cible* : `OptionsScene` **push** depuis menu et pause ; sections en liste (pas d'onglets) : **Contrôles** / **Vidéo** / **Audio** / **Retour**. **Décision D6 : une seule scène + attribut `section`** (pas de sous-scenes multiples). `ESC`/`ui_back` = `pop` (retour menu ou pause selon la scène dessous).
- *Réception* : push depuis pause → `pop` restaure la pause (étendre `test_scenes.py`).

**UI-5 — Écran de rebinding (données portées par le contrôle C-7)**
- *Constat* : `input_bindings.py:5` promet la personnalisation des touches ; les defaults sont en dur (`:31-76`), sans `to_dict`/`from_dict` ni écriture disque — **constat détaillé et plan de données en `notes/audit_controles.md` C-7 / C-Lot 0d (décision C-D6)**. Ici ne reste que **l'écran**.
- *Cible (partie UI)* : `src/application/settings_store.py` — sections `video` / `audio` / `ui` de `settings.json` (même contrat que `SaveGame` : `version`, fallback, `KNIGHTROCK_SAVE_DIR` + `/.knightrock/settings.json`) ; la section `bindings` est **écrite/lue par C-Lot 0d** et seulement **consommée** par l'écran Contrôles :

  ```json
  {
    "version": 1,
    "bindings": { "...": "porté par audit contrôles C-7 — cf. audit_ui UI-5 renvoi" },
    "video": { "fullscreen": false, "vsync": false, "windowed_size": [1440, 900] },
    "audio": { "master": 1.0, "sfx": 1.0, "music": 1.0 },
    "ui": { "scale": "normal" }
  }
  ```

  - `SettingsStore.load()/save()`, defaults en code, **mêmes catches parenthésés** que UI-11.
  - Écran Contrôles : état `waiting_for_key` — injecter `Event(KEYDOWN, key=…)` met à jour le binding **via l'API du contrôle** ; conflit → refuser + message (D10).
- *Réception (partie UI)* : capture de touche headless ; roundtrip disque des sections vidéo/audio/ui (bindings = DoD C-Lot 0d) ; fichier corrompu → defaults sans crash.

**UI-6 — Aucun réglage vidéo (priorité moyenne, effort M)**
- *Constat* : `Display` (`settings.py:8-18`) : `WIDTH=1440, HEIGHT=900, FPS=180` constants ; `game.py:84` crée la fenêtre une fois via `set_mode(SIZE)` sans `RESIZABLE`, sans vsync, sans bascule plein écran. Le commentaire `settings.py:14-16` annonce « rendering at 120 FPS » et traite 180 comme « *previous* 180 FPS setting » (référence audit F1.4/F6.1) alors que `FPS = 180` (ligne 17) — l'incohérence R-1 est **toujours non résolue**. **Décision : le lot 3 absorbe R-1** (voir §7 croisements).
- *Cible* : bascule plein écran via `pygame.FULLSCREEN | pygame.SCALED` (reco.) ou `pygame.display.toggle()` ; `RESIZABLE` en fenêtré ; vsync : recréer le display avec `pygame.display.set_mode(size, flags, vsync=1)` (pygame-ce) — relever le FPS clock en conséquence. Résolutions fenêtrées proposées : `[1280×720, 1440×900, 1920×1080]` uniquement. `PanelLayout` est déjà « responsive by construction » (`panel_renderer.py:8-46`).
- *Réception* : headless — toggles appliqués à un display de test, persistés dans `settings.json`.

### Axe C — HUD & feedback joueur

**UI-7 — Pas de HUD joueur ; l'« UI » actuelle est l'outil de debug (priorité haute, effort M)**
- *Constat* : `UIManager` (`ui_manager.py:20-156`) n'expose que des panneaux debug (`draw_state_panel`/`draw_stats_panel`/`draw_scene_panel`/`draw_help_panel`/`draw_legend_panel`/`draw_performance_panel` — routage `renderer.py:201-222`, affichés uniquement quand `Debug.is_enabled()` via `level.py:328-334`). `player_ui.py:13-140` montre des valeurs internes en jargon debug, utiles au dev, illisibles pour un joueur. `world_ui.py` (1275 lignes) est l'overlay debug : excellent outil, pas un HUD.
  - *Nuance (re-vérification 2026-09-22)* : `level.py:316` appelle `draw_health_bars` **hors** du gate Debug — des barres de vie *world-space* pour les entités avec `health` (`world_ui.py:1247-1275`) s'affichent déjà en jeu normal. Ce n'est **pas** un HUD joueur : ni posture, ni dash, ni combo, ni ancrage fixe écran.
- *Impact* : en jeu normal, l'écran ne dit ni la posture, ni les charges de dash, ni le combo — alors que le combat (posture, riposte, juggle/OTG) est précisément conçu autour de ces fenêtres.
- *Cible* : `src/ui/hud.py` — **champs figés** (lecture seule, mêmes attributs que `player_ui.draw_stats_panel`) :

  | Élément HUD | Source | Seuils couleur |
  |---|---|---|
  | Barre de vie | `player.health` / `player.max_health` | >50 % OK, >25 % WARN, sinon CRIT (`styles`) |
  | Posture de garde | `player.guard_posture` / `player.guard_posture_max` | ≤30 % WARN ; `guard_lockout_timer > 0` → CRIT |
  | Charges de dash | `player.dash_charges` / `player.max_dash_charges` | pastilles pleines/vides |
  | Combo | `player.combat.combo_count`, `combo_timer` | affiché si `count > 0` |

  - Ancrage écran (coin bas-gauche vie/posture, bas-droite dash/combo), **pas** de world-space, **pas** de `Debug.is_enabled()`. Classe `HUD.draw(player) -> None` ; **branchement D9** : `GameplayScene.draw` (`src/application/`, périmètre autorisé) appelle `self.level.renderer.ui_manager.draw_hud(self.level.player)` **après** `level.draw()` — ni `level.py`, ni `renderer.py` modifiés (règle 1).
- *Réception* : headless — HUD dessiné sans `Debug.is_enabled()`, contenu et couleurs vérifiés par état (vie basse → rouge) via snapshot de texte/Rects (pas de pixel-perfect).
- *État (2026-09-22)* : **soldé**. `src/ui/hud.py` (`HUD.draw(player) -> list[Rect]`), seuils UI-7 dans `health_color`/`posture_color`, largeur de barre proportionnelle bornée à l'écran (`bar_width_for`), `HudLayout` gelé pour l'assertion par état ; `UIManager.draw_hud` + branchement D9 dans `GameplayScene.draw`, rects HUD ajoutés au set dirty (frame non-debug). 23 tests dans `tests/unit/test_hud.py` (ancrage, seuils, pips, combo expiré, clamp des résolutions, rects présentés).
- *Complément (2026-09-22)* : la **barre world-space du joueur est retirée** (redondante avec le HUD) — gate `faction == "player"` dans `WorldUI._has_health_bar` (`src/ui/`, règle 1 respectée ; `level.py:316` inchangé), ce qui supprime aussi la salle réservée par les cartes debug pour une barre jamais dessinée. Les barres des **entités ennemies** restent hors debug. Test `test_player_has_no_world_space_health_bar`.

**UI-8 — Pas d'aide aux contrôles, libellés figés (priorité moyenne, effort S/M)**
- *Constat* : le seul panneau « aide » (`ui_manager.py:59-83`) liste `1-4 test attacks / F1-7 boxes/step…` = touches du banc de debug. Les libellés de menu (`"ENTER: play"`, `menu_scene.py:37-42`) sont des chaînes en dur qui ne reflètent ni `InputBindings` ni d'éventuels rebidings (UI-5). Aucun écran « Contrôles » consultable depuis menu ou pause.
- *Cible* : section `controls` d'`OptionsScene` (D6) listant chaque action × (nom de touche clavier, bouton manette) générés depuis `InputBindings` effectif ; libellés de menu calculés (`f"{name_key}: continue"`). Accessible depuis menu **et** pause (push d'`OptionsScene` au lot 3).
- *Réception* : headless — le texte affiché contient le nom de touche retourné par les bindings (après rebinding, le libellé change).

**UI-9 — Feedback et parcours joueur incomplets (priorité moyenne, effort M)**
- *Constat* :
  - **Sélection de niveau impossible** : le menu n'offre que « continue » (reprenant `last_level_id`, `menu_scene.py:52`) et « new game ». `SaveGame.unlocked_levels` (`save_game.py:27`) peut contenir plusieurs niveaux, mais il n'existe **aucun moyen** d'y accéder.
  - **Fin de jeu sans écran de victoire** : `gameplay_scene.py:83-99` (`_advance_level`) — dernier niveau fini → `switch(MenuScene)` direct (`:97`).
  - **Transitions brutes** : `switch` sans fondu ; Game Over pousse un panneau statique (`gameover_scene.py:41-57`).
- *Cible* :
  - `LevelSelectScene` : **liste verticale** (pas grille — réutilise `MenuModel`) des niveaux **uniquement** dans `unlocked_levels` triés ; les ids non débloqués ne sont **pas** affichés morts (règle « no dead options ») ou affichés `enabled=False` avec libellé `level N (locked)` — **choix : afficher locked `enabled=False`** pour montrer l'existence. Item → `GameplayScene(game, level_id)`.
  - `VictoryScene` : titre, `level_id`, boutons `Next`/`Retry`/`Menu` via `MenuModel`. Déclenchée par `_advance_level` quand `next_id is None`.
  - Fade : `src/ui/fade.py` helper 0→255 alpha sur N frames, appelé par `SceneManager.switch` wrapper **sans modifier `scene_manager`** — helper utilisé explicitement par les scènes qui transitionnent. (Lot 5.)
- *Réception* : headless — ouvrir la sélection, lancer un niveau N débloqué, naviguer ↑/↓ ; fin du dernier niveau → `VictoryScene` ; les ids non débloqués ne sont pas activables.

### Axe D — Fondations & santé du code

**UI-10 — Aucun audio (priorité moyenne, effort L — prérequis des volumes d'UI-6/lot 3)**
- *Constat* : `pygame.mixer`/`Sound`/`music` : **0 hit** dans `src/`. **Décision : le lot 5 porte `AudioBus`** et couvre donc R-2.4 (§7 croisements).
- *Cible* : `src/application/audio_bus.py` — `init()` dummy-safe, canaux `sfx`/`music`, `set_volume(channel, v)`, hooks EventBus (`LevelStarted`, `PlayerDied`, `LevelCompleted`) + sons de menu sur `activate()`.
- *Réception* : headless — `SDL_AUDIODRIVER=dummy`, volumes appliqués et persistés ; absence de périphérique → dégradation silencieuse.

**UI-11 — Syntaxe Python 3.14 exclusive dans `save_game.py` (priorité basse, effort XS)**
- *Constat* : `save_game.py:63` et `:78` — `except` sans parenthèses (PEP 758). `pyproject.toml:6` : `requires-python = ">=3.14"`.
- *Cible* : `except (KeyError, TypeError, ValueError):` et `except (OSError, json.JSONDecodeError):`.
- *Réception* : `python3 -m py_compile src/application/save_game.py` + `uv run pytest tests/unit/test_save_game.py`.

**UI-12 — Incohérences commentaires/décisions à trancher (effort XS)**
- `settings.py:14-17` : commenter/aligner avec la valeur réelle **dans le lot 3** (R-1 absorbé) — si `FPS` passe à 120, réécrire le commentaire pour décrire 120, sinon le commentaire ne doit pas dire « previous 180 ».
- `menu_scene.py:23-25` : réécrire la docstring « deliberately textual » dès le lot 1 (elle décrit ce qui est remplacé).
- `input_bindings.py:5` : la promesse devient vraie via **C-7 / C-Lot 0d du contrôle** (données) + écran UI-5 — ne pas supprimer la phrase, l'implémenter côté contrôle.

**UI-13 — Accessibilité (transverse, effort M, lot 4)**
- Tailles fixes : `SysFont("Consolas", …)` (`panel_renderer.py:55-63`), `Debug.FONT_SIZE=24` (`settings.py:248`), menu 48/40 px (`menu_panel.py:29-30`).
- Palette : thème debug (`styles.py:2`) — étendre en charte UI (couleurs HUD dédiées) ou assumer.
- Cible : réglage `ui.scale` ∈ `small|normal|large` (0.8 / 1.0 / 1.25) multiplie les tailles de polices **menu + HUD uniquement** (pas les panneaux debug F1-F5).

**UI-14 — Panneau COMBAT affiché hors mode debug (nouveau constat, priorité moyenne, effort S)**
- *Constat* : `level.py:317-326` appelle `world_ui.note_clash(...)` et `world_ui.draw_metrics_panel(...)` **avant** le gate `if not debug_enabled: return dirty` (`level.py:328`). Le panneau COMBAT (`world_ui.py:382-425`) s'affiche en mode joueur, thème debug. Apparu en `a6d20f8`.
- *Impact* : bruit visuel ; contradiction avec §5 règle 5.
- ***Décision (figée) : option (a), gate DANS `src/ui/world_ui.py`*** — en tête de `WorldUI.draw_metrics_panel` et `WorldUI.note_clash` (+ le rendu du marqueur clash dans la boucle existante) :

  ```python
  if not Debug.is_enabled():
      return
  ```

  - **Aucune édition de `level.py`** → règle 1 intacte (pas d'exception).
  - Option (b) (asserter le panneau comme feedback joueur) est **rejetée** pour l'instant : à rouvrir seulement avec une refonte vers `ui/hud.py` et une ligne écrite ici.
- *Réception* : headless — `DEBUG` unset : `draw_metrics_panel` ne blitte rien (compteur de `display_surface` ou spy) ; `DEBUG=1` : comportement inchangé (`test_debug_overlay.py` / `test_ui_debug_panels.py` restent verts).
- *État (2026-09-22)* : **soldé autrement que par le gate sec** — `draw_metrics_panel` collecte les lignes (gate `Debug.is_enabled()` dans `world_ui.py`, zéro édition de `level.py` : décision D1 intacte) et le **flux de colonnes** les dessine (`UIManager.draw_combat_panel`, appelé par `Renderer.draw_debug_panels`). Le COMBAT a donc en plus quitté sa position fixe `(10, 150)` où il s'empilait sur STATE/STATS. Tests : `tests/unit/test_debug_layout.py` (gate + flux) ; `DEBUG` unset → `combat_panel_lines` vide et aucun pixel COMBAT.

## 3. Cible proposée (architecture)

```
src/ui/menu_model.py        # MenuModel/MenuItem : API figée UI-3 (pur)
src/ui/menu_view.py         # draw_menu -> list[Rect] ; curseur ; alimente item.rect
src/core/input/event_router.py  # route KEYDOWN/MOUSE*/JOY* -> ui_* (porté par audit contrôles C-Lot 0b)
src/ui/hud.py               # HUD joueur (fields UI-7), sans Debug
src/ui/fade.py              # (lot 5) helper fade
src/application/settings_store.py   # settings.json versionné (schéma UI-5 ; section bindings = C-7 contrôle)
src/application/audio_bus.py        # (lot 5) — couvre aussi R-2.4
src/application/scenes/options_scene.py      # 1 scène + sections Contrôles/Vidéo/Audio (UI-4, D6)
src/application/scenes/level_select_scene.py
src/application/scenes/victory_scene.py
```

- Les scènes restent les points d'entrée `handle_event` ; le **routeur du contrôle** (`event_router.py`) est la porte unique des périphériques → actions `ui_*` ; l'UI branche `MenuModel` sur ces actions (hover/clic = Rects du modèle). Une seule table de navigation pour les 3 périphériques.
- `SceneManager` push/pop sert pour Options/Sélection/Victoire (`scene_manager.py:41-51`, aucune modification du manager).

## 4a. Décisions figées (ne pas rouvrir sans mise à jour écrite)

| # | Sujet | Décision |
|---|---|---|
| D1 | UI-14 | Option (a), gate **dans** `world_ui.py` (`Debug.is_enabled()`), zéro édition de `level.py` |
| D2 | R-1 (FPS/vsync) | **Absorbé par le lot 3** (UI-6) — ne pas traiter séparément dans `audit_consolide.md` tant que le lot 3 n'est pas soldé |
| D3 | `AudioBus` / R-2.4 | **Lot 5** livre l'implémentation unique ; R-2.4 est couverte quand le lot 5 passe ; sinon R-2 reste ouverte |
| D4 | Wrap navigation | **Wrap circulaire**, skip `!enabled` |
| D5 | Focus | **Un seul `index`** partagé clavier/manette/hover |
| D6 | Options | **1 scène** `OptionsScene` + attribut `section` (pas de sous-scenes multiples) ; section `controls` = écran Contrôles UI-8, livrée au **lot 3** avec le store |
| D7 | Level select | Liste ; locked **affichés** `enabled=False` + libellé `(locked)` |
| D8 | Contrôleur | **Routeur du contrôle** `src/core/input/event_router.py` (C-Lot 0b) produit les actions `ui_*` ; l'UI l'appelle via `route_event` et gère seulement focus/Rects (`MenuModel` + `menu_view`) — un seul routeur, pas deux |
| D9 | HUD branchement | Appelé depuis `GameplayScene.draw` après `level.draw()` (fichier autorisé) |
| D10 | Conflit rebinding | **Refuser** la capture + message (pas d'échange automatique) |
| D11 | Lot 1 scènes | **menu / pause / gameover uniquement** — `GameplayScene` n'a pas d'items de menu, hors lot 1 |
| D12 | Manette menu | boutons 0/1, hat + stick seuil 0.5/0.3, actions `ui_*` dans `InputBindings` — **codes/seuils portés par C-Lot 0a/0c du contrôle** ; le tableau UI-2 reste la référence UX |

## 4b. Fiches de lot (exécution agent)

Chaque fiche : **Ordre**, **Fichiers**, **Tests**, **DoD** (bloquant). Efforts : S ≈ 0,5 j, M ≈ 1-2 j, L ≈ 3-5 j.

### Lot 1 — Socle navigation (UI-3, UI-12 docstring) — effort M

**Prérequis** : **C-Lot 0a + 0b de `notes/audit_controles.md` verts** (vocabulaire `ui_*`, routeur d'événements) — voir C-D9.

**Ordre**
1. `src/ui/menu_model.py` — API UI-3 exacte (dataclass `MenuItem`, `MenuModel` : `rebuild/move/hover/point_inside/activate/current`, wrap D4, focus D5).
2. `tests/unit/test_menu_model.py` — wrap, skip désactivé, `activate()` désactivé → `False`, hover, rebuild vide/tous désactivés.
3. `src/ui/menu_view.py` — `draw_menu(...) -> list[pygame.Rect]`, curseur `▶` sur `model.index`, écrit `item.rect`.
4. `tests/unit/test_menu_view.py` — Rects non vides, curseur présent si `len(items)>0`.
5. Converter **`MenuScene`**, **`PauseScene`**, **`GameOverScene`** (D11) : remplacer les tuples de strings par `MenuModel` ; `enter()` → `rebuild()` (D-menu dynamique) ; `handle_event` : `UP/DOWN` (wrap), `ENTER`/`SPACE` → `activate()`, garder `ESC`/`Q` raccourcis existants **en plus** ; `draw` via `draw_menu`.
6. Réécrire la docstring `menu_scene.py:23-25` (UI-12).
7. Ne **pas** toucher `GameplayScene.handle_event` (ESC/F1-F7 restent).

**Fichiers créés** : `src/ui/menu_model.py`, `src/ui/menu_view.py`, `tests/unit/test_menu_model.py`, `tests/unit/test_menu_view.py`.  
**Fichiers modifiés** : `menu_scene.py`, `pause_scene.py`, `gameover_scene.py`, éventuellement `menu_panel.py` (réutilisation interne).

**DoD lot 1**
```bash
uv run pytest tests/unit/test_menu_model.py tests/unit/test_menu_view.py \
  tests/unit/test_menu_panel.py tests/headless/test_scenes.py -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
```
+ scénario headless : `KEYDOWN UP/DOWN` change l'item actif sur les 3 scènes ; `ENTER` déclenche le callback ; les 2-3 options dynamiques du menu principal suivent `has_progress`.

---

### Lot 2 — Souris + manette (UI-1, UI-2) — effort M

**Prérequis** : lot 1 vert ; **C-Lot 0b** (routeur KEYDOWN/MOUSE/JOY déjà en place — ici on ajoute le **focus/Rects**, pas le polling matériel) ; **C-Lot 0c** recommandé (stabilité hat/deadzone).

**Ordre**
1. Le dict `menu` (`ui_confirm:0`, `ui_back:1`) et les seuils stick (D12) **existent déjà** via le contrôle — ne pas les redéfinir.
2. `MenuModel` + la scène consomment les retours du routeur (`src/core/input/event_router.py`) : `MOUSEMOTION` → `model.hover`, `MOUSEBUTTONDOWN` → `activate` si `point_inside`, `JOYHAT`/`JOYAXIS` → `move`, `JOYBUTTONDOWN` → `activate` / `on_back`.
3. Supprimer tout filtre résiduel `!= KEYDOWN` dans les 3 scènes menu (le routeur est la porte unique).
4. Hot-plug inchangé (`game.py`).

**Fichiers** : **créés** `tests/unit/test_menu_route_bridge.py` (ou tests intégrés scènes), modifiés les 3 scènes, éventuellement `menu_view.py`.  
**DoD lot 2**
```bash
uv run pytest tests/unit/test_event_router.py tests/unit/test_menu_model.py \
  tests/headless/test_scenes.py tests/headless/test_input_manager.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ 3 parcours headless : clavier ↑↓Enter, souris motion+clic sur Rect, hat+button0/1 — même transition de scène.

---

### Lot 3 — Réglages persistés (UI-4, UI-5, UI-6, UI-11, R-1/D2) — effort L

**Prérequis** : lot 1 (Options est un menu) ; **C-Lot 0d du contrôle** pour la section `bindings` de `settings.json` (sinon l'écran Contrôles n'a rien à relire — C-D6).

**Ordre**
1. UI-11 quick win : parenthéser les 2 `except` de `save_game.py` + pytest save.
2. `src/application/settings_store.py` — schéma §UI-5 (**hors `bindings`, porté par C-7**), `default_settings_path()` miroir de `default_save_path()`, roundtrip + corrupted → defaults.
3. Wiring boot : `settings_store` (sections vidéo/audio/ui) + bindings chargés par **C-Lot 0d** déjà en place ; ne pas réimplémenter `InputBindings.to_dict` ici.
4. `src/application/scenes/options_scene.py` (D6) : sections Contrôles / Vidéo / Audio / Retour ; Contrôles = liste actions + capture (`waiting_for_key`, conflit → refus D10) **et** source de données de UI-8 (écrit via l'API bindings du contrôle) ; Vidéo = fullscreen/vsync/resolution (UI-6 cible) ; Audio = 3 sliders persistés (efficaces lot 5).
5. Intégrer : item « Options » dans `MenuScene` **et** `PauseScene` → `push(OptionsScene)` ; ESC → `pop`. La section Contrôles est donc accessible menu + pause dès ce lot (UI-8).
6. **R-1 (D2)** : dans la foulée vidéo, aligner `FPS` + commentaire (`settings.py:14-17`) et brancher le vsync demandé.
7. Remplacer `set_mode` fixe de `game.py:84` par un `apply_video_settings(settings)` appelé au boot et à chaque changement — **`game.py` est dans le périmètre autorisé**.

**Fichiers** : **créés** `settings_store.py`, `options_scene.py`, `tests/unit/test_settings_store.py`, `tests/unit/test_options_scene.py` ; modifiés `save_game.py`, `menu_scene.py`, `pause_scene.py`, `game.py`, `settings.py` (FPS/commentaire). `input_bindings.py` resté sous contrôle C-0d.

**DoD lot 3**
```bash
uv run pytest tests/unit/test_settings_store.py tests/unit/test_options_scene.py \
  tests/unit/test_save_game.py tests/headless/test_scenes.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ scénario : pause → Options → changer une touche → ESC → ESC → relancer le process (ou re-`load`) → binding conservé ; `settings.json` corrompu → defaults ; greps §7 « set_mode » montrent maintenant RESIZABLE/vsync **attendus** (mettre à jour le commentaire de §7 au besoin).

---

### Lot 4 — HUD & parcours (UI-7, UI-8, UI-9, UI-13, UI-14/D1) — effort L

**Prérequis** : lot 1 (`MenuModel`) ; UI-8 (libellés dynamiques post-rebinding) suppose le store du lot 3 pour un écran Contrôles *utile*, mais la section existe déjà au lot 3.

**Ordre**
1. **UI-14 (D1)** : `if not Debug.is_enabled(): return` en tête de `WorldUI.draw_metrics_panel` + `note_clash` (+ garde du marqueur) ; tests overlay existants verts sans `DEBUG`, vert avec `DEBUG=1`.
2. `src/ui/hud.py` + branchement `GameplayScene.draw` (D9) + `tests/unit/test_hud.py` (champs UI-7, couleurs par seuils).
3. `LevelSelectScene` (D7) depuis `MenuScene` (item « Level select » si `len(unlocked_levels) > 1`).
4. `VictoryScene` branchée sur `_advance_level` (`next_id is None`).
5. UI-8 : vérifier que la section `controls` (lot 3) affiche les bindings **effectifs** après rebinding ; calculer les libellés de menu depuis `InputBindings` (fin de UI-8).
6. UI-13 : `ui.scale` appliqué aux polices menu + HUD (pas debug).

**Fichiers** : **créés** `src/ui/hud.py`, `level_select_scene.py`, `victory_scene.py`, `tests/unit/test_hud.py`, `tests/unit/test_level_select.py`, `tests/unit/test_victory_scene.py` ; modifiés `world_ui.py` (gate), `gameplay_scene.py` (draw HUD + victoire), `menu_scene.py` (libellés), `panel_renderer.py`/`menu_view.py` (scale UI-13).

**DoD lot 4**
```bash
uv run pytest tests/unit/test_hud.py tests/unit/test_level_select.py \
  tests/unit/test_victory_scene.py tests/unit/test_ui_debug_panels.py \
  tests/unit/test_debug_overlay.py tests/headless/test_scenes.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ headless **sans** `DEBUG` : HUD présent (vie/posture/dash/combo), panneau COMBAT **absent** ; **avec** `DEBUG=1` : COMBAT présent, panneaux F1 inchangés ; level select n'offre que `unlocked_levels`.

---

### Lot 5 — Audio & polish (UI-10, R-2.4/D3, fades UI-9) — effort L — optionnel

**Ordre** : `audio_bus.py` dummy-safe → hooks EventBus → sons de menu sur `activate` → volumes branchés sur les sliders lot 3 → `src/ui/fade.py` + utilisation sur `switch` critiques (menu↔gameplay, gameover).

**DoD lot 5**
```bash
SDL_AUDIODRIVER=dummy uv run pytest tests/unit/test_audio_bus.py \
  tests/unit/test_settings_store.py tests/headless/test_scenes.py -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
+ mixer absent → pas de crash ; volumes persistés ; fade testé (alpha 0→255 sur N frames, pur).

---

### Dépendances
- **Prérequis global** : `notes/audit_controles.md` **C-Lot 0a + 0b** avant lot 1 (C-D9) ; **C-Lot 0c** recommandé avant lot 2 ; **C-Lot 0d** avant ou avec lot 3 (section `bindings`).
- Lot 2 ← lot 1 ; lot 3 ← lot 1 + C-Lot 0d ; lot 4 ← lot 1 (MenuModel) ; lot 5 ← lot 3 (sliders) seulement pour les volumes.
- Lots 3 ∥ 4 possibles (chevauchement unique : `menu_scene.py` — un seul éditeur à la fois ou fusion soignée).
- UI-14 (D1) : quick win autonome avant lot 1.

## 5. Règles (à respecter pendant l'implémentation)

1. **Aucun changement de gameplay** : les lots touchent `src/application/`, `src/ui/`, `src/core/input/`, `src/core/game.py` (boot video), `src/core/settings.py` (FPS/DISPLAY) — **jamais** `src/core/level/`, `src/combat/`, `src/entities/`, `src/states/`, `src/physics/`. UI-14 ne crée **aucune exception** (D1 : gate côté `src/ui/`).
2. **Pas de nouveau framework** : pygame seul, réutilisation de `SceneManager`, `PanelRenderer`, `PanelLayout`, `SaveGame`/`SettingsStore` pour la persistance.
3. **Tout item affiché est atteignable et testé** (README « No dead menu options ») — un item désactivé affiche sa cause (ex. `(locked)`).
4. **Réception headless uniquement** : `SDL_VIDEODRIVER=dummy`, événements `pygame.event.Event` injectés — aucune saisie réelle en CI.
5. **Panneaux debug intacts en mode debug** : F1-F7, `world_ui.py`, `player_ui.py` opérationnels avec `DEBUG=1` ; **rien de debug ne fuit sans `DEBUG`** (UI-14/D1). Le HUD joueur s'ajoute, il ne remplace pas.
6. **Deux fichiers de persistance** : `settings.json` (réglages) ≠ `savegame.json` (progression), même contrat version/fallback.
7. **Les décisions §4a font autorité** ; toute divergence doit modifier §4a **avant** le code.

## 6. Réception globale (checklist de bout en bout)

- [ ] Menu praticable **100 % clavier** (↑/↓/Enter/ESC), **100 % souris** (hover + clic), **100 % manette** (hat/stick/A/B) — trois parcours automatisés verts.
- [ ] Pause → Options → modifier une touche → retour → rechargement : rebinding conservé ; `settings.json` corrompu → defaults sans crash.
- [ ] Options Vidéo : plein écran/fenêtré + vsync persistés ; HUD et menus lisibles après redimensionnement (`PanelLayout`) ; R-1 soldé (FPS/commentaire cohérents).
- [ ] Options Audio : volumes master/sfx/music modifiables et persistés (sans périphérique : dégradation silencieuse).
- [ ] En jeu **sans `DEBUG`** : HUD (vie, posture, dash, combo) visible et à jour ; panneau COMBAT/clash **invisible**.
- [ ] En jeu **avec `DEBUG=1`** : COMBAT + F1-F7 + panneaux inchangés.
- [ ] Level select : navigation ↑/↓ ; seuls `unlocked_levels` activables (locked visibles `enabled=False`).
- [ ] Fin du dernier niveau → `VictoryScene` (plus de retour menu muet).
- [ ] Écran Contrôles depuis menu **et** pause, généré depuis les bindings effectifs.
- [ ] Suites existantes vertes + nouveaux tests des lots livrés ; `ruff`/`format`/`mypy` bloquants.
- [ ] Aucune édition dans `src/core/level/`, `src/combat/`, `src/entities/` (règle 1) — vérifier par `git diff --stat`.

## 7. Commandes de vérification

Rejouer l'audit (ou constater qu'un lot a bien couvert le point) — racine du dépôt :

```bash
# Souris : 0 hit tant que lot 2 non livré
grep -rnE 'MOUSEMOTION|MOUSEBUTTON|pygame\.mouse' src/

# Audio : 0 hit tant que lot 5 non livré
grep -rnE 'mixer|Sound\(|music\.' src/

# Modèle de sélection : 0 hit selected/focused/hover/highlight
grep -rnE 'selected|focused|hover|highlight' src/

# Menus KEYDOWN only (0 hit après lot 2, le contrôleur centralise)
grep -rn 'event.type != pygame.KEYDOWN' src/application/scenes/

# Pas d'actions de menu ni sérialisation bindings (0 hit après lot 2/3)
grep -rnE 'ui_confirm|ui_back|to_dict|from_dict' src/core/input/ ; echo "0 hit avant lots 2-3"

# Fenêtre : un set_mode de base ; RESIZABLE/vsync attendus APRÈS lot 3
grep -rnE 'set_mode|RESIZABLE|vsync|FULLSCREEN|SCALED' src/

# Scènes (4 + menu_panel avant lots 3-4 ; options/victory/level_select après)
ls src/application/scenes/

# UI-11 PEP 758 sans parenthèses (0 hit après lot 3)
grep -n 'except .*,' src/application/save_game.py

# FPS commentaire vs valeur (soldé par lot 3 / R-1)
sed -n '8,18p' src/core/settings.py

# UI-14 : gate présent dans world_ui après lot 4 (quick win)
grep -n 'Debug.is_enabled' src/ui/world_ui.py | head

# Comptage de tests
grep -rc 'def test_' tests/unit/*.py tests/headless/*.py
```

### Croisements avec `audit_consolide.md` et `audit_controles.md` (décisions §4a)

| Point | Audit UI | Audit consolidé | Audit contrôles | Décision |
|---|---|---|---|---|
| FPS 180 + vsync | UI-6, UI-12 (lot 3) | **R-1** | — | **D2 : absorbé par le lot 3** — ne pas faire R-1 deux fois ; soldé = DoD lot 3. |
| `AudioBus` | UI-10 (lot 5) | **R-2.4** (R-2 Phase 4) | — | **D3 : le lot 5 livre le seul `AudioBus`** ; R-2.4 couverte alors ; sinon R-2 reste ouverte. Écrire la décision dans les deux fichiers quand le lot 5 démarre. |
| Rebinding / bindings persistés | UI-5 (écran), UI-8 (libellés) | — | **C-7**, C-Lot 0d (données + disque) | **C-D6** : données et `settings.json` `bindings` côté contrôle ; UI ne livre que l'écran Contrôles. |
| Routeur / actions `ui_*` | UI-1, UI-2, D8 (focus Rects) | — | **C-1**, **C-3**, C-Lot 0b (`event_router.py`) | Un seul routeur sous `src/core/input/` ; l'UI ne fait que le modèle de focus et le rendu. |
| Mapping manette menu | UI-2, D12 (référence UX) | — | C-3 / C-5 (codes + seuils `settings.Input`) | Même mapping ; implémentation et tests matériels côté contrôle. |

## Validation du document

- Re-vérification code : 2026-09-22, `a6d20f8` — preuves §1/§2/§7.
- Durcissement agent : 2026-09-22 — §3, §4a, §4b, champs UI-7, mapping UI-2, schéma UI-5, D1-D12.
- Enchaînement contrôle : 2026-09-22 — renvois vers `notes/audit_controles.md` (C-Lot 0a/0b bloquants lots UI 1-2 ; rebinding porté C-7/C-D6 ; routeur `event_router.py`).
