# ADR — spike ECS : NO-GO (2026-11-23)

Branche : `refactor/cleanup`. Aucun fichier de production n'a été modifié pour ce spike : il s'agit d'une mesure de falsification, pas d'une migration.

## Hypothèse

> Remplacer le chemin `Projectile` + `ObjectPool` + `pygame.sprite.Group` par une table de composants dense keyée `(id, génération)` réduit le temps de simulation d'un montant **visible pour le joueur** sur les effectifs que le jeu produit réellement (1–8 combattants, 0–4 projectiles).

## Méthode

Harnais : `tests/headless/arena.py` (vrai `Level`, vrai `Player`/ennemis), arène sans tuiles, projectiles armés avec une durée de vie de 30 s et une vitesse nulle pour rester en vol. Mesures sur cette machine (Python 3.14.10, pygame-ce 2.5.7, SDL dummy, GC désactivé pendant la boucle, 5 lots × 600 ticks, médiane):

| Combattants | Projectiles | Tick complet | Étape projectiles (grille comprise) | Part du tick |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0,226 ms | 0,0023 ms | 1,0 % |
| 1 | 4 | 0,684 ms | 0,0022 ms | 0,3 % |
| 8 | 4 | 1,606 ms | 0,0375 ms | 2,3 % |
| 8 | 32 | 2,328 ms | 0,0374 ms | 1,6 % |
| 8 | 64 | 2,716 ms | 0,0318 ms | 1,2 % |
| 8 | 256 | 12,986 ms | 0,0312 ms | 0,2 % |

À 256 projectiles, le coût supplémentaire du tick vient des autres étages qui parcourent les groupes, pas de `ProjectileSystem.process`, qui reste constant. Le chemin projectiles n'est donc pas le goulot, même dans un cas que le jeu ne produit jamais.

## Critères go/no-go (du plan)

- **Statistique** : IC bootstrap bas > 1,05 sur ≥4 scénarios réalistes — non mesuré, car le plafond théorique ci-dessous rend le test inutile.
- **Produit** : ≥0,5 ms de gain absolu à 4 ennemis et ≥1,0 ms à 8, ou ≥0,5 ms sur le p99 — **échec** : l'intégralité de l'étape projectiles vaut au plus 0,038 ms à 8 ennemis. Supprimer totalement cette étape (ce qu'aucune implémentation ne peut faire : il faut bien intégrer et résoudre les tirs) rendrait **au plus 2,3 % du tick**, soit 0,23 % du budget frame de 16,7 ms.
- **Échapatoire stress** : gain uniquement à 64–256 projectiles — **échec également** : le coût de l'étape y est le même qu'à 4 projectiles.

## Décision : NO-GO

Aucune migration ECS. Trois raisons structurelles confirment la mesure :

1. `Entity` est déjà une façade sur des composants (`Vitals`, `MovementComponent`, `CombatComponent`, `ReactionComponent`, machine à états) ; `tests/unit/test_entity_composition.py` constate qu'il n'y a rien à en extraire.
2. Les bénéfices annoncés ne s'appliquent pas : pas de contrôle du cache en CPython, composition déjà pilotée par JSON, dépendances intra-tick strictes (18 des 24 opérations parcourent des groupes) interdisant des systèmes parallèles.
3. Le coût d'une migration réelle serait une réécriture : 440 champs épinglés par le test d'invariant rollback, 91 accès `entity.velocity` et 26 `entity.on_surface` reposant sur des objets mutables vivants, 3 digests de simulation, 675 issues de coups, ~64 fichiers de test.

## À la place

Investir dans le vrai coût de frame mesuré par `tests/benchmarks/fx_benchmark.py` : la construction FX (atterrissage complet ≈1,6 ms ici, ~10 % du budget) et le rendu. `src/core/object_pool.py:9–12` désigne déjà les particules FX comme prochain candidat au pool — un changement local, mesurable et sans toucher au modèle d'entités.

## Sources

- Dennis Gustafsson, [*Thoughts on ECS*](https://blog.voxagon.se/2025/03/28/thoughts-on-ecs.html).
- [StackPractices — ECS Pattern](https://stackpractices.com/patterns/entity-component-system-pattern).
- Martin Fowler, [*Branch By Abstraction*](https://martinfowler.com/bliki/BranchByAbstraction.html).
