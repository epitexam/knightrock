# Écarts hitbox — état de conformité 2026-09-24

> Synthèse courante des écarts O1–O9. La source historique détaillée reste `notes/hitbox_amelioration.md`.
> Cette version décrit uniquement le code présent sur `audit-hitbox-partial-compliance`.

## Récapitulatif

| ID | Sujet | État | Preuve principale |
|---|---|---|---|
| O1 | `block_mask` | Clos | `HitProperties`, `HitResolver`, `Guard.take_hit`, `test_height_block.py` |
| O2 | Tags de coup et zones invulnérables | Clos | `frame_data.py`, `contact_system.py`, `test_multi_hurtbox.py` |
| O3 | `hit_level` light/med/heavy | Clos | `frame_data.py`, `player_controllers.py`, `test_height_block.py` |
| O4 | Benchmark de contact | Clos | `tests/benchmarks/contact_benchmark.py`, contacts 1/16/64 |
| O5 | Export JSON F9 | Clos | `src/application/attack_authoring.py`, `test_attack_authoring.py` |
| O6 | Perf et déterminisme | Clos | buffers de broadphase, `geometry_checksum`, tests associés |
| O7 | Sweep melee-only | Clos par décision produit | `projectile_system.py`, `hazard_damage.py`, `contact_damage.py` |
| O8 | Offset des keyframes | Clos | `_validate_keyframes`, `test_attack_validation.py` |
| O9 | Indices debug | Clos par décision de forme | `world_ui.py`, points `●/○`, `test_debug_overlay.py` |

**Limites hors périmètre :** grab/throw/command-grab, extension du sweep aux projectiles/hazards/contact, réseau et rééquilibrage global.

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

### O7 — Sweep melee-only

Le sweep bilatéral est volontairement limité au melee. Les projectiles, hazards et contact conservent une collision discrète et émettent un `swept` trivial. Toute extension nécessite une nouvelle décision produit.

**Tests :** `tests/unit/test_contact_unified.py`, `tests/unit/test_projectile_system.py`, `tests/unit/test_hazard_damage.py`.

### O8 — Offset des keyframes

`attack_loading._validate_keyframes` vérifie l’ordre, le range et l’enveloppe 2× sprite pour les offsets de chaque keyframe primaire ou extra.

**Tests :** `tests/unit/test_attack_validation.py`.

### O9 — Indices debug

Les indices de boîte sont dessinés comme points vectoriels `●/○` en place dans la boîte, plutôt que comme libellés `bN`.

**Tests :** `tests/unit/test_debug_overlay.py`.

## Recette de référence

- `pytest -q` : **906 passed** ;
- `ruff check .` : propre ;
- `mypy src` : propre, 128 fichiers ;
- benchmark de contact : reproductible, contacts 1/16/64 ;
- tests UI : hermétiques avec et sans `DEBUG=1`.

Dernière mise à jour : 2026-09-24, branche `audit-hitbox-partial-compliance`, aucun commit.
