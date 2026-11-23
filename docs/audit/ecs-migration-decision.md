# ADR — migration ECS forcée (décision utilisateur, 2026-11-23)

Le spike de falsification (`ecs-spike-2026-11.md`) a donné un **NO-GO** mesuré : l'étape projectiles coûte 0,002–0,038 ms, au plus 2,3 % du tick. L'utilisateur a **annulé ce NO-GO en connaissance de cause** et demandé la migration complète malgré l'absence de gain performance attendu.

## Ce que cela engage

- La migration est un choix architectural assumé, **pas** une optimisation. Aucun gain de frame n'est promis.
- Coût accepté : plusieurs semaines de travail, réécriture d'environ 64 fichiers de test, re-baseline explicite du test d'invariant à 440 champs, dérive possible des 3 digests et des 675 issues de coups.
- Aucun golden n'est recapturé sans preuve de cause unique : un seul changement à la fois, diff lu et expliqué, ancien digest reproduit par revert du changement.
- `NOT_SNAPSHOTTED` n'est jamais élargi pour masquer un champ oublié ; `requires_assets` n'est jamais désactivé.

## Baseline de départ

```text
HEAD = f3443cc9da1eab0fd01398baef6407b01a99ba80
attacks.json      da91b02c61f95d0d777ce25fe94dc5a1ab6e5e50df6adaeca3e7e14fcbc0879f
hit_outcomes.json e74f27740a19646787060eab72f0b01f7b84f2f7569a4a445b43789baac92a8d
PHYSICS  c84740a6cd47840a75bbc0eb206b1b8e5f75c82c216ed3b0aa00c6b1fba79d92
RIDE     d49f5b9bf1d6e36714d61e00ad4701531effeeac5ca8f3663f1f2f4969d44098
RESPAWN  3e37730c583750c0b95d7d1c785eaff271f81cd96a5c248c8125c9f6a867ec46
Tests collectés : 3784
```

## Approche retenue

Pas de framework ECS externe : des **tables de composants en stockage latéral** derrière la façade `Entity`, promues couche par couche (branch by abstraction), avec les groupes pygame conservés comme projections de rendu jusqu'à la dernière étape.

Ordre : identité/génération → projectiles → mouvement → composants restants → systèmes dans l'ordre du pipeline → adaptateur de rendu et retrait de `Sprite` → suppression des doubles écritures.

Tout se déroule sur la branche unique `refactor/cleanup`, sans tags, chaque commit vert (`pytest`, `DEBUG=1 pytest`, `mypy src`, `ruff`).

## Progression

- **Étape 0** (baseline + ADR) : faite.
- **Étape 1** (identité `(id, generation)` + table dense) : faite — `src/core/ecs/table.py`.
- **Étape 2** (tranche projectiles) : faite en trois commits — table latérale et mirror, promotion des lectures de contact/geometry, handles de génération transportés par `ProjectileSnapshot` et restaurés au rewind. Les projectiles sont désormais pilotés par la table ; le `Projectile` poolé reste le proxy de rendu.
- **Étape 3** (mouvement) : faite — `src/core/ecs/movement_table.py` porte `vx`, `vy` et les trois drapeaux de contact en colonnes primitives, exposés par des vues stables qui préservent `entity.velocity.x = ...` et `entity.on_surface["floor"] = ...`. Les 91 + 26 sites de mutation en place n'ont pas changé ; le composant reste mirror pour les snapshots et l'invariant à 440 champs.
- **Étapes 4 à 6** (autres composants, systèmes, retrait de `Sprite`) : **non encore faites**. Elles exigent la promotion de `Vitals`, de la géométrie et de `CombatComponent`, puis le re-baseline explicite du test à 440 champs et des digests.

Le chantier 06 résiduel (`getattr` de l'overlay debug sur des groupes hétérogènes, prose d'invariant) reste également à traiter après la migration d'entités, conformément à l'ordre retenu.
