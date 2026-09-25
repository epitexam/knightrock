# Audit consolidé - Tâches restantes Knightrock

> **État au 2026-09-19 (rev `e0fa07d`, branche `master`) :** vérifié un par un
> contre le code. **1092 tests verts** (`1092 passed`), `ruff check` clean,
> `mypy src` clean (120 fichiers).
>
> **Historique :** remplace `notes/audit.md` (86% : Phases 1-3 + 5 faites),
> `notes/audit_phase5.md` (100% mécanique) et `notes/refactoring_handoff.md`
> (~91% technique, RF-4/5/6 à 100%). Seul ce fichier subsiste dans `notes/`.
> Tout ce qui était terminé est résumé en section 1 et **n'est plus à faire**.
> Tout ce qui reste est en section 2 (R-1 à R-9).

---

## Sommaire

- [1. Ce qui est terminé](#1-ce-qui-est-terminé-rappel-ne-pas-rouvrir)
- [2. Tâches restantes](#2-tâches-restantes) : R-1 à R-9
- [3. Récapitulatif](#3-récapitulatif)
- [4. Règles](#4-règles-toujours-valables)
- [5. Commandes de validation](#5-commandes-de-validation)
- [6. Réception globale](#6-réception-globale)

---

## 1. Ce qui est terminé (rappel, ne pas rouvrir)

| Périmètre | État | Détail |
|---|---|---|
| Phase 1 | 95 % | `__init__.py`, README, code mort supprimé, magic numbers centralisés (`Collision`, `PlatformRide`, `Separation`, `Locomotion`, `Respawn` dans `src/core/settings.py`), `EnemyState(Enum)`, `.gitignore` propre, `NULL_KNOCKBACK`, ruff + mypy en CI, `dictConfig`, `tests/unit/helpers.py`, tests headless. |
| Phase 2 | 100 % | `AssetLibrary` + `Animator`, dirty-rects (`core/rendering/renderer.py`), `Player` 698 puis 357 lignes (`controller_view.py`, `player_input.py`), `SceneManager` + scènes, `EventBus` (`application/events.py`), `SaveGame` JSON + `level_unlock`, CI `--cov-fail-under=80`. |
| Phase 3 | 100 % | `EntityGrid`, `ObjectPool`, composants `Movement` / `Reaction`, `Level` façade (320 lignes), `RollbackSystem` local, JSON data-driven (`data/gameplay/*.json` + `src/data/*.py`). |
| Phase 5 | 100 % mécanique | Multi-hitbox, hitbox animée per-frame, projectiles poolés, juggle / hit-stun avancé - testés, typés, câblés. |
| RF-4 / RF-5 / RF-6 | 100 % | `ruff check --select C901` propre ; `resolve_collisions`, `HitResolver.resolve`, `_collect_candidates`, `SpawnSystem.process`, `_handle_attack_input` décomposés (`test_rf6_branches.py`). |

---

## 2. Tâches restantes

### R-1 - `Display.FPS` 180 vers 60/120 + VSYNC (reliquat Phase 1) — **CLOS 2026-09-25**

| Champ | Contenu |
|---|---|
| Fichiers | `src/core/settings.py:14-17` |
| Constat | Le commentaire annonce 120 FPS mais `FPS = 180`. La simulation est à 60 Hz : 2 frames sur 3 redessinent un état identique. `convert_alpha` déjà traité via `AssetLibrary`. |
| À faire | Passer `FPS` à 60 ou 120 ; activer `SDL_VSYNC` / vsync au `set_mode` si applicable ; mesurer le FPS réel avant/après. |
| Réception | Constante alignée sur le commentaire, aucun test cassé. |
| Effort / Priorité | Moins de 1 h / Basse. |

---
### R-2 - Phase 4 cinématique et narrative : 0/4 (faire ou déclarer hors-scope)

| Champ | Contenu |
|---|---|
| Constat | Aucun symbole trouvé (`CinematicScene`, `Timeline`, `DialogueRenderer`, `AudioBus`). Dépendances déjà livrées (SceneManager + EventBus). |
| Réception | Soit les 4 chantiers livrés avec tests headless, soit décision `hors-scope` écrite ici. Ne pas laisser en suspens. |
| Effort / Priorité | 1 à 2 sem. / À arbitrer (feature, pas de dette). |

| # | Chantier | Livrable attendu |
|---|---|---|
| R-2.1 | `CinematicScene` (`application/scenes/cinematic_scene.py`) | Séquence scriptée (caméra, spawns, fades) via `Renderer` et `Camera`, input = skip, enchaînée par `SceneManager`. |
| R-2.2 | Timeline data-driven | Script JSON horodaté (`wait`, `camera_to`, `spawn`, `dialog`, `fade`, `play_music`, `goto_scene`), tické en fixed timestep. |
| R-2.3 | `DialogueRenderer` | Boîte de dialogue via `PanelRenderer` (machine à écrire optionnelle). |
| R-2.4 | `AudioBus` minimal | Musique + SFX `pygame.mixer`, déclenchés par `EventBus` (`LevelStarted`, `PlayerDied`, `LevelCompleted`) et la timeline. |

- **Réception :** soit les 4 livrés avec tests headless, soit décision écrite
  `hors-scope` dans ce fichier. Ne pas laisser en suspens.
- **Effort :** 1 à 2 sem. **Priorité :** à arbitrer (feature, pas de dette).

---

### R-3 - RF-1 : finir les contrats combat explicites (70 % vers 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `src/combat/hit_resolver.py:80-86,151-157`, `src/combat/combatant_protocol.py:56-130` |
| Constat | `AttackerPort`, `CombatPort` et `Combatant` existent (`on_surface`, `otg_timer`, `set_juggle`, `record_hit_landed`, `test_combat_contracts.py`). Restent 3 blocs dynamiques : `dash` / `state_machine` / `current_state_name == "dash"` avec `charges` (`:80-86`), état `DIZZY_STATE` (`:151-153`), `is_invincible` (`:157`), plus le contrat `AttackComboPort` à vérifier pour les projectiles (`:76`). Note : `grep getattr|hasattr src` donne 234 occurrences dont beaucoup légitimes (parsing TMX, hazards) - le périmètre R-3 couvre uniquement `hit_resolver.py`. |
| À faire | Étendre `AttackerPort` (vue `is_dashing` / `dash_charges` en lecture seule) et `Combatant` (`is_invincible`, `current_state_name` ou vue `DizzyPort`) ; remplacer par des accès typés ; migrer les doubles (`tests/unit/helpers.py`, stubs) au lieu d'ajouter des fallbacks ; documenter les capacités vraiment optionnelles. |
| Tests | `test_damage_resolution.py`, `test_juggle.py`, `test_knockback_feel.py`, `test_projectile_system.py`, `test_combat_contracts.py` : combo 1x, sol/air, OTG allow/block, dash-refresh, dizzy, invincibilité. |
| Réception | Zéro `getattr` / `hasattr` dans `hit_resolver.py`, contrats vérifiés par `mypy` (test runtime seul insuffisant). |
| Effort / Priorité | 0,5 à 1 j / Haute. |

---
### R-4 - RF-2 : constructeur GameplayLoop optionnel (80 % vers 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `src/core/level/systems/gameplay_loop.py:58-72,137-149` |
| Constat | `update()` valide tout le wiring via `_require` avant toute mutation ; ordre spawn vers tick preserve ; `combat_only()` comme fixture explicite. Reste : 12 systemes a `None` par defaut au constructeur, donc un assemblage invalide n'echoue qu'a `update()`, pas a la construction. |
| A faire | Au choix, a documenter : rendre obligatoires (nommes) les etapes d'une boucle complete en gardant `combat_only()` comme seule construction partielle, puis adapter `Level` et les tests `GameplayLoop()` nu ; ou acter la validation a l'entree d'`update` comme suffisante et clore avec justification ecrite. |
| Tests | `test_gameplay_loop.py`, `test_level_orchestration.py` : cablage invalide = `RuntimeError` avant mutation, ordre inchange. |
| Effort / Priorite | 0,5 j / Moyenne. |

---

### R-5 - RF-3 : table de propriete des reactions (90 % vers 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `src/entities/components/reaction.py`, `src/entities/entity.py`, `src/states/reaction_states.py` |
| Constat | `ReactionComponent` extrait, zero `hasattr`, `reset_hurt_state()` utilise (`:240,285`), `test_reaction_ownership.py` present. Reste la table proprietaire / ecrivains / reset / snapshot par donnee : velocite-contacts, sante-protections, stagger, juggle/OTG, etats combat et reaction. |
| A faire | Ecrire la table en docstring de module, sans deplacer juggle/OTG sauf reset et restauration coherents ; separer tout correctif fonctionnel du deplacement structurel. |
| Tests | `test_reaction_states.py`, `test_reaction_friction.py`, `test_reset_position.py`, `test_rollback_snapshots.py`, `test_rollback_e2e.py` ; blocage, super-armure, lancement et stagger preserves. |
| Effort / Priorite | 0,5 j / Moyenne. |

---
### R-6 - RF-7 : contrat rollback et type ignore restants (90 % vers 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `src/core/rollback/rollback.py:68-76`, `src/core/level/systems/spawn_system.py:176`, `src/application/events.py:65,73`, `src/data/attacks.py:62` |
| Constat | `record(level: SnapshotCapable)` type. Restent : (1) `rollback_to(level: Level, ...)` (`:76`) prend le `Level` concret alors que `record` prend la capacite minimale - qualifier cette asymetrie ; (2) 4 `type: ignore[arg-type]` : `spawn_system.py:176` (`player_reference`), `events.py:65,73` (genericite `EventT`), `attacks.py:62` (`KnockbackConfig`). |
| A faire | Typer ou justifier chaque `ignore` un par un, sans dependance inversee artificielle ; documenter les dependances intentionnelles. |
| Tests | `test_rollback_system.py` et headless rollback ; demarrage sans rupture d'import. |
| Effort / Priorite | 0,5 j / Moyenne. |

---

### R-7 - RF-8 : typage progressif restant (95 % vers 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `pyproject.toml:48-57`, `.github/workflows/build.yml:32-35` |
| Constat | CI deja bloquante (`ruff check`, `format --check`, `mypy src`, `pytest --cov-fail-under=80`). Reste la dette listee en `pyproject.toml:44-45` : overrides `disallow_untyped_defs = false` pour `src.core.level.*`, `src.core.rendering.*`, `src.core.sprites`, `src.core.hazards`, `src.ui.*`, `src.physics.*` (`combat`, `entities`, `states` deja stricts). |
| A faire | Migrer module par module, reduire les overrides en gardant ceux des modules non migres ; mesurer instructions et branches separement ; garder C901 deja propre comme garde-fou ; aligner le README. |
| Effort / Priorite | Continu / Moyenne-basse. |

---
### R-8 - Residuels Phase 5 : contenu et docstring (mecanique 100 %)

| Champ | Contenu |
|---|---|
| Fichiers | `src/core/object_pool.py:11`, `data/gameplay/attacks.json`, `src/core/settings.py:105-107` |
| A faire | (1) Docstring `object_pool.py:11` dit encore que le pool est inutilise alors que `ProjectileSystem` le consomme - reformuler (vrai uniquement pour les particules). (2) Contenu `attacks.json` : `extra_hitboxes: []` partout sauf 1 entree, `hitbox_keyframes` vides (legacy statique), `juggle_gravity_mult` (`1.0`) et `otg_allowed` (`False`) jamais remplis - game design a faire. (3) Equilibrage `Combat` : `HITSTUN_DAMAGE_FACTOR = 0.004`, `JUGGLE_GRAVITY_TIME = 0.45`, `OTG_INVULN_DURATION = 0.5` - non regles en jeu, attendu. |
| Reception | Docstring a jour, 1 passe d'equilibrage consignee ou explicitement reportee. |
| Effort / Priorite | 0,5 j et playtests / Basse. |

---

### R-9 - Projectiles : extensions hors-scope initial (a decider)

| Champ | Contenu |
|---|---|
| Fichiers | `src/entities/projectile.py:118-126` (`save_state` minimal, pas encore de rollback), `src/core/level/systems/projectile_system.py` |
| Constat | Pas de `projectiles.json` data-driven (config en code, ex. `FIREBOLT_CONFIG`), pas de gravite projectiles, pas de collision projectile contre projectile (assume dans l'audit Phase 5). |
| A faire | Si mages, archers et pieges se multiplient : `src/data/projectiles.py` et JSON, gravite optionnelle par config, decision ecrite sur projectile contre projectile et snapshot rollback. |
| Effort / Priorite | 1 a 3 j si active / A decider au besoin feature. |

---
## 3. Recapitulatif

| ID | Tache | Effort | Priorite |
|---|---|---|---|
| R-1 | FPS 180 vers 60/120 et VSYNC | Moins de 1 h | Basse |
| R-2 | Phase 4 : Cinematic, Timeline, Dialogue, Audio (ou hors-scope ecrit) | 1 a 2 sem. | A arbitrer |
| R-3 | RF-1 : 3 blocs `getattr` dans `hit_resolver.py` et contrat combo | 0,5 a 1 j | Haute |
| R-4 | RF-2 : `GameplayLoop` obligatoire ou cloture justifiee | 0,5 j | Moyenne |
| R-5 | RF-3 : table de propriete des reactions | 0,5 j | Moyenne |
| R-6 | RF-7 : `rollback_to` et 4 `type: ignore` | 0,5 j | Moyenne |
| R-7 | RF-8 : overrides mypy 6 modules | Continu | Moyenne-basse |
| R-8 | Docstring pool, contenu `attacks.json`, equilibrage 3 constantes | 0,5 j | Basse |
| R-9 | Projectiles data-driven, gravite, snapshot (au besoin) | 1 a 3 j | A decider |

Ordre suggere : R-3, puis R-4 / R-5 / R-6 (un lot a la fois, diff revu),
puis R-1 / R-8 (quick wins), puis R-7 (fond), puis arbitrage R-2 / R-9.

---

## 4. Regles (toujours valables)

1. Baseline avant chaque lot : `git status --short`, suite complete, ruff, format check, mypy (voir section 5).
2. Preserver l'ordre des evenements, collisions, mises a jour et resultats simulation / rollback. Pas de changement des regles du jeu.
3. Pas de nouveau framework, ECS, service-locator ou dependance.
4. Pas de nouveau `Any`, `cast` ou `type: ignore` pour contourner un contrat.
5. Goldens : toute recapture exige un journal (rev, raison physique, procedure) ; interdit pour masquer une regression.
6. Apres chaque lot : tests cibles, suite complete, ruff, format, mypy et revue du diff ; consigner date, rev, fichiers, decisions et resultats.

---

## 5. Commandes de validation

```bash
git status --short
git diff --stat
git diff --check
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest tests
uv run pytest tests --cov=src --cov-report=term-missing
uv run pytest tests --cov=src --cov-branch --cov-report=term-missing
uv run ruff check src --select C901
```

---

## 6. Reception globale

- [ ] R-1 : FPS aligne sur le commentaire, mesure consignee.
- [ ] R-2 : Phase 4 livree OU decision hors-scope ecrite ici.
- [ ] R-3 : zero `getattr` / `hasattr` dans `hit_resolver.py`, doubles migres.
- [ ] R-4 : constructeur obligatoire OU cloture justifiee, ordre preserve.
- [ ] R-5 : table de propriete ecrite, etats preserves.
- [ ] R-6 : `rollback_to` qualifie, 4 ignores traites un par un.
- [x] R-7 : overrides supprimes (aucun `[[tool.mypy.overrides]]` restant) et `disallow_incomplete_defs` passe en global, 2026-09-25.
- [ ] R-8 : docstring pool a jour, equilibrage consigne ou reporte.
- [ ] R-9 : decision ecrite (faire maintenant ou au besoin feature).
- [x] Suite verte (`1092 passed` au 2026-09-25), ruff, format et mypy bloquants, aucun test desactive pour masquer une regression.
