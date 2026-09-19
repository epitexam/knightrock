# Audit UI — Interface, navigation, paramétrage (audit_consolide.md complément)

- **Commit audité** : `b493d802c8ecfde24eec9e487556cb62208b01be` (branche `master`).
- **Périmètre** : `src/application/` (scenes, scene_manager, save_game), `src/ui/`, `src/core/input/`, `src/core/game.py`, `src/core/settings.py` (Display/Debug), `tests/` existants.
- **Méthode** : relecture ligne à ligne des 4 scènes, du pipeline d'événements (`game.py:_handle_events`) et de la chaîne UI ; greps exhaustifs (souris, manette, audio, modèle de sélection, persistance de réglages) — chaque chiffre ci-dessous est vérifiable par un grep.
- **Verdict** : le ressenti « tout est à refaire » est **confirmé par le code**. Aucun des 4 usages attendus d'une interface de jeu n'est couvert : navigation souris (0 hit), navigation manette dans les menus (0 hit), sous-menus/réglages (0 scène, 0 fichier), HUD lisible par un joueur (tout est conditionné au mode debug). Le socle technique (`SceneManager` à pile, `PanelRenderer`, `InputBindings`, `SaveGame`) est sain et réutilisable — c'est le contenu UI qui manque, pas l'architecture.

## 1. État des lieux

| Capacité attendue | État actuel | Preuve |
|---|---|---|
| Menu navigable clavier | ❌ raccourcis fixes uniquement (`ENTER`/`N`/`Q`/`ESC`), pas de curseur | `menu_scene.py:47-57` |
| Menu navigable souris | ❌ aucun (`MOUSEMOTION`/`MOUSEBUTTON` : **0 hit** dans `src/`) | grep exhaustif |
| Menu navigable manette | ❌ menus = `KEYDOWN` only ; manette initialisée mais réservée au gameplay | `game.py:82,133-142`, scènes |
| Sous-menus / Options | ❌ 4 scènes plates (menu, gameplay, pause, gameover), aucune scène Options | `src/application/scenes/` |
| Réassignation des touches | ❌ defaults en dur, jamais sérialisés | `input_bindings.py:31-76` |
| Réglages vidéo (fenêtre/plein écran/vsync) | ❌ `set_mode` fixe, aucun `RESIZABLE`/vsync | `game.py` (init display) |
| Réglages audio (volumes) | ❌ aucun audio du tout (`pygame.mixer`/`Sound`/`music` : **0 hit**) | grep exhaustif |
| Sélection de niveau | ❌ seuls « continue » (dernier niveau) et « new game » ; `unlocked_levels` au-delà du dernier **inaccessibles** | `menu_scene.py:32-55`, `save_game.py:27-28` |
| HUD joueur lisible | ❌ tout l'affichage "UI" est derrière `Debug.is_enabled()` ; pas de barre de vie/posture en jeu normal | `level.py:299-319`, `ui_manager.py:20-120` |
| Écran d'aide aux contrôles | ❌ le panneau « aide » liste les touches du banc de debug, pas les contrôles du joueur | `ui_manager.py:59-71` |
| Modèle de sélection (focus/hover) | ❌ 0 hit `selected/focused/hover/highlight` (les 15 hits `cursor` sont des curseurs de layout debug) | `world_ui.py:825-848`, `panel_renderer.py:23-41` |

Base de tests existante réutilisable pour la réception : `tests/headless/test_scenes.py` (14 tests, verts), `tests/unit/test_menu_panel.py`, `test_save_game.py`, `test_input_manager.py`, `test_player_ui.py`, `test_ui_debug_panels.py`.

## 2. Constats

### Axe A — Navigation

**UI-1 — Aucune interaction souris (priorité haute, effort M)**
- *Constat* : toutes les scènes filtrent à la source sur le clavier — `menu_scene.py:48` (`if event.type != pygame.KEYDOWN: return`, idem `pause_scene.py:33`, `gameover_scene.py:34`) ; `gameplay_scene.py:93-107` ne traite qu'ESC et F1-F6. Aucun hit-test, aucune zone cliquable : `draw_centered_menu_panel` (`menu_panel.py:20-62`) retourne pourtant un `Rect` (prévu « useful for headless tests », `:40-42`) mais personne ne le réutilise.
- *Impact* : un joueur sans clavier AZERTY/QWERTY connu ne peut ni lancer, ni reprendre, ni quitter proprement.
- *Cible* : chaque item de menu expose son Rect ; clic = activation, survol = focus visuel.
- *Réception* : headless — injecter `pygame.event.Event(MOUSEBUTTONDOWN, pos=…)`, vérifier le changement de scène ; hover change le rendu de l'item.

**UI-2 — Manette inutile dans les menus (priorité haute, effort S/M)**
- *Constat* : la manette est correctement gérée au niveau application (`game.py:82` `joystick.init()`, `:133-142` `JOYDEVICEADDED/REMOVED` avec hot-plug et réassignation), mais `MenuScene/PauseScene/GameOverScene` ne traitent que `KEYDOWN`. `InputBindings.gamepad_buttons` (`input_bindings.py:47-57`) ne couvre que les actions de gameplay (jump/attack/guard), aucune action de menu (`ui_confirm`, `ui_back`, `ui_up/down`).
- *Impact* : joueur manette > obligé de poser la manette pour naviguer. Contradiction directe avec la cible « beat'em up jouable à la manette ».
- *Cible* : actions de menu dédiées (déplacer/valider/retour) mappées sur dpad, stick gauche (seuil), bouton A/B (ou équivalent), traitées dans le même contrôleur que clavier/souris.
- *Réception* : headless — `Event(JOYHATMOTION)` et `Event(JOYBUTTONDOWN)` simulés changent l'item courant / activent / reviennent.

**UI-3 — Pas de modèle de sélection (priorité haute, effort M — socle de UI-1/UI-2)**
- *Constat* : les options sont des chaînes figées : `self.options: tuple[str, ...]` (`menu_scene.py:34-42`), `"ENTER / ESC: resume"` (`pause_scene.py:23`), dessinées en texte brut (`menu_panel.py:46`). Aucun index d'item courant, aucun état `enabled`, aucun ordre de navigation — greps `selected|focused|hover|highlight` = 0 hit.
- *Impact* : impossible d'ajouter souris/manette/sous-menus sans d'abord inventer ce modèle à chaque scène. C'est la racine de « menu impraticable ».
- *Cible* : `MenuModel` (liste de `MenuItem(label, enabled, callback, rect)`, `index`, `move(+1/-1)`, `activate()`, `point_inside(pos)`) + rendu du curseur (flèche `▶`/surlignage) — la flèche *est* la preuve visuelle de l'item courant, absente aujourd'hui.
- *Réception* : tests unitaires purs du modèle (move/clamp/wrap/activate sur item désactivé) + rendu du curseur.

### Axe B — Paramétrage

**UI-4 — Aucun sous-menu, aucune scène Options (priorité haute, effort M)**
- *Constat* : `src/application/scenes/` contient exactement `menu_scene.py`, `gameplay_scene.py`, `pause_scene.py`, `gameover_scene.py`. `SceneManager` (`scene_manager.py:34-51`) expose `switch/push/pop` — la pile supporte nativement un sous-menu — mais jamais utilisée autrement que pause/game-over.
- *Cible* : `OptionsScene` pushée depuis menu et pause, avec onglets ou sous-liste : **Contrôles** / **Vidéo** / **Audio** / **Jeu** (difficulté). ESC/B = retour (pop).
- *Réception* : push depuis pause → retour par pop restaure la pause (déjà testable dans `test_scenes.py`).

**UI-5 — Bindings non réassignables, non persistés (priorité moyenne, effort M)**
- *Constat* : `input_bindings.py:5` promet « *These mappings can be customized to support user-defined keybinds* » mais : defaults en dur (`:31-76`), aucun `to_dict`/`from_dict`, aucune écriture disque. `SaveGame` (`save_game.py:24-29`) ne persiste que `unlocked_levels` + `last_level_id`. Un réglage éventuel serait perdu à chaque lancement.
- *Cible* : `settings.json` versionné (même schéma robuste que `SaveGame` : version, fallback sur anomalie, `KNIGHTROCK_SAVE_DIR` réutilisé) contenant bindings + réglages vidéo/audio ; écran Contrôles avec capture de touche (« appuyez sur une touche… ») et détection de conflit.
- *Réception* : roundtrip JSON ; capture de touche headless (événement simulé) ; fichier corrompu → defaults sans crash (même contrat que `save_game.py:63-65`).

**UI-6 — Aucun réglage vidéo (priorité moyenne, effort M)**
- *Constat* : `Display` (`settings.py:8-18`) : `WIDTH=1440, HEIGHT=900, FPS=180` constants ; `game.py` crée la fenêtre une fois via `set_mode(SIZE)` sans `RESIZABLE`, sans vsync, sans bascule plein écran. Le commentaire `settings.py:14-16` dit « rendering at 120 FPS » alors que `FPS = 180` (ligne 17) — incohérence déjà relevée (R-1, audit consolidé) et toujours non résolue.
- *Cible* : plein écran/fenêtré, résolution fenêtrée, vsync on/off ; `PanelLayout` est déjà « responsive by construction » (`panel_renderer.py:8-46`) — atout existant pour suivre le redimensionnement.
- *Réception* : headless — toggles de réglages appliqués à un display de test, persistés.

### Axe C — HUD & feedback joueur

**UI-7 — Pas de HUD joueur ; l'« UI » actuelle est l'outil de debug (priorité haute, effort M)**
- *Constat* : `UIManager` (`ui_manager.py:20-120`) n'expose que `draw_state_panel/draw_stats_panel/draw_scene_panel/draw_help_panel/draw_performance_panel` — affichés uniquement quand `Debug.is_enabled()` (routage dans `level.py:299-319`). `player_ui.py:13-140` montre des valeurs internes en jargon debug (`State/prev/Hist/buf/coy/pen`), utiles au dev, illisibles pour un joueur. `world_ui.py` (878 lignes) est l'overlay debug (hitboxes, labels flottants) : excellent outil, pas un HUD. Seul `draw_health_bars` (`ui_manager.py:119-120`) est orienté joueur.
- *Impact* : en jeu normal, l'écran ne dit ni la vie, ni la posture, ni les charges de dash, ni le combo — alors que le combat (posture, riposte, juggle/OTG) est précisément conçu autour de ces fenêtres.
- *Cible* : `ui/hud.py` distinct des panneaux debug : barre de vie, posture de garde, charges de dash, compteur de combo — alimentés par les mêmes données que `player_ui.py`, présentés joueur.
- *Réception* : headless — HUD dessiné sans `Debug.is_enabled()`, contenu et couleurs vérifiés par état (vie basse → rouge).

**UI-8 — Pas d'aide aux contrôles, libellés figés (priorité moyenne, effort S/M)**
- *Constat* : le seul panneau « aide » (`ui_manager.py:59-71`) liste `1-4 test attacks / F1-4 boxes…` = touches du banc de debug. Les libellés de menu (`"ENTER: play"`, `menu_scene.py:37-42`) sont des chaînes en dur qui ne reflètent ni `InputBindings` ni d'éventuels rebidings (UI-5). Aucun écran « Contrôles » consultable depuis menu ou pause.
- *Cible* : écran Contrôles généré depuis les bindings effectifs (clavier + manette), accessible depuis menu et pause ; libellés de menu calculés depuis les actions, plus des touches en dur.
- *Réception* : headless — le texte affiché contient le nom de touche retourné par `InputBindings`.

**UI-9 — Feedback et parcours joueur incomplets (priorité moyenne, effort M)**
- *Constat* :
  - **Sélection de niveau impossible** : le menu n'offre que « continue » (reprenant `last_level_id`, `menu_scene.py:52`) et « new game ». `SaveGame.unlocked_levels` (`save_game.py:27`) peut contenir plusieurs niveaux, mais il n'existe **aucun moyen** d'y accéder — ni relancer un niveau antérieur, ni choisir son point de départ.
  - **Fin de jeu sans écran de victoire** : `gameplay_scene.py:83-91` — dernier niveau fini → `switch(MenuScene)` direct, aucune célébration ni bilan.
  - **Transitions brutes** : `switch` sans fondu ; Game Over pousse un panneau statique (`gameover_scene.py:41-57`).
- *Cible* : écran de sélection de niveau (grille des `unlocked_levels`, verrouillé au-delà), écran de victoire, fondu de transition simple (fade alpha) partagé.
- *Réception* : headless — ouvrir la sélection, lancer un niveau N débloqué, naviguer ←/→ ; fin du dernier niveau → scène victoire.

### Axe D — Fondations & santé du code

**UI-10 — Aucun audio (priorité moyenne, effort L — prérequis des volumes d'UI-6/lot 3)**
- *Constat* : `pygame.mixer`/`Sound`/`music` : **0 hit** dans `src/`. Aucun son de menu, d'impact, ni musique. La cible « volumes dans Options » (UI-4/UI-6) n'a de sens qu'avec un `AudioBus` minimal (mixer, canaux sfx/musique, volumes master/sfx/music persistés).
- *Réception* : headless — mixer forcé en mode dummy (`SDL_AUDIODRIVER=dummy`), volumes appliqués et persistés ; absence de périphérique audio → dégradation silencieuse (comportement déjà exigé par le README pour l'affichage).

**UI-11 — Syntaxe Python 3.14 exclusive dans `save_game.py` (nouveau constat, priorité basse, effort XS)**
- *Constat* : `save_game.py:63` `except KeyError, TypeError, ValueError:` et `:78` `except OSError, json.JSONDecodeError:` — sans parenthèses. Valide uniquement via PEP 758 (Python ≥ 3.14) ; `pyproject.toml:6` fixe bien `requires-python = ">=3.14"`, donc cohérent aujourd'hui, mais fragile si la cible Python recule, et inhabituel à lire.
- *Cible* : parenthéser `except (KeyError, TypeError, ValueError):` — comportement identique, lisibilité et portabilité accrues.
- *Réception* : `python3 -m py_compile` + tests existants verts (`tests/unit/test_save_game.py`, 10 tests).

**UI-12 — Incohérences commentaires/décisions à trancher (effort XS)**
- `settings.py:14-17` : commentaire « rendering at 120 FPS » vs `FPS = 180` (recette R-1).
- `menu_scene.py:23-25` : docstring « *Rendering is deliberately textual (minimal scene)* » — cette décision de Phase 2 est précisément ce que cet audit invalide ; à réécrire dès le lot 1.
- `input_bindings.py:5` : promesse de personnalisation sans implémentation (cf. UI-5).

**UI-13 — Accessibilité (transverse, effort M, à traiter avec le lot 4)**
- Tailles fixes : `SysFont("Consolas", …)` (`panel_renderer.py:55-63`), `Debug.FONT_SIZE=24` (`settings.py:227`), menu 48/40 px (`menu_panel.py:29-30`) ; aucune mise à l'échelle selon la fenêtre.
- Palette : `text_muted (185,192,198)` sur `panel_bg (20,22,26,220)` (`colors.py:57-63`) — contraste correct, mais thème pensé pour du debug (styles.py:2 « *Debug/HUD theme* ») ; à assumer ou étendre en charte UI dédiée.
- Cible : au minimum, un réglage taille d'interface (petite/normale/grande) appliqué aux polices du menu et du HUD.

## 3. Cible proposée (architecture)

```
src/ui/menu_model.py    # MenuModel/MenuItem : index, move/activate, point_inside (pur, testable)
src/ui/menu_view.py     # rendu items + curseur + hover ; retourne les Rects pour le hit-test
src/ui/hud.py           # HUD joueur (vie/posture/dash/combo), indépendant de Debug
src/application/settings_store.py  # settings.json versionné : bindings + vidéo + audio
src/application/scenes/options_scene.py    # Contrôles / Vidéo / Audio / Jeu
src/application/scenes/level_select_scene.py
src/application/scenes/controls_scene.py
src/application/audio_bus.py               # (lot 5) mixer + volumes
```
- Les scènes restent les points d'entrée `handle_event` ; un contrôleur UI commun route `KEYDOWN`/`MOUSE*`/`JOY*` vers `MenuModel` (une seule table de navigation pour les 3 périphériques — c'est ce qui garantit la cohérence clavier/souris/manette).
- `SceneManager` push/pop sert pour Options/Sélection/Contrôles (aucune modification du manager nécessaire, `scene_manager.py:41-51` suffit).
## 4. Plan par lots (ordre d'implémentation)

Chaque lot est livrable et recevable indépendamment ; l'ordre suit les dépendances (le modèle de sélection conditionne tout le reste).

| Lot | Contenu | Constats couverts | Effort | Réception principale |
|---|---|---|---|---|
| **1. Socle navigation** | `MenuModel`/`MenuItem` + curseur visuel ; scènes menu/pause/gameover/gameplay converties en items navigables (↑/↓ + Enter/ESC conservés) | UI-3, UI-12 (docstring menu) | M | tests unitaires du modèle + headless ↑/↓/Enter |
| **2. Souris + manette** | Contrôleur UI commun : hover/clic souris sur Rects d'items ; actions menu manette (dpad/stick/A/B) ; hot-plug réutilisé | UI-1, UI-2 | M | events souris/manette simulés ; 3 parcours clavier/souris/manette verts |
| **3. Réglages persistés** | `SettingsStore` (`settings.json` versionné) + `OptionsScene` : Contrôles (capture + conflits), Vidéo (plein écran/vsync), Audio (volumes, effectifs dès lot 5) ; parenthéser `save_game.py` | UI-4, UI-5, UI-6, UI-11 | L | roundtrip JSON, capture headless, persistance relance |
| **4. HUD & parcours** | `ui/hud.py` (vie/posture/dash/combo) sans Debug ; sélection de niveau depuis `unlocked_levels` ; écran Contrôles consultable ; écran de victoire ; taille d'interface (UI-13) | UI-7, UI-8, UI-9, UI-13 | L | HUD headless sans Debug ; sélecteur navigue les niveaux débloqués |
| **5. Audio & polish** (optionnel) | `AudioBus` (mixer dummy-safe) + sons menus/impacts + musique ; fades de transition | UI-9 (transitions), UI-10 | L | mixer dummy headless ; volumes persistés ; fade testé |

Estimations d'effort : S ≈ demi-journée, M ≈ 1-2 j, L ≈ 3-5 j (hors polissage visuel/itérations game-feel).

### Dépendances
- Lot 2 dépend du lot 1 (sans modèle d'items, pas de hit-test ni de navigation manette).
- Lot 3 dépend du lot 1 (Options est un menu) ; lot 5 n'est pas requis pour livrer les volumes (lot 3 les persiste, lot 5 les alimente).
- Lot 4 est parallélisable avec le lot 3 (aucun chevauchement de fichiers, à part `menu_scene` pour le lien Sélection).

## 5. Règles (à respecter pendant l'implémentation)

1. **Aucun changement de gameplay** : les lots touchent `src/application/`, `src/ui/`, `src/core/input/` (exposition des bindings) — jamais la simulation (`src/core/level/`, `src/combat/`, `src/entities/`).
2. **Pas de nouveau framework** : pygame seul, réutilisation de `SceneManager`, `PanelRenderer`, `PanelLayout`, `SaveGame` comme modèle de persistance.
3. **Tout item affiché est atteignable et testé** (convention « No dead menu options » du README §Tests) — un item désactivé doit afficher sa cause.
4. **Réception headless uniquement** : tous les tests passent via `SDL_VIDEODRIVER=dummy` et événements `pygame.event.Event` injectés — aucune saisie réelle requise en CI.
5. **Panneaux debug intacts** : F1-F5, `world_ui.py` et `player_ui.py` restent opérationnels pendant et après les lots ; le HUD joueur s'ajoute, il ne remplace pas.
6. **Un seul fichier de persistance joueur** : `settings.json` (réglages) séparé de `savegame.json` (progression), même contrat de version/fallback.

## 6. Réception globale (checklist de bout en bout)

- [ ] Menu praticable **100 % clavier** (↑/↓/Enter/ESC), **100 % souris** (hover + clic), **100 % manette** (dpad/stick/A/B) — trois parcours automatisés verts.
- [ ] Pause → Options → modifier une touche → retour → relancer le jeu : le rebinding est conservé (`settings.json`), et un `settings.json` corrompu retombe sur les defaults sans crash.
- [ ] Options Vidéo : bascule plein écran/fenêtré persistée ; HUD et menus restent lisibles après redimensionnement (`PanelLayout`).
- [ ] Options Audio : volumes master/sfx/music modifiables et persistés (même sans périphérique audio : dégradation silencieuse).
- [ ] En jeu **sans mode debug** : barre de vie, posture, charges de dash, combo visibles et à jour.
- [ ] Menu : écran de sélection des niveaux débloqués navigable ; tous les `unlocked_levels` atteignables (fin du blocage UI-9).
- [ ] Fin du dernier niveau → écran de victoire (plus de retour menu muet).
- [ ] Écran Contrôles accessible depuis le menu **et** la pause, généré depuis les bindings effectifs.
- [ ] `python3 -m py_compile src/**/*.py` OK ; suites existantes vertes (`test_scenes.py`, `test_menu_panel.py`, `test_save_game.py`, `test_input_manager.py`, `test_player_ui.py`, `test_ui_debug_panels.py`) + nouveaux tests des lots 1-4.
- [ ] mypy strict sur les nouveaux modules (pas d'override à ajouter au `pyproject.toml` — l'UI est déjà dans le périmètre typé).

