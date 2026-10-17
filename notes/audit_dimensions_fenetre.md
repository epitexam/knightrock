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

> **Ces chiffres mesurent un système qui n'existe plus.** La cible de rendu
> valait `cadrage × entier` et la frame finie était ré-échantillonnée sur la
> fenêtre ; les deux ont disparu (§14). Le tableau est conservé tel quel parce
> que c'est lui qui a décidé du rework — mais la conclusion « la présentation
> coûte selon la fenêtre, pas selon la cible », qui était vraie, ne l'est plus
> du tout : la présentation est un `blit` 1:1, et le coût qui reste est celui du
> dessin du monde.

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
| `smoothscale` à l'échelle 1:1 est gratuit | **2.19 ms**. `Presentation` court-circuite le cas 1:1 — et il n'y a plus de `smoothscale` à court-circuiter (§14) |
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

## 8. Recette manuelle — partiellement faite, sur une session

`tools/display_acceptance.py` a été étendu : il énumère les écrans (nom, taille,
taux, origine, zone utilisable), affiche la politique de mise à l'échelle, et
imprime **le monde visible en unités monde** plutôt que des pixels de cible. Le
point 4 ci-dessous se lit maintenant directement dans sa sortie.

> Ce qui reste non fait est écrit tel quel, pas masqué.

Rien de ce qui suit n'est vérifiable sous le driver dummy. Sur la session de
développement (Wayland, `SDL_VIDEO_HIDPI`, un seul écran `eDP-1` 1920×1080 @60) :

**Fait, vérifié sur la vraie session :**

1. `is_vsync()` **vrai en mode fenêtre** — `set_mode(RESIZABLE, vsync=1)` donne
   `is_vsync() == True` sous SDL 2.32.10. Le tableau §6 disait « SDL ne l'honore
   que pour une surface `SCALED` ou `GL` », et **c'était faux ici**. Le menu
   rapporte ce que le driver dit, donc la ligne est juste ;
2. bascules de mode : fenêtre / borderless / plein écran, sans saut, la fenêtre
   revient centrée ;
3. `get_desktop_refresh_rates()` → `(60,)` ;
4. redimensionner la fenêtre : le cadrage ne change pas — vérifié sur 12 fenêtres
   × 4 cadrages × 3 politiques, la propriété est testée ;
5. **la zone utilisable est lue et honorée** : le panneau fait 1920×1080, la zone
   utilisable 1920×1048 (32 px de panneau en haut). Une fenêtre borderless
   dimensionnée sur le panneau **couvrirait ce panneau** — c'est la différence
   entre « borderless » et « par-dessus » ;
6. Wayland : le placement de fenêtre et le plein écran fonctionnent ; la fenêtre
   est centrée par `WINDOWPOS_CENTERED` et par le calcul d'origine quand le
   probe SDL répond.

**Non fait — un seul écran est connecté sur cette machine :**

7. **le multi-écran réel n'a pas été validé à l'œil.** Le code est écrit et testé
   sur une topologie synthétique de 2 et 3 écrans (dont un primaire à origine
   positive et un écran gauche à origine négative), mais brancher un second
   écran et regarder la fenêtre le suivre reste à faire. C'est le seul point du
   système qui n'a pas été vu ;
8. le branchement à chaud en cours de session : le polling est en place
   (0,75 s) et pygame n'expose **aucun** événement pour une écran ajouté ou
   retiré — mesuré sur les constantes que pygame exporte, `SDL_DISPLAYEVENT_*`
   n'est pas traduit. Sans second écran, le chemin ne peut pas être exercé ;
9. la restauration du mode après un plein écran exclusif interrompu par le
   gestionnaire de fenêtres.

## 8 bis. Ce que le menu vidéo ne faisait pas bien

Ajouté après le système multi-écran, parce que les deux se sont trouvés
ensemble : un réglage qu'on peut choisir mais qu'on ne peut pas *voir* n'est pas
un réglage, c'est une devinette. Trois défauts, tous mesurés.

**Le cycle était le mauvais contrôle pour une longue liste.** Le driver annonce
28 modes plein écran sur cette machine : atteindre une résolution demandait donc
jusqu'à **27 pressions de →**, et un joueur qui ignore que la valeur existe n'a
aucun moyen de le découvrir. Tout ce qui dépasse quelques valeurs ouvre
désormais une liste. Restent en cycle ce qui a deux ou trois états : mode
d'affichage, VSync.

**Une ligne morte, et pas une ligne mal étiquetée.** L'art en pixels entiers et
la politique « entier » du cadrage étaient **le même réglage sur deux lignes**.
Avec `zoom` sélectionné, appuyer sur « pixels entiers » faisait passer le label
de `off` à `on`, changeait l'indicateur stocké — et laissait l'image
*strictement identique*, au pixel près. Une ligne qui répond à toutes les touches
et ne fait rien : indiscernable d'une touche cassée. Elle a disparu au profit
d'une entrée dans la liste de cadrage, et l'invariant qui la remplace est testé —
quelle que soit la politique, l'indicateur en découle, donc un fichier v3 ne peut
plus écraser un choix fait plus tard.

**Le plein écran n'était atteignable qu'en plein écran.** La ligne était
*désactivée* hors de ce mode — ce qui est mieux qu'une ligne absente, mais
demandait au joueur de deviner la condition. Elle est désormais toujours
présente, grisée hors plein écran.

Le défilement, lui, a été une **régression introduite puis corrigée** pendant le
travail : appliquer le découpage à toutes les listes a fait tomber le bouton
« Retour » du menu vidéo sous le bord de l'écran — il n'était plus dessiné, donc
plus cliquable à la souris. Le défilement est maintenant demandé par l'écran qui
veut, et `MenuView` le teste.

Chiffré sur la vraie session, 29 entrées dans une fenêtre 640×480 : six lignes
visibles à l'échelle 0,8, quatre à 1,0 ; panneau à l'intérieur de la fenêtre,
dernière entrée toujours atteignable. Coût du tracé 0,24 ms.

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

## 14. Ce que la revue a cassé, quatrième fois : la fenêtre ne pouvait pas être la cible

Le symptôme rapporté, mot pour mot : *« le jeu est plus lent et flou (littéralement,
l'écran est complètement flou) »*, et ensuite *« tout le menu video settings est
buggé de fond en combre, aucun des settings ne persiste après le redémarrage »*.

Les deux sont la même cause, et elle est dans une phrase que ce document asserts
 depuis §3 : **la cible de rendu valait `cadrage × entier`.**

### 14.1 Le flou et le coût, mesurés

Une cible fixe oblige à ré-échantillonner la frame finie sur la fenêtre. Le
nombre de pixels d'écran qu'occupe une unité monde vaut `fenêtre / cadrage`,
**quels que soient les entiers** : le facteur s'annule. À 2176×1224 avec
DEFAULT_FRAMING 1152×648, une unité monde fait donc 1.889 px — et aucune valeur
du menu n'atteignait 1.0, parce qu'aucune fenêtre 16:9 n'est un multiple entier
de 1152×648. La configuration relevée sur la machine (`render_scale: 1`) aggravait
le choses : cible 1152×648 agrandie de 1.889× par `smoothscale`, à chaque frame.

| | monde | présentation | total | couleurs du tileset |
|---|---|---|---|---|
| config relevée (1x, lissé) | 1.01 ms | **4.24 ms** | 5.25 ms | 13 → **128** |
| 2x, lissé | 2.73 ms | 7.06 ms | 9.79 ms | 13 → 88 |
| master (1:1 dans une fenêtre 1440×900) | 1.94 ms | 0 | 1.94 ms | 13 → 13 |

Le nombre de couleurs est la mesure la plus honnête du flou : un `smoothscale`
n'invente pas de nouvelles couleurs, il fabrique des couleurs intermédiaires
entre les pixels qu'il mélange. 13 → 128, c'est « l'écran complètement flou ».
Et 4.24 ms de `smoothscale` par frame, c'est la moitié du budget d'une frame 60 Hz
dépensée à ré-échantillonner une image que le jeu venait de dessiner.

Le correctif n'est pas un réglage : **la cible de rendu est la fenêtre.** Le
rectangle de la fenêtre qui porte l'image, aux barres près, et la densité est
lue *sur* ce rectangle. Le `blit` final est 1:1, donc il n'y a plus de ratio, plus
de `smoothscale`, et plus rien qui puisse adoucir un pixel. Mesuré après
(`tests/benchmarks/render_benchmark.py`) :

| fenêtre | cible | densité | monde | présentation | total | % frame 60 Hz | whole-pixel |
|---|---|---|---|---|---|---|---|
| 1280×720 | 1280×720 | 1.111 | 1.91 ms | 0.50 ms | 2.42 ms | 14% | 1.83 ms |
| 1920×1080 | 1920×1080 | 1.667 | 2.75 ms | 0.90 ms | 3.65 ms | 22% | 1.92 ms |
| 2560×1440 | 2560×1440 | 2.222 | 6.02 ms | 2.52 ms | 8.54 ms | 51% | 7.21 ms |
| 3840×2160 | 3840×2160 | 3.333 | 11.67 ms | 5.70 ms | 17.37 ms | 104% | 15.63 ms |

Une passe, sous le driver dummy : le terme « monde » varie de ±30% d'une passe à
l'autre (mélange alpha logiciel), le terme « présentation » ne varie pas — c'est
une copie, et c'est celui-là qui a changé.

À 1080p, la frame coûte **moins** qu'avant (5.31 → 3.65 ms) *et* elle est nette.
Le seul terme qui grandit avec la fenêtre est le dessin du monde, et il grandit
parce que la fenêtre est plus grande : afficher 1152×648 unités monde sur un
écran 4K, c'est 8.3 Mpx de mélange alpha, et aucun réglage ne rend cela moins
cher. La seule chose qui l'est, c'est une fenêtre plus petite ou **Whole-pixel
art** (dernière colonne : 15.63 ms à 4K, et 1.92 ms à 1080p contre 3.65).

### 14.2 Le menu, et ce qui ne persistait pas

Le reproché sur le menu est le même bug, vu par le joueur. Une taille de fenêtre
était un réglage, donc une affirmation sur l'écran du joueur — que le jeu ne peut
pas vérifier. Trois conséquences, toutes reproductibles :

- **`Stage._window_size` ignorait la taille stockée en borderless** (la fenêtre
  est alors celle du bureau) et **rien ne réécrivait la différence**. Le menu
  affichait `settings.width × settings.height`, donc 2176×1224 grisé, pendant que
  le jeu tournait en 2560×1440. Le menu mentait, et un joueur qui règle sa
  résolution voit le menu et l'écran se contredire ;
- **`_resolve_display_settings` réécrivait `width`/`height` à chaque lancement**
  dès que `size_mode` valait `auto`, et remettait `size_mode = auto` derrière.
  Mesuré : 870×653 → 2176×1224 d'un lancement à l'autre. Une taille ne pouvait
  donc pas être mémorisée en auto, et une taille manuelle qui ne tenait plus
  était remplacée en silence ;
- **`render_scale` était écrit une fois au lancement** (`with_video(render_scale=…)`
  dans `initialize_display`) puis cru ensuite, parce que `_render_scale` honore
  une valeur stockée. Une fois le fichier_rwrit, la résolution automatique de la
  netteté n'était plus jamais réévaluée.

Je n'ai pas pu reproduire une perte *totale* de réglages : le round-trip JSON est
exact pour les sept champs, et le fichier du joueur contient bien des valeurs non
défaut (fullscreen, 2176×1224, manual). Ce que le joueur vivait, c'est
« je change, ça ne prend pas » sur la seule ligne dont la valeur était vraiment
réécrite — et sur une ligne dont l'affichage mentait. Les deux sont supprimées
avec la cause, pas contournées.

Reste le risque de fond, et il est réel : **`load()` attrapait toutes les erreurs
et retournait les défauts, sans un log.** Un schéma qui ne correspond plus, une
écriture tronquée, un fichier édité à la main : le joueur revient à un jeu qui
a oublié ses réglages, sans une ligne pour dire pourquoi, et le premier changement
ensuite écrase le fichier qui contient encore ses *bindings*. C'est maintenant
journalisé (niveau ERROR, chemin, raison), le fichier illisible est laissé intact,
et `save()` garde ce qu'il remplace dans `settings.json.bak`.

### 14.3 Ce qui a été supprimé, et la règle qui l'explique

| supprimé | pourquoi |
|---|---|
| `width`, `height`, `size_mode` | une affirmation sur l'écran, plus le mécanisme qui la réécrivait |
| `render_scale` | décrivait une cible fixe qui n'existe plus ; c'était le réglage qui se figeait |
| `smoothing` | décrivait un ré-échantillonnage par frame, qui n'existe plus |
| `ResolutionScene`, `window_size_choices`, `largest_window_size`, `fits_on_desktop`, `WINDOW_SIZE_FRACTIONS`, `SizeMode` | le sélecteur de résolution, et l'arithmétique dont il avait besoin |
| `Viewport.render_scale_for`, `Framing.viewport_size`, `checked_render_scale` | la dérivation de la cible, et la politique entière qui la rendait entière |
| `_cost_hint` | l'avertissement ne servait qu'à cause du resample — et il recommandait « Render scale 1x », le pire choix possible pour la netteté |

**La règle** : un réglage est un choix que le joueur fait et que le jeu peut
honorer, ou ce n'est rien. Un réglage qui décrit l'écran du joueur est une
affirmation que le jeu ne peut pas vérifier — et elle est fausse plus souvent
qu'elle n'est vraie. Ce document portait déjà cette idée (§1, §3) ; elle s'appliquait
au *mode* d'écran et pas à la *taille*, et c'était l'incohérence.

Il ne reste donc dans le fichier que des choix : `display` (avec `auto`),
`pixel_perfect`, `vsync`, `frame_limit`, `ui.scale`, et les bindings. Le schéma
passe en v3 ; un fichier v1 ou v2 se charge toujours, ses clés vidéo ignorées —
un joueur qui a remappé ses touches ne doit pas retomber sur les défauts à cause
d'une clé vidéo qui ne veut plus rien dire. `test_video_settings_persistence.py`
conduit le **vrai** runtime ligne par ligne et vérifie les trois étapes qui
manquaient : la valeur bouge, la charge utile écrite la porte, et un **second
runtime** qui la relit. Les tests du menu existants utilisaient un
`SimpleNamespace` dont `apply_settings` était une affectation — ils prouvaient
« la ligne appelle apply_settings avec la bonne valeur » et rien de plus, ce qui
explique trois générations de bugs de menu au vert.

### 14.4 Le piège de l'arrondi, et pourquoi il est dans `Camera`

Une densité de 1.889 veut dire qu'un sprite de 64 unités fait 121 px. `pygame.blit`
**rééchantillonne silencieusement** une source qui ne remplit pas sa destination :
une image de 121 px dans un rect de 120.9 px, et c'est le §9 de ce document qui
recommence, un cran plus loin. D'où une règle unique,
`Camera.scaled_size()`, dont l'image agrandie *et* son rect de blit sont tous deux
tirés, et dont le test de propriété (`test_a_real_levels_sprites_are_never_resampled`)
revient à **zéro pixel** d'écart sur les assets du niveau réel, à cinq densités et
treize fenêtres.

Le round de la taille est **vers le haut** (`ceil`), et c'est un choix prouvé
plutôt qu'esthétique. La position est arrondie **vers le bas** ; l'écart entre
deux positions arrondies est donc entre `floor(pas)` et `ceil(pas)`. Avec une
taille de `round(pas)`, il arrive que le voisin commence à droite de la fin du
précédent — mesuré à densité 0.5, pas = 69.25, taille = 69, un trou d'un pixel
tous les quelques tuiles, soit une ligne de fond à travers le terrain. Avec
`ceil(pas)`, le pire cas est un chevauchement d'un pixel, invisible, contre un
trou qui ne l'est pas. Fuzzé sur 4 cadrages × 6 densités × 300 positions : 0 trou.

### 14.5 Whole-pixel art, le seul réglage de netteté qui reste

Il n'y a plus de « rendu net ou lissé » parce qu'il n'y a plus de
ré-échantillonnage. Ce qui reste est un choix de knap : remplir la fenêtre, ou
donner à chaque pixel d'art un bloc *k*×*k* exact. Le second coûte des barres,
et n'existe pas sur une fenêtre plus petite que le cadrage — la ligne le dit
plutôt que d'accepter un réglage qui ne fait rien.

Une ligne **Window** en bas du menu vidéo a remplacé l'ancien sélecteur : elle
rapporte ce que le jeu a déduit (`2304x1296 at 2.00x + bars`), c'est-à-dire
exactement l'information qui manquait quand la ligne « taille » affichait un
nombre que le jeu n'utilisait pas. Elle est non sélectionnable, et `MenuModel` ne
la sélectionne même pas : une ligne morte, et non pas une ligne qui répond à un
clic en changeant autre chose.

### 14.6 Ce que la recette manuelle a attrapé, et pas les tests

`tools/display_acceptance.py` applique désormais les états d'affichage *et* les
transitions de taille de fenêtre, et il a trouvé un bug qu'aucun test ne voyait :
`apply_settings` n'écrivait `presentation.pixel_perfect` que sur la branche qui
**ne** reconstruit pas la fenêtre. Un changement de mode et un changement de
netteté appliqués ensemble laissaient donc la présentation caler sur des pixels
entiers pendant que le réglage disait le contraire — et une cible de la mauvaise
taille est une cible parfaitement valide, donc rien ne signale l'erreur. Le
correctif est de l'écrire avant tout, inconditionnellement, et le test qui le
couvre marche les six combinaisons mode × netteté.

C'est le troisième fois que cette recette attrape ce que la suite ne voit pas
(§9, §10, et maintenant §14.6), et la raison est toujours la même : les
combinaisons. Un test qui appelle une méthode ne teste pas l'ordre des méthodes.

La recette de §8 vaut toujours, avec une ligne de plus : **redimensionner la
fenêtre à la souris pendant une partie** — la cible, la densité et l'échelle
d'interface doivent suivre, et la quantité de monde visible ne doit pas changer
d'un pixel.


## 15. Débogage invisible, et l'UI qui ne suivait pas l'échelle

Trois défauts distincts, une seule cause commune : **deux espaces de pixels
confundus.** Une grandeur écrite dans l'un, comparée à une grandeur écrite dans
l'autre. Aucun des trois ne lève d'exception ; les trois produisent une frame
qui a l'air correcte.

**Le cull de debug comparait des rectangles *monde* à un rectangle *cible*.**
`WorldUI` eliminait les sprites via une boîte passée par `camera.apply` — des
pixels cibles — contre `sprite.rect`, qui est en unités monde. Les deux ne
coïncident qu'à l'origine de la caméra, ce qui n'arrive jamais : **tous** les
sprites étaient éliminés, donc `F1` basculait bien un booléen et ne dessinait
rien. Un cull qui rejette tout ressemble exactement à un cull vide — pas
d'erreur, pas de log, une frame identique à celle d'avant. Le correctif n'est
pas une conversion de plus : c'est de ne plus convertir et de demander à
`camera.is_visible`, qui est déjà le cull monde du renderer.

**Le debogage ne suivait pas l'échelle.** Traits, espacements, rayons : des
littéraux en pixels cibles, à l'époque où une unité monde valait un pixel
cible — alors que les rectangles décorés venaient de `camera.apply`, qui
multiplie. À une densité de 1.889, une hitbox de 1px arrive à 53% de son
intention et disparaît dans la grille de tuiles. `WorldOverlayMetrics` dérive
tout d'un seul nombre, avec un plancher à 1px : en dessous, un trait arrondi à
zéro n'est pas un trait fin, c'est une absence.

**Une clé morte ne dit rien.** F1–F11 sans `--debug` ne faisaient
strictement rien. Rendre l'overlay inconditionnel serait la mauvaise réponse
— un joueur qui a dit non aux panneaux veut ne pas avoir de panneaux — mais une
clé qui ne fait rien est indiscernable d'un bug. Une notice transitoire nomme le
drapeau, une fois, puis expire. Testé : deux F-keys ne donnent qu'une seule
notice, et 600 frames plus tard elle a disparu.

**Et les menus, eux, ne suivaient pas l'échelle non plus.** `GridView`
prenait `min(34, 30*scale)` pour une hauteur de ligne pendant que son texte
mesurait `22*scale` — 49px. La bande cliquable couvrait donc 44% du libellé
qu'elle décorait : **cliquer la ligne qu'on lit activait la ligne du dessus.**
C'est le pire défaut qu'un menu puisse avoir, parce qu'il ne *semble* pas cassé —
il répond, à la mauvaise chose. La largeur était plafonnée à 900px, un nombre de
bureau, sur une fenêtre de 2176px : un tiers du panneau était une gouttière
dimensionnée pour les libellés, pas pour les valeurs.

Le correctif est `src/ui/metrics.py` : une table, une entrée (l'échelle), et
aucun littéral de mise en page dans une vue. Trois règles en découlent, et les
tests les énoncent comme des *ratios* plutôt que comme des pixels, ce qui les
rend incapables de dériver :

1. **Une ligne n'est jamais plus courte que son texte.** La hauteur vient des
   polices réelles, mesurées : une Consolas de 22px a une boîte de ligne plus
   haute que 22, et sur une machine sans Consolas la police de repli en a une
   autre. Une liste qui ne rentre pas abandonne la *taille du texte* (plancher
   `MIN_TEXT_RATIO`) et jamais la hauteur de ligne.
2. **Le panneau se dimensionne sur son contenu**, plus de plafond fixe, et
   l'intérieur du cadre suit l'échelle du contenu — sinon la boîte continue de
   déborder pendant que le texte rétrécit, parce qu'elle ne croit pas le texte.
3. **Un titre est centré**, partout, la grille et le panneau d'options dans la
   même règle.

Ce qui ne rentre toujours pas déborde par le bas, et c'est un choix explicite :
une étiquette illisible n'est pas une option, et une fenêtre plus petite que
l'interface à l'échelle que le joueur a choisie est à lui de la résoudre. Le
test le vérifie dans ce sens — un débordement n'est permis qu'une fois le texte
au plancher, jamais « avec de la place en rab ».

Coût mesuré : **0.81ms** par dessin de grille à 2176x1224 avec 8 lignes, dont
0.038ms pour `_layout` et le reste en blits — sur un panneau de 1431x846, soit
3.4 fois la surface de l'ancien panneau de 900px de large, parce qu'il ne tronque
plus ses propres valeurs. La boucle de mesure ne boucle pas en régime établi :
elle sort au premier tour dès que la hauteur convient, et les polices ne sont
reconstruites que si l'échelle du texte a changé. Le cache de texte rendu est
d'ailleurs keyed sur `id(font)` : reconstruire les polices à chaque frame — ce
qu'un `draw` qui veut une police fraîche ferait volontiers — vide ce cache et
re-rend trente chaînes par frame. D'où le `self._fonts = None` qui n'y est pas.

## 16. La souris, deuxième passe : la liste qui fuyait sous le curseur

Cinq correctifs, dans l'ordre où ils ont été trouvés, et un thème commun : **le
défilement était décidé par une chose et observé par une autre.**

**La molette n'était pas routée du tout.** `EventRouter.route` n'avait pas de cas
`MOUSEWHEEL` : il renvoyait `None`, et chaque cran tombait à terre. Une liste que
la souris ne peut pas faire défiler est un contrôle à moitié construit. Elle
navigue — un cran, une ligne — plutôt qu'elle ne sélectionne, parce qu'une
sélection changerait un réglage par cran et qu'un `y` fractionnaire de trackpad
appliquerait une demi-valeur.

**Un même point de souris sélectionnait quatre lignes.** Le défilement suivait le
curseur clavier avec une marge au-dessus, donc le pointeur survolait la dernière
ligne dessinée, la liste descendait, la ligne sous le pointeur changeait, la liste
redescendait. Une main qui descend régulièrement choisissait les lignes 7, 13, 19,
25 **sans que le curseur bouge**. La règle est maintenant minimale : la liste ne
défile que pour garder la ligne pointée à l'écran, et par le plus petit montant qui
le fait. Aucun défilement vers un pointeur posé dans la marge — la liste
continuerait d'avancer et le pointeur la poursuivrait jusqu'en bas, c'est le même
défaut avec des étapes en plus.

**Le défilement n'était jamais écrit.** `_scroll_for` calculait la bonne première
ligne et la passait à la vue, mais le champ restait à zéro : toute question
ultérieure — quelle ligne est sous le pointeur — était posée sur une liste qui
n'était plus celle dessinée.

**Le `y` mémorisé outvotait le clavier.** Après une touche, le défilement suivait
le curseur puis revenait où la souris était restée. Toute entrée non-souris efface
maintenant le `y` mémorisé.

**Une liste coupée ne le disait pas.** D'où trois ajouts : une glissière dans
l'écart à droite du panneau (le poussoir fait la fraction visible en hauteur et la
position défilée en place), ce même strip répond à un press — en dessous du poussoir
on avance d'une page, au-dessus on recule, sur le poussoir rien — et les touches de
liste, `PgUp`/`PgDn`/`Début`/`Fin`, pageant selon **le nombre de lignes que la
fenêtre montre** : la clé veut dire « là où je regarde », et une fenêtre plus
petite doit vouloir dire une page plus courte. Les épaules 4/5 d'une manette font
la même chose (Guard et Attaque 4 en gameplay, une autre map).

Une description est coupée avec un `…` quand elle ne tient pas : mesuré, 190
caractères rendent 1158px de large contre un panneau de 616, et le texte centré
déborde des deux côtés. Coupée et pas enroulée, parce que la bande réserve une
ligne de haut — l'enrouler rendrait la hauteur du panneau fonction de la longueur
de la note, qui est exactement le reflow qu'une liste qui défile ne doit pas
avoir.

## 17. Ce que la vraie session a cassé, cinquième fois : la fenêtre elle-même

Un joueur a pris la branche en testant : « tout est encore plus bugé qu'avant ».
Les quatre sections qui suivent sont ce que la recette manuelle a trouvé, mesuré
sur la même session (X11 sous RDP, deux écrans `rdp-0` 2560×1440 à (1920, 0) et
`rdp-2 24"` 1920×1080 à (0, 130)). Aucun n'est visible dans la suite de tests :
les quatre sont des demandes que la plateforme refuse, et personne ne les vérifiait
après coup.

**Le premier `set_mode` qui change les drapeaux est perdu.** SDL répond
`Requested window size: (1600, 900) / New window size: (2560, 1440)`, et le second
appel identique est honoré. Le joueur passait en fenêtré, choisissait une taille,
et la fenêtre restait celle de son bureau — sans rien à l'écran qui l'explique.
`Stage` lisait pourtant la taille accordée : il la mesurait, puis y croyait. La
correction est de **redemander** (`SIZE_ATTEMPTS = 2`), parce que « mesuré, jamais
supposé » ne veut rien dire quand la supposition peut être posée par terre.

**`set_mode`'s index d'écran ne déplace pas une fenêtre qui existe déjà.** Mesuré
deux fois de suite : la fenêtre reste sur l'autre écran. Et la ligne « Screen »
était une ligne morte — le menu affichait le nouvel écran, le fichier l'enregistrait,
la fenêtre ne bougeait pas. `Stage._place` ne plaçait qu'en mode `WINDOW` ; or
`FULLSCREEN | NOFRAME` *est* une fenêtre (mesuré à 1600×900 : encore positionnée et
déplaçable). Elle est donc placée dans les deux modes, et la demande est **répétée
jusqu'à ce que la fenêtre soit sur le panneau demandé** — la seule figure que le
jeu peut vérifier, la taille en pixels d'un cadre que le gestionnaire de fenêtres
décale de 32 px sur chaque axe (`TITLE_BAR_KEEP`).

Quand le gestionnaire de fenêtres refuse malgré tout, le jeu **le dit** :
« The window stayed on rdp-2 24". / rdp-0 could not be used. » C'est la moitié de
la régression qui est la sienne : non pas que le déplacement échoue — certains
gestionnaires refusent, et le joueur peut déplacer la fenêtre à la main — mais que
le jeu le fasse silencieusement. L'avertissement est **retiré** au premier
reconstruction qui atterrit, parce qu'un avertissement sur un échec qui n'est plus
vrai ment sur le présent.

**Un redimensionnement accompli n'est pas une préférence, et rien ne l'écrivait.**
La ligne du menu disait « a normal window; drag it, and its size is remembered »
et c'était faux : mesurer la taille 1600×900, glisser la fenêtre à 1200×800, basculer
le VSync — et la fenêtre revenait à 1600×900. Toute phrase du menu qui rebuild la
fenêtre était une façon de jeter le dernier mot du joueur. Ce qui est oublié est le
**choix**, pas la mesure : la taille stockée repart à `None`, qui veut maintenant
dire « suivre la fenêtre ». Le fichier dit donc que le joueur a cessé de choisir
une taille, au lieu de porter un nombre qui décrit son panneau — la règle de
`test_a_window_that_moves_does_not_rewrite_the_settings`. Le redimensionnement que
SDL annonce pour *son propre* `set_mode` est distingué de celui du joueur par la
taille à laquelle la fenêtre a été construite.

**Un `MOUSEMOTION` sans mouvement n'est pas un geste.** Une fenêtre recréée — ce que
fait *chaque* réglage d'affichage — fait émettre par SDL un `MOUSEMOTION` avec
`rel == (0, 0)` : le pointeur n'a pas bougé, la fenêtre sous lui si. Routé comme un
geste, il emporte la sélection du menu, parce qu'une liste lit sa ligne active dans
la ligne sous le pointeur. Mesuré : le focus était sur « Display mode », le joueur
changeait le mode d'affichage, et le focus revenait sur « Back » — la pression
suivante fermait le menu, et une ligne plus bas c'était « Reset video settings ».
C'était déjà vrai avant ce rework ; la branche a triplé les déclencheurs, en
ajoutant la taille et l'écran à la signature qui rebuild la fenêtre.

Deux défauts sans rapport avec la fenêtre, trouvés le même jour :

- **`GridView._fit` mesurait le préfixe sans le marqueur.** La recherche binaire
  trouvait le plus long préfixe entrant dans la largeur, retirait un caractère et
  ajoutait un `…` jamais mesuré — donc une étiquette pouvait revenir *plus large*
  que sa cellule : 44 px contre un budget de 40. Ça ne se voyait qu'avec une police
  de repli plus large que la prévue (Consolas absent). `MenuView._fit_text`, écrit
  le même jour, mesurait correctement ; le même fichier avait les deux.
- **La ligne « Window » décrivait l'image sous *bars*, quelle que soit la politique.**
  Sous `zoom`, une fenêtre d'un autre format que le cadrage était annoncée avec des
  barres qu'elle n'avait pas, à une taille où rien n'était dessiné.

### Ce qui reste à la plateforme

Le gestionnaire de fenêtres de cette session ne connaît qu'un panneau : il borne
toute fenêtre à celui de `rdp-2` et refuse les positions qui iraient vers `rdp-0`,
quelle que soit la demande. Le jeu peut poser la demande, la vérifier et dire
qu'elle a échoué ; il ne peut pas placer une fenêtre sur un écran que le
gestionnaire ne voit pas. C'est aussi pourquoi §8 mesurait sur une seule session :
le multi-écran réel reste la seule partie du système qui n'a pas été vue (§8, point 7).

## 18. Ce que la vraie session a cassé, sixième fois : le redimensionnement

« Quand je bouge la fenêtre avec Super et les flèches, l'affichage ne se met pas à
jour, et les dimensions, si elles sont trop grosses, la fenêtre déborde. »

Le premier symptôme est mesuré jusqu'à sa cause ; le second en est la conséquence
et disparaît avec lui.

**Le jeu écoutait un seul des événements de fenêtre.** pygame-ce traduit les
événements SDL de fenêtre en sept événements distincts, et celui qui porte un
redimensionnement dépend de la plateforme *et du geste*. Mesuré sur la session de
développement :

```
Super + ← / →  (un snap)   ['WindowSizeChanged', 'VideoExpose', 'WindowExposed']
maximiser, restaurer       ['WindowSizeChanged', 'VideoResize', 'WindowResized', ...]
un glissement à la souris   VIDEORESIZE
```

`Game._handle_events` ne traitait que `VIDEORESIZE`. Donc le snap — le geste qui
produit le plus de redimensionnements de tous — ne disait rien du tout, tandis que
maximiser passait, parce qu'il émet aussi cet événement-là. C'est aussi pourquoi
« parfois ça marche ».

**La conséquence est exactement ce qui a été décrit.** Après un snap en 640×500, la
cible valait toujours 1000×562 : le blit 1:1 de `present` plaçait un rectangle plus
grand que la fenêtre, rogné à droite et en bas. Dans l'autre sens — snap vers
1600×1100 — la nouvelle partie de la fenêtre gardait la frame précédente, et les
barres peintes étaient celles de l'ancienne taille. Les deux mesurés, les deux
visibles dans une capture.

**Le correctif lit la fenêtre au lieu d'écouter un événement.** Une liste
d'événements ne couvre que les événements que pygame choisit d'émettre. La taille
de la fenêtre, elle, est vraie dans tous les cas : en jetant la file d'événements
entière, la surface déclarait déjà 700×600. Un `get_size()` par frame coûte
**0,07 µs**, et `_retarget` décide lui-même si quelque chose a bougé — c'est donc
une comparaison, pas une cascade. Les trois événements sont déclarés dans
`_WINDOW_SIZE_EVENTS` avec une seule fonction : **les sortir des scènes**, et non
les réagir ici. C'est la seule couture que cet audit contredit : §9 affirmait que le
chemin de rendu était adapté, et il l'est — il lisait une taille, pas un événement.

**Un snap est un drag.** Il tombe donc sur la même règle que le §17 : la taille
choisie dans le menu repart à `None`, et le jeu suit la fenêtre. Le redimensionnement
que le gestionnaire de fenêtres impose pour son propre compte compte aussi comme un
geste du joueur.

**Une fenêtre sous le plancher est refusée, pas ajustée.** L'interface a son propre
plancher d'échelle, et une fenêtre sous `MIN_WINDOW` met la densité en dessous :
mesuré, 240×180 demande une échelle de 0,21 que `checked_ui_scale` refuse par une
exception et non par une police plus petite. `Presentation.recompute` refuse donc
la fenêtre et garde la dernière cible dessinable — un glissement sous le plancher est
rogné pendant sa durée au lieu d'emporter le jeu avec lui. La **première** exception
prouve la règle : un runtime qui s'ouvre sur une fenêtre aussi petite — un appel
headless, une plateforme qui refuse la contrainte — reçoit quand même une surface.
Les deux planchers sont dans des couches différentes (`core/display` n'importe pas
`ui/scale`), donc un test affirme qu'ils coïncident.

### La recette ne pouvait pas le voir

`tools/display_acceptance.py` redimensionnait la fenêtre par `set_mode` — le seul
chemin qui produit un `VIDEORESIZE` — **et faisait la réaction à la main**. Elle ne
pouvait donc pas voir un redimensionnement que le jeu n'aurait pas vu. L'outil a
maintenant une étape qui passe par le handle `Window`, sans `set_mode` et sans
événement posté, et chaque état du rapport répond à une question : *l'image affichée
est-elle celle que cette fenêtre appelle ?* Vérifié qu'elle a du mord — la réaction
retirée, l'étape dit `NO -- THE FRAME IS STALE`.

Le snap se fait en mode fenêtré, et c'est dit : un snap d'une fenêtre borderless est un
changement de mode déguisé, et une plateforme refuse de redimensionner une fenêtre
qu'elle affiche en plein écran. L'étape rapporterait alors un redimensionnement qui
n'a pas eu lieu, ce qu'un contrôle de ce genre ne doit jamais faire.

## 19. Ce que la vraie session a cassé, septième fois : le clic et le taux

Trois rapports, et deux causes — dont une n'était pas celle qu'on attendait.

« Les menus ne réagissent plus après un changement d'écran : la zone cliquable
a bougé. » — **La géométrie du clic et la géométrie du blit n'étaient pas le même
document.** Un clic est converti par la picture *en vigueur*, qui change dès que la
fenêtre change, puis il est testé contre `item_rects`, que le dernier dessin a
produits. Les deux sont vrais, ils ne sont pas vrais ensemble : mesuré après un
snap, la dernière ligne du menu vidéo était à 891 là où elle avait été dessinée à
657 — **244 px d'écart**, soit plusieurs lignes, et le clic atterrissait sur une
voisine ou sur rien. C'est ce que « la zone cliquable a bougé » décrit ; pire
qu'un clic mort, parce que c'est un clic *faux*.

Le correctif n'est pas de rejeter le clic d'une frame, c'est de le mesurer dans la
géométrie qu'il va rencontrer. `Game.step` sonde donc la fenêtre **avant** les
entrées, et quand elle a bougé, dessine la pile une fois de plus :

```
_follow_the_window()  →  la fenêtre a-t-elle changé de taille ?
                       → oui : scene_manager.draw(_draw_target())
_handle_events()      → le clic est alors mesuré contre les lignes qui viennent
                        d'être dessinées
```

Un dessin de plus, uniquement dans la frame où la fenêtre bouge, et le dessin de
fin de frame le recouvre : il n'y a pas de trace à l'écran. Le test ne vérifie pas
« le clic n'est pas perdu » — il vérifie que les rectangles mesurés au moment de la
dispatch sont ceux que la frame dessine ensuite, ce qui est l'invariant lui-même.
Vérifié qu'il mord : l'ordre rétabli, l'échec dit `hit-test used Rect(436, 370,
1687, 89)` contre `frame drew Rect(332, 315, 1256, 64)`.

Le geste du pointeur dans ce test est un **déplacement**, pas un clic, et c'est
délibéré : un clic qui tombe sur une ligne de valeur change un réglage, et un
réglage comme l'échelle reconstruit la fenêtre — la frame finirait sur une
*troisième* géométrie et l'assertion parlerait de la ligne que le clic a trouvée
par hasard. Un déplacement passe par les mêmes rectangles et ne change rien.

`MenuView.reset_cache` efface aussi `self._item_rects`. Le runtime couvre le cas
qu'il voit venir ; ceci couvre celui qu'il ne peut pas voir : un changement que le
jeu fait **pendant** qu'il traite une entrée, avec une seconde entrée déjà en file
derrière dans la même frame — deux clics, le premier appliquant un réglage vidéo qui
reconstruit la fenêtre. Un rectangle vide ne touche rien, ce qui est la réponse
sûre : un clic qui ne fait rien vaut mieux qu'un clic qui change un réglage que le
joueur n'a pas cliqué.

« VSync reste sur 60 Hz. » — **La ligne disait le taux du moniteur *principal*.**
`desktop_refresh_rates()[0]` est le taux de l'écran principal quoi que fasse la
fenêtre : sur un bureau à deux dalles, un joueur lisait « 60 Hz » sur une fenêtre
posée sur la dalle 60 Hz — et le même « 60 Hz » sur une fenêtre posée sur la dalle
180 Hz. Un nombre qui parle d'un écran qu'on ne regarde pas, sans rien dans la ligne
qui le dise. C'est aussi ce qui rendait le symptôme « c'est figé » : le nombre ne
changeait pas, puisque seule la position de la fenêtre changeait.

`Game.window_monitor()` donne le moniteur que la fenêtre occupe **réellement**, par
son coin haut-gauche à travers la topologie, `nearest` compris pour une fenêtre plus
grande que la dalle — décision cohérente avec le placement. Et quand personne ne
peut le dire — une topologie dégradée connaît des tailles, pas des origines — la
ligne **ne dit rien** plutôt que de dire le taux du principal. Un taux absent est
une indication manquante ; un taux erroné est un fait, à l'endroit exact où le joueur
lit son réglage. L'implémentation, c'est `desktop_refresh_rates` qui devient inutile
dans `video_scene.py` : l'import a disparu, la donnée est lue là où elle est vraie.

La suite est à **3154 tests**, avec et sans `DEBUG=1`.

## 21. La fenêtre stricte : ce qui a été supprimé, et pourquoi

*(Une section 20 a été écrite sur un chemin de travail abandonné — un repli
fenêtré avec notice de refus et chien de garde — qui a été mis de côté et n'est
plus dans l'arbre. Le numéro n'est pas réutilisé, pour que l'historique ne se
réécrive pas ; ce qui suit est ce qui a été retenu à la place.)*

**La demande.** Dégraisser la codebase, rendre le jeu **toujours fenêtré**, laisser
le joueur choisir la taille de la fenêtre, supprimer la machinerie de mode
d'affichage et de choix d'écran. Rien de plus.

**La règle qui a tranché les cas.** *Un réglage que le jeu ne peut pas garantir ne
doit pas être proposé.* C'est la même règle que §14.3 avait déjà fait tomber sur
`render_scale` et `smoothing` ; ici elle emporte les deux derniers réglages de la
famille :

- le **choix d'un écran** est une requête qu'un gestionnaire de fenêtres a le
  droit de refuser. Mesuré en §17 : la fenêtre demandée sur la dalle principale
  restait sur l'autre, `set_mode` répondait « succès », et le fichier gardait
  l'écran que le joueur venait de quitter — le menu affichait donc un écran où le
  jeu n'était pas. Un réglage qui peut mentir sur sa propre valeur est exactement
  ce que la règle interdit ;
- le **mode d'affichage** (`auto` / fenêtré / sans bordure / plein écran) est le
  mode qui *demande au pilote un changement de mode* : c'est la seule chose de tout
  le sous-système qui puisse éteindre l'écran d'un portable bi-GPU au milieu d'une
  session, et c'est pour cette raison que `borderless` existait — pour l'éviter
  sans renoncer au plein. Trois noms pour deux drapeaux, et la façon la plus simple
  de garantir qu'aucun ne sera jamais plus demandé est de retirer les trois.

**Ce qui a été supprimé, et le test part avec.**

| Retiré | Où |
|---|---|
| `DisplayMode` et le module entier | `src/core/display/mode.py` (fichier supprimé), `detection.auto_display_mode`, `ASPECT_TOLERANCE` |
| `ResolutionReason`, `Resolution`, `Topology.resolve`, `Topology.label_for` | `src/core/display/monitors.py` |
| `Monitor.origin`, `Monitor.detail`, `fit_position` | `src/core/display/monitors.py` |
| drapeaux de mode, `_flags`, `_mode_for`, `_supported_modes`, `_fullscreen_size`, `_display_index`, `Stage.on_monitor`, `_reported_position`, `PLACE_ATTEMPTS`, `TITLE_BAR_KEEP` | `src/core/display/stage.py` |
| champs `display`, `monitor`, `window_position`, `fullscreen_mode` | `src/application/settings_store.py` |
| lignes `screen_options`, `display_options`, `fullscreen_mode_options`, `_submenu_monitor`, `_submenu_resolution`, `_cycle_enum`, `DISPLAY_VALUES` | `src/application/scenes/video_options.py`, `video_scene.py` |
| `_resolve_display_settings`, `_window_notice`, `_say_where_the_window_landed`, `_withdraw_the_window_notice` | `src/core/game.py` |

Le format de fichier **ne bouge pas** : `SETTINGS_FORMAT_VERSION` reste à 4. Les
clés retirées ne sont simplement plus lues — le lecteur tolérant les ignore au lieu
de rejeter le fichier, ce qui préserve les bindings d'un joueur qui ne les a pas
redemandés.

**Ce qui reste, une fois la poussière.** La fenêtre est le seul objet :

- `WindowSpec` se réduit à `{vsync, size}` ; l'écran n'en fait plus partie et vient
  de `Stage(spec, monitor)`, où `monitor` est le **primaire** que
  `_monitor()` rend ;
- `_place` fait **une** requête — centrée sur la dalle d'ouverture — sans
  vérification, sans réessai, sans `on_monitor`. Il n'y a plus de requête à refuser,
  donc plus rien à quoi un refus serait faux ;
- `SIZE_ATTEMPTS = 2` reste : c'est la seule re-demande qui garde un sens (le
  gestionnaire peut rogner la taille demandée) ;
- `Stage._window_size` reste la source : taille choisie si elle existe, taille
  d'ouverture de la dalle sinon ;
- `Topology.nearest` / `containing` restent, parce que `window_monitor()` les
  utilise pour dire sur **quelle** dalle la fenêtre est posée — c'est le taux de
  rafraîchissement de la ligne VSync, et cette lecture reste exacte.

Les lignes du menu vidéo sont, dans l'ordre : **Window size · Picture fit · VSync ·
Frame limit · UI scale · (Debug panel scale, sous `DEBUG=1`) · Reset video
settings · Back · Window**. Le read-out est désactivé et n'ouvre rien.

**Les tests qui sont partis avec le code.** Les tests de mode, de placement
mémorisé, de refus et de notice d'écran ont été supprimés plutôt que réécrits : ils
affirmaient l'existence d'un mécanisme, et un test qui survit à la suppression de
son sujet est un test qui ne teste plus rien. Là où une propriété avait un sens
encore, elle a été **réécrite sur le nouveau sujet** — `nearest`/`containing`
gardent une propriété sur grille, la nouvelle ligne « Window size » a le test
d'existence et d'ouverture que l'ancienne ligne de résolution avait, et la taille
mémorisée garde son test de non-réécriture.

**Conséquence sur le compte.** La suite passe de 3154 à **3126 tests** : 28 tests
en moins, aucune couverture perdue en échange — chaque test parti décrivait un
mécanisme qui n'est plus là, et chacun des invariants qui restaient a son test.

## 22. Le chemin de remédiation, exécuté (2026-10-17)

La table de décision de l'audit (D1–D7) a été implémentée en trois commits, chacun vert sur
toute la suite (3166 tests collectés, mypy strict, Ruff). Ce qui a été fait, et ce qui a dévié :

- **D1/D2** — `_vsync_is_active()` supprimé ; la ligne dit « on · requested » / « off » et le
  test qui monkeypatchait la fonction qu'il testait est parti avec le bras qu'il prétendait
  couvrir. La limite d'images dit « ignored while VSync is on » sur la ligne et sur chaque
  entrée de l'échelle, et `DISPLAY_SAFETY_CEILING_FPS` documente le contrat inverse
  (`MAX_FRAME_LIMIT` *sous* le plafond, volontairement — le présent c'est la requête, l'échelle
  est ce qui tourne quand rien ne bloque).
- **D3** — `Game.effective_fit()` est l'unique définition de la politique en vigueur ; la règle
  de réconciliation (`pixel_perfect` → `integer` sauf choix explicite) vit dans
  `letterbox.effective_fit()`, fonction pure, lue par le rendu, par le read-out et par les
  stand-ins de test. Le test d'invariant du rendu (`bars`/`integer`/`zoom`) a demandé une
  fenêtre qui n'est pas déjà un multiple : le standard du fichier de test (2304×1296) en est un
  exact, et c'est précisément un des deux no-ops ci-dessous.
- **D4** — `_reset()` remet `fit`+`pixel_perfect` ensemble et ne touche pas à `window_size`
  (la taille est là où le joueur a posé la fenêtre ; la défaire n'est pas ce qu'un reset vidéo
  veut dire).
- **D5 (Règle W)** — `Game.monitor()` (ex-`_monitor()`, passée publique) rend **la dalle qui
  tient la fenêtre**, repli primaire au premier lancement et en topologie dégradée ;
  `_submenu_size` ancre l'échelle de tailles dessus. Vérifié sur la session réelle
  (`rdp-0`/`rdp-2`) : l'ancre suit la fenêtre.
- **D6** — `Stage._place` ne déplace la fenêtre que si le **rectangle actuel ne tient plus**
  dans la dalle ancrée : `monitors.sits_within` est le prédicat, testé par rectangle (axe par
  axe, origines négatives comprises). Mesuré sur la session réelle : un changement de taille ne
  téléporte plus la fenêtre ; la dérive résiduelle de quelques pixels est le placement en
  cascade du gestionnaire de fenêtres, pas le nôtre.
- **D7** — l'entrée « the screen's own resolution » est **supprimée** (c'était une requête
  sans bordure déguisée : le gestionnaire la rogne de la barre de titre) ; la tête de l'échelle
  est « as large as fits, measured with the title bar in mind », bornée par
  `_largest_fitting` (un `min` par axe de `opening_size` et de l'aire utile) ; les notes des
  échelons sont relatives au **plus grand offert** (« half of the largest »), et un échelon
  relevé au plancher l'écrit (« · floored at the readable minimum »).
- **B8 — dévié de l'écrit.** La garde « `< 1` » telle qu'enregistrée ne peut pas rattraper la
  dalle 1×1 fabriquée (1 n'est pas `< 1`), et la garde d'origine (`<= 0` sur `usable_size`)
  était du code mort : `usable_size` retombe sur la dalle quand l'aire est dégénérée, donc une
  garde sur *elle* ne tire jamais. La garde teste maintenant le **rapport brut** (la propre
  taille de la dalle et le rectangle utile brut, `< 1` par axe), ce qui attrape les rapports
  sans pixel ; la dalle 1×1 fabriquée **passe** et reçoit une requête de 1×1, et c'est le
  docstring — qui promettait `FALLBACK_WINDOW` à une dalle qui ne l'a jamais reçu — qui a été
  corrigé plutôt que le code forcé à tenir un mensonge. Les planchers qui restent ont chacun
  un endroit écrit : `Stage._limit_size` pour une fenêtre réelle, le refus de
  `Presentation.recompute` pour le dessin.
- **Bancs d'essai ajoutés** : dalle sous plancher (640×400 — l'échelle dérivée devient
  honnêtement vide au lieu d'offrir des tailles illisibles), ultra-large (3440×1440 — un tiers
  de la hauteur est déjà floored), et le prédicat `sits_within` sur six coins, panneau avec
  taskbar et origine négative.

Phase 4 (atomicité `Stage.rebuild`, ordre de `apply_settings`, code mort
`covers_window`/`letterbox()`/`initial_window_size`, docstrings restantes) reste à faire.

Dernière mise à jour : 2026-10-17, branche `fix/remediation`.
