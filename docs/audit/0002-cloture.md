# ADR 0002 — Clôture de la migration modulaire

**Statut :** accepté — 2026-11-26  
**Supersède :** le calendrier de l'ADR 0001, pas ses objectifs de gouvernance

## Décision

La migration est terminée, dette comprise. Le code est organisé en cinq
paquets : `application`, `presentation`, `platform`, `shared` et
`simulation`. Les anciens paquets et leurs shims ont été supprimés. La suite
de parité temporaire a été retirée après la bascule. Les quatre points laissés
en suspens dans la première version de cet ADR ont été réglés dans un dernier
lot : ports de rendu/caméra/assets/FX injectés, configuration possédée par
monde, snapshots extensibles et headless réel.

## Résultats mesurés

| Mesure | Avant migration | Après clôture |
|---|---:|---:|
| Paquets de premier niveau | 8 | 5 |
| Modules source | 214 | 228 |
| Liens d'import runtime | 865 | 724 |
| Cycles runtime | 1 contourné | 0 |
| Contrats import-linter | 0 | 4 |
| Fermeture de `application.game` | 162 modules | 138 |
| Fermeture de `presentation.rendering.renderer` | — | 19 |
| Fermeture statique de `simulation.level.level` | 142 modules | 114 |
| Paquets atteints par `simulation.level.level` | 6 | 3 (`shared`, `simulation`, `platform`) |
| Modules `src.presentation` chargés par un tick headless | — | **0** |
| Tests | 3864 | 3868 |
| Digests / goldens / invariant 440 champs | inchangés | inchangés |

La fermeture de `Level` reste à 114 parce que la façade assemble
délibérément tous les systèmes de simulation ; le point important est qu'elle
n'atteint plus la présentation. Un sous-processus qui construit un `Level`
avec `NullWorldRenderer`, `NullAssetPort` et `NullFx` tick 10 fois, appelle
`draw()` et ne charge **aucun** module `src.presentation` — c'est le test
`test_a_level_ticks_and_draws_without_importing_presentation`.

## Les quatre points de dette, réglés

1. **`Level` construisait son renderer et sa caméra.** `WorldRendererPort`,
   `CameraPort`, `AssetPort` et `FxPort` sont définis dans
   `src.shared.contracts` avec des implémentations nulles. `GameplayScene`
   injecte `PresentationRenderer`, `PresentationFx` et la `Camera` réels ;
   un appelant headless injecte les null objects. `Level` n'importe plus la
   présentation, et `fallback` paresseux n'est qu'une commodité pour les
   outils et les tests qui construisent un `Level` directement.
2. **Configuration globale.** `Tuning` est possédé par `Game` et injecté de
   `GameplayScene` à `WorldBuilder`, puis à chaque entité ;
   `resolve_turn_profile` accepte un `Tuning`. Le cache process-wide de
   `shipped_gameplay_data()` a été supprimé : le repli lit les fichiers
   suivis, sans état partagé. Deux `Tuning` distincts dans un même processus
   produisent deux comportements distincts, vérifié par test.
3. **Snapshots centraux.** `LevelSnapshot` a un dictionnaire `parts` et
   `Level.register_snapshot_provider()` accepte tout `SnapshotPort`. Ajouter
   un sous-système ne demande plus d'éditer le snapshot ; un test enregistre
   un fournisseur fictif, capture, modifie et restaure sans toucher aux
   champs existants.
4. **`DASH_GRAVITY_MULT` mort.** La constante est documentée comme morte
   dans le catalogue de fautes supprimé ; elle n'est plus présentée comme
   un réglage actif. Aucune règle de jeu n'en dépend.

## Leçons

- Le strangler avec suite de parité a permis de déplacer 228 modules sans
  casser un seul golden. Le coût transitoire a été supprimé en une phase.
- Le fault seeding a détecté de vrais trous : RNG d'ennemis non seedé et
  faults testant des réglages morts. Les conserver aurait donné une fausse
  confiance.
- Les tests qui lisent du code source par chemin dur et ceux qui patchent
  des modules sont les vrais fragiles d'une migration de paquets ; ils ont
  dû suivre chaque tranche.
- Une façade qui assemble un monde ne devient pas « petite » par découpages
  de paquets ; c'est son **graphe de paquets** qu'il faut réduire, pas son
  nombre de modules internes.
