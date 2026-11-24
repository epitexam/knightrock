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

## Non livré — Phase E (décision séparée)

- **E1** : option de résolution interne réduite + upscale. Le levier le plus puissant en 4K (24,7 ms mesurés), mais c'est un réglage visible et un changement du pipeline `Screen`/`Presentation`.
- **E2** : mypyc ciblé sur `physics/`, `hit_resolver.py` et `contact_system.py` (1,5–5× annoncé sur du code typé ; build C et conservations des modules interprétés).
- **E3** : pré-rendu des calques statiques (~20 Mo/calque, invalidations au changement de format).

Écartés avec preuve : dirty rects (caméra mobile), free-threaded Python 3.14t (pénalité mono-thread + GIL réactivé par les extensions C), GPU/moderngl (inutile à ~100 sprites), optimisation du fingerprint 440 champs (test-only).
