# ADR 0002 — Clôture de la migration modulaire

**Statut :** accepté — 2026-11-26  
**Supersède :** le calendrier de l'ADR 0001, pas ses objectifs de gouvernance

## Décision

La migration parallèle est terminée. Le code est organisé en cinq paquets :
`application`, `presentation`, `platform`, `shared` et `simulation`. Les
anciens paquets (`core`, `physics`, `combat`, `entities`, `states`, `data`,
`ui`) et tous leurs shims ont été supprimés. Le harnais de parité temporaire
(`tests/parity/`) est retiré : il a rempli son rôle pendant la migration.

## Résultats mesurés

| Mesure | Avant | Après |
|---|---:|---:|
| Paquets de premier niveau | 8 | 5 |
| Modules source | 214 | 220 |
| Liens d'import runtime | 865 | 719 |
| Cycles runtime | 1 (contourné) | 0 |
| Contrats import-linter | 0 | 4 |
| Fermeture de `application.game` | 162 modules | 138 modules |
| Fermeture de `presentation.rendering.renderer` | — | 19 modules |
| Fermeture de `simulation.level.level` | 142 modules | **127 modules** |
| Tests | 3864 | 3865 |
| Digests / goldens / invariant 440 champs | inchangés | inchangés |

Le tick médian reste dans le bruit de mesure ; aucun benchmark n'a été
recapturé, aucun golden n'a été régénéré.

## Ce que la refonte a apporté

- Des frontières **explicites et vérifiées en CI** : import-linter refuse tout
  import de `application` depuis les quatre autres paquets, et tout import
  croisé depuis le noyau partagé.
- Une structure qui **montre** la séparation simulation / présentation /
  plateforme au lieu de seulement la documenter.
- Une base saine pour les changements futurs : le renderer, l'audio et les
  entrées sont des adaptateurs identifiables, et le noyau partagé est minimal.
- Une migration **sans régression fonctionnelle** : chaque phase est restée
  verte et le jeu restait jouable.

## Dette restante — explicitement non réglée

1. `simulation.level` importe encore `presentation.rendering` et
   `presentation.fx` : `Level` construit son `Renderer` et sa `Camera`.
   Les ports `WorldRendererPort` et `CameraPort` existent dans
   `src.shared.contracts` mais ne sont pas encore injectés. C'est pour cela
   que la fermeture de `simulation.level.level` reste à 127 modules, loin de
   l'objectif initial de 50.
2. La configuration globale n'est pas encore injectée : `PROFILES` et
   `shipped_gameplay_data()` restent des états process-wide.
3. Les snapshots restent centraux : `LevelSnapshot` connaît toujours sept
   sous-systèmes ; `SnapshotPort` n'a pas été introduit.
4. `DASH_GRAVITY_MULT` est une constante morte (assignée, jamais lue).

Ces quatre points sont des **améliorations futures**, pas des régressions :
ils n'empêchent ni le fonctionnement du jeu ni la vérification des couches.
Ils feront l'objet d'ADR dédiés s'ils deviennent des besoins (headless réel,
netcode, deux mondes avec des réglages distincts).

## Leçons

- Le strangler avec suite de parité a permis de déplacer 220 modules sans
  casser un seul golden. Le coût transitoire (shims) a été supprimé en une
  seule phase, après la bascule.
- Le fault seeding a détecté de vrais trous : des scénarios non déterministes
  (RNG d'ennemis non seedé) et des faults qui testaient des réglages morts.
  Les garder aurait donné une fausse confiance.
- Les tests qui lisent du code source par chemin dur et ceux qui patchent des
  modules sont les vrais fragiles d'une migration de paquets ; ils ont dû
  suivre chaque tranche.
