# Dimensions, fenêtre et cadrage — rework du 2026-09-26

> Ce document remplace le verdict « Clos » que `notes/audit_ui.md` portait sur
> UI-6 (Vidéo). Ce verdict était faux, et il l'était pour une raison structurelle
> qu'il faut écrire : **la livraison qu'il décrivait était correcte, et c'est
> précisément ce qui rendait son critère faux.** Le critère était « la fenêtre
> n'est pas redimensionnable, donc le viewport logique est stable ». Il est
> stable, et pour la mauvaise raison : la fenêtre est la source de vérité, donc
> le joueur ne peut rien choisir. Un critère qui ne peut pas échouer ne prouve
> rien.

## 1. Le symptôme

Le monde visible était la fenêtre divisée par un zoom fixe. La fenêtre venait
d'une liste de sept résolutions absolues. Le joueur pouvait donc voir plus de
niveau en ouvrant le menu vidéo.

Mesuré sur le niveau réellement enregistré (`LEVEL_PATHS[0]` → `1.tmx`,
40×30 tuiles = 2560×1920 px monde), avec le zoom 1.25 de l'époque :

| preset | monde visible | portion du niveau |
|---|---|---|
| 1024×576 | 819 × 461 | 32% L / 24% H |
| 1280×720 | 1024 × 576 | 40% L / 30% H |
| 1440×900 (défaut) | 1152 × 720 | 45% L / 38% H |
| 1920×1080 | 1536 × 864 | 60% L / 45% H |
| 2560×1440 | 2048 × 1152 | **80% L / 60% H** |

Et sur les niveaux 40×15 (`3`, `5`, `6`, `omni`, 2560×960 — non enregistrés,
mais présents dans le dossier) : **120% de la hauteur** au preset 2560×1440,
c'est-à-dire le niveau entier d'un coup, avec la marge autour.

La course linéaire est de 2.5×, la course en surface de 6.25×, entre le plus
petit et le plus grand preset. Le temps de réaction, la distance de dash à
l'écran et la quantité de niveau visible étaient tous des fonctions d'un réglage
vidéo.

## 2. La cause

Il n'y avait aucun nom pour « la surface sur laquelle on dessine ». Le code
l'appelait `display_surface`, et elle *était* la fenêtre. Toute la chaîne en
dépendait :

```
Game._configure_display  ->  Level.__init__  ->  Camera(window_w, window_h)
                                                       |
                                        viewport_width = width / zoom
```

`Camera` lisait la fenêtre, donc « combien de monde est visible » était une
question de vidéo. Aucun test ne pouvait l'attraper : les tests vérifiaient que
la caméra suivait le joueur et que le culling était cohérent, ce qui restait vrai
dans tous les cas.

Le second défaut, moins grave mais dans la même famille : la liste de
résolutions était une affirmation sur l'écran du joueur que le jeu n'a aucun
moyen de vérifier. D'où 2560×1440 proposé à un portable 1366×768, et une fenêtre
plus grande que l'écran à l'ouverture.

## 3. La correction

Trois grandeurs qui n'en formaient qu'une :

| Objet | Rôle | Ne sait rien de |
|---|---|---|
| `Framing` | le rectangle de monde visible, en unités monde. **Fixe.** | tout |
| `Viewport` | la surface pixel fixe sur laquelle tout est dessiné | la fenêtre |
| `Stage` | la fenêtre OS : mode, taille, position, DPI, vsync | le monde |
| `Presentation` | `Viewport` → fenêtre, et le pointeur en retour | — |

> **L'invariant :** la simulation lit `Framing` et rien d'autre. Taille de
> fenêtre, DPI, mode d'écran et dimensions du bureau ne sont pas observables
> depuis elle.

Conséquences, toutes des suppressions :

- **la caméra n'a plus de zoom.** `screen = world - offset`. Comment le monde
  est *dessiné* est la question de l'échelle de rendu, décidée au chargement.
  `test_camera.py` assert l'**absence** de `zoom` et `set_viewport_size`, pour
  que les remettre ne soit pas un retour silencieux au comportement d'avant ;
- **plus de présentation partielle.** La cible étant fixe, la frame terminée
  est mise à l'échelle d'un bloc sur la fenêtre. L'appareil de dirty rects,
  son budget, la déclaration d'overlay rects et le contournement « le HUD est en
  retard d'une frame » ont disparu avec le besoin qu'ils servaient — environ
  180 lignes dont le seul métier était de garder d'accord une région d'effacement,
  un ensemble d'overlays déclarés et un ensemble présenté ;
- **un redimensionnement de fenêtre n'atteint plus aucun dessin.** `VIDEORESIZE`
  recalcule le rectangle de lettrebox et s'arrête. La fenêtre est
  redimensionnable, et le glissement ne peut plus changer ce que le joueur voit ;
- **la liste de résolutions devient une fonction du bureau.**

## 4. Preuves

| invariant | test |
|---|---|
| Le cadrage est plus petit que **tout** `.tmx`, sur les deux axes | `test_framing_contract.py` |
| Le manifeste des niveaux est vrai | `test_levels_manifest.py` |
| La simulation est identique à 5 tailles de fenêtre et 3 échelles de rendu | `test_sim_is_display_independent.py` |
| Un clic dans les barres de letterbox ne déclenche rien | `test_presentation.py`, `test_pointer_mapping` via `Game._to_target_coordinates` |
| La barre ne peut pas Cadre → fenêtre | `test_display_detection.py` |
| Un bouton « décaler vers l'écran sous le curseur » n'existe pas | reste à trancher, voir §7 |

`test_framing_contract.py` lit `data/levels_manifest.json` et non les `.tmx` :
`assets/` est git-ignoré, donc un test qui lit les vrais fichiers passerait en CI
sans avoir jamais vu un niveau — exactement l'échec que ce rework corrige.
`test_levels_manifest.py` régénère le manifeste depuis les fichiers réels et
échoue sur toute dérive quand ils sont présents.

## 5. Ce que la mesure a changé

Deux chiffres ont fait bouger des décisions, et ils ne sont pas ceux qu'on
attendait.

**La présentation coûte selon la fenêtre, pas selon la cible.**
`tests/benchmarks/render_benchmark.py` :

| fenêtre | lissé | nearest | + dessin 2× | % d'une frame 60 Hz |
|---|---|---|---|---|
| 1280×720 | 3.95 ms | 1.03 ms | 8.17 ms | 49% |
| 1920×1080 | 5.75 ms | 2.33 ms | 9.97 ms | 60% |
| 2560×1440 | 7.46 ms | 3.63 ms | 11.68 ms | 70% |
| 3440×1440 | 9.49 ms | 4.64 ms | 13.72 ms | 82% |
| 3840×2160 | 13.32 ms | 7.20 ms | 17.54 ms | **105%** |

L'échelle de rendu ne change rien à ce coût : elle rend les sprites plus nets ou
plus flous, pas la frame moins chère. C'est un réglage de **netteté**, et le
dernier plan recommandait 2× « parce que c'est net » sans savoir qu'en 4K la
frame ne tient pas. Le menu vidéo dit maintenant au joueur quand sa fenêtre est
trop grande pour le couple par défaut.

**Un seul cadrage possible par niveau.** Les niveaux 3/5/6/omni font 960 px de
haut. Un cadrage de 648 px en montre 68%. Resserrer davantage n'est pas une
question de code : c'est la taille de ces niveaux.

## 6. Faits plateforme vérifiés (pas supposés)

Chacun de ceux-ci a coûté une erreur, et chacun a été vérifié contre
pygame-ce 2.5.7 plutôt que lu dans une doc :

Le passage en revue sur une **vraie session** a invalidé une ligne de ce
tableau : voir §9.

| supposition | réalité |
|---|---|
| `pygame.HIDPI` active le high-DPI | **n'existe pas**. C'est `SDL_VIDEO_HIDPI=1`, avant `pygame.init()` |
| `pygame.Window` remplace `set_mode` | **ni `.vsync` ni `.fullscreen`** en 2.5.7 |
| `WINDOWPOS_CENTERED` recentre la fenêtre | **refusé** par `pygame.display.set_window_position` (« position must be two numbers »), mais **accepté** par `pygame.Window.position`, qui est le seul moyen correct — voir §9 |
| un index d'écran hors bornes est ignoré | **lève** `displayIndex must be in the range 0 - 0` |
| `get_current_refresh_rate()` avant la fenêtre | **lève** `No open window`. `get_desktop_refresh_rates()` non, et couvre tous les écrans |
| `pygame.SCALED` est une base stable | pygame la documente comme **expérimentale**. Elle est sortie : la cible de rendu fait le letterbox |
| un renderer SDL déporterait le scaling sur le GPU | `Renderer` n'a pas `create_texture` et `from_window(None)` échoue. **Pas d'évasion GPU** en 2.5.7 |
| `smoothscale` à l'échelle 1:1 est gratuit | **2.19 ms**. `Presentation` court-circuite le cas 1:1 |
| le vsync en mode fenêtre fonctionne | SDL ne l'honore que pour une surface `SCALED` ou `GL`, et nous n'en avons plus. `is_vsync()` est interrogé après coup et le menu affiche « off (unavailable) » |

## 7. Choix assumés, et ce qui reste ouvert

**Letterbox, pas étirement.** Le mode « expand » de Godot — qui laisse la
hauteur fixe et élargit la largeur au ratio de l'écran — montrerait 101% de la
largeur d'un niveau de 24 tuiles en 21:9, et 150% en 32:9. Ce n'est pas
proposé : ce serait ouvrir exactement la porte que ce rework ferme. Si un jour il
l'est, il faut savoir qu'il rend la cible de rendu dépendante de la fenêtre, et
donc l'invariant ci-dessus faux dans ce mode-là.

**Écran primaire, fenêtre centrée, rien de persisté.** Choix du joueur. Le
multi-monitor est résolu ainsi : l'index d'écran est toujours 0, ce qui supprime
le seul risque réel (un `settings.json` voyageur qui fait planter la première
frame sur un portable), et la fenêtre est centrée sur l'écran primaire avec un
bornage à zéro. Un joueur dont l'écran de jeu n'est pas le primaire peut
déplacer la fenêtre à la main en mode fenêtre, mais pas l'obtenir en borderless.
Échappatoire possible, non implémentée : une ligne « Déplacer vers l'écran sous
le curseur ».

**Le mode d'écran a une valeur `auto`.** Elle se résout à chaque lancement.
C'est plus qu'un réglage : c'est la déclaration que le jeu ne connaît pas
l'écran du joueur et ne le devine pas.

**Écartés faute de mesure à ce jour :** la position de multi-monitor persistée
(le joueur l'a refusée), et le nombre d'écrans proposals dans le menu (aucun
besoin avec l'index fixe à 0).

## 8. Recette manuelle — en cours

Rien de ce qui suit n'est vérifiable sous le driver dummy. À faire sur une
session réelle avant de considérer cette migration comme récettée :

1. `is_vsync()` après `set_mode` en fenêtre et en borderless — noter si le
   driver honore la demande, et si la ligne du menu dit vrai ;
2. basculer fenêtre → borderless → fenêtre : la fenêtre doit revenir **centrée
   sur l'écran primaire**, sans saut ;
3. `get_desktop_refresh_rates()` sur l'écran courant ;
4. redimensionner la fenêtre à la souris : **le cadrage ne doit pas changer** ;
5. brancher un second écran en cours de session puis relancer ;
6. sur Wayland : le placement de la fenêtre et le comportement du plein écran.

## 9. Ce que la revue a cassé

Une passe de relecture a demandé si le chemin de rendu était réellement adapté.
Il l'était — et la réponse était fausse, parce que la question avait été posée
sur la forme plutôt que sur le fond.

**La caméra ne peut pas être une translation pure.** J'avais supprimé son
échelle enJuguant que « la magnification appartient au pipeline d'assets ». C'est
faux : la magnification s'applique aux **rectangles** autant qu'aux images. La
cible vaut `Framing × échelle`, donc un rectangle monde doit être multiplié pour
atterrir sur les bons pixels.

Concrètement, à l'échelle 2 : un sprite de 64 unités était agrandi en 128 px
puis blité dans un rect de 64 px — et `pygame.blit` **rééchantillonne la source
pour l'ajuster à la destination**, sans rien dire. Le monde était donc dessiné à
la moitié de la densité qu'annonce le cadrage, et n'occupait que le **quart
supérieur gauche** de la cible. C'est ce que « tout est cassé » décrivait, et
c'était ma régression.

La correction : la caméra a de nouveau une échelle, mais elle n'est plus une
constante divisée par la taille de la fenêtre — elle est **l'entier dont la
cible a été construite**, lu sur la cible par `Camera.for_target`. La propriété
qui compte survit intacte : `viewport = Framing × échelle`, donc le monde visible
est le cadrage et ne dépend d'aucun réglage.

Trois conséquences de conception, qui valent d'être écrites parce que chacune
aurait dû être posée avant :

- **une cible qui ne correspond à aucun entier est refusée**, pas arrondie.
  Arrondir dessinerait le monde à une densité que personne n'a demandée et le
  cadrage cesserait de décrire ce qui est à l'écran ;
- **la caméra détient l'échelle et le renderer la lit.** Deux dérivations du même
  nombre, c'est une de trop : la caméra s'en sert pour les rectangles, donc un
  désaccordscale les images et pas les rects — précisément le bug ci-dessus ;
- **`Renderer.set_surface` prévient la caméra.** Sans cela, un changement
  d'échelle de rendu laissait la caméra à l'ancienne valeur.

Le test de chaîne des surfaces ne l'avait pas vu, et c'est instructif : il
vérifiait l'**identité** des objets, pas la géométrie. Une chaîne de surfaces
peut être entièrement correcte et dessiner une frame cassée. Il vérifie
maintenant qu'un sprite agrandi et son rect de blit font la même taille, à
chaque échelle.

## 10. Ce que la revue a cassé, deuxième fois : le menu vidéo

« Le menu vidéo est inutilisable, je peux cliquer sur pas grand chose. »

Le menu était **entièrement** câblé au clavier, et à la souris six de ses neuf
lignes ne faisaient rien. Le symptôme est discret parce que la ligne
**s'illuminait quand même** : le clic était reçu, il déplaçait le focus, et il
fallait ensuite appuyer sur une flèche pour que la valeur bouge. Une ligne qui
répond en sursautant est plus Trompeuse qu'une ligne qui reste grise.

Deux bugs distincts, dont un ne se voyait pas :

- **`handle_routed` ne traitait que `size`, `reset` et `back` au clic.** Les six
  autres renvoyaient leur action, et personne ne la consommait. L'ancien code
  gérait `fullscreen`, `vsync` et `scale` au clic ; la réécriture v2 l'a perdu.
- **un clic sur une ligne booléenne déjà active ne faisait rien non plus.**
  `←`/`→` *positionnent* la valeur — c'est le bon modèle pour balayer une liste,
  et les deux touches ne se ressemblent pas. Mais un clic n'a pas de direction :
 routé sur `UI_RIGHT`, il *positionnait* `on`. Sur une ligne affichant déjà « on »,
  il ne se passait rien. Une ligne qui répond une fois sur deux est une ligne
  morte.

Le correctif est une seule méthode `_cycle(name, action, click=)`, appelée par
les deux chemins. Les deux listes de lignes sont la cause : elles nommaient les
mêmes lignes, et il n'y avait rien qui les oblige à rester d'accord. Un clic
avance d'une valeur ; sur un booléen, il bascule.

**Ce que les tests disaient.** Les tests existants passaient tous : ils
appelaient `model.activate(index)` et vérifiaient l'action *retournée*. Ce qui
manquait est l'étape d'après — la consommation de cette action par la scène, qui
est précisément là où le bug se logeait. Le nouveau test clique sur le rectangle
**que la vue a réellement dessiné**, passe par `handle_routed`, et vérifie que
les settings ont bougé. Un `test_every_row_does_something` complète vérifie
qu'aucune ligne n'est hors des deux listes.

Vérifié de bout en bout : les neuf lignes répondent à un clic converti depuis
une position fenêtre, via le chemin réel `Game._to_target_coordinates` →
`SceneManager.handle_event`. Le sélecteur de résolution, lui, était sain (5/5).

## 11. L'audit de la branche entière

Demande : aucune régression sur les commits de la branche, aucun code inutile,
et un nouveau système en phase avec le reste.

**La méthode, d'abord, parce qu'elle est le résultat.** Les deux régressions
précédentes ont été introduites par cette branche et sont passées au vert. Un
contrôle par « les tests passent » aurait répondu « aucune régression » — la
réponse était fausse deux fois. La suite testait des *points* ; les bugs
étaient dans les *espaces* : une échelle de rendu qu'aucun fixture n'utilisait,
et un chemin de code qu'aucune assertion ne suivait jusqu'aux réglages. D'où
`tests/unit/test_display_properties.py` : des grilles, pas des cas.

### Ce qui a été vérifié sain

- La promesse centrale : la cible ne dépend que de l'échelle, sur 13 fenêtres.
- Le letterbox préserve le ratio à moins d'un pixel d'arrondi près, sur 13
  fenêtres — compris carrée, portrait et ultrawide.
- Le mapping pointeur est écrit une seule fois et appelé une seule fois.
- Les suppressions sont complètes : `FrameStats`, `frame_stats`, `scene.surface`,
  `RenderTarget`, `on_resize`, toute l'API `dirty()`. Zéro trace.
- `display` est une feuille (zéro import de projet) ; `core → application/ui`
  est le style préexistant.
- Le `except` sans parenthèses est la PEP 758, valide en `>=3.14`. Le français
  dans les commentaires est la convention de la base (17 fichiers avant, 16
  après). Deux fausses alertes vérifiées plutôt que signalées.

### Code mort **ajouté** par la branche

`Viewport.size_in_world_units` et `UserSettings.is_windowed` : supprimés, sans
appelant. `MIN_SAFE_FRAME_LIMIT` : supprimé, et son explication déplacée sur
`MIN_FRAME_LIMIT`, qui était la constante réellement appliquée — même nombre,
deux noms, et le nom qui s'expliquait n'était pas celui qui comptait.

`desktop_refresh_rates(index)` acceptait un index qu'il ignorait, et sa
docstring affirmait « covers every display ». pygame 2.5 ne prend aucun
argument : la promesse était inimplementable. Paramètre supprimé, docstring
corrigée, et la limite dite — les taux sont ceux de l'écran principal, ce qui ne
tient que parce que la fenêtre est posée sur l'écran 0.

`UserSettings.frame_rate` : supprimé. Il renvoyait `Display.FPS` quand
`frame_limit` est `None`, alors que la boucle, elle, renvoie 0 = sans limite.
Du code mort, et faux : il promettait 60 fps à qui venait de demander
l'inverse.

`Framing.is_smaller_than` reste. Elle n'est appelée que par un test, mais elle
*est* la définition du contrat de cadrage, et ce test la fait tourner sur
chaque `.tmx` du dossier. La déplacer dans le test l'éloignerait de ce
qu'elle garantit.

### La garde qui avait disparu

L'ancien `Camera` rejetait un zoom non positif, et un test le prouvait.
`Camera.__init__` faisait `max(1, int(scale))` — un clamp silencieux, et
`Camera(framing, 1.9)` répondait `1`. C'est exactement la divergence
images/rectangles que cette branche avait déjà livrée. La production n'était pas
atteignable (`for_target` seul), mais `Viewport` et `Camera` avaient deux
politiques sur le même nombre.

Les deux passent maintenant par `checked_render_scale`, et refusent la même
chose. Le test de refus est revenu.

### La troisième régression : le réglage ignoré au lancement

`apply_settings` reconstruisait la cible quand `render_scale` changeait, mais
`initialize_display` construisait la cible depuis la constante :

    self.viewport = Viewport(DEFAULT_FRAMING, DEFAULT_RENDER_SCALE)

Un « Render scale 3x » choisi au menu s'appliquait immédiatement — le menu
affichait 3x et le jeu dessinait bien en 3x — et le **lancement suivant**
revenait à 2x, le menu affichant toujours 3x. Un réglage qui marche jusqu'au
redémarrage, la plus difficile à remarquer.

Le réglage est maintenant honoré au lancement, et un test le prouve pour 1, 2
et 3.

### L'écart de cohérence

`DEFAULT_RENDER_SCALE = 2` était une constante dure, alors que la taille de
fenêtre avait reçu un mode `AUTO`. Sur un portable 1366×768, le jeu rendait
2304×1296 puis réduisait : 4× le coût de remplissage pour une image plus
floue. Le système s'était adapté à la machine pour la taille, et pas pour la
netteté.

`render_scale_for(size, framing)` choisit désormais la plus petite échelle
offerte dont la cible couvre la fenêtre. La fenêtre, pas le bureau : un jeu
fenêtré en 4K garde 2x pour une fenêtre 2560×1440.

| Fenêtre | Avant | Après |
|---|---|---|
| 911×512 (portable 1366) | 2x | **1x** |
| 1280×720 | 2x | 2x |
| 1440×900 | 2x | 2x |
| 2560×1440 (borderless) | 2x | **3x** |
| 3840×2160 (borderless) | 2x | 3x (borné) |

Un fichier de réglages qui **n'a jamais** choisi d'échelle la laisse au
lancement, qui l'écrit ensuite comme les autres. Un fichier qui en a une la
garde, même si la machine a changé : le joueur l'a choisie. Bureau inconnu
(headless) → l'ancienne constante, donc le comportement d'aujourd'hui est
intact hors machine réelle.

C'est le compromis assumé : la valeur ne change que sur une configuration
neuve, ou après un reset des réglages vidéo. Le menu affiche « auto » tant que
la fenêtre n'existe pas, ce qui est rare et exact.

### Le nom qui a produit le bug

Trois « scale » dans un sous-système, dont deux ne sont pas la même chose :
`Viewport.scale` et `Camera.scale` sont des entiers — la cible est ce nombre de
fois le cadrage, dessiné pixel pour pixel. Celui de `Presentation` est une
fraction et ne décrit que la frame finie en route vers l'écran. Il s'appelle
maintenant `fit`, et la raison est écrite sur l'attribut : le bug de la caméra
est venu précisément de l'homonymie.

### Ce que les tests de propriété ont révélé en les écrivant

Trois de mes propres assertions étaient fausses, et il valait la peine de les
corriger plutôt que d'assouplir le code :

- l'identité de l'image source ne vaut **qu'à l'échelle 1** ; je l'avais
  paramétrée sur toutes, ce qui n'aurait pu passer qu'à 1 ;
- à 1366×768 le letterbox fait 1365×768 — l'arrondi au pixel, pas un
  étirement. Ma tolérance de 1e-6 sur le ratio était irréaliste ; la borne
  est maintenant exprimée en pixels, ce qui veut dire quelque chose ;
- une fenêtre au ratio du cadrage n'a **aucune barre**, donc « le bord gauche
  est une barre » est faux pour une 16:9 sur une 16:9. Le test compare
  désormais `pointer_in_viewport` à `rect.collidepoint` sur une grille, sans
  supposer quel axe porte les barres.

Et une vraie mesure : un seul asset du niveau enregistré est à un pixel de son
propre rect, **à toutes les échelles, 1x comprise**. Ce n'est donc pas
l'échelle — c'est l'arrondi d'une hauteur de monde fractionnaire. La propriété
qui distingue l'arrondi de la régression est donc que le désaccord **ne grandit
pas** avec l'échelle, et c'est celle-ci qui est testée.

1369 tests, avec et sans `DEBUG=1`.

## 12. Le tremblement de la pause

« Pourquoi quand j'appuie sur pause, le jeu tremble ? »

La pause gèle bien la simulation : `SceneManager.update` n'avance que la scène
du dessus, donc le niveau ne tick plus. Ce qui ne se gelait pas, c'est
**l'image**.

`SceneManager.draw` repeint toute la pile à chaque frame — par conception, pour
qu'une surcouche translucide puisse couvrir une scène figée — et la scène de
jeu figée ne produisait pas les mêmes pixels deux fois.

La cause est l'interpolation. `begin_frame` mélange la position de départ du
dernier tick et celle d'arrivée, et **seul un tick peut refermer l'écart**. Sans
tick, l'écart reste ouvert, et `render_alpha` — la fraction du reste dans
l'accumulateur — continuait d'errer, parce que l'accumulateur reçoit toujours
du temps réel et se vide dans des ticks qui ne font rien. Chaque fraction
errante était dessinée comme du mouvement.

Mesuré, en pause, `camera._shift_y` par frame :

    -1047,055  -1046,639  -1046,223  -1045,808  -1045,392

et 1800 à 6500 points échantillonnés changeaient d'une frame à l'autre.

Le même défaut existait sur `GameOverScene` et `VictoryScene`, qui font
exactement la même chose que `PauseScene`. Il y était invisible parce que leur
`draw` remplit la cible en opaque : le monde dessous est caché. Ce qui est
cohérent avec le symptôme rapporté, qui ne parle que de la pause.

**Le correctif** est une propriété, pas un cas particulier :
`Scene.halts_simulation`. Une scène qui arrête le monde le déclare, et
`render_alpha` renvoie alors 1 — la picture est exactement où est la
simulation, ce qui est à la fois vrai et immobile. Une scène qui oublie de le
déclarer retrouve le monde qui glisse, et rien d'autre dans le système ne le lui
dirait.

Après : **zéro octet modifié** d'une frame à l'autre, en pause comme en game
over.

### Ce que les tests m'ont appris à force

Trois fois de suite, mes tests initiaux passaient avec le bug présent. Chacun
méritait une correction, pas un assouplissement :

- le test de pixels **échantillonnait un pixel sur trois**, alors que la dérive
  est *sous le pixel* (0,4 unité monde, 0,8 px à l'échelle 2). Il regardait une
  frame glisser sans la voir. Il compare maintenant les buffers bruts : exact,
  et assez rapide pour l'être vraiment ;
- le fixture **laisait la physique du joueur décider** si la caméra avait un
  écart à interpoler. Il le crée maintenant explicitement, et il échoue si l'écart
  n'existe pas — un test qui ne peut pas être vide ;
- le test d'interpolation **dépendait du temps réel** sur trente frames, et
  échouait pour la mauvaise raison quand le résidu d'accumulateur était nul
  chaque frame. Il écrit l'accumulateur et vérifie la correspondance.

Un quatrième cas, et celui-là vient de l'environnement plutôt que de moi : le
test de pixels passait sans `DEBUG=1` et échouait **avec**. La cause est l'overlay de
debug, qui affiche des temps de frame vivants en haut à droite et *doit* changer
à chaque frame. Le test est donc ignoré sous `DEBUG=1`, et le dit. Sans cela la
seule réponse honnête aurait été d'affaiblir l'assertion, ce qui aurait jeté
l'exactitude qui fait son intérêt. La couverture sous debug reste assurée par
les autres tests, qui n'y sont pas sensibles.

1378 tests, avec et sans `DEBUG=1`.

## 13. Ce que la vraie session a cassé

Le premier passage sur la machine de développement (Wayland, deux écrans :
2560×1440 @180 Hz en primaire, 1920×1080 @60 Hz à sa gauche) a invalidé une
décision prise plus tôt dans ce document.

`detection.centered_on_primary` calculait la position de la fenêtre en supposant
que **l'écran primaire est à l'origine du bureau virtuel**. C'est la convention
Windows et macOS. Elle est fausse ici : le primaire est à l'origine
**(1920, 0)** — c'est l'écran de droite.

Conséquence mesurée : une fenêtre de 2176 px de large était placée à x=192,
c'est-à-dire **sur l'autre moniteur**. Ce n'était pas « pas recentré », c'était
« recentré sur le mauvais écran » — un résultat pire que l'absence de
comportement, et impossible à voir sans deux écrans.

La cause de l'erreur est structurelle et déjà notée dans le tableau ci-dessus :
**pygame n'expose pas les bornes des écrans**, seulement leurs tailles. Une
position sur le bureau virtuel est donc incalculable à partir des seules
informations disponibles. Il ne fallait pas le calculer.

Correctif : laisser SDL placer la fenêtre.
`pygame.Window.position = pygame.WINDOWPOS_CENTERED` résout la constante contre
l'écran où se trouve réellement la fenêtre, ce que SDL sait et nous non.
Vérifié sur la machine : x=2112 (1920 + 192), y=108 — sur le primaire.

`pygame.display.set_window_position` refuse cette constante (« position must be
two numbers »), d'où le passage par le handle `Window`. C'est la seule ligne de
la migration qui touche une API dépréciée : pygame avertit à juste titre que les
deux APIs `@pygame-ce` se sépareront. L'avertissement est laissé visible et le
mode d'échec est le `except` : si l'appel cessait de fonctionner, la fenêtre
resterait là où le gestionnaire de fenêtres l'a mise.

`centered_on_primary` est **supprimé** plutôt que corrigé. Une fonction dont la
prémisse est fausse et dont la correction exigerait une information que la
plateforme ne fournit pas est un piège : le prochain appelant lui ferait
confiance. Un test vérifie son absence.

Autres observations de la même passe :

- l'écran primaire est un **180 Hz**, et `FRAME_LIMITS` s'arrêtait à 144. La
  liste ne couvrait donc pas le seul taux que le joueur regarde. **Corrigé** :
  180 a été ajouté, et `test_frame_limit_ladder_covers_the_screen` le vérifie
  contre le taux que la plateforme déclare ;
- `get_desktop_sizes()` renvoie bien les deux écrans, `get_num_displays()` aussi.
  C'est donc bien les **origines** qui manquent, et rien d'autre.

Dernière mise à jour : 2026-09-26, branche `feat/display-cadrage-system`.
