# Bilan — chantier de restructuration (2026-11-23)

Branche : `refactor/cleanup`, 25 commits depuis `aaa5aeb` (merge de `fix/hitbox-fluidity`). Aucun tag, historique linéaire, chaque commit vert.

## Vérification finale

```text
uv run pytest -q               3783 passed, 1 skipped
DEBUG=1 uv run pytest -q       3781 passed, 3 skipped
uv run mypy src                203 fichiers, 0 erreur
uv run ruff check               propre
PyInstaller 6.22.2             build OK + boot headless OK (SDL dummy)
git status                     propre
```

## Livré

- **Extractions** : null-objects de combat, sérialiseur d'attaques, transforms/afterimages du renderer, échelle de shatter FX.
- **Dédup** : légende/aide DEBUG, flags de statut, validation des transitions, déplacement de binding, recherche d'ellipse, setup des grains, `required_field`, résidus `attack_state`/renderer.
- **Réorganisation** : package `ui/world_overlay/` (8 modules, 56 références, shims retirés).
- **Bus** : `[T: GameEvent]` sans `type: ignore`, monde fermé vérifié, handles d'abonnement, sémantique de rejeu « au moins une fois » documentée et testée.
- **Dette** : bug du knockback `fixed` négatif corrigé, docs fausses corrigées, prose historique de `settings_store` et du renderer réduite avec garde AST, 33 `getattr` de contrat remplacés par des lectures déclarées (fakes mis à la vraie forme).

## Reste volontairement non fait

| Point | Raison |
|---|---|
| Migration ECS complète | **NO-GO mesuré** : l'étape projectiles vaut 0,002–0,038 ms, au plus 2,3 % du tick. Voir `ecs-spike-2026-11.md`. |
| Bus générique `EventBus[E]` | Affaiblit la vérification à l'abonnement (mypy accepte alors un type étranger) et force du churn dans 7 fichiers. Les handles couvrent le besoin réel. |
| Observation interpolation 120/144 Hz | Nécessite un écran 120/144 Hz ; le code est déjà livré et testé en headless. À faire sur le matériel, puis seulement une note ou un réglage minimal. |
| `getattr` de l'overlay debug (~130) | Groupes réellement hétérogènes (tuiles, entités, FX, projectiles) : les adaptateurs `rect`/`hitbox` sont le contrat, pas une tolérance. |
| Adaptateurs de collision (~11) | Deux formes réelles (tuile `rect` vs entité `hitbox`) ; documentés dans `spatial_hash.py`/`collisions.py`. |
| Prose résiduelle | Le reste est majoritairement des docstrings d'invariant ; les retirer nuirait à la lisibilité sans gain mesurable. |
