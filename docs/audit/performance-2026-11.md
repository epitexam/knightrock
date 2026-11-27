# Audit performance — novembre 2026

Branche `refactor/cleanup`, 10 commits de optimisation après `354d80f`. Mesures sur la machine de développement (SDL dummy, machine chargée) : les ratios sont fiables, les millisecondes absolues bruitées.

## Profil initial

| Poste | Mesure |
|---|---|
| Tick (1–8 ennemis) | 1,0 – 2,5 ms, dont physique ~50 %, séparation ~15 %, contact ~10 % |
| GC en régime établi | 0 collection, 0 pause |
| Rendu 1920×1080 | 7,79 ms/frame (47 % du budget) |
| Rendu 2560×1440 | 14,90 ms/frame (89 %) |
| DEBUG activé | +1,4 – 3,0 ms/frame |
| Overlay debug | 884 tuiles parcourues via `every_sprite`, ~2072 `getattr`/frame |
| Démarrage | ~460 ms dont ~299 ms d'imports |
| Binaire | 46 Mo |

Le chunk index des tuiles était déjà optimal (1,3 ms vs 50,8 ms de scan à 22 000 tuiles) et n'a pas été touché.

## Livré

- **Phase A** : roster de fighters calculé une fois/tick et réutilisé par physique, feedback, combat et projectiles ; proxies dash/pivot résolus une fois/frame ; colonnes mises en cache dans les vues ; grain surfaces et zones DEBUG mémoïsées ; cache de texte grid borné ; timers FX nettoyés en place.
- **Phase B** : boxes de collision liées localement dans les boucles de physique ; `sync_rects` court-circuité quand la géométrie est inchangée ; carte de positions du broadphase réutilisée et test de recouvrement redondant supprimé ; tuple de cibles de contact partagé dans le tick.
- **Phase C** : overlay DEBUG alimenté par les sprites déjà cullés au lieu des 884 tuiles ; nombres DEBUG quantifiés et capacité du cache texte portée à 1024 ; dicts de strike trails mutés sur place.
- **Phase D** : import de `GameplayScene` différé au premier lancement de niveau ; free-list de `ObjectPool` plafonnée ; `strip=True` dans le spec PyInstaller. L'init audio au premier son a été **essayée puis annulée** : elle changeait le contrat « bus non démarré = silencieux ».

## Résultats

```
pytest -q          3804 passed, 1 skipped
DEBUG=1 pytest -q  3802 passed, 3 skipped
mypy src           211 fichiers, 0 erreur
ruff                propre
render_benchmark   1920×1080 : 7,27 ms (avant 7,79)
                   2560×1440 : 9,65 ms (avant 14,90)
build PyInstaller  OK, 45 Mo, smoke headless OK
```

Aucun golden, digest, oracle ou empreinte de données n'a changé.

## Phase E — livraisons et décisions

- **E1 — livré** (`phase/render-scale`) : `video.render_scale` (1.0 / 0.75 / 0.5, défaut 1.0), migration v5, upscale direct dans la fenêtre et inversion de souris exacte. Vert et sans régression au défaut, mais **sans gain ici** : l'upscale CPU coûte plus que le draw économisé (table complète dans `docs/audit/phase-e-plan.md`).
- **E2 — livré** (même branche) : build mypyc optionnel de cinq modules de `src/physics/`, avec conservation du mode interprété et A/B reproductible. Détails et séries ci-dessous.
- **E3 — livré mais désactivé** : producteur de calques pré-peints (`src/core/rendering/static_layer.py`), invalidé via `ResourceCoordinator` et réappliqué au changement de cible. Le chemin collection est trois fois moins cher, mais le blit d'un plein viewport coûte plus que les ~115 tuiles du chunk index : le réglage reste **off** (`ENABLE_BAKED_PLANES = False`). Détails ci-dessous.

### A/B mypyc (E2)

`uv run python tools/build_native.py` puis `uv run python tools/benchmark_native.py --rounds 15 --iterations 100`. Chargement : 540 tuiles dans le hash, 168 queries, 256 corps (gravité + trois frictions), 16 plateformes. Le checksum couvre désormais les candidats rendus par le hash/query (les deux modules compilés qu'il ignorait), les deux composantes de vitesse et la position des plateformes. Ordre alterné à chaque round pour annuler le bruit ; checksum `14438.843` identique dans les trente exécutions.

| série | rounds | natif | interprété | speedup |
|---|---|---|---|---|
| dernière | 15 | 1,994 ms | 2,231 ms | **1,12×** |
| précédente | 9 | 1,627 ms | 1,888 ms | 1,16× |
| première | 5 | 2,294 ms | 2,903 ms | 1,27× |

L'écart entre les séries montre à quel point le chiffre dépend de la charge de la machine : 1,12–1,27× sur ce micro-bench, pas une promesse sur le tick complet. Le périmètre compile surtout des helpers dont les paramètres sont `Any` (aucun type à exploiter) et exclut les modules qui touchent aux vues ECS (voir `tools/build_native.py`). Le build natif n'est donc **pas intégré** au spec PyInstaller : le jeu livré reste pure Python, avec l'option de compiler localement pour mesurer.

### Pré-rendu des calques statiques (E3)

Le producteur existe, avec plafond mémoire (64 Mo/calque), fallback `TileChunkIndex`, invalidation au changement de format et réapplication au changement de densité. Il est branché sur le même point d'injection que l'index, donc l'ordre de peinture ne dépend pas du producteur. `ENABLE_BAKED_PLANES` reste à `False` après A/B en ordre alterné sur le niveau réel :

| chemin | 1920×1080 | 1152×648 |
|---|---|---|
| calque pré-peint | 7,4 ms | 3,4 ms |
| chunk index | 4,3 ms | 2,5 ms |

La collecte est bien plus rapide (0,20 ms contre 0,65 ms pour réunir les blits avec le vrai chunk index), mais copier tout le viewport depuis une surface de 54 Mo coûte plus que blitter les tuiles visibles et laisser le `fill` faire le fond. Le pré-rendu est donc un levier uniquement si la copie de grandes surfaces devient moins chère (machine ou format different) ; le code et ses cinq tests restent pour refaire la mesure.

À densité entière et offset caméra entier, les deux chemins produisent exactement les mêmes octets. À un offset interpolé fractionnaire, une poignée de décors dont le rect est fractionnaire peut différer d'un pixel : une seule origine ne peut pas reproduire deux arrondis indépendants. Le chemin livré (index) est inchangé.

Écartés avec preuve : dirty rects (caméra mobile), free-threaded Python 3.14t (pénalité mono-thread + GIL réactivé par les extensions C), GPU/moderngl (inutile à ~100 sprites), optimisation du fingerprint 440 champs (test-only).

## Vérification du 27 novembre 2026

L'audit a été relu après la migration modulaire et le chantier de typage. Les
**décisions** ci-dessus tiennent toujours : phases A–D présentes dans le code,
`every_sprite` réduit à sa définition, `render_scale` livré, `ENABLE_BAKED_PLANES`
toujours à `False`, build natif hors du spec PyInstaller, choices écartées
inchangées. Les **millisecondes absolues**, elles, ne sont pas transférables
d'une session à l'autre — la phrase liminaire de cet audit le disait déjà.

| Poste | Audit | Mesure du 27-11 |
|---|---:|---:|
| Tick, 1 joueur seul | — | 0,13 ms |
| Tick, 1 / 4 / 8 ennemis | 1,0 – 2,5 ms | 0,21 / 0,60 / 1,08 ms |
| GC en régime établi | 0 collection | 0 collection sur 600 ticks |
| Rendu 1920×1080, frame | 7,27 ms | 2,02 – 2,43 ms |
| Import de `src.application.game` | ~299 ms | ~197 ms |
| Binaire | 45 Mo | non re-mesuré (`dist/` absent) |
| A/B mypyc | 1,12 – 1,27× | **1,19×** (0,583 natif / 0,692 interprété, checksum `14438.843` sur 18 exécutions) |

Le tick et le rendu ont été mesurés avec les mêmes scripts que l'audit
(`tests/headless/arena.py`, `tests/benchmarks/render_benchmark.py`), sur une
machine moins chargée : les ratios entre lignes restent significatifs, pas les
valeurs absolues. L'écart DEBUG (+1,4 – 3,0 ms) n'a pas pu être rejoué sur le
niveau réel avec ses panneaux ; sur un niveau programmatique, `level.draw`
passe de 0,198 ms à 0,216 ms avec `DEBUG=1`, ce qui ne contredit pas l'audit —
la charge des panneaux dépend du nombre de sprites et de texte affichés.

### Deux points soulevés par le chantier de typage

1. La raison donnée en E2 pour le périmètre étroit du build natif (« les
   paramètres sont `Any`, aucun type à exploiter ») n'est plus exacte : les
   helpers de `src/simulation/physics/` portent désormais des protocols
   (`FrictionBody`) et des types concrets (`MovingPlatform`). Le build compile
   toujours et l'A/B reste dans la fourchette historique ; il faudrait refaire
   l'expérience d'un périmètre plus large avant de conclure quoi que ce soit
   sur un gain possible.
2. Conséquence concrète : mypyc applique maintenant ces types. Le banc
   `tests/benchmarks/native_benchmark.py:101` donne à la plateforme fictive un
   `waypoints` en **tuple**, alors que le code compilé attend une **list** ;
   l'A/B ci-dessus n'a été obtenue qu'en corrigeant cette ligne dans une copie
   temporaire. Le dépôt est inchangé : ce point reste ouvert et devra être
   traité avant de rejouer `tools/benchmark_native.py` sur un build natif.

Enfin, le typage lui-même n'a eu aucun effet mesurable : tick moyen avant
0,1248 ms / après 0,1261 ms, rendu 1920×1080 dans le bruit, import plutôt en
baisse. La refonte a acheté de la maintenabilité, pas de la vitesse.

## Enquête ciblée sur les modules existants (27 novembre, suite)

Même principe que l'audit : mesurer dans le code tel qu'il tourne, puis ne
conserver que les pistes dont le gain est reproductible. Aucun changement de
runtime ni d'architecture n'a été envisagé.

### Postes mesurés

| Poste | Mesure |
|---|---:|
| Tick, 1 joueur | 0,13 ms |
| Tick, 8 ennemis | 1,08 ms |
| Contact 8v8 (`contact_benchmark`) | 1,55 ms/tick |
| Rendu 1920×1080 | 2,0 – 2,4 ms/frame |
| Blit loop, 130 surfaces `convert_alpha` | 0,109 ms |
| `Surface.blits` | 0,093 ms |
| **`Surface.fblits`** | **0,056 ms** |
| Menu UI (`ui_benchmark`) | 0,5 – 1,5 ms/frame |
| Construction FX | 3 – 52 µs par effet |

Un `cProfile` sur 300 ticks avec 8 ennemis donne 96 628 appels à
`Entity.hitbox`, 53 222 à `Entity.velocity` et 153 051 à `DenseTable.column`.
Le profileur majore le coût d'un appel Python, mais l'ordre de grandeur est
confirmé sans profileur : `GeometryTable.hitbox_of()` met 5,67 µs pour 50
accès contre 2,65 µs avec la colonne liée localement ; lire `entity.hitbox`
coûte ~0,17 µs de plus qu'une variable locale.

### Pistes retenues (non livrées ici)

1. **`presentation/rendering/renderer.py`** : remplacer la boucle de blits par
   `Surface.fblits`. La file de blits du renderer n'utilise pas de
   `special_flags` (les seuls flags sont dans le passage flashes), donc
   l'API s'applique directement. Gain mesuré sur le primitives : ~0,05 ms/frame.
2. **`simulation/physics/{movement,collisions}.py` et
   `simulation/level/systems/{separation,contact}_system.py`** : lier les
   propriétés ECS et les colonnes en variables locales au début des boucles.
   Gain attendu ~50 µs/tick à 8 ennemis, soit ~5 % du tick et ~0,3 % du budget
   frame. À garder avec des checksums de monde en garde-fou.

### Pistes écartées avec preuve

- **`__slots__` sur les particles/événements** : 0,209 → 0,163 µs par instance,
  mais quelques instances par frame seulement — moins de 1 µs gagné. Gain mémoire
  uniquement ; source : [Python Morsels](https://www.pythonmorsels.com/__slots__/).
- **`array.array` pour les colonnes ECS** : le SoA ne bat l'AoS qu'à des
  milliers d'entités ([The Essence of ECS, 2026](https://arxiv.org/html/2606.14919v1)) ;
  le roster livré est de 1 à 9.
- **Cache d'écrans UI entiers** : 0,5–1,5 ms/menu, mais invalidation par
  densité, thème et choix utilisateur ; le cache de texte est déjà à 1024
  entrées. Risque supérieur au gain.
- **Périmètre mypyc élargi** : prototype compilé (11 extensions) mais plantage
  à l'exécution sur `SurfaceFlagsView` dans `collisions.py` et `movement.py`.
  La conclusion E2 tient toujours.
- **PyPy/GraalPy, NumPy/JAX, Cython/Rust, free-threaded, GPU** : voir la
  [l'échelle d'optimisation 2026](https://cemrehancavdar.com/2026/03/10/optimization-ladder/)
  et l'audit initial ; nos hot paths sont des objets, des vues ECS et des
  appels pygame C, pas des boucles numériques pures, et la compatibilité des
  extensions reste un risque.

Sources directes pour les pistes retenues :
[pygame-ce — Performance Comparisons](https://github.com/pygame-community/pygame-ce/wiki/Performance-Comparisons-Against-Upstream-Pygame)
(`fblits`, vecteurs C) et la [FAQ Python sur les variables locales](https://docs.python.org/3/faq/programming.html).

Aucun code n'a été modifié par cette enquête ; les gates restent ceux de la
vérification ci-dessus.
