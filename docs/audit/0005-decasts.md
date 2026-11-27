# ADR 0005 — Dés-castage des coutures typées

**Statut :** accepté — 2026-11-27  
**Branche :** `refactor/typed-core`

## Contexte

L'ADR 0004 a réduit `Any` de 503 à 109 occurrences, mais le nombre de `cast`
est passé de 18 à 103. Un cast n'est pas une vérification : mypy croit
l'affirmation sur parole. Deux hotspots concentraient des casts répétés
mécaniquement et sans garantie documentée.

## Décision

Trois changements de signature, aucun comportement modifié :

1. Les générateurs FX acceptent `Group[FxParticle]` au lieu d'un groupe
   pygame non paramétré : l'adaptateur passe son groupe directement, sans cast.
2. `draw_debug_panels` prend des paramètres explicites et typés
   (`fps`, compteurs, `frame_time`, `cache_size`, `scene_host`, `debug_stats`)
   dans le protocole, le null object, le renderer et l'interface : les 8 casts
   du sac de compteurs disparaissent, et la signature documente elle-même ce
   qu'une frame fournit.
3. Les `enter()` d'état utilisent `number_arg` / `int_arg`, deux validateurs
   locaux du module `state_machine`, à la place de casts sur `kwargs`.

Règle de convention adoptée : un cast n'est autorisé qu'au dernier mètre,
près de la garantie runtime, avec une raison explicite. Les 75 casts restants
sont surtout des conversions de ports (`object` → type concret dans
l'adaptateur) et des valeurs de defaults déjà validées.

## Résultat

| Mesure | Avant | Après |
|---|---:|---:|
| `cast` dans `src` | 103 | **75** |
| `cast` dans `presentation/fx/adapter.py` | 26 | **17** |
| `cast` dans `presentation/ui/ui_manager.py` | 12 | **4** |
| `type: ignore` | 21 | 21 |

Tous les gates restent verts : 3869 tests, suite `DEBUG=1`, couverture
94,17 %, mypy strict, ruff, quatre contrats import-linter.
