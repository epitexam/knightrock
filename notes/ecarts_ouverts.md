# Écarts hitbox — état de conformité 2026-09-26

> Synthèse courante des écarts O1–O10. La source historique détaillée reste `notes/hitbox_amelioration.md`.
> Cette version décrit uniquement le code présent sur `master` au `40ca5a9`.
> O1–O9 sont des écarts hitbox ; O10 est un écart de recette, ajouté le 2026-09-26.

## Récapitulatif

| ID | Sujet | État | Preuve principale |
|---|---|---|---|
| O1 | `block_mask` | Clos | `HitProperties`, `HitResolver`, `Guard.take_hit`, `test_height_block.py` |
| O2 | Tags de coup et zones invulnérables | Clos | `frame_data.py`, `contact_system.py`, `test_multi_hurtbox.py` |
| O3 | `hit_level` light/med/heavy | Clos | `frame_data.py`, `player_controllers.py`, `test_height_block.py` |
| O4 | Benchmark de contact | Clos | `tests/benchmarks/contact_benchmark.py`, contacts 1/16/64 |
| O5 | Export JSON F9 | Clos | `src/application/attack_authoring.py`, `test_attack_authoring.py` |
| O6 | Perf et déterminisme | Clos | buffers de broadphase, `geometry_checksum`, tests associés |
| O7 | Sweep multi-producteurs | Clos | `projectile_system.py`, `hazard_damage.py`, `contact_system.py` ; contact reste discret |
| O8 | Offset des keyframes | Clos | `_validate_keyframes`, `test_attack_validation.py` |
| O9 | Indices debug | Clos par décision de forme | `world_ui.py`, points `●/○`, `test_debug_overlay.py` |
| O10 | Recette `DEBUG=1` | **Ouvert** | `test_frame_presentation.py`, `renderer.py:252-259`, `level.py:359-375` |

**Limites hors périmètre :** grab/throw/command-grab, extension du sweep aux hazards statiques ou au contact damage, réseau et rééquilibrage global.

## Preuves et décisions

### O1 — `block_mask`

`HitProperties.block_mask` accepte `any`, `stand` et `crouch`. La valeur est sérialisée, transmise par `HitResolver`, puis combinée avec `height` dans `Player.receive_damage` et `Guard.take_hit`. La table de posture est dans `src/core/settings.py`.

**Tests :** `tests/unit/test_height_block.py`.

### O2 — Tags et zones invulnérables

`HitProperties.tags` est lu par les données d’attaque et transmis au matcher `_zone_vulnerable`. Une zone dont les tags correspondent est ignorée ; la zone suivante peut absorber le contact. Le E2E des jambes en vol est couvert par `test_airborne_legs_invulnerable_e2e`.

**Tests :** `tests/unit/test_multi_hurtbox.py`, `tests/unit/test_contact_unified.py`.

### O3 — `hit_level`

`HitProperties.hit_level` accepte `light`, `med` et `heavy`. `heavy` applique un coût de posture supérieur selon `Guard.POSTURE_COST_MULT`.

**Tests :** `tests/unit/test_height_block.py`.

### O4 — Benchmark de contact

Le harness est exécutable directement :

```bash
uv run python tests/benchmarks/contact_benchmark.py --iterations 300 --repeats 5
```

Il remet les cibles à leur état initial avant chaque itération, mesure `ContactSystem.resolve` dans les modes grille et exhaustif et produit 1, 16 et 64 contacts pour les scénarios 1v1, 4v4 et 8v8. La commande module reste disponible :

```bash
PYTHONPATH=. uv run python -m tests.benchmarks.contact_benchmark
```

### O5 — Export F9

F9 exporte l’attaque sélectionnée vers un JSON relisible dans `KNIGHTROCK_EXPORT_DIR`, sans modifier `data/gameplay/attacks.json`. Le round-trip est couvert par `tests/unit/test_attack_authoring.py`.

### O6 — Perf et déterminisme

`ContactSystem` réutilise ses buffers de broadphase. `CombatSnapshot` contient un checksum géométrique quantifié ; la restauration le vérifie via `verify_geometry_checksum`.

**Tests :** `tests/unit/test_geometry_checksum.py`, `tests/unit/test_p5_integration.py`, `tests/unit/test_contact_unified.py`.

### O7 — Sweep multi-producteurs

Le sweep AABB bilatéral est actif pour la melee, les projectiles AABB et les hazards mobiles. Les hazards statiques restent discrets et le contact damage conserve sa collision discrete. Les projectiles utilisent aussi le swept pour la broadphase, la narrowphase et les collisions contre les murs ; les formes avancées conservent leur broadphase AABB swept et leur narrowphase de forme.

**Tests :** `tests/unit/test_contact_unified.py`, `tests/unit/test_projectile_system.py`, `tests/unit/test_hazard_damage.py`.

### O8 — Offset des keyframes

`attack_loading._validate_keyframes` vérifie l’ordre, le range et l’enveloppe 2× sprite pour les offsets de chaque keyframe primaire ou extra.

**Tests :** `tests/unit/test_attack_validation.py`.

### O9 — Indices debug

Les indices de boîte sont dessinés comme points vectoriels `●/○` en place dans la boîte, plutôt que comme libellés `bN`. L’overlay lit la transform unique de la caméra (le blend est dans `Camera.begin_frame`), donc une annotation ne peut plus se détacher du sprite qu’elle décrit, et le pin debug à `alpha = 1.0` a disparu. `F4` statics est **off par défaut** : un niveau porte ~970 tuiles de terrain, et le gate `statics` passe maintenant avant la construction de la référence, qui était le poste le plus lourd de la frame (2.8 ms).

**Tests :** `tests/unit/test_debug_overlay.py`, `tests/unit/test_frame_coherence.py`.

### O10 — `DEBUG=1` : la suite n’est pas verte

`DEBUG=1 uv run pytest -q` donne **1 failed, 1116 passed** au `40ca5a9` :

- `tests/unit/test_frame_presentation.py::test_level_draw_presents_the_health_bar_rects`
  exige que `Level.draw` renvoie un ensemble de rects partiels à présenter. Or le
  chemin debug fait toujours un refresh complet — `Renderer.draw` renvoie `None`
  dès que `debug_enabled` est vrai (`renderer.py:252-259`), et `Level.draw` aussi
  (`level.py:359-375`). Le test échoue donc sur `assert rects is not None`.
- Le même test échoue **isolé**, avec ou sans `DEBUG` : il hérite de l’écran
  320×240 du fixture de module et compte sur un test précédent
  (`test_a_resolution_change_drops_the_converted_art`) pour l’agrandir en 800×600.
  Sans cela, la caméra cull l’ennemi de test placé en (200, 200) et la passe de
  barres ne peint rien.

Ce n’est pas une régression : le test est né avec `40833b0` et la branche debug
renvoyait déjà `None` avant la session du 2026-09-25. C’est un contrat de test faux
(dans un cas) et une dépendance à l’ordre d’exécution (dans l’autre). Les audits
qui annonçaient une suite verte « avec et sans `DEBUG` » n’étaient plus exacts ;
`notes/audit_consolide.md` le suit sous **R-10**.

**Correction envisagée :** assumer que la présentation partielle n’a de sens
qu’hors debug (l’assertion saute sous `DEBUG=1`) et faire construire le niveau à
la taille d’écran voulue par le test plutôt que d’hériter de l’état global — le
test doit alors passer isolément. Aucun code de rendu n’est en cause.

## Recette de référence

- `pytest -q` : **1117 passed** ;
- `DEBUG=1 pytest -q` : **1 failed, 1116 passed** (O10) ;
- `ruff check .` : propre ;
- `mypy src` : propre, 142 fichiers (144 pour `mypy src main.py tools`) ;
- couverture : 89 % instructions, 86 % branches ;
- benchmark de contact : reproductible, contacts 1/16/64 ;
- tests UI : hermétiques avec `DEBUG=1` **sauf** le test de O10.

Dernière mise à jour : 2026-09-26, branche `master` au `40ca5a9`.
