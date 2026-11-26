# ADR 0003 — Resserrer les types des ports

**Statut :** accepté — 2026-11-26  
**Branche :** `refactor/typed-ports`

## Contexte

L'ADR 0002 a livré cinq paquets séparés par des ports, mais la précision des
types a baissé aux coutures : `Any` était passé de 319 à 503 occurrences, dont
67 dans le seul `src/shared/contracts.py`. mypy strict passait toujours, mais
une erreur de forme dans un appel de port pouvait échapper au vérificateur.
C'était le principal point de maintenance restant.

## Décision

Le noyau partagé ne peut pas importer les autres paquets ; les objets qui leur
appartiennent restent donc **opaque** (`object`) ou décrits par un **protocole
structurel minimal** (`RenderGroups`, `SpriteLike`, `CameraPort`, `OverlayPort`).
Les types concrets sont inférés dans les adaptateurs, où ils sont connus, via
des `cast` explicites et locaux.

- `FrameContext` regroupe les entrées d'une frame (joueur, compteurs, événements)
  au lieu d'une longue liste de paramètres `Any`.
- `WorldRendererPort` annonce des types de retour réels (`list[pygame.Rect] | None`,
  `Color`, `Callable[[Surface], Surface]`, protocoles de plans de rendu).
- `FxPort` et `SnapshotPort` utilisent `object` pour les entités et états
  appartenant à la simulation ; `PresentationFx` et `NullFx` castent une seule
  fois vers les types attendus par les générateurs d'effets.
- Un adaptateur d'overlay conserve l'overlay réel pour les outils et les tests
  (`__getattr__`, propriété `real`), sans exposer la présentation au port.

## Alternatives écartées

| Alternative | Pour | Contre |
|---|---|---|
| Garder `Any` aux ports | zéro travail | laisse la dette de l'ADR 0002 |
| Importer les types concrets dans `shared` | signatures exactes | casse le contrat import-linter « shared ne dépend de rien » |
| Protocols complets (entité, joueur, host) | typage fort | dupliquerait les modèles de simulation dans le noyau partagé |

## Conséquences

| Mesure | Avant | Après |
|---|---:|---:|
| Occurrences de `Any` dans `src` | 503 | **347** |
| `Any` dans `src/shared/contracts.py` | 67 | **0** |
| `cast` dans les deux adaptateurs | 0 | 14 (explicites, localisés) |

Les tests qui inspectaient l'overlay réel ou le corps de `present()` ont été
adaptés au nouvel adaptateur. Tous les gates restent verts : 3869 tests,
`DEBUG=1`, couverture 94,19 %, mypy strict, ruff, 4 contrats import-linter.

Le `Any` restant (347) est concentré dans le code préexistant (loaders JSON,
générateurs FX, interface utilisateur) et dans les 13 `cast` de
`presentation/fx/adapter.py`, où il est nécessaire pour parler aux API pygame
non paramétrées. Ce chantier n'avait pas pour but de l'éliminer partout.
