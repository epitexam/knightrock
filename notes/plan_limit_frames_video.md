# Plan d'implémentation — Limite de frames dans le menu vidéo

## 0. Objet et contraintes

Ce plan décrit l'ajout d'un réglage de limite de frames dans `VideoScene`, aujourd'hui absent.

Contraintes :

- ne pas nommer le réglage « FPS » : avec le vsync, cette valeur ne contrôle rien ;
- ne pas modifier le comportement par défaut (la cible actuelle reste `Display.FPS`) ;
- ne pas faire entrer la limite dans `_mode_signature` : elle s'applique à chaud, sans recréer la fenêtre ;
- ne pas bumper `SETTINGS_FORMAT_VERSION` : la clé est optionnelle avec défaut ;
- valider chaque affirmation chiffrée contre le code réellement présent.

État observé :

- `pytest -q` : **1117 tests passés** ;
- `mypy src` : **142 fichiers analysés, aucune erreur** ;
- `ruff check src tests` et `ruff format --check src tests` : propres ;
- `Display.FPS = 60` (`src/core/settings.py:17`) ; une valeur supérieure a été
  essayée puis revertie pendant la rédaction de ce plan, sans commit. Le
  plafond doit rester robuste à ce réglage, d'où la dérivation en §4.2 ;
- `UserSettings` (`src/application/settings_store.py:27`) contient `width`, `height`, `fullscreen`, `vsync`, `ui_scale` — **pas de limite de frames** ;
- `Display.FPS` n'est consommé que par `Game._frame_delta` et par la dérivation du plafond anti-emballement.

## 1. Le problème : « FPS » serait un réglage qui ne fait rien

`Display.FPS` ne désigne pas la même chose selon le vsync :

| mode | comportement observé | code |
|---|---|---|
| vsync **off** | `clock.tick(Display.FPS)` cadence la boucle : c'est la cible | `src/core/game.py:276` |
| vsync **on** | la constante est **ignorée** ; le present bloque jusqu'au blanc vertical, donc c'est la fréquence de l'écran qui décide | `src/core/game.py:277` |

Un curseur nommé « FPS » serait donc inerte pour quiconque a le vsync actif — pire que son absence, puisqu'il donne l'illusion de maîtriser la cadence.

**Décision :** le régler s'appelle un *plafond de frames* (`Frame limit`), avec une option `Uncapped`. Un plafond garde un sens dans les deux modes, et l'affichage du taux réel de l'écran rend l'interaction lisible au lieu d'être devinée.

## 2. Preuves mesurées

### 2.1 Le plafond interagit avec le vsync

Écran 60 Hz modélisé, present bloquant, ~2 ms de travail par frame :

| limite | cadence réelle | min / max par frame | compteur |
|---|---|---|---|
| 240 (> écran) | 16.67 ms — **60.0 fps** | 16.59 / 16.75 | 59.9 |
| 120 (> écran) | 16.67 ms — 60.0 fps | 16.65 / 16.68 | 59.9 |
| 60 (= écran) | 16.67 ms — 60.0 fps | 16.65 / 16.68 | 59.9 |
| 30 (< écran) | 33.33 ms — 30.0 fps | **16.66 / 50.00** | 30.4 |

Deux conséquences :

1. **Au-dessus du taux de l'écran, le plafond ne mord pas** — comportement correct, et le compteur reste honnête.
2. **En dessous, la moyenne est juste mais la cadence est irrégulière** : à 30 fps sur 60 Hz, les frames alternent entre 16.7 ms et 50 ms. Le jeu annonce « 30 fps » et saccade. C'est inhérent à la combinaison des deux attentes, pas un bug — mais c'est ce qui rend l'affichage du taux réel indispensable.

### 2.2 La borne basse est dictée par `Simulation.MAX_FRAME_TIME`

`src/core/game.py:284` — `self._accumulator += min(self._frame_delta(), Simulation.MAX_FRAME_TIME)`, avec `Simulation.MAX_FRAME_TIME = 0.1` (`src/core/settings.py:302`).

| plafond | période | delta retenu | ticks sim/frame | temps perdu |
|---|---|---|---|---|
| 5 fps | 200.0 ms | 100.0 ms | 6.00 | **100 ms (50 %)** |
| 10 fps | 100.0 ms | 100.0 ms | 6.00 | 0 |
| 20 fps | 50.0 ms | 50.0 ms | 3.00 | 0 |
| 30 fps | 33.3 ms | 33.3 ms | 2.00 | 0 |

Sous 10 fps le delta est tronqué et le jeu tourne au ralenti. 10 est le seuil exact, sans marge : le moindre à-coup (chargement de niveau, pause GC) le dépasse.

### 2.3 Alignement sur la simulation

La simulation tourne à `Simulation.TICK_RATE = 60` (`src/core/settings.py:294`). Seules les valeurs qui **divisent 60** donnent un nombre entier de ticks par frame — 24 fps donne 2.5, qui alternent entre 2 et 3. Au-delà de 60, l'interpolation prend le relais.

## 3. Décisions

| sujet | choix | justification |
|---|---|---|
| nom du réglage | `Frame limit` | ne pas promettre ce que le vsync ignore |
| défaut | `Display.FPS` (60) | préserve le comportement actuel ; sinon `tick(0)` ferait tourner la boucle à la vitesse maximale (~500 fps sur cette machine) en consommant un cœur |
| min | **20** | période 50 ms contre un plafond dur de 100 ms → 2× de marge ; 3 ticks/frame pile |
| max | **500** | au-delà la limite est inatteignable (frame ~2 ms) ; sert à rejeter un JSON bricolé |
| valeurs exposées | `Uncapped, 20, 30, 60, 120, 144, 240` | 20/30/60 divisent 60 ; 144 couvre un écran 144 Hz sans deviner |
| vsync actif | ligne **reste éditable**, suffixe avec le taux réel | permet de plafonner sous le refresh pour économiser, et explique pourquoi au-delà ça ne change rien |
| simulation | inchangée | alimentée par le temps réel ; une limite basse fait sauter des frames affichées sans rien casser |
| persistance | pas de bump de schéma | clé optionnelle avec défaut : un fichier v1 existant prend le défaut |

## 4. Changements

### 4.1 `src/application/settings_store.py`

- `UserSettings` : ajouter `fps_limit: int | None = Display.FPS`.
- `to_dict()` : écrire `fps_limit` dans la section `video`.
- `from_dict()` : relire par `_bounded_int(video.get("fps_limit", Display.FPS), "video.fps_limit", 20, 500)`, en acceptant `None` comme « non plafonné ».

### 4.2 `src/core/game.py`

- Helper `_frame_rate()` → `settings.fps_limit if settings.fps_limit else Display.FPS`.
- Branche vsync off : `clock.tick(0)` si `fps_limit is None` (expression honnête de « sans plafond »), sinon `clock.tick(_frame_rate())`.
- Plafond anti-emballement : dérivé de `_frame_rate() * 4`, donc il suit toujours la limite et ne peut plus passer dessous, y compris sur `Uncapped`.
- **Aucun changement de `_mode_signature`** (`(width, height, fullscreen, vsync)`) : la limite s'applique à chaud, comme `ui_scale`.

### 4.3 `src/application/scenes/video_scene.py`

- `FRAME_LIMIT_VALUES = (None, 20, 30, 60, 120, 144, 240)`.
- Ligne `Frame limit: Uncapped` / `Frame limit: 240`, en reprenant le motif de `_cycle_scale` (index courant, direction gauche/droite, modulo).
- Suffixe quand vsync est actif : `Frame limit: Uncapped (screen 144 Hz)` via `pygame.display.get_current_refresh_rate()` ; masqué si la valeur vaut 0 (inconnue, cas headless).
- L'action rejoint le groupe qui cycle sur les trois entrées dans `_handle_row_value_navigation`.
- `fps_limit` ajouté à `_current_signature()` et à `_reset()`.

## 5. Tests

- **Persistance** : aller-retour avec et sans la clé ; bornage (19 et 501 rejetés vers le défaut) ; **non-régression** : un fichier v1 sans `fps_limit` est accepté.
- **Pacing** : `tests/unit/test_frame_pacing.py` référence `Display.FPS` **6 fois** → router via le réglage ; ajouter le cas `Uncapped → tick(0)` ; le plafond reste `>` la limite dans tous les cas.
- **Menu** : le cycle n'affiche jamais `None` comme valeur ; le suffixe n'apparaît que si vsync est actif ; `_reset` restaure bien la valeur.

## 6. Compromis assumé

Une limite **en dessous** du taux de l'écran avec vsync actif produit une cadence irrégulière (mesuré : 16.7 ms / 50 ms à 30 fps sur 60 Hz). Le compteur reste exact et la moyenne juste, mais le rendu saccade. Ce n'est pas un défaut de l'implémentation — c'est la conséquence physique de deux attentes qui se partagent la frame. L'affichage du taux de l'écran dans le menu est ce qui rend le phénomène compréhensible au lieu d'obscur.

## 7. Point ouvert

Si un jour le vsync doit être couplé à un choix de taux (au lieu d'être un simple booléen), la section 2.1 devra être refaite : le double cadencement vient du fait que les deux attentes visent la même refresh.
