# Plan A — Fix Minimal (Implémenté)

## Objectif
Corriger la couleur de la flèche de knockback dans l'overlay debug sans toucher au système de knockback lui-même.

## Design
- Un champ **render-only** `hit_push_timer` sur `Entity` (même statut que `flash_timer`)
- Arme aux **2 seuls sites** qui appliquent un push :
  - `ReactionComponent.apply_knockback` (couvre joueurs, ennemis, dummies, projectiles, hazards)
  - `Player._apply_block_damage_reaction` (blocage joueur)
- Lu par l'overlay via `getattr` (zéro changement de protocole consommateur)
- Test `== "knockback"` conservé en filet

## Constantes
- `HitPushMark.DURATION = 0.4` dans `Combat` (settings.py)

## Fichiers modifiés
1. `src/core/settings.py` — `HitPushMark` class + `DURATION = 0.4`
2. `src/entities/entity.py` — `hit_push_timer` field + decay dans `update()` + exclusion snapshots
3. `src/entities/components/reaction.py` — armement dans `apply_knockback` + `ReactionOwner.hit_push_timer`
4. `src/entities/player.py` — armement dans `_apply_block_damage_reaction`
5. `src/ui/world_ui.py` — lecture `hit_push_timer` dans `_draw_velocity`
6. Tests: `test_hit_push_mark.py`, `test_reaction_ownership.py`, `test_debug_overlay.py`

## Ce qui N'EST PAS touché
- `collisions.py` (rebond mur lit état — sémantique correcte)
- `state_machine.py`, `hit_resolver.py`, pipeline, snapshots
- Seuil heavy 400, frictions, formules
- Goldens inchangés

## Statut
✅ **Implémenté** (branche `fix/knockback-debug-arrow`, 3 commits)

## Commit 4 conditionnel (en attente d'essai visuel)
- Si durée 0.4s convient → retirer filet `"knockback"`
- Sinon → ajuster `HIT_PUSH_MARK_S`