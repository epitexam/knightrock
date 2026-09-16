# 🔍 Audit Phase 5 — Hitbox / combat avancé hack'n'slash

**Référentiel :** `audit.md § Phase 5` (4 chantiers), constats de départ : socle mêlée complet
(`HitboxManager` 1 rect offensif, `hurtbox` distincte, frame data startup/active/recovery,
`CombatSystem` two-pass déterministe, `HitResolver`, overlay debug).
**Périmètre vérifié :** commits `9719d60` (#1), `67a1449` (#2), `1f931a5` (#3), `63488a1` (#4) —
tête `63488a1`, working tree propre.
**Méthode :** relecture des modules touchés, grep des symboles clés, exécution de la suite
complète (`444 passed`), `ruff check`, `mypy src`, tests ciblés
(`test_hitbox_pipeline` + `test_projectile_system` + `test_juggle` + `test_gameplay_data` : 54 passed).

**Verdict global : 4/4 implémentés.** Aucun chantier manquant côté code. Le résiduel est du
*contenu/équilibrage* (valeurs JSON, boss multi-zones, mages), pas de la mécanique.

---

## #1 — Multi-hitbox disjointe ✅ IMPLÉMENTÉ (`9719d60`)

**Exigé :** `HitboxManager.rect: FRect | None` → `tuple[FRect, ...]` ; `CombatSystem` itère les
sous-box ; `targets_hit` par phase conservé (pas de double dégât).

| Point | Preuve |
|---|---|
| `HitboxSpec` + `PhaseDefinition.extra_hitboxes` | `src/combat/frame_data.py:96-119,202,234` |
| Pool `rects` (primaire d'abord, `rects[0] is rect`) | `src/combat/hitbox_manager.py:18,28-30,59-82` |
| Exposition `attack_boxes` + protocole | `src/combat/combat_component.py:128`, `src/combat/combatant_protocol.py:62` |
| Itération `any(box.colliderect(hurtbox))` + requête grille **par box** + ordre groupe restauré | `src/core/level/systems/combat_system.py:80-114` |
| JSON `extra_hitboxes` optionnel + fallback `()` | `src/data/attacks.py:100-105,150`, sérialisation `:230` |
| Overlay debug dessine toutes les box | `src/ui/world_ui.py:30-49` |

**Tests :** `test_hitbox_pipeline.py` (extra boxes, contact unique partagé).
**Écart :** extras statiques par design (documenté `hitbox_manager.py:63`) — l'animé ne concerne
que la box primaire (#2). `data/gameplay/attacks.json` n'utilise pas encore `extra_hitboxes`
(valeurs legacy) : mécanique prête, contenu à remplir.

## #2 — Hitbox animée par frame ✅ IMPLÉMENTÉ (`67a1449`)

**Exigé :** taille/offset fixes par phase → courbe per-frame, éditée via JSON (dépend Phase 3 #4).

| Point | Preuve |
|---|---|
| `HitboxKeyframe{frame,size,offset}` + validation (ordre strict, span startup+active) | `src/combat/frame_data.py:207,235,248` |
| Interpolation linéaire `hitbox_at(frame)` | `src/combat/frame_data.py:255-275` |
| `animation_frame` mappé sur startup/active | `src/combat/attack_state.py:130` |
| Primaire positionnée depuis la courbe (startup live pour overlay/sweep, dégâts toujours gatés `is_active`) | `src/combat/hitbox_manager.py:52,63-66` |
| JSON `hitbox_keyframes` strict + sérialisation | `src/data/attacks.py:123-129,153-154,234-240` |

**Tests :** `test_hitbox_pipeline.py` (courbe, interpolation, bornes), `test_gameplay_data.py`
(roundtrip JSON).
**Écart :** aucun côté code. Comme #1, les attaques livrées restent à courbes vides
(comportement legacy statique) — attendu, rétrocompatible.

## #3 — Projectiles ✅ IMPLÉMENTÉ (`1f931a5`)

**Exigé :** brancher `ObjectPool` sur un `ProjectileSystem` (hitbox volante + `hurtbox`,
faction, durée de vie) réutilisant `HitResolver`/`EntityGrid`.

| Point | Preuve |
|---|---|
| `ProjectileConfig{size, lifetime, hit, pierce}` + `Projectile(Sprite)` poolé (`id pN`, `launch/reset/update`, `hurtbox=hitbox`, `targets_hit`) | `src/entities/projectile.py:27-120` |
| `ProjectileSystem.spawn/process` : pool `acquire/release`, intégration + expiry, mur via `spatial_hash` (vrai `colliderect`), cibles via `EntityGrid.near()` triées en ordre groupe, dégâts via `HitResolver`, `pierce` vs one-shot, gel à `dt<=0` (hit-stop) | `src/core/level/systems/projectile_system.py:30-147` |
| Groupe dédié (rendu via `all_sprites` existant) | `src/core/sprite_groups.py:15` |
| Câblage pipeline après `process_combat_and_separation` (grille déjà rebuildée) | `src/core/level/systems/gameplay_loop.py:67,91,146-147` |
| Assemblage `Level` | `src/core/level/level.py:20,132,146` |
| `ObjectPool` : docstring `unused by the simulation` désormais caduque côté projectiles (toujours vrai pour particules) | `src/core/object_pool.py:11` |

**Tests :** `tests/unit/test_projectile_system.py` — 7 tests (move/expiry/reuse `created==1`,
hit via resolver, friendly-fire ignoré, pierce multi-cibles sans double-hit, mur, grille vs
exhaustif, freeze hit-stop).
**Écarts / suivis :**
- Pas de `projectiles.json` data-driven (config en code uniquement) — envisager `src/data/projectiles.py` si mages/archers/pièges se multiplient.
- Pas de gravité projectiles, pas de collision projectile-vs-projectile, pas de snapshot rollback
(`save_state` minimal debug uniquement) — hors scope de l'audit, à décider au besoin feature.
- Docstring `object_pool.py:11` à mettre à jour (mentionne encore « unused »).

## #4 — Juggle / hit-stun avancé ✅ IMPLÉMENTÉ (`63488a1`)

**Exigé :** au-delà de `heavy_knockback` + `stagger` — hitstun scalé dégâts, gravité en juggle,
invuln OTG, compteur combo air.

| Sous-point | Preuve |
|---|---|
| Hitstun scalé : `stagger + final_damage × HITSTUN_DAMAGE_FACTOR` | `src/combat/hit_resolver.py:118-123`, `src/core/settings.py:87` (`0.004`) |
| Gravité juggle : `HitProperties.juggle_gravity_mult` appliqué si victime airborne via `set_juggle(mult, JUGGLE_GRAVITY_TIME)` | `src/combat/frame_data.py:79-95,102`, `src/combat/hit_resolver.py:103-107`, `src/core/settings.py:88` (`0.45 s`) |
| État victime : `gravity_scale/juggle_timer/otg_timer`, tick + atterrissage depuis juggle → guard OTG + reset gravité, persisté dans `EntitySnapshot.extra` | `src/entities/entity.py:200-202,613-634,664-669,729-733,759-761` |
| Gravité lit `gravity_scale` | `src/physics/gravity.py:14` |
| OTG : `HitProperties.otg_allowed`, gate pré-dégâts (sol + `otg_timer>0` + non-OTG → ignoré), fenêtre `OTG_INVULN_DURATION` | `src/combat/hit_resolver.py:74-77`, `src/core/settings.py:89` (`0.5 s`) |
| Compteur air : `ComboTracker.air_count` + `on_hit_landed(airborne)`, `CombatComponent.record_hit_landed/air_combo_count`, snapshot `air_combo_count`, no-op côté `Null` | `src/combat/combo_tracker.py`, `src/combat/combat_component.py:41,52,180-186,336,350` |
| JSON `juggle_gravity_mult` / `otg_allowed` (defaults `1.0`/`False`) + sérialisation | `src/data/attacks.py:80-81,227-228` |

**Tests :** `tests/unit/test_juggle.py` — 7 tests (scaling stagger, juggle air vs sol, OTG
block/allow, compteur air, grant OTG au landing, roundtrip JSON).
**Écarts / suivis :**
- Détection « airborne » = `on_surface["floor"]` au moment du hit (duck-typing, défaut
« grounded » si inconnu) — simple et déterministe, mais pas de vrai état « knockdown ».
- `HitResolver` notifie le combo attaquant en duck-typing (`record_hit_landed` puis fallback
`combo.on_hit_landed`) pour ne jamais casser projectiles/stubs — robuste, au prix d'un
contrat implicite à documenter si `CombatPort` est étendu.
- Équilibrage (`0.004 / 0.45 s / 0.5 s`, `mult` par coup) non réglé en jeu — attendu.

## Dépendances Phase 3 — réglées, rien à retoucher

* **`EntityGrid`** (`src/physics/entity_grid.py`, rebuild `gameplay_loop.py`) : utilisé par #1
(requête par box), #3 (requête par projectile), #4 indirect (aucun besoin grille).
* **`ObjectPool`** (`src/core/object_pool.py`) : brique générique inchangée, désormais consommée
par #3 ; le `no max-size` documenté reste un choix (caps côté wiring futur).
* **JSON data-driven** (`src/data/attacks.py`, `data/gameplay/attacks.json`) : supporte
`extra_hitboxes`, `hitbox_keyframes`, `juggle_gravity_mult`, `otg_allowed` avec strict-fail ;
contenu legacy = tous defaults → rétrocompatible.

## Vérifications exécutées

* `uv run pytest -q` → **444 passed** (dont 54 ciblés
`hitbox_pipeline + projectile_system + juggle + gameplay_data`).
* `uv run ruff check src tests` → **clean**.
* `uv run mypy src` → **clean (118 fichiers)**.

## Conclusion

Phase 5 complète côté mécanique : multi-hitbox, hitbox animée, projectiles poolés,
juggle/hit-stun avancé sont implémentés, testés, typés et câblés au pipeline déterministe
(grille partagée, hit-stop respecté, rollback étendu pour #4). Reste du *game design* :
remplir `attacks.json` (extra boxes, keyframes, `juggle_gravity_mult`, `otg_allowed`),
ajouter des configs projectiles data-driven si besoin, équilibrer les 3 constantes
`Combat`, et corriger la docstring obsolète `object_pool.py:11`.
