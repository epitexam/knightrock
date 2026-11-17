# Standards d'ingénierie — Knightrock

> Règles de qualité à appliquer lors du futur refactoring et aux développements
> ultérieurs. Elles formalisent les conventions **existantes** (README §Conventions,
> `pyproject.toml`, `.pre-commit-config.yaml`, `tests/unit/test_layer_boundaries.py`,
> `tests/unit/test_source_conventions.py`) et ajoutent les règles que l'audit rend
> nécessaires. Aucun outil nouveau n'est installé dans cette mission.

---

## 1. Conventions Python

- **Version** : Python 3.14 strict (`requires-python = ">=3.14"`, `.python-version`).
  La syntaxe `except A, B:` sans parenthèses (PEP 758) est le style maison
  (commit `fdf7e2c6`) : **ne pas** la « réparer » en parenthésant, et documenter que
  Python ≤ 3.13 ne peut même pas lire le code (audit F2).
- **Format et lint** : Ruff (`line-length = 100`, règles `E,F,W,I,UP,B,C4,C901,SIM,N`
  avec les trois exemptions documentées dans `pyproject.toml`). `ruff format` fait foi.
- **Nommage** : modules et fonctions en `snake_case`, classes en `PascalCase`,
  constantes de module en `UPPER_SNAKE` (`SCALE_CACHE_MAX`, `SIMULATION.TIMESTEP`).
  Les noms d'états suivent la convention `(str, Enum)` (exemption `UP042` assumée).
- **Docstrings** : le « pourquoi », pas l'historique. Toute prose racontant un audit
  passé, une date ou un ancien bug est réécrite à l'occasion d'une retouche du fichier
  (règle déjà écrite dans le README). Les réécritures éditoriales de fond (F7) se font
  par lots isolés, **sans** aucun changement d'AST.
- **Pas de TODO/FIXME** : la règle actuelle (zéro occurrence dans `src/`) est maintenue ;
  les points ouverts vivent dans `docs/`.

## 2. Typage

- **mypy strict, bloquant** : `disallow_untyped_defs`, `disallow_incomplete_defs`,
  `warn_return_any`, sans override par module (état actuel, à conserver). `mypy src
  main.py tools` doit rester à 0 erreur.
- **Protocols** pour les contrats multi-implémentations (`Combatant`,
  `WorldOverlay`, `InputProvider`) : toute nouvelle couture passe par un Protocol, pas
  par du canard typé `Any`.
- **`Any` interdit sauf justification écrite** : les `Any` restants sont ciblés
  (`EntitySnapshot.entity` et références locales du rollback — F15 à réduire ; évènements
  pygame). Un nouveau `Any` en production exige un commentaire qui dit pourquoi.
- **`getattr(x, "nom", défaut)` interdit en production** sauf évènements pygame et
  sonde d'existence justifiée. La méthode de remplacement est celle de l'étape 6 de
  l'audit précédent : donner aux faux objets la forme réelle (`tests/fakes.py`), puis
  lire l'attribut directement (F5).

## 3. Responsabilités des modules et règles de dépendances

- Les huit couches (`application`, `combat`, `core`, `data`, `entities`, `physics`,
  `states`, `ui`) et leurs directions restent celles vérifiées par
  `tests/unit/test_layer_boundaries.py`. Toute élargissement de l'allowlist est un
  commit délibéré avec sa justification dans le message.
- Règles additionnelles à faire vérifier par le même mécanisme AST :
  - `import pytmx` autorisé uniquement dans `src/core/level/level_manager.py` et
    `src/core/level/level_data.py` (état actuel : déjà vrai — le figer).
  - `pygame.mixer` importé uniquement dans `src/core/audio.py`.
  - Écritures disque utilisateur uniquement via `application/persistence.py` (après F1).
- **Un module, un domaine** : après l'éclatement de `core/settings/` (F3), un module de
  domaine de settings n'importe pas un autre module de domaine.
- **État process-wide** (F14) : les singletons de module existants
  (`shared_library`, caches FX, `_language`, `_compact_panels`, `_bindings_cache`) sont
  acceptés ; tout nouveau doit exposer un hook de reset (`clear_*`) et être listé ici.

## 4. Gestion des erreurs

- **Bordures explicites** : un `except Exception` large n'est légitime qu'à une frontière
  (bus d'évènements, entrées manette, chargement d'une librairie externe, dernier recours
  de la boucle) et porte `# noqa: BLE001` avec la raison — convention existante à
  maintenir. `stage.py` (2 sites) doit être aligné sur cette convention lors d'une
  prochaine retouche.
- **Échouer tôt, échouer fort** : les données obligatoires lèvent (`GameplayDataError`,
  `LevelLoadError`, `UnknownLevelError`) ; aucun fallback silencieux sur des valeurs non
  relues (décision C4).
- **Persistance** (F1) : toute écriture de fichier utilisateur est atomique (tempfile
  dans le même répertoire + `Path.replace`) avec backup `.bak` best effort ; un échec de
  backup ne fait jamais échouer l'écriture.
- **Erreurs d'abonnés** : jamais propagées à l'émetteur ; journalisées et listées
  (`EventBus._failures`) — comportement existant à préserver.

## 5. Tests

- **Exigences** : tout changement de `src/` arrive avec ses tests ; la couverture ne
  descend pas sous le seuil CI (`--cov-fail-under=80`, mesuré ~92 %).
- **Pyramide en place, à préserver** :
  - *unit* (`tests/unit/`) : comportements isolés, faux objets épinglés (`test_fakes.py`) ;
  - *headless* (`tests/headless/`) : scénarios de simulation complets sans écran ;
  - *goldens* : matrice de 421 issues de coups (`tests/golden/hit_outcomes.json`),
    captures d'interface (`tests/golden/*.png`), empreintes de simulation ;
  - *invariants* : rollback (392 valeurs), pas de pixel périmé, frontières de couches,
    affirmations du README (`test_readme_claims.py`).
- **Après tout changement volontaire de combat** : regénérer la matrice
  (`UPDATE_GOLDENS=1`) et **lire le diff** du JSON — c'est le relevé exact de ce qui a
  changé (règle du rapport final §10).
- **Déterminisme** : aucun test ne dépend du hasard non contrôlé ni de l'horloge réelle ;
  les tests de pacing utilisent l'horloge factice (correctif B3). Les tests mesurant le
  temps réel sont interdits hors `tests/benchmarks/`.
- **Environnement** : `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy` (CI et modules de
  tests) ; `monkeypatch` pour `DEBUG`, jamais d'écriture directe dans `os.environ`.
- **Un faux objet incomplet doit échouer**, jamais être toléré par le code de production.

## 6. Préservation du comportement

- Le comportement actuel de la branche (y compris les changements de gameplay récents,
  audit F12) est **la référence**. Un refactoring ne change ni les déplacements, ni les
  contrôles, ni la physique, ni les dégâts, ni les timings, ni les transitions d'état,
  ni l'IA, ni les niveaux, ni l'interface.
- Avant le premier jour de refactoring : regénérer une fois les goldens sur la tête de
  branche, lire le diff, geler.
- Toute tâche touchant un système de jeu porte une section « Préservation du
  comportement » dans le plan et s'appuie au minimum sur : la matrice des coups, les
  empreintes de simulation, l'invariant de rollback, les goldens d'interface.
- Si l'équivalence ne peut pas être garantie, la tâche passe en
  `REQUIRES_INVESTIGATION` et n'est pas exécutée.

## 7. Outils (évaluation, non installés dans cette mission)

| Outil | Verdict | Rôle |
|---|---|---|
| **Ruff** (check + format) | déjà en place, bloquant CI + pre-commit | conserver tel quel |
| **mypy** strict | déjà en place, bloquant CI + pre-commit | conserver ; étendre aux `Any` du rollback (F15) |
| **Pytest + pytest-cov** | déjà en place, bloquant, seuil 80 % | conserver ; surveiller le test `test_death_is_a_still_picture.py` signalé instable 2/20 |
| **Coverage.py** | via pytest-cov | conserver |
| **Pre-commit** | déjà en place (ruff, mypy, pytest) | conserver |
| **CI/CD** (GitHub Actions) | en place, multi-plateforme, actions épinglées par SHA, `--frozen` | conserver ; ajouter le déclenchement sur la branche de travail (F13) |
| **Bandit** | **absent — à ajouter** (F16), non-bloquant d'abord puis bloquant après tri des faux positifs | filet anti-régression sécurité |
| **Pyright** | non recommandé : redondant avec mypy strict déjà bloquant, coût de double maintenance | ne pas ajouter |

## 8. Règle de revue

- Un commit = une intention (convention des messages actuels : phrase descriptive,
  préfixe `feat/fix/refactor/perf/docs/test(scope)`).
- Un refactoring qui touche un système de jeu cite dans son message les garde-fous
  passés (matrice, goldens, invariants).
- Les documents de `docs/audit/` restent des instantanés datés : on ne les réécrit pas,
  on ajoute un nouveau rapport.
