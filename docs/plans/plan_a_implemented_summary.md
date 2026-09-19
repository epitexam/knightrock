# Résumé — Plan A Implémenté (Branche `fix/knockback-debug-arrow`)

## Contexte
- Branche : `fix/knockback-debug-arrow` (basée sur `feature/core-rework` @ `673366f`)
- Commits : 3 commits + commit 4 conditionnel en attente d'essai visuel

## Commits

### 1. `16891a7` — `feat(debug): track applied hit push on Entity (render-only)`
- `src/core/settings.py` : `HitPushMark` class + `DURATION = 0.4`
- `src/entities/entity.py` : `hit_push_timer` field + decay dans `update()` + exclusion snapshots
- `tests/unit/test_hit_push_mark.py` : décroissance, exclusion rollback

### 2. `89d2633` — `feat(debug): arm push mark at knockback application sites`
- `src/entities/components/reaction.py` : `apply_knockback` arme `hit_push_timer` + `ReactionOwner.hit_push_timer`
- `src/entities/player.py` : `_apply_block_damage_reaction` arme la marque
- `tests/unit/test_reaction_ownership.py` : asserts d'armement + double mis à jour

### 3. `fa23d37` — `feat(debug): knockback arrow follows applied push, not state name`
- `src/ui/world_ui.py` : `_draw_velocity` lit `hit_push_timer` (rouge si frais), filet `"knockback"` conservé
- `tests/unit/test_debug_overlay.py` : 3 nouveaux tests (hurt, sans-état, expiré→jaune)

## Validation
| Gate | Résultat |
|------|----------|
| ruff check | ✅ |
| ruff format --check | ✅ |
| mypy src | ✅ |
| C901 | ✅ (0 erreurs) |
| Suite complète | 624 passed / 5 failed (baseline inchangée) |
| Goldens | ✅ verts (aucune recapture) |

## Fichiers explicites NON touchés
- `collisions.py` (rebond mur lit état — sémantique correcte)
- `state_machine.py`, `hit_resolver.py`, pipeline, snapshots
- Seuil heavy 400, frictions, formules
- Aucun golden recapturé, aucun test existant modifié (`test_knockback_vector_is_red` passe tel quel)

## Commit 4 conditionnel (en attente)
**Essai visuel demandé** en mode debug :
1. Coup léger sur ennemi → flèche rouge ?
2. Blocage joueur poussé → flèche rouge ?
3. Launcher lourd (≥400) → flèche rouge (filet `"knockback"` aussi) ?
4. Dummy jonglé → flèche rouge ?
5. Slide résiduel après 0,4 s → repasse jaune ?

**Décision** :
- Si durée 0.4s convient → commit `refactor(debug): drop legacy knockback-state color fallback` (retire filet `"knockback"`, ajuste test)
- Sinon → `fix(debug): tune HIT_PUSH_MARK_S` (ajustement + justification)

## Fichiers modifiés au total
```
src/core/settings.py              |  6 ++++
src/entities/entity.py            |  8 +++++++-
src/entities/components/reaction.py| 12 ++++++-
src/entities/player.py            |  5 +++
src/ui/world_ui.py                |  2 ++
tests/unit/test_hit_push_mark.py  | 18 ++++++++++
tests/unit/test_reaction_ownership.py| 12 ++++++
tests/unit/test_debug_overlay.py  | 27 ++++++++++++++++++++++
```

## Risques assumés et documentés
1. **Migration d'un double de test** (`_narrow_owner`) — mécanique, tranché par mypy
2. **Fraîcheur post-rollback** : marque exclue des snapshots → rouge fugace possible après rollback (même classe que `flash_timer`, précédent accepté)
3. **Durée 0.4s** : jugement de confort visuel, à valider à l'œil ; filet `"knockback"` borne le pire cas

## Ce qui N'EST PAS fait (par design)
- ❌ Pas d'enum `ReactionKind`, pas de `ReactionStatus` typé
- ❌ Pas de migration `collisions.py` (le rebond lit un état, sémantique correcte)
- ❌ Pas d'autorité unique `Reaction` (pas B1/B2)
- ❌ Pas de recapture golden
- ❌ Pas de test désactivé

## Branche et historique
```
fix/knockback-debug-arrow
├── fa23d37 feat(debug): knockback arrow follows applied push, not state name
├── 89d2633 feat(debug): arm push mark at knockback application sites
├── 16891a7 feat(debug): track applied hit push on Entity (render-only)
└── 673366f Merge branch 'chore/refactoring-handoff' into feature/core-rework
```