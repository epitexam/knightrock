# Plan B1 — Contrat en lecture seule, transitions synchrones

## Objectif
`ReactionComponent` possède un statut explicite (`ReactionStatus`) lu par l'overlay et la physique, **sans inverser le contrôle** — les `change_state` restent immédiats et synchrones aux mêmes sites.

## Design
- `ReactionComponent` possède `status: ReactionStatus {kind, magnitude, direction}` + âge render-only
- Règle de propriété : **Reaction possède la cause, SM possède la catégorie, overlay lit la cause**
- **Aucun instant de transition ne bouge** : les `change_state` restent aux mêmes sites, même tick, même ordre → **zéro retard d'un tick**

## Nouvelles constantes partagées
```python
# reaction_states.py
KNOCKBACK_STATE = "knockback"
STAGGER_STATE = "stagger"
```

## Sites d'armement (4)
1. `apply_knockback` → `kind = "push"`
2. `handle_heavy_knockback` → `kind = "launch"`
3. `stagger` → `kind = "stagger"`
4. Nouveau `note_blocked_push()` → `kind = "blocked"` (appelé par `Player._apply_block_damage_reaction`)

## Migrations des lecteurs
- `world_ui._draw_velocity` : rouge si `kind in ("push","launch","blocked")` et frais
- `collisions._is_knocked` : rebond mur sur `kind == "launch"` (optionnel, risque sans bénéfice visible)

## Âge render-only
- `Entity.hit_push_age` décrémenté dans `update`, exclu de `EntitySnapshot`
- Arme aux 4 sites ci-dessus + `Player._apply_block_damage_reaction`
- Durée proposée : `Combat.HIT_PUSH_MARK_S = 0.4`

## Tests
- Asserts `changes[-1] == "knockback"` **inchangés** (preuve zéro-délai)
- Nouveaux tests : `kind`/magnitude après chaque opération, round-trip rollback sans le champ

## Portes
- ruff + format + mypy + C901 verts
- Suite complète sur baseline (616 passed / 5 échecs connus)
- Goldens verts (attendu : aucun changement sim)

## Différences avec Plan A
| Aspect | Plan A | Plan B1 |
|--------|--------|---------|
| Structure | 1 champ timer | `ReactionStatus` typé + âge |
| Lecture overlay | `getattr(hit_push_timer)` | `reaction_status.kind` |
| Rebond mur | intact (lit état) | migré vers contrat (optionnel) |
| Vocabulaire | littéraux `"knockback"` | constantes partagées |

## Statut
📝 **Planifié — non exécuté** (Plan A choisi à la place)

## Risques
- Doubles de tests à mettre à jour (`ReactionOwner` gagne 2 membres)
- Fraîcheur post-rollback (artefact comme `flash_timer`)
- Exhaustivité des 4 sites à vérifier