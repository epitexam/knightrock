# Plan B1+B2 Repensé — Cohérence sans retard d'un tick

## Pourquoi B1+B2 au lieu de B1 seul ?
B1 laisse deux autorités en concurrence : `Reaction` pose un `kind` ("launch") **et** continue d'appeler `change_state("knockback")` par chaîne. Deux sources de vérité qui peuvent diverger. B2 établit une autorité unique.

## L'idée clé : garder les transitions synchrones, changer ce que lit l'affichage
Le retard d'un tick n'existait que si la state machine *suivait* `Reaction` via interrupts. On garde les `change_state` **immédiats et synchrones** (mêmes sites d'appel, même tick, même ordre → **zéro changement de timing prouvable**) et on fait porter la cohérence ailleurs.

## Design
1. **`ReactionComponent` possède un statut explicite** — `ReactionStatus {kind, magnitude, direction}` + âge **render-only** (décrémenté dans `Entity.update`, exclu d'`EntitySnapshot`). Écrit aux 4 sites exacts d'aujourd'hui.
2. **L'overlay lit le statut, plus jamais un nom d'état** : rouge si statut frais et `kind` avec vélocité, jaune sinon. Le couplage stringly-typé disparaît.
3. **On ne touche pas à ce qui marche** : `collisions._is_knocked` garde sa lecture d'état (le rebond mur dépend bien d'*être en lancement* — migrer ça serait du risque sans bénéfice visible) ; le chemin `hurt` par flag+interrupt reste tel quel ; seuil heavy 400, frictions, formules : inchangés.
4. **Vocabulaire centralisé à coût nul** : les `"knockback"`/`"stagger"` en dur dans `Reaction` deviennent des constantes partagées avec les enums `PlayerState`/`EnemyState` existantes.

## Pourquoi les deux autorités ne divergent plus
Règle de propriété documentée et testée :
- **`Reaction` possède la cause** (quel coup, quelle magnitude, quand)
- **La state machine possède la catégorie en cours** (hurt/block/launch…)
- Les deux sont écrites **aux mêmes sites, dans le même tick** → la divergence structurelle de B1 n'existe plus.

## Portes de validation (risque ≈ option A, cohérence ≈ B2)
- Les asserts existants `changes[-1] == "knockback"` passent **inchangés** — preuve directe d'aucun changement de timing.
- ruff + format + mypy + C901 verts ; suite complète sur la baseline ; **goldens mathématiquement intouchables** (aucun tick-order, timing, snapshot ou formule modifié).
- Nouveaux tests : `kind`/magnitude après chaque opération, round-trip rollback sans le champ.

## Différence avec Plan A
| Aspect | Plan A | Plan B1+B2 Repensé |
|--------|--------|-------------------|
| Structure | 1 champ timer | `ReactionStatus` typé (`kind`, magnitude, direction) + âge |
| Lecture overlay | `hit_push_timer > 0` | `reaction_status.kind in ("push","launch","blocked")` + âge |
| Rebond mur | intact (lit état) | intact (lit état) |
| Vocabulaire | littéraux `"knockback"` | constantes partagées + `ReactionKind` |
| Authority | 1 champ timer | `Reaction` possède la cause, SM la catégorie |

## Risques résiduels
- **Faible** : doubles de tests + typage structurel (pattern connu depuis RF-3)
- **Faible/cosmétique** : fraîcheur post-rollback (artefact comme `flash_timer`)
- **Négligeable** : cadavres (slide résiduel rouge 0.4s), hit-stop (âge gelé)
- **À vérifier** : exhaustivité des 4 sites d'armement

## Statut
✅ **Implémenté** — branche `feature/reaction-status` (basée sur `feature/core-rework` @ `673366f`) :
- `c3c0420` — `feat(reaction): typed ReactionStatus cause authority with render-only freshness (B1+B2)`
  (`settings.ReactionMark`, `ReactionKind`/`ReactionStatus`/`VELOCITY_KINDS` dans `reaction.py`, armement aux 4 sites, `KNOCKBACK_STATE`/`STAGGER_STATE` partagés, `Entity.reaction_age` + propriété `reaction_status`, `Player._apply_block_damage_reaction` → `note_blocked_push`)
- `9d4f4f3` — `feat(debug): velocity overlay reads ReactionStatus, never a state name`
  (`world_ui._is_reaction_push` lit le statut typé, filet `"knockback"` supprimé)
- commit 3 — `feat(debug): reaction cause flag in entity debug labels`
  (flag `RX <kind> <age>` / `RX~ <kind>` dans `_entity_lines` via `_reaction_flag`)
- commit 4 — `feat(debug): declutter entity labels with collision-aware placement`
  (labels dessinés en différé, triés joueur-d'abord puis haut→bas ; chaque label esquive vers le haut puis sous l'entité par pas de 28px, abandonné si aucun slot ; les panels ne se superposent plus jamais)

Portes : ruff + format + mypy verts ; **643 passed / 5 failed** (baseline 616/5 + 27 nouveaux tests) ; échecs connus (3 goldens + 2 enemy_jump) **bit-identiques** à la baseline — goldens intouchables.

## Note
C'est l'implémentation minimale qui donne une autorité unique à `Reaction` pour la *cause* sans payer le prix de l'inversion (le retard d'un tick), parce qu'on ne déplace aucun instant de transition.