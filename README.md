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
