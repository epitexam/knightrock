# Audit hitbox — ressenti de chaîne (2026-11-18)

Branche : `fix/hitbox-fluidity` (depuis `master` au `5c88305`).
Périmètre : joueur + ennemis, input → attack state → hitbox → contact → résolution.
Méthode : baseline vert, scenarios headless « depuis l'instant d'avant », benchmark
déterministe, goldens recapturés avec preuve de cause unique.

## 1. Ce qui n'allait pas

### 1.1 Mesurer était impossible (instrument)

- **Collision d'identifiants dans les harnais de test.** `Level` crée un
  `IdFactory` privé (joueur `e0`), mais `create_enemy` sans `id_factory` prend
  le factory *global* (premier ennemi `e0`). `_is_valid_target` rejette la
  cible comme étant le propriétaire : le premier duel du benchmark ne portait
  **aucun coup** (`landed_ratio = 0.0`). Le harnais (`tests/benchmarks/combat_feel.py`,
  `tests/headless/arena.py`) partage maintenant le factory du level. Le jeu
  réel n'était pas touché : `WorldBuilder` et `SpawnSystem` passent déjà leur
  factory.
- **Overlay debug faux.** `GeoLayer.swept_boxes` testait `callable(...)` sur
  `swept_attack_boxes`, une *property* tuple : aucune entité réelle ne dessinait
  ses fantômes de sweep. Les zones swept n'étaient pas dessinées non plus,
  alors que le contact teste `swept_hurtboxes()`. Une zone égale au collider
  était filtrée par identité, ce qui décalait les index de multiplicateurs/tags.
- **Suites `DEBUG=1` cassées** par trois doubles incomplets (patch
  `get_pressed` en dict, level `__new__` sans renderer).
- **Aucune métrique de latence**, et un benchmark qui ne peut pas échouer.

### 1.2 Ce qui allait déjà bien (préservé)

Le pipeline est déjà unifié (`OffensiveBox` + `ContactSystem`), les règles sont
centralisées dans un `HitResolver` stateless, la hiérarchie de cancels est
déjà différenciée (maillons 1-3 en `cancel_on_hit`, terminaux non), le buffer
d'attaque dure 12 ticks et survit au hit-stop, le sweep et le déterminisme
sont documentés. **Aucun rework complet n'était justifié.**

## 2. Ce qui a été fait

### Phase 0 — Baseline et instrumentation
- Suites normales et `DEBUG=1` vertes, mypy/ruff propres.
- `tests/headless/test_feel_latency.py` : 4 scénarios, valeurs de
  caractérisation. Latence mesurée : **4 ticks** depuis la recovery, **9 ticks**
  depuis un press en ACTIVE avant contact.
- `tests/unit/test_feel_contract.py` : faits de tuning assertés (hit-stops,
  cancels de chaîne, recovery des terminaux).

### Phase 1 — Fidélité (aucun gameplay modifié)
- Fantômes de sweep des boîtes **et** des zones hurtbox dessinés.
- Index des zones préservés (le contour redondant alone est sauté).
- Docstring `Refusal` alignée sur `is_retryable` (`COOLDOWN` + `NO_CANCEL`).
- Sérialiseur par défaut passé en v2, comme le fichier livré.

### Phase 2 — Rework partiel (deux coutures)
- Primaire et extras passent par le même `HitboxSpec` et le même interpolateur ;
  `interpolate_keyframes` (doublon) supprimé. `hitbox_at` reste un shim.
- Une seule lecture de la géométrie swept côté overlay.

### Phase 3 — Tuning (validé avant application)
| Changement | Valeur | Effet mesuré |
|---|---|---|
| `hit_stop` explicite sur les 8 coups ennemis | ~0.088 → **0.04 s** | part de freeze en baisse (ex. slash vs goblin 0.36 → 0.31) ; latence de chaîne 9 → **7 ticks** |
| `slash_high_4`, `slash_low_4` | recovery 14 → **11** | fin de chaîne moins engageante |
| `slash_high_4`, `slash_low_4`, `air_slash` | `cancel_on_hit: true` | le lien part au contact, pas seulement en recovery |

Benchmark comparatif (10 s) : swings/s en hausse sur la plupart des duels
(slash vs slime 6.21 → 6.51, slash vs shell 5.57 → 5.97), taux de touche beat
vs goblin 0.75 → 1.0.

## 3. Preuves des goldens

- `tests/golden/hit_outcomes.json` : 35 lignes recapturées, **toutes** des
  `hit_stop` (0.0885 / 0.0796 / … → 0.04). Aucune autre issue n'a bougé.
- Digest RIDE : `e86caa42…` → `d49f5b9b…`. Cause unique prouvée : en révertissant
  **uniquement** les huit `hit_stop` ennemis dans un data root temporaire, le
  digest précédent est reproduit bit pour bit. PHYSICS et RESPAWN inchangés.

## 4. Poursuite de l'audit (deux points initialement reportés)

### 4.1 Prédicat d'éligibilité unique — rejeté, micro-refactor fait

Les six gardes ne sont pas des doublons mais des phases distinctes :

| Garde | Phase | Effet de bord |
|---|---|---|
| `_is_valid_target` / `can_contact` | sélection de la paire | aucun ; mémoire armée après |
| `MomentumGate` / `OffensiveBox.accept` | filtre producteur | aucun, vitesse mutable |
| zones / tags | narrowphase (melee seul) | fixe `zone_mult` → dégâts |
| `_misses` | pré-dégâts | `on_hit_evaded()` **mute** (rush, fury, dash) |
| `guards_against` | défense | **mute** batterie/recul, peut casser la garde puis refuser |
| `receive_damage` → `Vitals` | autorité finale | dégâts, i-frames, hook de mort |

Un prédicat pur unique déplacerait ces effets, casserait les 675 outcomes, les
events/hit-stop et les digests de cooldown. **Fusion totale rejetée.** À la place :
- `hit_refusal()` classe les refus de `_misses` sans produire d'effet ;
  `on_hit_evaded()` reste appelé au même point et dans le même ordre ;
- `_invulnerable()` factorise la notion « esquive » dans le seul producteur
  contact, où les deux usages sont silencieux (contrairement au resolver).

### 4.2 `PhaseDefinition.boxes` — canonicalisation totale faite

Le chiffre initial (« ~200 fichiers de tests ») était faux : mesure réelle,
**5 fichiers source et 11 fichiers de tests**, ~95 occurrences. La refonte a été
faite :
- `boxes` est le seul champ stocké ; les 9 champs plats sont des propriétés en
  lecture seule dérivées de `boxes[0]` ;
- un constructeur accepte l'ancienne forme plate (adaptateur v1, fixtures,
  `dataclasses.replace`) et la forme `boxes` (loader v2) ; plus de réaplat
  v2 → plat → spec ;
- `boxes` reste un champ comparé/haché : l'égalité des définitions dépend
  toujours de leur géométrie ;
- 2 tests qui contournaient la validation via `object.__setattr__` sur un champ
  plat mutent désormais le `HitboxSpec` stocké.

**Aucun golden recapturé, aucun fichier de données réécrit.** Le fichier
`attacks.json` reste byte-identique, les 675 issues et les 3 digests passent tels
quels — la preuve que la refonte est bien behavior-preserving.

## 5. Recette finale

`pytest -q` : **3753 passed, 1 skipped**. `DEBUG=1 pytest -q` :
**3751 passed, 3 skipped**. `mypy src` : 197 fichiers, aucune erreur.
`ruff check .` : propre.

## 6. Toujours écarté (décision de design)

- **Références externes** (God of War : cancels pré-hit réservés aux attaques de
  base ; Sakurai : hit-stop court + secousse du modèle rendu uniquement ; NMH :
  changement de stance au milieu du combo). Le cancel pré-hit est **rejeté** ici :
  `can_cancel_into` n'a qu'un appelant et le lock en STARTUP est un choix de
  commitment documenté (README ligne 168-170).

## 7. Sources consultées

- Eric Williams, *Combat Canceled: God of War & Action Game Design*.
- Notes de Sakurai sur les 8 techniques de hit-stop.
- *Designing great hitboxes for a 2D beat-'em-up* (Wulverblade).
- *Combat Analysis: Guacamelee*, et analyses de Shank / Katana Zero.
