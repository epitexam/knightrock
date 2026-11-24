# Plan — Phase E : optimizations structurantes

Statut : **E1, E2 et E3 implémentés** (branche `phase/render-scale`, 2026-11-24). E1 et E3 sont optimistes mais désactivés par défaut après mesure ; E2 reste optionnel et non embarqué. À exécuter uniquement après les phases A–D du plan de performance (voir `docs/audit/performance-2026-11.md`).

## Contexte et pourquoi une décision séparée

Après les phases A–D, la branche `refactor/cleanup` est verte : `pytest -q` 3804/1, `DEBUG=1` 3802/3, `mypy src` 211 fichiers sans erreur, aucun golden/digest modifié. Les gains mesurés : 7,79 → 7,27 ms en 1920×1080, 14,90 → 9,65 ms en 2560×1440.

La Phase E n'est pas une suite de micro-optimisations : chacune des trois options change soit le **produit visible** (E1), soit la **chaîne de build** (E2), soit le **pipeline de rendu et la mémoire** (E3). Elles nécessitent donc leurs propres gates, pas un simple « suite verte ».

Oracles à préserver pour toute option : 3 digests de simulation, 675 issues de coups, invariant à 440 champs, goldens PNG de menu/overlay/render, `test_readme_claims`, smoke PyInstaller.

---

## E1 — Option de résolution interne réduite + upscale

### Objectif

Rendre le coût de remplissage indépendant de la résolution de la fenêtre. Mesure faite sur cette machine : 3840×2160 coûte **24,66 ms/frame** (148 % du budget) contre 7,27 ms en 1920×1080. Un rendu interne en 1080p puis un upscale vers 4K ramènerait la frame vers ~7–9 ms.

### Conception

1. **Nouveau réglage** `video.render_scale` dans `src/application/settings_store.py` (valeurs discrètes : 1.0, 0.75, 0.5 ; défaut 1.0 pour ne rien changer). Migration v5 ou champ optionnel accepté par tous les lecteurs v1–v4 ; `to_dict` conserve la valeur.
2. **Ligne de menu** dans `src/application/scenes/video_options.py` / `video_scene.py` (même forme que `FRAME_LIMITS`), avec `test_video_scene.py` et `test_video_settings_persistence.py` mis à jour.
3. **Pipeline de présentation** : `Screen.open()` crée une surface de rendu hors écran de taille `window × render_scale`, et `Presentation` travaille sur cette surface ; une présentation finale fait `pygame.transform.scale` (ou `smoothscale`) vers la fenêtre. Conserver `convert_alpha()`/`convert()` sur la surface de présentation.
4. **Entrées** : les coordonnées souris doivent être divisées par `render_scale` avant routage (`src/core/input/event_router.py`) ; sans cela les clics de menu sont décalés. Ajouter un test de clic à chaque scale.
5. **Interface** : `ui_scale` s'applique désormais au target interne ; les polices et panneaux sont recalculés dans `_follow_the_target` (`src/application/game.py`). Les goldens de menu doivent être recapturés pour chaque scale livré.
6. **Caches** : `clear_frame_cache()` et les caches de shear/text sont invalidés quand le scale change, comme pour un changement de format d'affichage.

### Vérification

- `uv run python tests/benchmarks/render_benchmark.py` avec le target interne forcé à chaque scale.
- Goldens PNG recapturés **uniquement avec preuve de cause unique** (un scale = un commit = un diff de captures lu).
- `test_render_target_chain.py`, `test_frame_coherence.py`, `test_menu_goldens.py`, `test_video_settings_persistence.py`, suites complètes et `DEBUG=1`.
- Smoke PyInstaller.

### Mesure (machine de travail, SDL dummy, 10 échantillons)

`uv run python tests/benchmarks/render_benchmark.py --repeats 10 --window 3840 2160` :

| scale | target | world | present | frame |
|---|---|---|---|---|
| 1.00 | 3840×2160 | 14,5 ms | 9,1 ms | 23,6 ms |
| 0.75 | 2880×1620 | 9,8 ms | 23,9 ms | 33,8 ms |
| 0.50 | 1920×1080 | 4,5 ms | 23,6 ms | 28,1 ms |

Le draw suit bien le target, mais l'upscale CPU (`pygame.transform.scale` de la frame vers la fenêtre) coûte plus qu'il ne fait économiser ici : le reduced scale est **plus lent** que le 1:1 sur cette machine. Le réglage reste donc optionnel, avec 1.0 par défaut : il n'y a aucune régression sur le chemin livré. Un gain réel demanderait un upscale matériel (`pygame.SCALED`/OpenGL), exclu du périmètre par les décisions ci-dessous.

### Risques / rollback

Risque principal : le scaling casse la précision pixel-art (d'où des valeurs discrètes et un défaut à 1.0) ou les clics souris. Rollback : retirer le réglage et revenir à `Presentation` sur la surface de la fenêtre ; les migrations de settings restent compatibles si le champ est ignoré.

---

## E2 — mypyc ciblé sur les modules chauds

### Objectif

Compiler en extensions C les modules où le profile montre le plus de temps Python pur, en tirant parti du fait que `src/` est déjà 100 % typé sous mypy strict. La documentation mypyc annonce 1,5–5× sur du code annoté, 5–10× après ajustement. Gain réaliste ici : ~0,3–0,6 ms/tick sur la physique (qui représente ~50 % du tick), soit 2–4 % d'une frame 60 Hz — et un possible gain au démarrage car mypyc est AOT.

### Conception

1. Ajouter `mypyc` aux dépendances de dev et un script `tools/build_native.py` qui compile une liste explicite de modules :
   - `src/physics/` (collisions, movement, spatial_hash, entity_grid) ;
   - `src/combat/hit_resolver.py` ;
   - `src/core/level/systems/contact_system.py`.
2. **Conserver le mode interprété** pour le développement : les modules compilés restent importables en Python pur, le build natif est un artifact optionnel. Aucun changement de sémantique, aucun golden touché par la compilation elle-même.
3. **Contraintes mypyc** : classes natives à héritage simple, attributs slottés, pas de descripteurs ni de surcharge d'opérateurs dans les modules compilés ; `Any` est un type effacé et ne rapporte rien. `Entity`, les protocols et les vues ECS restent donc interprétés — le périmètre ci-dessus est volontaire.
4. **A/B vérifiable** : benchmarks avec ordre alterné (le host est bruité), mêmes goldens/digests dans les deux modes. Publier les deux séries dans `docs/audit/performance-2026-11.md`.
5. **Packaging** : intégrer les `.so` dans `knightrock.spec` seulement si le gain est mesuré ; sinon le build reste pure Python.

### Vérification

`mypy src`, suite complète + `DEBUG=1`, digests, 675 issues, benchmarks de contact et de tick A/B, build PyInstaller avec et sans extensions.

### Livré et mesure

`tools/build_native.py` compile cinq modules (gravity, platforms, spatial_hash, spatial_query, velocity) dans une copie jetable du source, puis installe les extensions avec un manifeste que `--clean` sait retirer. Suite complète verte en mode natif : 3823 passed / 1 skipped, digests et goldens inchangés.

Trois modules du périmètre initial ont dû rester interprétés, sans toucher au code de jeu : `collisions`, `movement` et `hit_resolver` annotent la vue ECS `SurfaceFlagsView` comme un `dict[str, bool]` ; mypyc en fait une vraie vérification de dict et chaque contact lève `TypeError`. `contact_system` appelle le resolver, et `entity_grid` est sous-classé par un double de test (interdit par mypyc). Le périmètre réel est donc documenté dans le script de build.

`tools/benchmark_native.py` exécute les deux modes en processus séparés, en ordre alterné, avec le même checksum dans les dix mesures : médiane 2,294 ms (natif) contre 2,903 ms (interprété), soit 1,27× sur ce micro-bench. Le gain est réel mais limité ; le spec PyInstaller n'intègre donc **pas** les `.so`, et le jeu livré reste pure Python.

### Risques / rollback

Risque : certaines optimisations mypyc changent des comportements limites (runtime type checks sur des valeurs `Any`, classes dynamiques). Rollback : `uv run python tools/build_native.py --clean` (ou ne jamais lancer le build) ; le code source reste identique et interprétable. Ne jamais fusionner le build natif sans A/B favorable.

---

## E3 — Pré-rendu des calques statiques

### Objectif

Supprimer le cull et les ~115 blits de tuiles par frame en peignant chaque calque statique une seule fois dans une surface de la taille du niveau, puis en blittant la tranche viewport. Gain estimé 0,5–1,5 ms/frame.

### Conception

1. Construire au chargement du niveau une surface par calque statique (`static_sprites`, `fg_sprites`) de la taille du niveau (2560×1920 → ~19,7 Mo en 32-bit par calque). Ne garder le chunk index que pour les niveaux trop grands pour cette mémoire.
2. `TileChunkIndex` continue d'exister comme fallback et pour les tests de partition ; documenter le seuil de taille.
3. Invalider les surfaces de niveau quand le format d'affichage change (`ResourceCoordinator`).
4. Respecter l'ordre de peinture : fond statique → FX `behind` → sprites mobiles → FX avant → premier plan.

### Vérification

`test_tile_chunk_index.py` (partition totale), goldens de rendu et de culling, `render_benchmark.py` (cull et frame), `test_frame_coherence.py`, suites complètes.

### Livré et mesure

`src/core/rendering/static_layer.py` paint chaque calque gelé une fois à la densité de la cible, avec plafond de 64 Mo par calque et `TileChunkIndex` en fallback. Les surfaces sont invalidées par `ResourceCoordinator` et repaintées par `GameplayScene.set_surface`. `ENABLE_BAKED_PLANES` est **False** après A/B : le blit d'un viewport entier coûte plus que les tuiles visibles (7,4 ms contre 4,3 ms en 1920×1080), malgré une collecte trois fois moins chère. Table complète dans `docs/audit/performance-2026-11.md`.

### Risques / rollback

Risque : consommation mémoire (~20–60 Mo selon les calques), parallaxe et formats de tuiles avec offset, formats d'affichage changeants, et décalage d'un pixel sur les décors à rect fractionnaire sous une caméra interpolée. Rollback : constant déjà à `False` — le chemin `TileChunkIndex` reste le seul producteur livré ; le pré-rendu est une optimisation du producteur, pas du contrat du renderer.

---

## Ordre et portes de décision

1. **E1 d'abord** si la cible est le 1440p/4K : c'est le seul levier capable de diviser le coût frame.
2. **E2 ensuite** uniquement si, après E1, le tick reste > 2 ms avec 8 ennemis sur la machine cible.
3. **E3 seulement si** le remplissage de tuiles domine encore après E1/E2 (comparer les lignes « cull only » du benchmark).

Écartés définitivement, avec preuve : dirty rects (doc pygame-ce, caméra mobile), free-threaded Python 3.14t (pénalité mono-thread 5–10 % et GIL réactivé par les C ext), GPU/moderngl (inutile à ~100 sprites), optimisation du fingerprint à 440 champs (code de test uniquement).

## Sources

- [Documentation pygame-ce — `Surface.fblits`](https://pyga.me/docs/ref/surface.html)
- [Documentation pygame-ce — dirty rects](https://pyga.me/docs/tutorials/en/newbie-guide.html)
- [mypyc — introduction](https://mypyc.readthedocs.io/en/stable/introduction.html), [types et annotations](https://mypyc.readthedocs.io/en/stable/using_type_annotations.html)
- [Étude EASE 2025 — compilateurs Python](https://arxiv.org/html/2505.02346)
- [Python 3.14 — free-threading](https://docs.python.org/3/whatsnew/3.14.html)
