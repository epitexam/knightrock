# ADR 0001 — Migration modulaire par implémentation parallèle

**Statut :** accepté — 2026-11-26  
**Branche :** `refactor/parallel-modularisation`

## Contexte

Le dépôt contient 214 modules, 47 230 lignes, 3864 tests, trois digests de
simulation, 675 issues de coups et un invariant à 440 champs. Les paquets
 actuels forment un graphe sans cycle d'import à l'exécution, mais les
frontières sont implicites : `core` est un hub concret (168 imports reçus,
75 émis), `data` dépend de `entities`, 55 modules lisent `core.settings`, et
importer `core.level.level` charge 142 modules sur 214.

Une refonte « déplacer puis vérifier » a été étudiée et écartée : elle rend la
preuve de non-régression dépendante de la discipline de chaque commit et rend
le retour arrière difficile. Le projet a déjà payé ce prix lors de la migration
ECS (plusieurs semaines, ~64 fichiers de test réécrits, aucun gain de
performance).

## Décision

Migrer vers `shared / simulation / presentation / platform / application` **par
implémentation parallèle**, avec les règles suivantes :

1. Le code existant reste intact et jouable ; la bascule `KNIGHTROCK_ARCH`
   reste sur `legacy` par défaut jusqu'à la phase de coupure.
2. Chaque frontière suit *expand → migrate → contract* : ajouter le nouveau
   chemin, migrer les appelants par groupes, supprimer l'ancien seulement quand
   le nombre d'importateurs est nul.
3. Aucune tranche n'est migrée avant d'avoir prouvé la parité : une suite de
   tests black-box exécute le même scénario dans l'ancienne et la nouvelle
   implémentation, dans deux processus séparés, et compare un digest canonique.
4. La suite de parité est elle-même validée par injection de fautes : douze
   mutations volontaires de la simulation doivent toutes être détectées avant
   le premier déplacement.
5. Les étapes destructives (suppression des anciens chemins, bascule du défaut)
   sont isolées en fin de projet et réversibles par `git revert`.

## Alternatives écartées

| Alternative | Pour | Contre |
|---|---|---|
| Big bang (tout réécrire d'un coup) | simple à décrire | aucune preuve de parité avant coupure, retour arrière impossible |
| Refonte in-place avec shims | peu de fichiers dupliqués | la régression est découverte après le déplacement, pas avant |
| Ne rien faire | coût nul | les frontières restent implicites et non vérifiées |

## Conséquences

- Un harnais `tests/parity/` temporaire est ajouté et supprimé en fin de
  migration ; il ne fait pas partie de la suite permanente.
- Le nombre de fichiers augmente temporairement (ancien et nouveau chemins
  coexistent). C'est une architecture de transition assumée.
- La CI gagne une étape `lint-imports` ; les contrats commencent avec les
  interdits déjà vrais aujourd'hui et sont resserrés à chaque tranche.
- Les tests visuels de parité ne tournent que si `assets/` est présent ; les
  scénarios de simulation tournent toujours, y compris en CI sans assets.

## Confiance et déclencheurs de réévaluation

Confiance : **élevée** sur la préservation du comportement (filet de parité +
goldens existants), **moyenne** sur le calendrier (5 à 6 semaines estimées).

Réévaluer si : un digest diffère sans cause unique identifiée ; une faute
injectée survit ; l'écart de tick dépasse 3 % ; un import non prévu apparaît
dans le périmètre d'une tranche.
