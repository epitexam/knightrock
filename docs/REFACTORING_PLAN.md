# Plan directeur de refactoring — Knightrock

> **Statut : plan préparé, non exécuté.** Toutes les tâches sont `TODO`. Ce document est
> l'unique roadmap du futur refactoring ; il sera mis à jour (statuts, fichiers modifiés,
> résultats de tests) lors d'une future mission, **après autorisation explicite**.
> Sources : [`ARCHITECTURE_AUDIT.md`](ARCHITECTURE_AUDIT.md) (constats F1–F16),
> [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ENGINEERING_STANDARDS.md`](ENGINEERING_STANDARDS.md).

**Résumé** : 18 tâches — 3 haute, 7 moyenne, 8 basse. Aucune tâche critique : aucun
constat critique ou majeur n'a survécu aux remédiations déjà réalisées sur cette branche.

---

## Organisation en phases

| Phase | Thème | Tâches |
|---|---|---|
| A | Prérequis et sécurité | T-01 → T-04 |
| B | Fondations architecturales | T-05, T-06 |
| C | Contrats typés et découplage | T-07 → T-09 |
| D | Architecture des entités | T-10 |
| E | Rendu et ressources | T-11, T-12 |
| F | Tests | T-13 |
| G | Hygiène et documentation | T-14 → T-18 |

Ordre = dépendances réelles : la référence comportementale est gelée avant toute
modification (T-01), la CI observe la branche avant qu'on y touche (T-02), les
restructurations de modules (T-05) précèdent les extractions qui s'y appuient (T-10).

---

# Phase A — Prérequis et sécurité

## T-01 — Geler la référence comportementale de la tête de branche

- **ID** : T-01.
- **Titre** : regénérer une fois les goldens de simulation et de combat sur la tête de
  `fix/remediation`, lire le diff, puis les geler comme référence du refactoring.
- **Priorité** : haute.
- **Statut** : TODO.
- **Problème constaté** : la branche porte des changements de gameplay assumés
  (audit F12 : dash retravaillé, charge, boucle No More Heroes 2, dark step, FX). La
  matrice des 421 issues de coups et les empreintes de simulation (RESPAWN, PHYSICS,
  RIDE) datent d'avant une partie de ces changements ; le refactoring a besoin d'une
  référence certaine.
- **Preuves** : `git log origin/master..fix/remediation` (commits « a gameplay change »
  `7e5ffd8`, `6d508e9`, `25c1301`, `d01baae`, `6a98588`) ; `tests/golden/hit_outcomes.json` ;
  empreintes dans `tests/headless/test_simulation_golden.py`.
- **Objectif** : toute tâche ultérieure compare à l'état réel de la branche, pas à un
  instantané périmé.
- **Principe concerné** : préservation du comportement (standards §6).
- **Solution proposée** : regénération volontaire unique (`UPDATE_GOLDENS=1`), lecture
  ligne à ligne du diff JSON, commit de gel avec le diff commenté.
- **Étapes d'implémentation** :
  1. Exécuter la suite complète sur la tête de branche (CI ou local 3.14).
  2. Regénérer `hit_outcomes.json` et les empreintes de simulation.
  3. Lire le diff ; chaque divergence doit correspondre à un commit de gameplay nommé.
  4. Committer les goldens à jour avec le message de gel.
- **Fichiers concernés** : `tests/golden/hit_outcomes.json`, empreintes de simulation
  (emplacement tel que défini par `tests/headless/test_simulation_golden.py`).
- **Dépendances** : aucune.
- **Risques** : si une divergence ne correspond à aucun commit identifié, c'est un bug
  inconnu → arrêter, documenter, ne pas geler.
- **Stratégie de tests** : suite complète verte avant et après le gel.
- **Critères d'acceptation** : goldens à jour, diff expliqué ligne à ligne, suite verte.

**Préservation du comportement :** cette tâche ne change aucun comportement ; elle
consomme et fige celui qui existe. Elle est le prérequis de toutes les tâches D et E.

---

## T-02 — Faire observer la branche par la CI

- **ID** : T-02.
- **Titre** : faire tourner les portes qualité (ruff, mypy, pytest/coverage, builds) sur
  l'état actuel de `fix/remediation`.
- **Priorité** : haute.
- **Statut** : TODO.
- **Problème constaté** : aucun run CI n'existe pour la branche (audit F13) : le workflow
  ne se déclenche que sur `master`, les tags, les PRs vers `master` et
  `workflow_dispatch`. ~57 900 lignes insérées non vérifiées côté GitHub, et la
  compatibilité Windows/macOS des derniers changements n'est pas observée.
- **Preuves** : `gh run list --branch fix/remediation` vide ; déclencheurs dans
  `.github/workflows/build.yml` (l.2-9).
- **Objectif** : vérifier l'état de la branche avant de la modifier.
- **Principe concerné** : intégration continue réelle.
- **Solution proposée** : ouvrir une PR **draft** `fix/remediation` → `master` (sans
  intention de fusion immédiate) ou déclencher `workflow_dispatch`. Ne pas modifier le
  workflow dans un premier temps.
- **Étapes d'implémentation** :
  1. Pousser la branche à jour.
  2. Ouvrir la PR draft (ou lancer le dispatch).
  3. Laisser tourner les trois jobs (test + builds multi-plateformes).
  4. Consigner les résultats dans le présent fichier (section journal).
- **Fichiers concernés** : aucun fichier du projet (opérationnel) ; éventuellement
  `.github/workflows/build.yml` si le développeur veut un déclenchement permanent sur
  cette branche (à sa demande).
- **Dépendances** : aucune.
- **Risques** : aucun code ; risque de découverte (échecs CI) qui prioriserait le reste
  du plan — c'est le but.
- **Stratégie de tests** : c'en est une.
- **Critères d'acceptation** : au moins un run CI complet sur la tête de branche, résultat
  consigné.

**Préservation du comportement :** sans objet (aucun code).

---

## T-03 — Écriture atomique de la sauvegarde

- **ID** : T-03.
- **Titre** : répliquer le protocole d'écriture durable de `SettingsStore` dans
  `SaveGame.save`, via un utilitaire partagé.
- **Priorité** : haute.
- **Statut** : TODO.
- **Problème constaté** : `SaveGame.save` écrit directement dans le fichier final
  (audit F1) ; un crash pendant l'écriture corrompt le JSON et la progression est perdue
  (chargement → sauvegarde neuve). `SettingsStore.save`, même paquet, même dossier
  utilisateur, applique déjà tempfile + `replace` + backup `.bak`.
- **Preuves** : `src/application/save_game.py:67-70` (`path.write_text(...)`) vs
  `src/application/settings_store.py:509-527` (`tempfile.NamedTemporaryFile(...,
  dir=self.path.parent, delete=False)` + `temporary_path.replace(self.path)` +
  `_keep_backup`).
- **Objectif** : une seule politique de persistance durable ; plus de perte de
  progression sur crash d'écriture.
- **Principe concerné** : robustesse, DRY, gestion des erreurs (standards §4).
- **Solution proposée** :
  1. Créer `src/application/persistence.py` avec une fonction
     `write_json_atomic(path, payload) -> None` (mkdir parents, tempfile même
     répertoire, `json.dump`, `Path.replace`, backup `.bak` best effort avec
     `logger.warning` en cas d'échec de backup).
  2. `SettingsStore.save` délègue à cet utilitaire (son comportement est conservé à
     l'identique, y compris l'ordre backup-avant-écriture).
  3. `SaveGame.save` délègue à son tour.
- **Étapes d'implémentation** :
  1. Écrire `persistence.py` + tests unitaires dédiés (succès, échec de backup, échec
     de remplacement).
  2. Migrer `SettingsStore.save` ; vérifier `test_settings_store.py` et
     `test_video_settings_persistence.py` au vert.
  3. Migrer `SaveGame.save` ; vérifier `test_save_game.py`.
  4. Ajouter un test « écriture interrompue » : simuler une exception pendant
     `json.dump` et vérifier que l'ancien fichier reste intact.
- **Fichiers concernés** : créer `src/application/persistence.py` ; modifier
  `src/application/save_game.py`, `src/application/settings_store.py` ; tests :
  `tests/unit/test_save_game.py`, `tests/unit/test_settings_store.py`, nouveau
  `tests/unit/test_persistence.py`.
- **Dépendances** : T-01 (référence gelée) — formellement, mais aucun comportement de
  jeu n'est touché.
- **Risques** : très faibles ; le seul point sensible est l'ordre backup/écriture de
  `SettingsStore` (à conserver exactement).
- **Stratégie de tests** : tests unitaires existants + nouveaux tests d'échec ;suite
  complète.
- **Critères d'acceptation** : les deux écritures passent par `persistence.py` ; un
  crash simulé pendant l'écriture laisse l'ancien fichier intact ; suite verte.

**Préservation du comportement :** aucun comportement de jeu concerné (écriture disque
uniquement). Les fichiers produits doivent rester byte-à-byte identiques
(`json.dumps(..., indent=2)` inchangé) pour ne pas surprendre les tests et les
utilitaires existants.

---

## T-04 — Ajouter Bandit en non-bloquant

- **ID** : T-04.
- **Titre** : ajouter le scanner de sécurité Bandit à la CI, en avertissement d'abord.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : aucune analyse de sécurité automatisée (audit F16). La surface
  d'attaque est faible (pas de réseau, pas d'`eval`/`exec`/`pickle` dans `src/`), mais
  une régression future ne serait signalée par aucun outil.
- **Preuves** : greps de l'audit (aucun hit réseau/exécution dynamique) ;
  `.pre-commit-config.yaml` et `build.yml` limités à ruff/mypy/pytest.
- **Objectif** : filet anti-régression sécurité proportionné.
- **Principe concerné** : défense en profondeur (standards §7).
- **Solution proposée** : dépendance de dev `bandit` ; étape CI
  `bandit -r src -ll --quiet` **non bloquante** (`continue-on-error: true`) ; trier les
  résultats ; passer en bloquant dans une seconde tâche après le tri.
- **Étapes d'implémentation** :
  1. Ajouter la dépendance de dev et verrouiller (`uv lock`).
  2. Ajouter l'étape CI non bloquante.
  3. Trier les signalements ; documenter les exclusions retenues dans le workflow.
  4. Tâche de suivi (hors périmètre immédiat) : passer en bloquant.
- **Fichiers concernés** : `pyproject.toml`, `uv.lock`,
  `.github/workflows/build.yml`.
- **Dépendances** : T-02 (la CI observe la branche).
- **Risques** : faux positifs bruyants → profil `-ll` (severity medium+) et exclusions
  explicites commentées.
- **Stratégie de tests** : le run CI lui-même.
- **Critères d'acceptation** : l'étape tourne en CI sans bloquer ; les résultats sont
  triés et consignés.

**Préservation du comportement :** sans objet.

---

# Phase B — Fondations architecturales

## T-05 — Éclater `core/settings.py` en package à ré-export identique

- **ID** : T-05.
- **Titre** : convertir `src/core/settings.py` (1 055 lignes, ~36 dataclasses de domaines
  hétérogènes) en package `src/core/settings/` avec un module par domaine, sans changer
  un seul point d'import.
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : faible cohésion (audit F3) — affichage, physique, combat,
  caméra, IA, entrées, audio, animation, simulation et debug dans un seul module importé
  par toutes les couches ; chaque retouche d'un domaine touche le même fichier.
- **Preuves** : `src/core/settings.py` — `class Display` (l.9) … `class Gameplay`
  (l.1052) ; importeurs dans toutes les couches (ex. `entities/entity.py` importe onze
  noms ; `core/level/world_builder.py`, `physics/*`, `states/*`, `ui/*`).
- **Objectif** : un module par domaine, frontières visibles, imports existants inchangés.
- **Principe concerné** : Single Responsibility (niveau module), High Cohesion.
- **Solution proposée** :
  - `settings/display.py` : `Display`, `World`, `Interpolation` ;
  - `settings/physics.py` : `Physics`, `Collision`, `PlatformRide`, `GameFeel` ;
  - `settings/combat.py` : `Combat`, `Stun`, `Rush`, `Battery`, `Fury`, `Finisher`,
    `Throw`, `Clash`, `Slot`, `Guard`, `HitFlash`, `ParryFlash`, `ReactionMark` ;
  - `settings/camera.py` : `CameraShake`, `CameraFollow`, `Afterimage` ;
  - `settings/ai.py` : `AI`, `Turn`, `TurnProfile`, `resolve_turn_profile`, `Ledge`,
    `EnemyJump`, `Separation`, `Turn` (selon les dépendances réelles relevées à
    l'exécution) ;
  - `settings/input.py` : `Input` ; `settings/audio.py` : `Audio` ;
    `settings/animation.py` : `Animation`, `Locomotion` ; `settings/simulation.py` :
    `Simulation`, `Debug`, `Respawn`, `StateMachineConfig`, `Gameplay`.
  - `settings/__init__.py` ré-exporte **tous** les noms actuels (vérifié par mypy :
    tout importeur existant doit compiler sans modification).
- **Étapes d'implémentation** :
  1. Relever la liste exacte des noms publics et des dépendances entre groupes
     (AST) ; corriger le découpage ci-dessus en conséquence.
  2. Créer les modules et déplacer les classes verbatim (aucune valeur changée).
  3. Écrire `__init__.py` de ré-export complet ; supprimer l'ancien module.
  4. `mypy src` + `ruff check` + suite complète au vert, sans avoir touché un seul
     importeur.
  5. Ajouter la règle interne « un module de domaine n'importe pas un autre module de
     domaine » à `test_layer_boundaries.py` (ou fichier de règles voisin).
- **Fichiers concernés** : supprimer `src/core/settings.py` ; créer
  `src/core/settings/__init__.py` + modules de domaine. **Aucun importeur modifié.**
- **Dépendances** : T-01.
- **Risques** : oubli d'un nom dans le ré-export (attrapé par mypy) ; imports circulaires
  entre domaines (à résoudre en dupliquant une constante littérale assumée, jamais en
  accouplant les modules).
- **Stratégie de tests** : suite complète (3 674 tests) + mypy strict ; le diff doit
  montrer zéro modification hors `src/core/settings*`.
- **Critères d'acceptation** : `from src.core.settings import X` fonctionne pour tout X
  actuel ; aucun importeur modifié ; suite et mypy verts.

**Préservation du comportement :** déplacement pur de constantes et de fonctions pures
(`resolve_turn_profile`) — aucune valeur ne change. Les timings, profils de turn et
seulements de gameplay sont comparés via la matrice et les empreintes (T-01) : identiques.

---

## T-06 — Rendre les systèmes du `GameplayLoop` obligatoires

- **ID** : T-06.
- **Titre** : supprimer les défauts `None` de `contact_system` et `feedback_system` dans
  `GameplayLoop`.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : `GameplayLoop` accepte `ContactSystem | None = None` et
  `FeedbackSystem | None = None` puis instancie des défauts à la volée ;
  `reaper_feedback` reste `Optional` (audit F6, déjà classé P3 par l'audit précédent).
- **Preuves** : `src/core/level/systems/gameplay_loop.py:56-58, 64, 73, 121`.
- **Objectif** : une seule voie de construction, dépendances explicites, échec bruyant
  d'un montage incomplet.
- **Principe concerné** : dépendances explicites, fail-fast.
- **Solution proposée** : paramètres obligatoires (positionnels ou keyword sans défaut)
  ; `reaper_feedback` typé non-optionnel avec un `NullFeedbackSystem` si un appelant
  légitime n'en veut pas ; mettre à jour les montages de tests concernés.
- **Étapes d'implémentation** :
  1. Relever tous les constructeurs de `GameplayLoop`/`CombatLoop` (production + tests).
  2. Rendre les paramètres requis ; ajuster les appelants.
  3. Suite complète au vert.
- **Fichiers concernés** : `src/core/level/systems/gameplay_loop.py`,
  `src/core/level/world_builder.py` (montages), tests concernés
  (`tests/unit/test_level_world_systems.py`, `tests/headless/test_gameplay_loop.py`, …).
- **Dépendances** : T-01.
- **Risques** : faibles — échecs de construction bruyants si un montage est oublié ;
  aucun changement d'exécution.
- **Stratégie de tests** : suite complète ; les tests d'orchestration de niveau.
- **Critères d'acceptation** : plus aucun `| None` de système dans `GameplayLoop` ;
  suite verte.

**Préservation du comportement :** l'ordre d'exécution des systèmes et le comportement
de tick sont inchangés ; seules les signatures de construction changent. Vérification :
empreintes de simulation identiques (T-01).

---

# Phase C — Contrats typés et découplage

## T-07 — Typer `EntitySnapshot`

- **ID** : T-07.
- **Titre** : remplacer les `Any` du snapshot de rollback par des contrats typés.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : `EntitySnapshot.entity: Any`, `groups: list[Any]`,
  `extra: dict[str, Any]` (audit F15) ; le compilateur ne protège pas l'ajout d'un champ
  de simulation, seul le test d'invariant (392 valeurs) le fait à l'exécution.
- **Preuves** : `src/entities/entity.py:72-102` ; `src/core/rollback/snapshots.py` ;
  `src/core/rollback/rollback.py` ; décision D4 (rollback conservé pour le multijoueur).
- **Objectif** : mypy signale un champ de simulation absent du snapshot.
- **Principe concerné** : typage des contrats, préparation multijoueur.
- **Solution proposée** : définir un `Protocol` minimal « ce que le restore lit »
  (hitbox, velocity, on_surface, facing, vitals, combat, state machine, identité) et
  typer `entity: Rollbackable` ; typer `groups` par le type réel des groupes de
  `SpriteGroups` ; documenter dans le docstring la frontière local/réseau inchangée
  (les scalaires restent la partie sérialisable).
- **Étapes d'implémentation** :
  1. Relever les attributs réellement lus par `RollbackSystem.restore`.
  2. Écrire le Protocol ; typer le champ ; corriger les faux objets de tests.
  3. Vérifier l'invariant de rollback (392 valeurs) au vert.
- **Fichiers concernés** : `src/entities/entity.py`, `src/core/rollback/snapshots.py`,
  `src/core/rollback/rollback.py`, `tests/fakes.py`, `tests/unit/test_rollback_snapshots.py`.
- **Dépendances** : T-01.
- **Risques** : faibles — typage seulement ; le Protocol doit rester minimal pour ne pas
  figer trop tôt le futur schéma réseau.
- **Stratégie de tests** : `test_rollback_invariant.py`, `test_rollback_e2e.py`,
  `test_rollback_snapshots.py`, mypy.
- **Critères d'acceptation** : plus aucun `Any` dans `EntitySnapshot` ; invariant vert.

**Préservation du comportement :** aucun changement d'exécution ; les 392 valeurs de
l'invariant doivent rester identiques.

---

## T-08 — Réduire les `getattr` : lot 1, overlay de debug

- **ID** : T-08.
- **Titre** : premier lot de suppression de `getattr` défensifs dans l'overlay de debug
  (densité la plus forte : ~un tiers des 206).
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : les `getattr(x, "nom", défaut)` avalent les exceptions levées
  *dans* les propriétés et masquent les contrats (audit F5 ; preuve historique du
  `is_invincible` dans le rapport final §7).
- **Preuves** : comptage 206 (`grep -c getattr src/`) ; répartition par fichier à
  relever à l'exécution ; méthode validée par l'étape 6 de l'audit précédent.
- **Objectif** : contrats explicites ; les faux objets incomplets échouent au lieu d'être
  tolérés.
- **Principe concerné** : encapsulation, fail-fast, Protocols.
- **Solution proposée** : pour chaque site : identifier le contrat réel, donner aux faux
  objets (`tests/fakes.py`) la forme complète, lire l'attribut directement ; si un
  attribut est réellement optionnel, le modéliser (`X | None`) plutôt que `getattr`.
- **Étapes d'implémentation** :
  1. Lister les sites de `src/ui/world_overlay_*.py` et les trier par fichier.
  2. Traiter fichier par fichier, suite verte à chaque pas.
  3. Mettre à jour `tests/fakes.py` et `test_fakes.py` (épinglage).
- **Fichiers concernés** : `src/ui/world_overlay_*.py`, `tests/fakes.py`, tests
  `test_world_overlay_*.py`, `test_debug_overlay.py`.
- **Dépendances** : T-01.
- **Risques** : faibles — un attribut réellement absent devient une erreur visible ;
  c'est le but, mais ça peut révéler des faux positifs de tests à corriger au cas par
  cas.
- **Stratégie de tests** : suite overlay + debug + complète.
- **Critères d'acceptation** : zéro `getattr` défensif dans les fichiers du lot ;
  suite verte ; aucune divergence d'empreinte.

**Préservation du comportement :** l'overlay de debug est hors simulation (aucun effet
sur le gameplay) ; les goldens d'interface et `test_no_stale_pixels.py` vérifient le
rendu.

---

## T-09 — Réduire les `getattr` : lot 2, systèmes et combat

- **ID** : T-09.
- **Titre** : second lot de `getattr` dans `core/level/systems/*` et `combat/*`
  (~20 légitimes sur les évènements pygame exclus).
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : même motif que T-08 sur les systèmes de niveau et le combat
  (audit F5).
- **Preuves** : comptage 206 ; sites à relever à l'exécution.
- **Objectif / Principe** : identiques à T-08.
- **Solution proposée** : méthode de T-08 ; priorité aux sites qui lisent des attributs
  de `Combatant` (le Protocol existe : `src/combat/combatant_protocol.py`).
- **Étapes d'implémentation** : comme T-08, système par système
  (`contact_system`, `combat_system`, `projectile_system`, `separation_system`).
- **Fichiers concernés** : `src/core/level/systems/*`, `src/combat/*`, `tests/fakes.py`,
  tests unitaires correspondants.
- **Dépendances** : T-08 (méthode rodée), T-01.
- **Risques** : moyens — ces codes sont dans la simulation ; chaque fichier traité est
  validé par la matrice des coups et les empreintes.
- **Stratégie de tests** : matrice de caractérisation (421), empreintes, suite complète.
- **Critères d'acceptation** : zéro `getattr` défensif dans le lot ; matrice et
  empreintes identiques ; suite verte.

**Préservation du comportement :** zone sensible (combat/physique). Aucun changement
d'issue de coup toléré ; toute divergence = régression à corriger avant de continuer.

---

# Phase D — Architecture des entités

## T-10 — Extraire la géométrie de hurtbox d'`Entity`

- **ID** : T-10.
- **Titre** : déplacer zones/tags/multiplicateurs/sweep de hurtbox vers un module dédié,
  `Entity` délègue.
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : `Entity` (1 373 lignes, 102 méthodes) garde la géométrie
  hitbox/hurtbox/zones multiples et la capture de sweep en plus de l'identité, des
  vitals et de la délégation combat/réaction/locomotion (audit F4). La composition
  existe déjà pour le reste.
- **Preuves** : `src/entities/entity.py` — méthodes de géométrie l.519-620
  (`hitbox`, `hurtbox`, `hurtboxes`, `hurtbox_tags`, `hurtbox_mult`,
  `hurtbox_zone_names`, `capture_sweep_origin`, `swept_pushbox`,
  `swept_contact_shapes`, `swept_hurtboxes`, `swept_hurtbox`), données
  `src/entities/hurtbox_zones.py`, formes `src/combat/shapes.py`.
- **Objectif** : `Entity` plus court, géométrie testable isolément, sans changer un seul
  rectangle produit.
- **Principe concerné** : Single Responsibility, composition, testabilité.
- **Solution proposée** :
  1. Créer `src/entities/hurtbox_geometry.py` : fonctions pures
     (zones → rectangles monde, application des multiplicateurs et tags, calcul des
     hurtboxes balayées) prenant les données en argument.
  2. `Entity` garde ses propriétés publiques (aucun appelant modifié) mais délègue le
     calcul aux fonctions.
  3. Tests de propriété : pour un échantillon d'états, les rectangles produits sont
     identiques avant/après (comparaison exhaustrice sur les fixtures de test
     existantes).
- **Étapes d'implémentation** :
  1. Relever les entrées exactes de chaque méthode (champs d'`Entity` lus).
  2. Écrire les fonctions pures + tests unitaires directs.
  3. Faire déléguer `Entity` ; suite complète + matrice + empreintes.
- **Fichiers concernés** : créer `src/entities/hurtbox_geometry.py` ; modifier
  `src/entities/entity.py` ; tests : nouveau `tests/unit/test_hurtbox_geometry.py`,
  existants `test_multi_hurtbox.py`, `test_hitbox_pipeline.py`.
- **Dépendances** : T-01 (obligatoire), T-07 recommandé (le snapshot typé évite de
  bouger deux fois la même zone).
- **Risques** : moyens — toute divergence de rectangle change les dégâts ; la matrice
  des 421 issues et les empreintes sont les juges ; en cas de divergence inexpliquée,
  la tâche est annulée et reclassée `REQUIRES_INVESTIGATION`.
- **Stratégie de tests** : tests unitaires des fonctions pures, matrice de
  caractérisation, empreintes de simulation, suite complète.
- **Critères d'acceptation** : matrice et empreintes identiques ; suite verte ;
  `Entity` n'implémente plus le calcul, elle délègue.

**Préservation du comportement :**
- **À préserver** : chaque rectangle de hurtbox/hitbox produit, pour chaque état et
  chaque frame ; l'ordre de calcul ; les zones et multiplicateurs.
- **Sensible** : les hurtboxes multiples et leur balayage — le moindre arrondi diffère.
- **Résultats identiques exigés** : matrice des 421 issues de coups, empreintes
  RESPAWN/PHYSICS/RIDE, invariant de rollback.
- **Tests de non-régression** : T-01 (référence), `test_multi_hurtbox.py`,
  `test_hitbox_pipeline.py`, `test_hit_outcome_matrix.py`.
- **Risque d'automatisation** : la délégation doit être mécanique (mêmes entrées, mêmes
  sorties) ; si une méthode lit de l'état implicite non passé en argument, l'extraction
  est reportée (`REQUIRES_INVESTIGATION`).

---

# Phase E — Rendu et ressources

## T-11 — Pré-rendu des calques de tuiles statiques

- **ID** : T-11.
- **Titre** : pré-rendre les tuiles statiques par blocs depuis `TileChunkIndex`, avec
  invalidation au changement d'échelle **et** de format d'affichage.
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : ~117 blits de tuiles par frame ; et après un changement de
  format d'affichage, les tuiles du niveau en cours ne sont pas reconverties (audit F8,
  défaut B4 du rapport final) — blits lents jusqu'au rechargement du niveau.
- **Preuves** : `docs/audit/final-report.md` §11 (« Pistes », gain estimé 30-40 % du
  dessin ; B4 « non corrigé, faible ») ; `src/core/rendering/tile_chunk_index.py`,
  `src/core/rendering/renderer.py`, invalidation existante `clear_frame_cache`
  (`src/core/fx/particles.py:1433-1441`).
- **Objectif** : quelques blits de blocs par frame ; plus de tuile non reconvertie.
- **Principe concerné** : resource lifecycle, surface reuse, dirty flag.
- **Solution proposée** :
  1. Bloc = groupe de chunks contigus pré-rendus sur une surface convertie au format
     courant.
  2. Invalidation : même point de raccrochage que `AssetLibrary`/`clear_frame_cache`
     (changement de format), plus changement d'échelle.
  3. Bornes mémoire : nombre de blocs limité par la taille du niveau (les niveaux
     actuels : 24×30 à 60×20 tuiles de 64 px — quelques mégaoctets par niveau, à
     mesurer).
- **Étapes d'implémentation** :
  1. Écrire le pré-rendu avec un commutateur (ancien chemin / nouveau chemin) pour
     comparer.
  2. Test de comparaison **au pixel** : rendu complet du niveau 0 (et d'un niveau avec
     décor avant/arrière) identique entre les deux chemins, y compris les bords de
     blocs.
  3. Brancher l'invalidation ; supprimer le commutateur après validation.
- **Fichiers concernés** : `src/core/rendering/tile_chunk_index.py`,
  `src/core/rendering/renderer.py`, point d'appel du changement de format
  (`src/core/display/*` / `application/game.py`) ; tests :
  `test_tile_chunk_index.py`, `test_no_stale_pixels.py`, `test_world_render_perf.py`,
  `test_tile_reconversion.py`.
- **Dépendances** : T-01, T-02 (mesures de rendu fiables).
- **Risques** : moyens — un pixel faux sur un bord de bloc se voit ; mémoire accrue
  (à mesurer et documenter) ; le chemin de secours doit rester disponible jusqu'à
  validation.
- **Stratégie de tests** : comparaison au pixel (goldens de rendu du niveau), tests
  d'invalidation, benchmark `tests/benchmarks/render_benchmark.py` avant/après.
- **Critères d'acceptation** : rendu identique au pixel ; aucune tuile périmée après
  changement de format (test dédié) ; gain de dessin mesuré et consigné.

**Préservation du comportement :** présentation uniquement — la simulation n'est pas
touchée (aucun tick modifié). Les empreintes de simulation restent identiques par
construction ; le risque est purement visuel, couvert par la comparaison au pixel.

---

## T-12 — Consigner les seuils de déclenchement des optimisations restantes

- **ID** : T-12.
- **Titre** : documenter, dans le présent plan, les conditions qui justifieraient
  d'ouvrir les optimisations non retenues (voisinage par tick, `sync_rects`, pas
  d'`draw_arc_stroke`).
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : les pistes existent avec des gains estimés mais aucun seuil de
  déclenchement (audit F9) ; risque d'optimisation prématurée ou, à l'inverse, d'oubli.
- **Preuves** : `docs/audit/final-report.md` §11 (5,7 ms tick / 3,0 ms dessin à 53
  entités ; ~0,08 ms/entité) ; `docs/design/matrice-niveaux.md` (niveaux potentiellement
  plus grands).
- **Objectif** : décision future outillée par des seuils explicites.
- **Principe concerné** : pas d'optimisation prématurée.
- **Solution proposée** : pour chaque piste, écrire : mesure déclenchante (ex. « tick
  médian > 8 ms au pire scénario visé »), bench à lancer
  (`tests/benchmarks/combat_feel.py`, `contact_benchmark.py`), et le test de
  non-régression requis.
- **Étapes d'implémentation** : rédaction dans la section journal de ce document ;
  aucun code.
- **Fichiers concernés** : `docs/REFACTORING_PLAN.md` (section journal).
- **Dépendances** : T-02 (mesures CI fiables).
- **Risques** : aucun.
- **Stratégie de tests** : sans objet.
- **Critères d'acceptation** : chaque piste a un seuil chiffré et un bench désigné.

**Préservation du comportement :** sans objet.

---

# Phase F — Tests

## T-13 — Stabiliser `test_death_is_a_still_picture.py`

- **ID** : T-13.
- **Titre** : éliminer l'instabilité documentée du test (2 échecs sur ~20 exécutions le
  2026-11-12).
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : le test compare des octets de frame entre ticks et échoue
  sporadiquement sous charge (« 2119 bytes of the frame moved 43 ticks… », rapport final
  §12) — un test instable décrédibilise toute la suite.
- **Preuves** : `docs/audit/final-report.md` §12 (« Test instable ») ;
  `tests/headless/test_death_is_a_still_picture.py`.
- **Objectif** : zéro faux négatif.
- **Principe concerné** : isolation des tests, déterminisme (standards §5).
- **Solution proposée** : identifier la source de non-déterminisme (horloge réelle ?
  ordre de groupes ? surface non initialisée ?) ; remplacer la dépendance au temps réel
  par l'horloge factice (modèle du correctif B3 de `test_frame_pacing`) ou fixer la
  graine ; si la propriété testée est intrinsèquement dépendante du timing réel,
  la réécrire en assertion d'invariant (l'image ne change pas tant que aucun tick ne
  tourne).
- **Étapes d'implémentation** :
  1. Reproduire en boucle (`pytest -x --count` ou boucle shell) pour capturer un échec.
  2. Diagnostiquer la source exacte.
  3. Corriger selon la solution proposée ; vérifier 50 exécutions consécutives vertes.
- **Fichiers concernés** : `tests/headless/test_death_is_a_still_picture.py` (et
  éventuellement `tests/headless/conftest.py`).
- **Dépendances** : T-01.
- **Risques** : faibles — modification de test uniquement ; attention à ne pas affaiblir
  la propriété testée (la mort doit rester une image fixe).
- **Stratégie de tests** : 50 exécutions consécutives du test ; suite complète.
- **Critères d'acceptation** : 50/50 vertes ; la propriété « mort = image fixe » reste
  assertée avec la même force.

**Préservation du comportement :** sans objet (test) ; la propriété de comportement
vérifiée doit rester équivalente.

---

# Phase G — Hygiène et documentation

## T-14 — Réécriture éditoriale : `core/fx/tuning.py`

- **ID** : T-14.
- **Titre** : premier lot de réduction de prose sur le pire fichier (602 lignes, ~190 de
  code).
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : ~30 % des lignes de `src/` sont de la prose narrative
  (historique d'audit) ; `fx/tuning.py` est le cas extrême (audit F7 ; R9 « en partie »
  du rapport final).
- **Preuves** : comptages de l'audit ; règle d'écriture déjà dans le README.
- **Objectif** : ne garder que le « pourquoi » du code vivant.
- **Principe concerné** : KISS, lisibilité.
- **Solution proposée** : réécrire les docstrings en conservant la sémantique ; **aucun**
  changement d'AST (vérifié par un diff AST, méthode du précédent audit : « 132
  références retirées, AST du code identique »).
- **Étapes d'implémentation** :
  1. Réécrire le fichier.
  2. Vérifier l'équivalence d'AST (fonctions/classes/noms/docstrings exclus).
  3. Suite complète au vert.
- **Fichiers concernés** : `src/core/fx/tuning.py`.
- **Dépendances** : T-01.
- **Risques** : nuls si l'AST est vérifié ; sinon perte d'information utile — ne pas
  supprimer un « pourquoi » encore vrai.
- **Stratégie de tests** : diff AST + suite complète.
- **Critères d'acceptation** : AST du code identique ; suite verte.

**Préservation du comportement :** garanti par l'équivalence d'AST.

---

## T-15 — Réécriture éditoriale : lots suivants

- **ID** : T-15.
- **Titre** : poursuivre la réduction de prose fichier par fichier (entity.py, gros
  modules ui/ et core/), par lots isolés.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté / Preuves / Objectif / Principe** : identiques à T-14 (audit F7).
- **Solution proposée** : un lot = un domaine (ex. `entities/`, puis `ui/`), un commit
  par fichier, diff AST à chaque pas ; jamais mélangé à un changement de comportement.
- **Étapes d'implémentation** : prioriser par ratio prose/code relevé à l'exécution ;
  répéter T-14.
- **Fichiers concernés** : `src/entities/entity.py`, `src/ui/*` (gros fichiers),
  `src/core/level/systems/*`.
- **Dépendances** : T-14 (méthode validée).
- **Risques** : identiques à T-14.
- **Stratégie de tests** : identiques à T-14.
- **Critères d'acceptation** : ratio prose réduit et consigné dans le journal ; AST
  inchangé ; suite verte.

**Préservation du comportement :** garanti par l'équivalence d'AST.

---

## T-16 — Documenter l'état process-wide et ajouter un fixture de reset si nécessaire

- **ID** : T-16.
- **Titre** : lister les états globaux de module acceptés et garantir leur réinitialisation
  dans les tests.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : six états globaux de module (audit F14) : `_SHARED_LIBRARY`,
  caches FX (`clear_frame_cache` existe), `_language`, `_compact_panels`,
  `_bindings_cache` ; les deux options d'interface n'ont pas de hook de reset dédié.
- **Preuves** : `src/core/asset_library.py:159`, `src/core/fx/particles.py:925,1395-1441`,
  `src/ui/text.py:170`, `src/ui/panel_renderer.py:403`,
  `src/core/display/sdl_probe.py:256`.
- **Objectif** : état global documenté, tests isolés par construction.
- **Principe concerné** : état global maîtrisé, isolation des tests.
- **Solution proposée** : section « état process-wide » dans
  `ENGINEERING_STANDARDS.md` (liste + règles) ; fixture pytest de reset pour
  `_language`/`_compact_panels` si un cas de fuite est observé (ne pas en créer sans
  besoin).
- **Étapes d'implémentation** :
  1. Rédiger la section standards.
  2. Vérifier chaque global : hook de reset présent (oui/non).
  3. Ajouter les fixtures manquantes seulement si un fuite réelle existe.
- **Fichiers concernés** : `docs/ENGINEERING_STANDARDS.md` ; éventuellement
  `tests/conftest.py`.
- **Dépendances** : aucune.
- **Risques** : aucun.
- **Stratégie de tests** : suite complète (isolation vérifiée par l'existant).
- **Critères d'acceptation** : section rédigée ; chaque global a un hook de reset ou une
  justification d'absence.

**Préservation du comportement :** sans objet.

---

## T-17 — Documenter la contrainte Python 3.14 / PEP 758

- **ID** : T-17.
- **Titre** : documenter que la lecture même du code exige Python ≥ 3.14 (style PEP 758
  assumé).
- **Priorité** : moyenne.
- **Statut** : TODO.
- **Problème constaté** : cinq modules utilisent `except A, B:` sans parenthèses (PEP
  758) ; tout outillage ≤ 3.13 échoue à la parse avec un message trompeur (audit F2 ;
  arrivé à cet audit).
- **Preuves** : `src/core/input/event_router.py:525`, `src/core/display/stage.py:223`,
  `src/ui/world_overlay_velocity.py:70`, `src/application/save_game.py:63,78`,
  `tools/display_acceptance.py:173` ; commit `fdf7e2c6` (style maison assumé).
- **Objectif** : un contributeur sur 3.12/3.13 comprend immédiatement pourquoi rien ne
  parse.
- **Principe concerné** : outillage reproductible, documentation.
- **Solution proposée** : encadré dans le README (Quick start) : « Python 3.14 est requis
  même pour lire le code (PEP 758) ; utiliser `uv` » ; mention dans les conventions.
  Ne **pas** réécrire les clauses.
- **Étapes d'implémentation** : rédaction README + vérification que `uv sync` couvre le
  cas.
- **Fichiers concernés** : `README.md`.
- **Dépendances** : aucune.
- **Risques** : aucun.
- **Stratégie de tests** : `test_readme_claims.py` continue de passer.
- **Critères d'acceptation** : la contrainte est documentée en tête de README.

**Préservation du comportement :** sans objet (documentation).

---

## T-18 — Vérifications finales et mise à jour des chiffres

- **ID** : T-18.
- **Titre** : à la clôture du refactoring : suite complète, couverture, mypy, ruff,
  comparaison des goldens, mise à jour des chiffres du README si nécessaire.
- **Priorité** : basse.
- **Statut** : TODO.
- **Problème constaté** : le README affiche des chiffres (tests, couverture) vérifiés par
  `test_readme_claims.py` ; tout refactoring qui ajoute des tests change ces chiffres.
- **Preuves** : `tests/unit/test_readme_claims.py` ; `README.md` (badges, §Tests &
  quality).
- **Objectif** : clôture cohérente et vérifiable.
- **Principe concerné** : documentation exacte.
- **Solution proposée** : checklist de clôture : `uv run pytest -q`,
  `uv run mypy src main.py tools`, `uv run ruff check . && uv run ruff format --check .`,
  matrice des coups identique (ou diff expliqué), empreintes identiques, invariant de
  rollback vert, chiffres README à jour.
- **Étapes d'implémentation** : exécuter la checklist ; consigner les résultats dans le
  journal de ce plan.
- **Fichiers concernés** : `README.md` (chiffres), `docs/REFACTORING_PLAN.md` (journal).
- **Dépendances** : toutes les tâches précédentes.
- **Risques** : aucun.
- **Stratégie de tests** : c'en est une.
- **Critères d'acceptation** : checklist complète au vert, consignée.

**Préservation du comportement :** sans objet.

---

# Éléments hors périmètre d'implémentation

## `OUT_OF_SCOPE` (recensés, non transformés en tâches)

| ID audit | Élément | Raison |
|---|---|---|
| F10 | Objets `water` de six niveaux ignorés par le world builder | Décision de design requise (nage/dégâts/ralentissement) ou retrait des cartes ; touche cartes + gameplay |
| F12 | Changements de gameplay récents de la branche (dash, charge, boucle NMH2, dark step, FX) | Ce sont des fonctionnalités assumées ; le plan les **préserve**, il ne les retouche pas. Consommés par T-01 (gel de référence) |

Tout rééquilibrage, toute nouvelle mécanique, toute proposition de game design est hors
périmètre, conformément à la mission.

## `REQUIRES_INVESTIGATION` (à instruire avant toute décision)

| ID audit | Élément | Ce qui manque | Condition de sortie |
|---|---|---|---|
| F4 (partie c) | Déplacement de la capture de sweep hors d'`Entity` (`combat/shapes.py`) | Analyse des états implicites lus par `capture_sweep_origin`/`swept_*` | Si toutes les entrées sont explicites → convertible en tâche (méthode T-10) |
| F9 (partie) | Voisinage `get_nearby` une fois par entité/tick ; `sync_rects` ; pas d'`draw_arc_stroke` | Une mesure motivante à la charge réelle | Seuils définis par T-12 dépassés + bench avant/après |
| F11 | Interpolation des entités (décision D5) | Observation réelle à 120/144 Hz | Observation faite → implémenter ou clore |
| — | Direction de la projection lourde en mode `fixed` (corrigée par B2, à confirmer en jeu) | Validation manuelle au pad | Confirmation développeur |

## Vérification de complétude (mission §5.5)

- ✅ Les 16 constats de l'audit (F1–F16) sont représentés : 14 en tâches (T-01 à T-18),
  2 en `OUT_OF_SCOPE` (F10, F12), 1 partiellement en `REQUIRES_INVESTIGATION`
  (F4c, F9, F11).
- ✅ Les dépendances sont cohérentes et minimales (T-01 racine ; T-02 avant T-04 et T-12 ;
  T-08 avant T-09 ; T-14 avant T-15 ; T-18 dernière).
- ✅ Chaque tâche a des critères d'acceptation vérifiables et une stratégie de tests.
- ✅ Chaque tâche touchant un système de jeu (T-06, T-07, T-08, T-09, T-10, T-11, T-13)
  porte une section « Préservation du comportement ».
- ✅ Aucun changement de gameplay n'est prévu : aucune tâche ne modifie
  `data/gameplay/*.json`, les cartes Tiled, les valeurs de `core/settings*`, ni les
  règles de combat/physique.
- ✅ Les statuts sont tous `TODO` ; aucune tâche n'est commencée.

---

# Journal d'exécution

(À tenir lors de la future mission de refactoring : date, tâche, fichiers modifiés,
résultats de tests, écarts.)

| Date | Tâche | Statut | Fichiers | Tests | Notes |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
