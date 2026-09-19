# Index des Plans de Refactoring — Knockback Debug Arrow

## Plans disponibles

| Plan | Fichier | Statut | Description |
|------|---------|--------|-------------|
| **Plan A** | [`plan_a_minimal_fix.md`](plan_a_minimal_fix.md) | ✅ **Implémenté** | Fix minimal : 1 champ render-only, 2 sites d'armement, 1 lecture overlay |
| **Plan A — Résumé** | [`plan_a_implemented_summary.md`](plan_a_implemented_summary.md) | ✅ **Implémenté** | Détails complets de l'implémentation (branche `fix/knockback-debug-arrow`) |
| **Plan B1** | [`plan_b1_readonly_contract.md`](plan_b1_readonly_contract.md) | 📝 Planifié | Contrat en lecture seule, transitions synchrones, `ReactionStatus` typé |
| **Plan B2** | [`plan_b2_inverted_control.md`](plan_b2_inverted_control.md) | 📝 Planifié | Inversion complète : SM suit `Reaction` via interrupts |
| **Plan B1+B2 Repensé** | [`plan_b1b2_rethought.md`](plan_b1b2_rethought.md) | 📝 Planifié | Cohérence sans retard d'un tick — transitions synchrones + autorité unique |

## Historique des décisions

1. **Demande initiale** : "la flèche de knockback n'est pas de la bonne couleur"
2. **Diagnostic** : L'overlay regarde le nom d'état (`"knockback"`) au lieu de la cause (vélocité due à un coup). Les coups légers (état `"hurt"`), le blocage (état `"block"`), les dummies (pas de SM) → flèche jaune alors que c'est bien du knockback.
3. **Plan A choisi** : Fix minimal additif (1 champ render-only, 3 commits, zéro risque gameplay). Branche `fix/knockback-debug-arrow`.
4. **Plan B1/B2 proposés** : Vers une architecture plus propre (autorité unique `Reaction`), mais plus risqués (retard d'un tick pour B2, complexité pour B1).
5. **Décision finale** : Plan A implémenté. Plan B2 écarté car "repenser le système de knockback" jugé disproportionné pour une couleur debug. Plan B1 écarté car laisse deux autorités en concurrence.

## Branche active
- `fix/knockback-debug-arrow` (3 commits, commit 4 conditionnel en attente d'essai visuel)

## Prochaine action
**Essai visuel requis** (mode debug) pour valider la durée 0.4s :
- Coup léger → rouge
- Blocage → rouge
- Launcher ≥400 → rouge
- Dummy → rouge
- Slide après 0.4s → jaune

Puis commit 4 : soit retrait filet `"knockback"`, soit ajustement `HIT_PUSH_MARK_S`.

## Fichiers de référence
- Branche de travail : `fix/knockback-debug-arrow`
- Baseline : `feature/core-rework` @ `673366f`
- Suite de tests : 624 passed / 5 failed (5 échecs baseline connus inchangés)