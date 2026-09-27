# Écarts hitbox — état de conformité 2026-09-26

> Synthèse courante des écarts O1–O10. La source historique détaillée reste `notes/hitbox_amelioration.md`.
> Cette version décrit uniquement le code présent sur `feat/display-cadrage-system` au `c679234`.
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
| O10 | Recette `DEBUG=1` | Clos | Suppression de la présentation partielle ; `test_level_draw_paints_the_health_bars_over_the_world`, `test_camera.py` |

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

### O10 — `DEBUG=1` : la suite n’est pas verte — **Clos 2026-09-26**

Le 2026-09-25, `DEBUG=1 pytest -q` donnait 1 failed, 1116 passed :
`test_frame_presentation.py::test_level_draw_presents_the_health_bar_rects`.
Le chemin debug renvoyait `None` (présentation complète) et la branche non-debug
renvoyait des rects partiels, et le test exigeait les deux.

**La correction n’est pas une correction de test : la présentation partielle
n’existe plus.** La cible de rendu a une taille fixe, donc la frame terminée est
mise à l’échelle d’un bloc sur la fenêtre et il n’y a plus de chemin partiel à
emprunter. L’appareil de dirty rects a été supprimé avec le besoin qu’il
servait (voir `notes/audit_dimensions_fenetre.md` §3).

Le test lui-même a disparu, remplacé par
`test_level_draw_paints_the_health_bars_over_the_world`, qui vérifie ce qui
restait vérifiable : qu’une barre atteint les pixels. `add_overlay_rects` n’existe
plus non plus, et `test_camera.py` assert son absence.

Le second défaut du même test — hériter de la taille d’écran laissée par un
test précédent — a disparu avec lui : plus aucun test ne dépend de l’état
d’un autre.

Vérifié le 2026-09-26 sur `feat/display-cadrage-system` :
`pytest -q` → **1273 passed**, `DEBUG=1 pytest -q` → **1273 passed**.
C’est la première fois que les deux sont vertes.

**Ce que cet écart disait de la méthode, et pas seulement du test.** L’écart était
consigné depuis six jours avec une « correction envisagée » qui consistait à
faire sauter une assertion sous `DEBUG=1`. C’était traiter un symptôme. La
question utile était : *pourquoi existe-t-il deux chemins de présentation ?*
Réponse : parce que la fenêtre était la cible de rendu, donc qu’une présentation
partielle avait un sens. La question suivante était : *que devient la
présentation partielle quand la cible ne dépend plus de la fenêtre ?* Réponse :
rien. Un écart de recette est parfois le dernier témoin d’une architecture qui
n’a plus lieu d’être.

## Recette de référence

Recette au 2026-09-26, branche `feat/display-cadrage-system` :

- `pytest -q` : **1273 passed** ;
- `DEBUG=1 pytest -q` : **1273 passed** (O10 clos) ;
- `ruff check .` : propre ;
- `mypy src` : propre, 152 fichiers (154 pour `mypy src main.py tools`) ;
- couverture : 89 % instructions ;
- benchmark de contact : reproductible, contacts 1/16/64 ;
- tests UI : hermétiques avec `DEBUG=1`, sans exception.

Dernière mise à jour : 2026-09-26, branche `feat/display-cadrage-system`.
