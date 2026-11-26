# ADR 0004 — Typage du cœur et de la frontière JSON

**Statut :** accepté — 2026-11-26  
**Branche :** `refactor/typed-core`

## Contexte

L'ADR 0003 a supprimé tout `Any` du noyau partagé, mais 347 occurrences
textuelles restaient dans le dépôt, dont 258 annotations réelles : machines à
états, présentation, cœur de simulation et chargeurs JSON. mypy strict passait,
mais ces coutures étaient peu vérifiées.

## Décision

Quatre lots, un commit chacun, les mêmes gates qu'habitude :

1. **Machines à états et physique** : protocole `MachineState`, `**kwargs: object`,
   `EntityGrid` typé sur `Entity`.
2. **Présentation** : types concrets (`Player`, `Entity`, `Projectile`,
   `CombatComponent`), signature explicite des panneaux de debug partagée par le
   protocole, le null object et `UIManager`.
3. **Cœur de simulation** : snapshots, restauration, accesseurs ECS, effets et
   plateformes mobiles typés ; extraction de `_restore_entity` pour garder le
   gate de complexité.
4. **Frontière JSON** : alias récursif `JsonValue` dans
   `src/simulation/data/errors.py`, validateurs (`read_string`, `read_strings`,
   `read_numbers`, `read_optional_string`, `read_string_mapping`) et lecture
   versionnée des réglages via le même alias.

## Résultats

| Mesure | Avant | Après |
|---|---:|---:|
| Occurrences textuelles de `Any` | 503 | **109** |
| Annotations `Any` (AST) | 258 | **68** |
| `Any` dans `src.shared` | 0 | 0 |
| `Any` dans `src.platform` | 5 | **0** |
| `Any` dans `src.presentation` | 78 | **2** (docstrings) |
| `Any` dans `src.simulation` | 233 | **85** |
| `Any` dans `src.application` | 38 | **22** |

Les validateurs existants refusent toujours les mêmes fichiers avec les mêmes
messages : plusieurs tests d'erreur ont échoué pendant le lot 4 quand une
nouvelle règle de lecture changeait un message, et ils ont été corrigés en
préservant le comportement d'origine, pas en assouplissant le test.

Tous les gates restent verts : 3869 tests, suite `DEBUG=1`, couverture 94,17 %,
mypy strict, ruff, quatre contrats import-linter.

## Ce qui n'a pas été typé, et pourquoi

Les 68 annotations restantes se concentrent dans :

- les fonctions `*_to_dict` des writers JSON (`dict[str, Any]`) — des sorties
  hétérogènes déjà validées à l'écriture ;
- `DenseTable` — des colonnes volontairement hétérogènes (owners, Scalaires,
  handles) où un `object` obligerait à caster chaque lecteur ;
- quelques sacs dynamiques de scènes d'options et de contrôles ;
- des signatures de commandes de combat et de zones de dégâts.

Activer `disallow_any_explicit = true` exigerait de réécrire ces writers et ces
sacs sans gain de robustesse : ce sont des valeurs déjà validées en aval. Ce
chantier s'arrête donc ici ; le gain (503 → 109, soit -78 %) est obtenu sans
changer une seule règle de jeu.
