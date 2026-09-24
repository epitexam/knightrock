# Plan d’implémentation — Hitbox amelioration

## 0. Objet et contraintes

Ce plan traite les écarts partiellement conformes ou non conformes identifiés lors de l’audit de `notes/hitbox_amelioration.md`.

Contraintes :

- aucun commit dans cette étape ;
- ne pas modifier le comportement gameplay validé par les goldens sans preuve et test associé ;
- conserver P0–P5 ; le sweep melee reste actif, avec extension prévue aux projectiles AABB et hazards mobiles ;
- traiter la modification existante de `src/core/settings.py` comme un changement hors périmètre ;
- valider toute modification documentaire contre le code réellement présent.

État observé :

- `pytest -q` : **910 tests passés** dans l’ordre actuel ;
- `mypy src` : **128 fichiers analysés, aucune erreur** ;
- `ruff check .` : propre ;
- sweep AABB actif pour melee, projectiles et hazards mobiles ; hazards statiques et contact damage restent discrets ;
- le test UI est désormais hermétique avec et sans `DEBUG=1` ;
- le benchmark est directement lançable et produit des contacts réels 1/16/64 ;
- le rapport principal et `notes/ecarts_ouverts.md` sont synchronisés avec P5/O1–O9.

## 1. Objectifs de sortie

1. Le rapport principal reflète l’état réel du code.
2. Les statuts O1–O9 sont cohérents dans les deux documents.
3. Les tests passent isolément et en suite complète sans dépendance involontaire à l’environnement.
4. Le benchmark est lançable par une commande documentée et mesure un contact réel.
5. `uv run ruff check .` passe, ou chaque exception restante est explicitement justifiée.
6. Aucun écart n’est présenté comme clos alors qu’il ne l’est pas.

## 2. Phase A — Synchroniser la documentation

### A.1 Compteurs et recette

Fichiers : `notes/hitbox_amelioration.md`, `notes/ecarts_ouverts.md`.

Actions :

- remplacer les valeurs historiques 856/861 par le nombre réel de tests ;
- remplacer 125/127 fichiers mypy par le nombre réellement analysé ;
- ajouter date, commandes et commit de référence de la recette ;
- distinguer la base historique du résultat actuel ;
- ne pas déclarer la recette verte avant la fin des phases B, C et E.

### A.2 Actualiser P5

Fichier : `notes/hitbox_amelioration.md`.

Actions :

- remplacer « P5 non engagé » et « formes avancées hors périmètre » par « P5 implémenté » ;
- documenter AABB, cercle, capsule, OBB, rotation, easing, anchors et keyframes ;
- documenter `test_hitbox_shapes.py` et `test_p5_integration.py` ;
- conserver la limite : le sweep bilateral melee reste actif ; ajouter le sweep AABB projectile et hazard mobile ; contact reste discret ;
- mettre à jour le modèle JSON et les règles de validation réelles ;
- supprimer les mentions obsolètes de `block_mask`, `hit_level` ou tags « absents ».

### A.3 Corriger O1–O9

Fichiers : `notes/hitbox_amelioration.md`, `notes/ecarts_ouverts.md`.

Actions :

- mettre à jour le tableau récapitulatif ;
- remplacer chaque « ouvert » par « clos », « clos par décision produit » ou « hors périmètre » ;
- supprimer les preuves historiques contredites par le code ;
- ajouter des preuves basées sur les chemins et tests actuels ;
- conserver O7 comme « clos par décision produit » ;
### A.4 Cohérence documentaire

Le nombre de tests, le statut P5, les statuts O1–O9, les limites produit et les commandes de validation doivent correspondre à l’état réel du dépôt.


## 3. Phase B — Tests hermétiques

### B.1 Corriger la fuite `DEBUG`

Fichiers : `tests/unit/test_debug_layout.py`, `tests/unit/test_debug_overlay.py`.

Actions :

- remplacer les affectations directes à `os.environ["DEBUG"]` par `monkeypatch.setenv` et `monkeypatch.delenv` ;
- ajouter une fixture/helper si nécessaire ;
- ne pas modifier le comportement runtime de `Debug.is_enabled()`.

### B.2 Isoler le test UI

Test : `tests/unit/test_debug_overlay.py::test_gameplay_scene_function_keys_toggle_overlay_layers`.

Actions :

- configurer `DEBUG=1` explicitement dans le test F1–F5 ;
- ajouter un test vérifiant que F1–F5 sont ignorés sans debug si ce contrat est requis ;
- ne pas compter sur un test précédent pour activer l’environnement.

### B.3 Validation

```bash
env -u DEBUG uv run pytest -q tests/unit/test_debug_overlay.py::test_gameplay_scene_function_keys_toggle_overlay_layers
DEBUG=1 uv run pytest -q tests/unit/test_debug_overlay.py::test_gameplay_scene_function_keys_toggle_overlay_layers
env -u DEBUG uv run pytest -q
DEBUG=1 uv run pytest -q
```

Réception : le test isolé et la suite complète passent dans les modes adaptés, sans fuite d’environnement.

## 4. Phase C — Benchmark reproductible

### C.1 Lancement

Le lancement direct de `tests/benchmarks/contact_benchmark.py` échoue actuellement avec `ModuleNotFoundError: src`. Retenir soit un bootstrap d’import, soit la commande documentée :

```bash
PYTHONPATH=. uv run python -m tests.benchmarks.contact_benchmark
```

Éviter de modifier le code de production ou `pyproject.toml` uniquement pour le benchmark.

### C.2 Mesure d’un contact réel

Le préchauffage marque actuellement les cibles via `targets_hit`, donc les itérations suivantes produisent `contacts=0`.

Actions :

- réinitialiser les cibles et mémoires de contact entre itérations, ou construire un état frais ;
- conserver la mesure broadphase/narrowphase ;
- ajouter un scénario overlap avec contacts stables et non nuls ;
- ajouter si possible un scénario sans contact ;
- distinguer contacts initiaux et contacts répétés.

### C.3 Documentation

Mettre à jour la section 2.2, la section 10 et O4 avec la commande exacte, Python, pygame, plateforme, itérations, répétitions, version JSON, résultat et règle de comparaison entre révisions.


## 5. Phase D — Qualité globale

### D.1 Ruff global

Corriger dans `main.py` uniquement les imports et la newline finale, sans modifier la logique du bootstrap :

```bash
uv run ruff check .
```

### D.2 Modification locale de `settings.py`

`src/core/settings.py` contient une modification locale de `FPS`, hors périmètre hitbox. Ne pas la stage automatiquement ; décider explicitement si elle est conservée, revertée ou traitée dans un autre plan, puis documenter cette décision.

## 6. Phase E — Validation finale

### Tests ciblés

```bash
env -u DEBUG uv run pytest -q tests/unit/test_debug_overlay.py
DEBUG=1 uv run pytest -q tests/unit/test_debug_overlay.py
env -u DEBUG uv run pytest -q tests/unit/test_hitbox_shapes.py tests/unit/test_p5_integration.py
env -u DEBUG uv run pytest -q tests/unit/test_contact_unified.py tests/unit/test_hitbox_sweep.py
```

### Suite, typage et lint

```bash
env -u DEBUG uv run pytest -q
DEBUG=1 uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
```

### Benchmark

```bash
PYTHONPATH=. uv run python -m tests.benchmarks.contact_benchmark --iterations 300 --repeats 5
```

### Contrôle documentaire final

Vérifier qu’il ne reste aucune mention obsolète de `P5 non engagé`, `block_mask NON IMPLEMENTE`, tags/checksum absents, 856/861 présentés comme résultat actuel, `contacts=0` sans explication, ou O1–O9 sans statut et preuve actualisés.

## 7. Ordre d’exécution

1. Phase B — tests hermétiques ;
2. Phase C — benchmark reproductible ;
3. Phase D — Ruff global et décision sur `settings.py` ;
4. Phase A — synchronisation documentaire ;
5. Phase E — validation finale.

## 8. Critères de sortie

- tests ciblés et complets reproductibles ;
- `uv run ruff check .` réussi ;
- `uv run mypy src` réussi ;
- benchmark lançable et mesurant un contact réel ;
- rapport hitbox synchronisé avec le code ;
- aucune preuve documentaire contredite par le code ;
- modification de `settings.py` traitée ou explicitement exclue ;
- aucun commit automatique ni modification de l’historique Git.
