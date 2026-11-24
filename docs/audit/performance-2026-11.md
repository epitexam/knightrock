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
- **E3 — non livré** : pré-rendu des calques statiques (~20 Mo/calque, invalidations au changement de format). À décider après E2.

### A/B mypyc (E2)

`uv run python tools/build_native.py` puis `uv run python tools/benchmark_native.py --rounds 5 --iterations 100`. Chargement : 520 tuiles dans le hash, 168 queries, 256 corps (gravité + trois frictions), 16 plateformes. Ordre alterné à chaque round pour annuler le bruit ; même checksum dans les dix exécutions.

| round | natif | interprété |
|---|---|---|
| 1 | 2,294 ms | 2,833 ms |
| 2 | 3,253 ms | 2,903 ms |
| 3 | 2,920 ms | 4,310 ms |
| 4 | 1,741 ms | 2,982 ms |
| 5 | 1,884 ms | 1,601 ms |
| **médiane** | **2,294 ms** | **2,903 ms** |

Speedup **1,27×** sur ce micro-bench, dans un bruit de ±1 ms. Ce n'est pas une promesse de gain sur le tick complet : le périmètre compile surtout des helpers dont les paramètres sont `Any` (aucun type à exploiter), et il exclut les modules qui touchent aux vues ECS (voir `tools/build_native.py`). Le build natif n'est donc **pas intégré** au spec PyInstaller : le jeu livré reste pure Python, avec l'option de compiler localement pour mesurer.

Écartés avec preuve : dirty rects (caméra mobile), free-threaded Python 3.14t (pénalité mono-thread + GIL réactivé par les extensions C), GPU/moderngl (inutile à ~100 sprites), optimisation du fingerprint 440 champs (test-only).
