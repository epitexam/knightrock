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

## 11. Ce que la vraie session a cassé

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
