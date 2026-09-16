# Knightrock

Hack'n'slash 2D développé en Python avec [pygame-ce](https://github.com/pygame-community/pygame-ce).

## Prérequis

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) (gestionnaire de paquets)

## Installation

```bash
uv sync --dev
```

## Lancer le jeu

```bash
uv run python main.py
```

Mode debug (overlay FPS / états / hitbox) :

```bash
DEBUG=1 uv run python main.py
```

## Contrôles

Déplacement : `←`/`→`, saut `Espace`, dash `Shift`, bloc `Q`, reset `R`.

Attaques : `A` (légère / aérienne en l'air), `S` (lourde chargeable, maintenir puis
relâcher), `D` (uppercut), `F` (dash attack), `G`+`H` (spéciale).

Debug spawn : `G` gobelin, `P` slime, `T` dummy.

## Banc d'essai Phase 5 (hitbox / combat avancé)

Touches disponibles en jeu, sans rien recompiler :

| Touche | Feature testée | Détail |
|---|---|---|
| `1` | Multi-hitbox (#1) | `twin_fangs` : lame + 2ᵉ box disjointe |
| `2` | Hitbox animée (#2) | `sweeping_arc` : la box grandit le long de la courbe |
| `3` | Juggle (#4) | `sky_launcher` : lance en l'air, gravité adoucie (`x0.5`) |
| `4` | OTG (#4) | `otg_slam` : seul coup autorisé pendant la garde OTG |
| `V` | Projectile (#3) | `firebolt` simple, réutilise `HitResolver` |
| `B` | Projectile perçant (#3) | traverse et touche chaque cible une fois |
| `C` | Dummy de juggle | pop un dummy en l'air devant le joueur |

Protocole suggéré : `C` puis `3` sous le dummy (neutre en l'air), jongler en
l'air (`A` en saut), finir au sol avec `4` pendant la garde OTG. L'overlay
debug (`DEBUG=1`) montre les box offensives, `Combo (air xN)`, `Juggle`,
`OTG guard` et le compteur `Shots` du panneau SCENE.

## Debug visuel (`DEBUG=1`)

L'overlay ne dessine que ce qui est à l'écran (culling viewport) :

- hitbox **bleue** = joueur, **rouge** = ennemi, **grise** = neutre ;
  hurtbox verte, box offensive orange, vecteur vitesse jaune ;
- contour **cyan** = garde OTG, **violet** = gravité de juggle ;
- labels courts (`Goblin chase 75/100`), 2ᵉ ligne seulement en attaque
  ou avec un flag (`STAG`, `OTG`, `JGx`, `AIR`) ; projectiles labellisés
  (vitesse, vie, perçant) ; tuiles ignorées, statiques sans texte ;
- `F1`/`F2`/`F3`/`F4` = on/off box / labels / vitesses / statiques
  (rappelés dans le panneau `DEBUG KEYS` en jeu).

## Moteur physique (assists, tous neutres par défaut)

Réglages dans `src/core/settings.py` (`GameFeel`, `Collision`, `PlatformRide`) :

- `JUMP_CUT_DIVISOR` — saut variable (relâcher coupe la montée) ;
- `GROUND_SNAP_PX` — colle au sol en bout de plateforme ;
- `STEP_UP_PX` / `CORNER_CORRECT_PX` — monte les marches, glisse les coins ;
- `MIN_PENETRATION_PX` — frôlements qui glissent au lieu de stopper ;
- `MAX_RESOLVE_PX` — garde anti-téléportation + flag `crushed` ;
- `STICKY_FACTOR` — suivi des plateformes descendantes rapides.

## Tests

```bash
uv run pytest
```

Avec couverture (seuil imposé par la CI : 50 %) :

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=50
```

Qualité (lint + types) :

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

## Architecture

- `src/core/` — bootstrap (`game.py`), `settings.py` (constantes), niveaux,
  gameplay (fixed-timestep 60 Hz), entrées, rendu.
- `src/entities/` — `Entity` (base), `Player` + contrôleurs
  (`Jump`/`Block`/`Dash`), ennemis data-driven (`configs.py`, `factory.py`).
- `src/combat/` — moteur de combat à frame data (startup/active/recovery),
  `CombatSystem`, `HitResolver`, `KnockbackConfig`.
- `src/physics/` — collisions, gravité, mouvement, `SpatialHash`,
  `SeparationSystem`, dégâts de contact / hazards.
- `src/states/` — machines à états (player, ennemis, réactions partagées).
- `src/ui/` — HUD joueur, barres de vie, panneaux de debug.
- `assets/` — niveaux TMX (`assets/data/levels/`) et sprites
  (`assets/graphics/`). **Requis au runtime** : ne pas l'ignorer via git.

## Conventions

- Code typé (`mypy` visé strict), formaté avec `ruff format`.
- Simulation déterministe à pas fixe (`Simulation.TICK_RATE = 60`) ;
  le rendu suit `Display.FPS`.
- Constantes de gameplay centralisées dans `src/core/settings.py` —
  pas de magic numbers dans les systèmes.
