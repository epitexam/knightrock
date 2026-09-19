# Plan B2 — Inversion complète : la SM suit `Reaction`

## Objectif
Autorité unique : `ReactionComponent` possède la réaction en cours, la state machine **suit** via interrupts, l'overlay et la physique **lisent** le même contrat.

## Architecture
```
ReactionComponent (source of truth)
    ├── pose ReactionStatus {kind, payload}
    ├── N'APPELLE PLUS change_state("knockback"/"stagger")
    └── expose via ReactionOwner.reaction_status

StateMachine (consommatrice)
    ├── interrupts: kind == "launch" → KNOCKBACK
    ├── interrupts: kind == "stagger" → STAGGER
    └── lit payload (direction, force, up_force) via entity._reaction

Overlay / Physique (consommatrices)
    ├── lit kind + magnitude + direction
    └── aucun string-matching
```

## Point porteur identifié : retard d'un tick
- Les interrupts sont évalués **en tête** de `StateMachine.update` (`state_machine.py:127-130`)
- `Entity.update` fait passer la SM **avant** le combat (`entity.py:801-802`)
- Un flag posé pendant la phase combat ne serait consommé qu'au tick suivant
- **Contraste** : `change_state` actuel est **immédiat** (même tick)

## Payload d'attente requis
- `KnockbackState.enter` lit `kwargs` (`direction`, `force`, `up_force`)
- Un interrupt appelle `change_state(target)` **sans kwargs**
- Solution : slot `Reaction._pending_launch_payload` lu par `KnockbackState.enter`

## Changements clés
1. `ReactionComponent` : plus de `change_state` impératif, pose `kind` + payload
2. `configure_player_state_machine` + `Enemy._setup_state_machine` :
   - interrupts `kind == "launch" → KNOCKBACK` (priorité à calibrer vs hurt-100/dash-80/block-60)
   - interrupts `kind == "stagger" → STAGGER`
3. `KnockbackState.enter` : lit payload via `entity._reaction._pending_launch_payload`
4. Migrer doubles : `SpyCombat`, `test_damage_resolution.py`, `test_reaction_ownership.py`, `test_reaction_states.py`, `test_reaction_friction.py` — asserts sur `kind`/payload
5. Re-caractériser : friction au sol, DI aérienne, `KNOCKBACK_MAX_DURATION` 2s, sortie d'état

## Phase B1 requise d'abord
- Contrat en lecture, migration des 2 lecteurs, comportement **strictement identique**
- Porte B1 : suite verte + goldens inchangés

## Phase B2 (inversion)
- Porte B2 : même qualité + goldens
- **Si un digest bouge** (probable : retard d'un tick) → recapture avec journal (règle 5 audit)

## Risques majeurs
| Risque | Impact | Mitigation |
|--------|--------|------------|
| Retard d'un tick à l'entrée knockback/stagger | Goldens bougent, feel 60Hz modifié | Caractériser avant/après, journal golden dédié |
| `NullStateMachine` (dummies) | Overlay lit contrat, OK | Aucun changement requis côté dummy |
| Migration `collisions.py` (rebond mur) | Lit état, sémantique correcte | Optionnel, garder état si risque |

## Fichiers touchés
- `reaction.py`, `entity.py`, `player.py`, `player_states.py`, `enemy_states.py`, `enemy.py`
- `reaction_states.py`, `state_machine.py` (vérification seulement)
- `world_ui.py`, `collisions.py` (optionnel)
- Tests : `test_debug_overlay.py`, `test_reaction_ownership.py`, `test_damage_resolution.py`, `test_reaction_states.py`, `test_reaction_friction.py`, `test_knockback_feel.py`
- `test_simulation_golden.py` (recapture + journal)

## Séquençage recommandé
1. **B1 d'abord** (étape validée : contrat en lecture, migration lecteurs, comportement identique)
2. **B2 ensuite** (inversion, suppression `change_state` impératifs)
3. Porte de validation entre les deux : suite verte + goldens inchangés après B1

## Statut
📝 **Planifié — non exécuté** (Plan A choisi à la place)

## Note importante
B1 seul serait le **pire choix** : deux autorités en concurrence (Reaction pose `kind` + appelle encore `change_state`). B2 est la seule version "complète" architecturalement.