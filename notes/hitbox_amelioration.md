# Rapport Hitbox — Audit et plan de refonte / implementation

- **Date :** 2026-09-20 (ameliore le 2026-09-20 : preuves dynamiques, corrections)
- **Perimetre :** `src/combat/`, `src/physics/`, `src/entities/entity.py`, `src/core/level/systems/combat_system.py`, `src/core/level/systems/projectile_system.py`, `src/core/level/systems/hazard_damage.py`, `data/gameplay/attacks.json`, `src/ui/world_ui.py` (debug)
- **Methode :** lecture du code + greps + mesures executees (repro tunneling, bench `_collect_candidates`, parite JSON/builtin, suite 719 tests)
- **Statut grab (rappel) :** aucun systeme de grab/throw/command-grab n existe. Seul faux positif : `generator.throw()` dans un test.
- **Base de tests :** 719 tests collectes et verts (`pytest -q` : 719 passed), voir section 7.

## Sommaire

1. [Etat des lieux](#1-etat-des-lieux)
2. [Preuves dynamiques](#2-preuves-dynamiques-repro-et-mesures)
3. [Diagnostic et limites](#3-diagnostic-et-limites)
4. [Axes d amelioration](#4-axes-damelioration-meme-refontes-profondes)
5. [Plan de refacto / implementation](#5-plan-de-refacto--implementation-p0-a-p5)
6. [Modele cible](#6-modele-cible-schemas-et-exemples)
7. [Validation et reception](#7-validation-et-reception)
8. [Risques et non-objectifs](#8-risques-et-non-objectifs)
9. [Decision attendue](#9-decision-attendue)
10. [Recettage par palier](#10-recettage-par-palier-l-agent-y-consigne-date--resultats)

---

## 1. Etat des lieux

### 1.1 Architecture actuelle

```
AttackDefinition (frame_data.py)
  └─ phases: PhaseDefinition[startup | active | recovery]
       ├─ hitbox_size / hitbox_offset (boite primaire, AABB)
       ├─ extra_hitboxes: HitboxSpec[] (boites secondaires, statiques)
       ├─ hitbox_keyframes: HitboxKeyframe[] (courbe animee, primaire seule)
       └─ hit: HitProperties (damage, knockback, stagger, ...)

CombatComponent (combat_component.py)
  ├─ AttackStateMachine (frame_counter, facing locke, targets_hit, charge)
  ├─ HitboxManager (pool de pygame.FRect, rect = rects[0])
  ├─ ComboTracker / ChargeHandler
  └─ is_hurt / hurt_timer / cooldowns

CombatSystem (systems/combat_system.py)
  1. _collect_candidates : pour chaque attaquant actif, requete EntityGrid
     autour de chaque attack_box, test attack_box.colliderect(target.hurtbox)
  2. _resolve_candidates  : HitResolver.resolve() + record_contact + hit-stop

Entity (entity.py)
  ├─ hitbox  : collider physique (murs, sols, plateformes)
  └─ hurtbox : hitbox.inflate(hurtbox_inflate), recentree, une seule zone
```

### 1.2 Fichiers de reference

| Fichier | Role | Points cles |
|---|---|---|
| `src/combat/frame_data.py:48-96,165-253` | `HitProperties`, `PhaseDefinition`, `HitboxSpec`, `HitboxKeyframe` | AABB uniquement, keyframes sur primaire seule, `reset_targets=True` par defaut |
| `src/combat/hitbox_manager.py:12-82` | Positionnement offensif | Pool sans alloc, actif des `startup`, miroir X selon facing, extras statiques |
| `src/combat/combat_component.py:55-103,122-131` | Orchestrateur par entite | `attack_box` (legacy) + `attack_boxes` (tuple), `can_contact` / `record_contact` via `targets_hit` |
| `src/core/level/systems/combat_system.py:47-167` | Detection melee en 2 passes | Prune `EntityGrid.near(attack_box)`, ordre deterministe, `colliderect` discret |
| `src/combat/hit_resolver.py:99-189` | Degats, knockback, stagger, finisher, dizzy, invincibilite | Pas de hauteur, pas de priorite, pas de clash |
| `src/entities/entity.py:175-176,399-438` | `hitbox` vs `hurtbox` | 1 seul hurtbox inflate, resync dans `sync_rects()` |
| `src/physics/collisions.py:68-76` | `hitbox_collide` | `colliderect` instantane, pas de sweep |
| `src/physics/spatial_hash.py:53,178-208` | Grille environnement | `QUERY_MARGIN_PX=32`, requete enflee, faux positifs OK |
| `src/physics/entity_grid.py:32-76` | Grille entites | Rebuild O(n) par tick, ordre legacy preserve |
| `src/combat/attack_data.py:18-310` | `PLAYER_ATTACKS` en dur = **fallback** | 10 attaques (light/heavy/uppercut/dash/air + 5 vitrines Phase 5) ; utilise seulement si le JSON est absent |
| `data/gameplay/attacks.json` | **Source de verite a l execution** | `provider.py:90-95` : JSON present et valide => utilise ; JSON malforme => erreur forte ; JSON absent => fallback builtin. Noms et valeurs verifies identiques (10/10 attaques, ex. `light_attack.cooldown=0.3`, `dash_attack=[70,24]`). Risque restant : drift silencieux si on edite un seul des deux => recommandation : test de parite en P0 |
| `src/combat/attack_state.py:91-93,263-278` | Fenetre de frappe discrete | `is_active` = sous-etat ACTIVE uniquement ; `update()` avance **au plus 1 frame par tick** (garde-fou anti-saut de fenetre). La detection ne voit donc que la geometrie finale du tick |
| `src/physics/movement.py:244-276` | Mouvement environnement **substeppe** | Decoupage `ceil(|v|.dt / SUB_STEP_SIZE)` plafonne par `MAX_SUBSTEPS_PER_AXIS`, `old_hitbox` mis a jour par sous-pas. Le tunneling environnement est donc deja traite ; **seule la detection offensive est discrete** (1 passe/tick sur les boites finales) |
| `src/core/level/systems/projectile_system.py:88-121` | Pipeline projectiles | `hitbox.colliderect(target.hurtbox)`, separe du `CombatSystem` |
| `src/core/level/systems/hazard_damage.py:31` | Pipeline hazards | `box.colliderect(entity.hitbox)`, 3e convention |
| `src/ui/world_ui.py:291-322` | Debug overlay | Dessine `hurtbox` (vert) + `attack_boxes` (orange), pas de trajectoire ni timeline |

### 1.3 Flux par tick (melee)

1. `CombatComponent.update(dt)` : timers hurt/cooldown/combo/charge, `resolve_facing`, `state.update(dt)`.
2. `CombatComponent.sync_attack_box()` : `HitboxManager.update(state)` repositionne les `FRect` depuis `hitbox.center + offset`.
3. `EntityGrid.rebuild(entities)` : re-bucket O(n).
4. `CombatSystem.process_attacks(combatants, entity_grid)` :
   - `_attacker_ready` : vivant + `state.is_active` + boxes non vides + phase non nulle.
   - `_nearby_targets` : requete par `attack_box`, filtre faction/self/mort/`can_contact`, tri par ordre de groupe.
   - test `any(attack_box.colliderect(target.hurtbox))` puis `HitCandidate` gele.
   - `_resolve_candidates` : `HitResolver`, `record_contact`, `guard_events`, hit-stop global, compteur parry->dizzy.
5. `update_timer(dt)` : decremente le hit-stop (simulation suspendue pendant `in_hit_stop`).

### 1.4 Startup vs ACTIVE : telegraph visuel non letal

Point de precision important (corrige une lecture trop rapide de la v1) :
`HitboxManager.update()` positionne la geometrie des `startup` **et** `active`
(commentaire `hitbox_manager.py:33-39`), mais `_attacker_ready`
(`combat_system.py:47-59`) exige `combat.state.is_active`, c est-a-dire le
sous-etat ACTIVE uniquement (`attack_state.py:91-93`). Les boites visibles
pendant le startup sont donc un telegraph, pas une zone de degats. La
detection ne teste qu une seule geometrie par tick (celle post-mouvement),
et `AttackStateMachine.update()` (`attack_state.py:263-278`) garantit qu une
fenetre ACTIVE n est jamais sautee meme sur gros delta (avancee d au plus
1 frame par tick). Consequence pour le plan : le sweep P1 ne concerne que la
geometrie ACTIVE (+ extras), pas le telegraph startup.

### 1.5 Ce qui marche bien (a preserver)

- Pool de `FRect` reutilises dans `HitboxManager` (pas d alloc par tick).
- Double passe collect-then-resolve : les trades simultanes ne dependent pas de l ordre d insertion.
- Ordre deterministe restaure apres prune grille (bit-identique avec/sans grille).
- `targets_hit` + `reset_targets` par phase : multi-hit propre.
- Hit-stop global proportionnel degats + knockback, bonus parry.
- `CombatMetrics(pairs_tested, overlaps, contacts)` : base d observabilite.

---

## 2. Preuves dynamiques (repro et mesures)

Constats verifies le 2026-09-20 avec `uv run python` (pygame-ce 2.5.7,
Python 3.14.7), a partir des helpers `tests/unit/helpers.py`
(`entity_at`, `make_attack`, `make_phase`). L agent peut reproduire chaque
mesure en collant les extraits ci-dessous dans un test temporaire ou une
console (`sys.path` racine requis hors pytest, car `src` n est importable
que via le package `tests`).

### 2.1 Repro tunneling discret (trou confirme)

Cas moteur minimal : un attaquant ACTIVE dont la boite 20x20 a saute de
30..50 (tick precedent) a 70..90 (tick courant, saut de 40 px, equivalent
lunge rapide), face a une cible 20..60. Le test discret sur la position
finale ne voit aucun contact, alors que la position precedente touchait et
que l union des deux toucherait.

```python
import pygame

from src.core.level.systems.combat_system import CombatSystem
from tests.unit.helpers import entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase

definition = attack(
    phase(startup=1, active=8, recovery=1, size=(20.0, 20.0), offset=(0.0, 0.0))
)
attacker = entity_at(60.0, faction="A", definition=definition)
target = entity_at(20.0, faction="B")
attacker.combat.start_attack("test")
attacker.combat.update(1 / 60)  # STARTUP(1) -> ACTIVE
attacker.combat.sync_attack_box()

system = CombatSystem()
system.process_attacks([attacker, target])
assert system.metrics.contacts == 0  # trou : la passe discret rate le coup

cur = attacker.combat.attack_box  # FRect(70, 10, 20, 20)
prev = pygame.FRect(cur.x - 40.0, cur.y, cur.width, cur.height)  # 30..50
assert prev.colliderect(target.hurtbox)        # la position precedente touchait
assert cur.union(prev).colliderect(target.hurtbox)  # le sweep P1 toucherait
```

Sortie constatee : `contacts=0 overlaps=0 pairs=1`, puis union -> True.
Geometrie pure equivalente : boite 20x20 de x=0 a x=60, cible 10x20 a x=35
(`prev=False`, `cur=False`, union 80x20 -> True). Apres P1, ce cas doit etre
couvert par `tests/unit/test_hitbox_sweep.py` (scenario reel a deux ticks
avec `prev_rects`).

### 2.2 Bench `_collect_candidates` (detection seule, sans resolve)

Methode : roster `entity_at` + `make_attack` (`dash_attack` 70x24, offset 42),
attaquants de faction A en ACTIVE (`start_attack` + `update(1/60)` +
`sync_attack_box`), 300 iterations de `_collect_candidates` (sans resolve,
donc sans consommation des contacts). Valeurs constatees :

| Config | ms/tick | Paires testees/tick |
|---|---|---|
| 1v1 (n=2) | ~0.003 | 1 |
| 4v4 (n=8) | ~0.029 | 16 |
| 8v8 (n=16) | ~0.075 | 64 |

Lecture : cout negligeable a petit roster, croissance en O(a.t) sans grille
(a = attaquants, t = cibles de faction opposee). Exigence P1 : pas de
regression > 10 % sur ces valeurs, mesurees sur la meme machine (les
micro-benchs varient de quelques microsecondes d un run a l autre :
comparer les ordres de grandeur, pas les decimales).

### 2.3 Parite JSON / builtin

`load_gameplay_data` (`provider.py:86-95`) : JSON present et valide => JSON ;
JSON malforme => `GameplayDataError` ; JSON absent => fallback builtin.
Verifie : `sets = {player, goblin, slime}`, 10/10 noms d attaques player
identiques, `light_attack.cooldown` 0.3 des deux cotes,
`dash_attack` (70.0, 24.0) des deux cotes. Le diagnostic v1 ("doublon sans
source de verite") est corrige : la source a l execution est le JSON, le
builtin est un fallback. Reste un risque de drift (edition d un seul cote)
=> test de parite recommande en P0.

### 2.4 Rollback : ce qui est snapshotte ou non

- Snapshotte : `AttackStateSnapshot` (nom, phase, sous-etat, compteur,
  `targets_hit`, facing locke, charge, accumulateur) + `old_hitbox`
  (`entity.py:857-895`, `combat_component.py:320-353`).
- Non snapshotte : la geometrie derivee (`HitboxManager._pool`) — re-derivee
  par `sync_attack_box()` au `load_state`, ce qui est correct a condition que
  le facing locke soit restaure avant (c est le cas : `load_state` restaure
  `locked_facing`, puis `sync_attack_box` repositionne).
- Volontairement non snapshotte (P1, D3 abandonnee) : `prev_rects` /
  `_prev_hurtbox`. Inutiles en snapshot : la capture frontiere du premier
  tick re-simule les re-derive (`cur` re-sync au load, `prev` re-capture
  avant toute detection) ; `load_state` les remet a vide/None par hygiene.

---

## 3. Diagnostic et limites

### L1 — Detection offensive discrete, tunneling (prouve en 2.1)

Seule la detection **offensive** est discrete : le mouvement environnement est
substeppe (`movement.py:244-276`), et la machine d attaque ne saute jamais une
fenetre ACTIVE (`attack_state.py:263-278`). Le trou restant : une seule
geometrie offensive testee par tick (post-mouvement), sans union prev+cur.
Cas a risque : `dash_attack` (lunge frame 1, boite 70x24, offset 42 px),
keyframes `sweeping_arc` (28 -> 70 px en 6 frames), chutes ~25 px/tick
(1500 px/s a 60 Hz) contre cibles fines. `QUERY_MARGIN_PX=32` protege la
broadphase (requete elargie), pas la narrowphase (`colliderect` instantane).

Symptomes : coups rapides qui passent au travers, whiffs visuels injustes
sur lunge et cibles fines.

### L2 — Geometrie pauvre : AABB uniquement

- Que des rectangles alignes aux axes. Pas de rotation, cercle, capsule, OBB, polygone.
- `extra_hitboxes` statiques par design (commentaire `#1 scope` dans `hitbox_manager.py:62`). Impossible d animer twin-fangs lame par lame ou un arc qui pivote.
- `hitbox_keyframes` sur la boite primaire seule, interpolation lineaire taille/offset, pas de courbe de position absolue ni d easing.

### L3 — Une seule hurtbox globale

`hurtbox = hitbox.inflate(...)` centree. Consequences :

- Pas de zones (tete/torse/jambes), pas de multiplicateur localise.
- Le `dash` qui ecrase la hitbox (`apply_squish`) retrecit aussi la vulnerabilite sans controle fin.
- Pas d invulnerabilite partielle (ex. jambes invulnees pendant un saut), pas de garde haute/basse.

### L4 — Pas de distinction push / hurt / hit

`hitbox` sert a la fois de corps physique, d ancrage des attaques et de reference hurtbox. Standard versus-fighter attendu :

- `pushbox` (collision corps-a-corps, separation),
- `hurtbox[]` (zones recevant),
- `hitbox[]` (zones emettrices).

Sans ca : cross-up aleatoires, separation qui pousse pendant un hit-stop, grab impossible a specifier proprement.

### L5 — Semantique de coup minimale

`HitProperties` = degats + knockback + stagger + armor-break + finisher + juggle + OTG. Manquent :

- hauteur (`high/low/mid`, overhead, must-block-crouch),
- `unblockable` / `grab` (bloque le design anti-garde),
- priorite, `clash` (hit-vs-hit), `trade`,
- `hit_level` (light/med/heavy -> hit-stop et pushback differencies),
- `whiff` vs `blocked` vs `hit` (feedback et cancel differents).

### L6 — Quatre pipelines divergents (corrige : v1 disait trois)

Melee (`combat_system.py`), projectiles (`projectile_system.py`), degats de
hazards (`hazard_damage.py`) **et** degats de contact (`contact_damage.py`,
seuil `CONTACT_DAMAGE_THRESHOLD=300`) : quatre conventions de test
(hit-vs-hurt, hitbox-vs-hurtbox, box-vs-hitbox, hitbox-vs-hitbox + seuil de
vitesse), quatre gestions faction/invincibilite, quatre debug. Ordre par tick
(fichier `gameplay_loop.py:149-171`, load-bearing) : spawn -> plateformes ->
hazards -> physique -> combat+separation (`:157-159`, rebuild grille,
separation, sync boxes, `process_attacks`) -> projectiles (`:163-164`) ->
contact (`:170`) -> hazard-damage (`:171`) -> morts -> respawn. Tout ajout
(sweep, priorite) doit etre porte quatre fois tant que P4 n unifie pas.

### L7 — Authoring : source connue, drift possible, validation faible

Corrige (v1 disait "sans source de verite", c est faux) : a l execution, le
JSON prime (`provider.py:90-95`), le code en dur est un fallback documente
(`provider.py:1-17`). Parite verifiee en 2.3. Restent :

- Aucun test de parite JSON/builtin en CI : une edition d un seul cote
  diverge silencieusement jusqu au prochain lancement sans JSON.
- Validation geometrique faible au chargement (`attack_loading.py` ne verifie
  que les `cancel_into`) : taille nulle, offset aberrant, keyframes hors
  `0..startup+active` (partiellement garde en `__post_init__`), multi-phase
  sans `reset_targets`, cooldown incoherent.
- Pas de previsualisation : tuner = editer JSON, relancer, rejouer le coup a la main.

### L8 — Debug limite

Overlay actuel : boites instantanees. Manquent : trajectoire sweep (prev->cur), timeline startup/active/recovery, identifiant par boite, paires testees vs overlaps, dump tick par tick, pause + avance frame par frame.

### L9 — Perf et determinisme sous pression (mesure en 2.2)

Sain aujourd hui : ~0.003 ms/tick en 1v1, ~0.07 ms en 8v8 sur la detection
seule. Risques a la montee en charge : requete grille par `attack_box`
(O(n . k . b)), `tuple()` + `sorted()` par tick chaud dans
`_nearby_targets`, `FRect`/`inflate` temporaires dans les requetes spatiales,
pas de checksum geometrie pour le rollback (snapshot logique uniquement,
geometrie re-derivee — voir 2.4).

---

## 4. Axes d amelioration (meme refontes profondes)

### Axe A — CCD / sweep continu (anti-tunneling, prouve en 2.1)

Remplacer `box(t) capte hurt(t)` par `balayage(t-1 -> t) capte hurt`, sur la
geometrie ACTIVE uniquement (le startup est un telegraph non letal, voir 1.4).

- Conserver `HitboxManager.prev_rects`, exposer `swept_rects` = union
  prev+cur par index ; meme chose cote cible (`prev_hurtbox`,
  `swept_hurtbox`). Tester `swept.colliderect(target.swept)`.
- Alternative : 2-3 sous-pas sur phases rapides (vitesse > seuil). L union
  est preferable : O(1) par boite, pas de passe resolve supplementaire.
- Fichiers : `hitbox_manager.py`, `combat_system.py`, `entity.py`,
  `settings.py` (seuils).
- Effet attendu : capture le cas repro 2.1 (rate en discret, touche en
  swept) ; cout mesure en 2.2 comme reference pour le bench avant/apres.

### Axe B — Vrai modele push / hurt / hit

- `pushbox` = ancien `hitbox` physique (murs, sols, separation).
- `hurtbox[]` = 1..n zones vulnérables derivees du pushbox + inflate par zone + tags.
- `hitbox[]` = zones offensives (existant, a etendre).
- Migration : `sync_rects()` derive les trois, `separation_system` et `platform_system` n utilisent que `pushbox`, le combat n utilise que `hurtbox[]`.
- Pre-requis du grab (attrape = test pushbox-vs-pushbox a courte portee, pas hit-vs-hurt).

### Axe C — Hurtboxes multiples + hitboxes expressives

- Hurtboxes nommees : `head/torso/legs` avec `damage_mult` et `invuln_tags`. Exemple : jambes invulnees en saut, tete x1.2 sur uppercut adverse.
- Hitbox : `shape in (aabb, circle, capsule)`, `keyframes` par boite (pas que primaire), easing, suivi d un point d ancrage (hanche, epee).
- Extension `PhaseDefinition` / `HitboxSpec` + migration JSON avec defaults (compat ascendante).

### Axe D — Hauteur, garde, priorite, clash

- `HitProperties += height, block_mask, unblockable, grab_spec, priority, clash, hit_level`.
- Resolution hit-vs-hit avant hit-vs-hurt : si deux actives se chevauchent, `priority` decide (beat/trade/clash), sinon les deux passent en whiff-clash avec hit-stop court.
- Hauteur : `high` bloque debout, `low` bloque accroupi (necessite un etat accroupi, absent aujourd hui), `mid`/`overhead` selon design.
- Ouvre la porte au grab : `grab_spec(range, whiff_time, tech_window)` + etats `grabbed/throw`.

### Axe E — Pipeline de contact unifie (4 producteurs, voir L6)

Un seul `ContactSystem` : melee, projectiles, hazards **et contact** produisent
des `OffensiveBox(box, swept, hit, faction, owner_id)` ; une seule broadphase
`EntityGrid`, une seule narrowphase (sweep + formes + zones), une seule passe
resolve. Supprime la quadruple maintenance. Inventaire et migration en 3
commits : voir P4.

### Axe F — Authoring data-driven + validation

- Source de verite : `data/gameplay/attacks.json` (supprimer le doublon en dur ou le generer).
- Validateur au chargement : taille > 0, offset dans une enveloppe sprite, keyframes tries dans `0..startup+active`, `reset_targets` exige sur multi-phase, cooldown >= duree totale,Facing lock coherent.
- Editeur minimal : overlay qui rejoue une attaque en boucle avec trajectoire + export JSON.

### Axe G — Debug temps reel

- Overlay : sweep (rect prev + fleche), timeline phase, id par boite, paires testees/overlaps/contacts en direct, mode pause + step frame.
- Dump : log binaire ou JSON des `HitCandidate` par tick pour rejouer un whiff suspect.

### Axe H — Perf / determinisme / rollback

- Eviter `tuple(sorted())` par tick chaud : ordre par index pre-calcule, buffers reutilises.
- Checksum geometrie dans `CombatSnapshot` (hash des `rects` quantifies) pour detecter un desync.
- Fixed-point ou quantification si netcode futur (hors scope immediat).

---

## 5. Plan de refacto / implementation (P0 a P5)

Conventions takeover pour tout le plan : tout le rework sur l unique branche
`hitbox/rework` (P0 deja dessus : docstring, goldens, scaffolding xfail),
un commit par tache du tableau,
jamais de refactor opportuniste hors scope du palier. Apres chaque palier :
`uv run pytest -q` (719 + nouveaux), `uv run ruff check .`,
`uv run mypy src`, mesures section 2 rejouees, mise a jour de la section
recettage de ce rapport (date + resultats). Condition d arret : si un garde
fou liste ci-dessous casse et ne se repare pas en restant dans le scope du
palier, stopper et demander arbitrage au lieu de contourner.

Gardes-fous transverses (ne doivent jamais regresser) :
`tests/unit/test_hitbox_pipeline.py`, `tests/unit/test_combat_behaviors.py`,
`tests/unit/test_damage_resolution.py`, `tests/unit/test_rollback_snapshots.py`,
`tests/unit/test_rollback_system.py`, `tests/headless/test_rollback_e2e.py`,
`tests/headless/test_simulation_golden.py`, `tests/unit/test_gameplay_data.py`.

### P0 — Gel et filet de securite (0.5 j, sans casse)

Objectif : pouvoir mesurer avant/apres. Aucun changement de comportement.

| # | Tache | Ancres exactes | Reception |
|---|---|---|---|
| P0.1 | Test golden trajectoires | Etendre `tests/unit/test_hitbox_pipeline.py` (helpers : `tests/unit/helpers.py:26-57` `make_phase`/`make_attack`, `:97-119` `entity_at`/`activate`) | `dash_attack`, `sweeping_arc`, `sky_launcher` issus de `src/combat/attack_data.py:87-225` : centres/tailles de boites figes par frame d animation (`animation_frame`, `attack_state.py:125-140`) + recenser pour les 10 attaques le deplacement de centre startup->active (seed) et par frame (keyframes) : lister celles >= 4 px (sweep attendu en P1, ex. `sweeping_arc` ~7 px/frame) pour revalider le golden simulation comme changement voulu, pas regression. Etendre aux transitions de phase (`special_attack` 5 phases, `claw_swipe` 2) : premier ACTIVE de phase N balaie depuis son propre startup (continuite assuree par capture — pas d invalidation de `prev` au changement de phase, qui recrerait un tick discret) |
| P0.2 | Test de parite JSON/builtin | Nouveau cas dans `tests/unit/test_gameplay_data.py` ; sources : `src/data/provider.py:86-95`, `data/gameplay/attacks.json` (`sets.player`, 10 attaques), `src/combat/attack_data.py:18-310` | Noms + `cooldown` + `hitbox_size`/`hitbox_offset` des 10 attaques player identiques ; echoue si drift |
| P0.3 | Doc source de verite | Etendre la docstring `src/data/provider.py:1-17` | Phrase : JSON = source a l execution, builtin = fallback d absence uniquement |
| P0.4 | Bench de reference | Methode section 2.2 (300 iterations, roster ACTIVE) | Valeurs notees en recettage (ref 2026-09-20 : 0.003 / 0.029 / 0.075 ms) |
| P0.5 | Repro de reference | Rejouer l extrait section 2.1 dans un test temporaire | Trou confirme (`contacts=0`, union -> True), note en recettage |

### P1 — Sweep CCD borne (1-2 j, faible casse)

Objectif : capturer le cas repro 2.1 sans changer le format JSON. Scope :
geometrie ACTIVE uniquement (startup = telegraph non letal, voir 1.4).

**Decisions tranchees (ne pas rouvrir sans arbitrage) — version finale normative :**

- D1 — Seuil en deplacement mesure, pas en vitesse : nouvelle constante
  `Combat.SWEEP_MIN_DISPLACEMENT_PX = 4.0` (`src/core/settings.py:71-108`,
  classe `Combat`). Distance euclidienne des centres, par index de boite.
  Si < 4.0 px depuis le tick precedent, `swept = cur` (golden stables).
  Sinon `swept = prev.union(cur)`. Justification : deterministe (pas derive
  de `velocity` annulable par `separation_system.py:74-93`), 4 px < cible
  fine ~10 px. Si `prev` vide/`None` (spawn, premier tick) ou deplacement >
  `SWEEP_MAX_DISPLACEMENT_PX` (D4) : `swept = cur`. Starter seed normatif
  (contre-avis 3e/4e LLM, trace verifiee code) : `CombatComponent.start_attack`
  positionne en cas de succes la geometrie startup frame 0 dans `_pool` ET
  `_prev_pool`. Indispensable, pas optionnel : tous les starts ont lieu
  pendant `Entity.update`, donc APRES la capture (input joueur dans
  `_pre_update`, `player.py:231-234` ; enchainements `player_states.py:162` ;
  IA `enemy_states.py:321`). Un sync seul ne seederait jamais `prev` en
  production — la capture aurait deja copie un `_pool` vide. Le seed couvre
  le tick de transition (`startup=1` : `update()` bascule en ACTIVE avant le
  premier sync, `entity.py:833+842`), c est-a-dire exactement le lunge
  (`dash_attack`) ; la capture couvre les ticks suivants. Chaine verifiee
  code, meme tick : input -> `start_attack` -> interrupt synchrone
  (`state_machine.py:127-130`, `enter()` immediat `:158`) ->
  `PlayerAttackState.enter()` pose la vitesse lunge
  (`player_states.py:147`) -> `combat.update` -> `move` -> `sync` ->
  detection. Le mouvement suit donc bien le seed avant le sync : le test
  (b) reflete l ordre reel et « indispensable » est justifie (le repli
  « mouvement au tick suivant » n existe pas dans ce code). Prix documente :
  touche possible 1 tick depuis une position non letale. Resize
  (`len(prev) != len(cur)`) : `swept = cur` pour ces index. `update()` ne
  touche JAMAIS a `prev` (positionnement pur, idempotent par construction —
  le double-sync `Entity.update:842` + `gameplay_loop.py:272` devient
  inoffensif) ; seul `clear()` vide les deux (fin d attaque). Capture
  explicite : `HitboxManager.capture_origin()` (copie profonde `_pool` ->
  `_prev_pool`), appelee une fois en frontiere de tick par `gameplay_loop`
  avant `platform.process`, dans la meme boucle que
  `Entity.capture_sweep_origin()` (D3). Aucun etat cache, aucun cas tordu
  tick-sans-avance : la capture copie la fin du tick precedent dans tous
  les cas. dt sim FIXE (`game.py:117-119` : boucle a pas fixe `TIMESTEP`,
  propage inchange `level.py:198` jusqu a la boucle ; `MAX_FRAME_TIME`
  jette du temps en slow-mo, ne gonfle jamais dt — mesure : 0 tick sans
  avance sur 3000 a `dt=1/60`).
- D2 — Grille : requeter `EntityGrid.near()` avec le `swept_box` (pas
  `attack_box`). `QUERY_MARGIN_PX` inchange. Invariant bloquant : ensemble
  des candidats + contacts identiques avec/sans grille (`pairs_tested`
  non bloquant : incremente apres elagage `combat_system.py:153`, donc
  differe par construction ; le comparer a une valeur attendue par
  scenario). Helper dans `test_hitbox_sweep.py`.
- D3 — Snapshots : **abandonnee, aucun champ ajoute** (contre-avis 3e LLM,
  verifie par l experience ci-dessus). Ni `CombatSnapshot.prev_attack_boxes`
  ni `EntitySnapshot.prev_hurtbox` : avec la capture frontiere explicite,
  `prev` est re-derive a chaque tick (load -> sync re-derivant `cur` ->
  capture copiant `cur` vers `prev`), jamais relu a travers un load sans
  etre re-capture avant (la capture ouvre chaque tick simule, avant
  `platform.process` ; les tests la rejouent explicitement, voir reception
  (c)). `load_state` des deux cotes remet `prev` a vide/None par hygiene
  (jamais observe : defaut sur = discret deterministe, pas de stale).
  Reste au plan : l extension `CombatPort`/`Combatant`
  (`combatant_protocol.py`) avec `swept_attack_boxes` + `swept_hurtbox()`
  (lecture narrowphase, pas de `getattr` sauvage), `NullCombatComponent` +
  `_NullHitboxManager` exposant `swept/prev = ()`, quantification
  `round(x, 1)` des unions si stockees. Sweep cible bilateral (`swept` vs
  `swept`) documente comme genereux voulu (cible esquivant de > 4 px
  touchable 1 tick, cas `test_dodge`).
- D4 — Borne haute (contre-avis 2e LLM, palier dit "borne" mais seul un
  seuil bas existait) : `Combat.SWEEP_MAX_DISPLACEMENT_PX = 64.0`. Au-dela
  (respawn a travers la carte, correction teleport, carry anormal),
  `swept = cur` (pas de smear geant, pas de touche fantome). Justifie a dt
  sim FIXE (`game.py:117-119`, `TIMESTEP` = 1/60 propage inchange) : pire cas
  legitime par tick = chute 1500/60 = 25 px (+ keyframe ~7 px + lunge),
  knockback max ~1082 px/s x charge 2.0 = 2164 px/s soit 36 px
  (`special_attack` phase 4 : 900,-600 ; juggle <= 1, finisher/dizzy =
  degats seuls) ; 64 px garde x1.6+ de marge et reste < toute
  discontinuite. Pas de spike de
  dt possible (`MAX_FRAME_TIME` jette du temps, ne le gonfle pas), donc un
  plafond fixe suffit — pas de plafond derive du dt. `reset_position()`
  (`entity.py:594-611`) doit aussi raz `_prev_hurtbox` (`combat.reset()` ->
  `hitbox.clear()` couvre deja `_prev_pool` via checklist). Test (g) dedie :
  teleport/respawn -> aucun contact fantome ; test (i) : invariant
  `SWEEP_MAX_DISPLACEMENT_PX >= VMAX * TIMESTEP * 1.5` avec VMAX = max sur
  (`Physics.MAX_FALL_SPEED`, `DASH_SPEED`, magnitudes knockback de
  `attacks.json`, `JUMP_FORCE`).

**Arbitrage 2026-09-20 (contre-avis integres, ne pas rouvrir) :**
D1/D2/D4 ci-dessus sont la version normative, **D3 snapshot abandonnee**.
D1 seedee via starter seed (pool+prev) dans `start_attack` + capture
frontiere explicite (double-sync traite par construction, sans etat cache ;
le sync seul, sans seed de `prev`, ne servirait a rien puisque tous les
starts ont lieu apres la capture). D2 sans `pairs_tested` bloquant. D3
remplacee par re-derivation (load -> sync `cur` -> capture `prev`) : aucun
champ snapshot, `load_state` remet `prev` a vide/None. D4 borne haute
justifiee a dt sim fixe (`TIMESTEP`, pas de spike de dt possible).
P0 recense les deplacements startup->active >= 4 px par attaque (golden
simulation a revalider comme changement voulu, pas regression).

**Checklist d implementation (ordre impose) :**

1. `src/core/settings.py` (classe `Combat`, apres `OTG_INVULN_DURATION:107`) :
   ajouter `SWEEP_MIN_DISPLACEMENT_PX = 4.0` + `SWEEP_MAX_DISPLACEMENT_PX = 64.0`
   + commentaires (D1 + D4).
2. `src/combat/hitbox_manager.py` :
   - `__init:22-26` : ajouter `self._prev_pool: list[pygame.FRect] = []`.
   - `update:32-52` : positionnement pur, NE TOUCHE JAMAIS a `_prev_pool`
     (idempotent par construction ; le seed et la capture en sont les seuls
     ecrivains avec `clear()`).
   - ajouter `capture_origin()` (copie profonde `_pool` -> `_prev_pool`),
     `prev_rects` (tuple, copie) + `swept_rects` (par index : `cur` si `prev`
     vide, taille differente (resize), ou deplacement < MIN ou > MAX (D4),
     sinon union prev+cur).
   - `clear:54-57` : vider aussi `_prev_pool`.
   - `rects:28-30` inchange (contrat `attack_boxes` preserve).
   - `combat_component.start_attack` (`:202-246`) : en cas de succes, seeder
     `_pool` ET `_prev_pool` avec la geometrie startup frame 0 (starter seed
     D1 : positionner via `sync_attack_box()` puis copier vers `prev`).
     Sans le seed de `prev`, le 1er tick ACTIVE serait discret en production
     (tous les starts ont lieu apres la capture).
3. `src/entities/entity.py` + `gameplay_loop.py:149-155` :
   - `__init__` (pres `:174-176`, champs `_hurtbox`) : ajouter
     `self._prev_hurtbox: FRect | None = None`.
   - ajouter `capture_sweep_origin()` (copie `_hurtbox` vers `_prev_hurtbox`)
     + `swept_hurtbox()` (par D1/D4 : `cur` si `prev` None, ou deplacement
     < MIN ou > MAX, sinon union ; bilateral genereux voulu, voir D3).
   - `gameplay_loop.update` : avant `platform.process`, boucle frontiere —
     `capture_sweep_origin()` sur `entity_sprites`,
     `combat.capture_attack_origin()` sur `combat_sprites` (D1/D3 ; couvre
     aussi le segment pre-carry, contrairement a un debut de `Entity.update`
     qui court apres le carry).
   - `reset_position:594-611` : raz `_prev_hurtbox` (= `None`) pour
     respawn/teleport sans smear (D4).
   - Snapshots (`entity.py:846-918`, `combat_component.py:320-353`) :
     AUCUN champ ajoute (D3 abandonnee) ; `load_state` remet `prev` a
     vide/None (hygiene, jamais observe avant la capture suivante).
4. `src/core/level/systems/combat_system.py` :
   - `_nearby_targets:61-85` : accepter la boite de requete en parametre
     (swept) au lieu de `attack_boxes` brutes ; tri par `order` inchange.
   - `_collect_candidates:134-167` : par attaquant, zipper
     `attack_boxes` + `combat.hitbox.swept_rects` (acceder via
     `CombatPort` etendu ou `getattr` documente — voir note contrats
     ci-dessous) ; requete grille sur le swept ; test
     `swept.colliderect(target.swept_hurtbox())`.
   - Note contrats : le chantier R-3 (`notes/audit_consolide.md`) veut zero
     `getattr` dans `hit_resolver.py` uniquement. Ici, etendre
     `CombatPort`/`Combatant` (`combatant_protocol.py`) avec
     `swept_attack_boxes` + `swept_hurtbox()` + `capture_attack_origin()`
     plutot qu un `getattr` sauvage ; `CombatComponent` implemente
     `capture_attack_origin()` (delegue a `hitbox.capture_origin()`),
     `NullCombatComponent`/`_NullHitboxManager` en no-op exposant
     `swept/prev = ()` ; les doubles `tests/unit/helpers.py:122-162`
     (`_ActiveAttackerCombat`) doivent implementer les nouveaux membres.
5. Rollback : D3 (re-derivation : `load_state` re-sync `cur`, la capture
   frontiere suivante refait `prev` ; aucun champ restaure) + cas
   `test_rollback_restore_synchronizes_derived_attack_geometry`
   (`test_hitbox_pipeline.py:109-120`) etendu (le test rejoue
   `capture_*` explicitement, comme la boucle).
6. `QUERY_MARGIN_PX` : ne pas toucher (regle D2).

**Reception P1 :** nouveau `tests/unit/test_hitbox_sweep.py` :
(a) scenario moteur de la section 2.1 (saut 40 px, ACTIVE, cible fine : miss en
discret simule par boxes finales, hit via sweep — le test rejoue la capture
frontiere comme `gameplay_loop`) ; (b) lunge frame 1 dans l ordre REEL
(`startup=1` : `capture_*` (prev vide) -> `start_attack` (seed pool+prev =
startup) -> `update(1/60)` (bascule ACTIVE) -> deplacement proprietaire 40 px
(lunge) -> `sync_attack_box` -> contact via sweep LE MEME tick ; sans le seed
de `prev`, discret et aucun contact — c est exactement ce cas qui impose le
starter seed) ; (b') `startup >= 2` : tick N (capture, start, update qui reste
STARTUP, sync), tick N+1 (capture -> `prev` = startup naturel, update ->
ACTIVE, sync, contact) ; (b'') transition de phase (`special_attack`,
`claw_swipe`) : premier ACTIVE de phase N balaie depuis son propre startup,
jamais depuis l ACTIVE de phase N-1 (pas d invalidation de `prev` : les
phases sont toujours separees par recovery + startup, `attack_state.py`) ;
(c) `save_state` / `load_state` puis `capture_*` puis contact au tick suivant
(non-regression 2.4 ; prouve la re-derivation D3 sans champ snapshot) ;
(d) parite grille : candidats + contacts avec/sans `EntityGrid` identiques sur
(a)-(b) (`pairs_tested` non bloquant : incremente apres elagage) ;
(e) golden P0.1 inchanges, golden simulation revalide contre le recensement P0
(sweep attendu sur attaques >= 4 px : changement voulu, pas regression) ;
(f) `test_dodge` : cible esquivant de > 4 px reste touchable 1 tick (sweep
bilateral genereux documente) ; (g) `test_teleport` : deplacement > MAX
(respawn, gros carry) -> `swept = cur`, aucun contact fantome ;
(h) proprietaire decale entre les deux syncs (push separation simule) :
`prev` intact, sweep pleine largeur ; (h') attaquant immobile 3 ticks :
`swept == cur` des le 2e tick ; (i) invariant
`SWEEP_MAX_DISPLACEMENT_PX >= max(MAX_FALL_SPEED, DASH_SPEED, JUMP_FORCE,
KB_MAX * CHARGE_MAX) * TIMESTEP * 1.5` avec KB_MAX = magnitude max des
`power` de `attacks.json`, `CHARGE_MAX = 2.0` (`charge_handler.py:114-115` ;
le knockback vitesse REMPLACE la velocite, `reaction.py:183-190`, donc pas
d addition de termes — juggle <= 1, finisher/dizzy = degats seuls) :
max(1500, 1100, 750, 1082*2) / 60 * 1.5 = 54.1 <= 64. dt sim fixe
`TIMESTEP`, pas de spike possible).
Bench : valeurs 2.2 sans regression > 10 % meme machine.
Gardes-fous transverses verts.

### P2 — Push / hurt / hit + multi-hurtbox (3-5 j, refonte moyenne)

Objectif : separer corps physique et vulnerabilite, supporter zones multiples. Compatible ancien JSON via defaults.

Pre-requis : P1 vert (le sweep s applique ensuite par zone : `swept` par
hurtbox, break des la premiere zone touchee).

**Checklist d implementation (ordre impose) :**

1. `src/entities/entity.py` (ancres : `__init__` ~`:113-176`,
   `hurtbox` `:398-401`, `sync_rects:430-438`, snapshots `:44-57,:846-918`) :
   - Introduire `pushbox` comme nom interne du collider physique actuel ;
     garder `hitbox` en alias (propriete deleguant au meme `FRect`) pendant
     une version — ne rien renommer chez les appelants a ce palier.
   - `hurtboxes: tuple[FRect, ...]` + `hurtbox_tags: tuple[tuple[str, ...], ...]`
     + `hurtbox_mult: tuple[float, ...]`, derives du pushbox via
     `hurtbox_zones` (1 zone par defaut = comportement actuel exact).
     Conserver `hurtbox` (singulier) = union des zones (compat : tous les
     systemes non migres continuent de compiler et de se comporter pareil).
   - `sync_rects()` derive pushbox -> `rect` sprite + chaque zone ;
     `swept_hurtbox()` (P1) devient `swept_hurtboxes()` (la version
     singulier delegue a l union).
   - Snapshots : zones derivees => rien a stocker sauf `hurtbox_zones`
     (config, pas runtime) ; `_prev_hurtbox` P1 devient `_prev_hurtboxes`.
2. Data (fallback inchange sur l ancien champ) :
   - `src/entities/player_config.py:93` (`hurtbox_inflate`) et
     `src/entities/enemies/schema.py:18` : ajouter `hurtbox_zones` optionnel
     `[{name, inflate, mult, tags}]`, defaut `None` => 1 zone legacy.
   - `src/data/player.py:83-84` + `src/data/enemies.py:95-96` (parsers
     `hurtbox_inflate`) : parser le nouveau champ, fallback sur l ancien.
   - `data/gameplay/player.json` + `enemies.json` : ne rien changer (defaults).
3. `src/combat/hitbox_manager.py` : keyframes par boite (P2.3 de la checklist
   P1 etendue) : `HitboxSpec` (`frame_data.py:106-130`) +=
   `keyframes: tuple[HitboxKeyframe, ...] = ()` ; `_position_rects:59-82`
   interpole chaque box via sa propre courbe (`hitbox_at` factorise en
   fonction utilitaire prenant `keyframes`). Primaire inchange si pas de
   keyframes extras (golden P0.1).
4. `src/core/level/systems/combat_system.py` :
   - `HitCandidate:20-28` += `zone_index: int = 0`, `zone_mult: float = 1.0`.
   - `_collect_candidates:134-167` : boucle zones (swept par zone), break a
     la premiere zone touchee non invulnerable (`invuln_tags` vs tags du
     coup — tags du coup : aucun en P2, champ reserve).
   - `_resolve_candidates:169-218` : `HitResolver.resolve(..., zone_mult)`
     ou multiplication dans le resolver (trancher a l implementation, noter
     le choix dans le commit).
   - Doubles `tests/unit/helpers.py:122-162` : ajouter zones par defaut.
5. Migration appelants (alias `hitbox` => aucun changement fonctionnel
   requis a ce palier ; verifier par grep `\.hitbox` dans `src/` que seuls
   ces systemes touchent au corps physique, tous conservent l alias) :
   - `separation_system.py:21-67` (corps-a-corps + `sync_rects:66-67`),
   - `platform_system.py` (carry `hitbox`/`old_hitbox`),
   - `hazard_damage.py:18-31` (`box.colliderect(entity.hitbox)`),
   - `contact_damage.py` (`hitbox.colliderect`, seuil 300),
   - `physics/movement.py:244-280` + `collisions.py` (inchanges).
6. Debug : `src/ui/world_ui.py:291-322` — une couleur par zone + label
   (`head/torso/legs`), sweep P1 dessine en pointille.

**Reception P2 :** `tests/unit/test_multi_hurtbox.py` (1 zone par defaut =
byte-identique au legacy ; tete x1.2 via `hurtbox_mult` ; jambes invulnees
en saut via tags ; squish dash `player.py` n elargit pas la vulnerabilite) ;
roundtrip JSON ancien/nouveau champ ; golden P0.1 + sweep P1 verts ;
gardes-fous transverses + `test_projectile_system.py`,
`test_hazard_damage.py`, `test_entity_pairing_systems.py`,
`test_movement_collision_cache.py` verts ; `mypy`/`ruff` propres.

### P3 — Hauteur / priorite / clash + base grab (3-5 j, en 2 temps)

Objectif : semantique de coup moderne. Etend le JSON (defaults = comportement actuel).

**Dependance bloquante :** aucun etat accroupi n existe (`player_states.py` :
idle/run/jump/fall/wall_slide/attack/charge/guard/hurt/knockback/dash/
stagger/dizzy). Donc en 2 temps :

- Temps 1 (sans nouveau state) : `unblockable`, `priority`, `clash`,
  `hit_level` + passe hit-vs-hit. Aucune hauteur exploitable avant l accroupi.
- Temps 2 (quand l accroupi existera) : `height` (high/low/mid/overhead) +
  `block_mask` dans `Guard.take_hit`.

1. `frame_data.py` (temps 1) : `HitProperties += unblockable: bool=False, priority: int=0, clash: str=trade, hit_level: str=med` (`HitProperties:48-103`, quantites validees en `__post_init__:97-103` — ajouter `priority >= 0`, `clash in (...)`, `hit_level in (...)`). Lecteurs JSON : `src/data/attacks.py` (`read_attacks_file`, utilise par `provider.py:92-93`) : defaults identiques (test P0.2 etendu aux nouveaux champs).
2. `CombatSystem` : passe hit-vs-hit avant hit-vs-hurt, dans
   `_collect_candidates:134-167` (collecter aussi les paires box-vs-box
   ennemies actives) puis `_resolve_candidates:169-218`. Deux boxes actives
   ennemies qui se chevauchent : priorite superieure gagne (l autre candidat
   est retire avant resolve), egalite = clash (les deux attaques s annulent
   via `combat.state.end()` + `hitbox.clear()` + hit-stop court
   `Combat.HITSTOP_BASE` + event `GuardEvent("clash", ...)` draine par
   `gameplay_loop.py:214-218` comme les autres), sinon trade (les deux
   resolvent, ordre deterministe existant).
   Ancres hit-stop : `combat_system.py:202-214` ; trauma :
   `gameplay_loop.py:235-240` (`_trauma_for_event` : ajouter `clash` ->
   `GUARD_TRAUMA`, pas de nouvelle constante).
3. Grab : **hors chantier, rapport dedie.** La base requiert etat `grabbed`,
   lock des deux cotes, whiff recovery, tech window, invuln de chope et
   distinction push-vs-hit (depend de P2) : trop pour 4 lignes de spec.
   P3 ne fournit que le pre-requis (`unblockable` + pushbox P2).
4. `Guard` (`player_controllers.py:186-202` + `player.py:267-296`
   `_apply_guard_reaction`) : `take_hit` prend en compte `unblockable`
   (temps 1 ; retourne le chemin non-garde) puis `height`/`block_mask`
   (temps 2), chip (`Guard.CHIP_RATIO`) et posture inchanges sinon.
   Gardes-fous : `test_guard_fx.py`, `test_parry_stun.py`,
   `test_combat_behaviors.py`.

Reception : `test_priority_clash.py` (beat/trade/clash), attaques existantes
inchangees (defaults) ; `test_height_block.py` reserve au temps 2.

### P4 — Unification + validation + editeur debug (3-4 j)

Pre-requis : P1-P3 verts. Ne pas commencer avant : l interface unifiee fige
les contrats sweep + zones + clash.

Inventaire des producteurs a unifier (ordre tick `gameplay_loop.py:149-171`) :
`combat_system.process_attacks(:273)` <- `sync_attack_box(:272)` ;
`projectile_system.process(:163-164, entity_grid)` ;
`contact_damage.process(:170, entity_grid)` ; `hazard_damage.process(:171)`.
Enregistrement : `level.py:122-147` ; re-export `systems/__init__.py:17-41`.

**Checklist :**

1. Nouveau `ContactSystem` (fichier `src/core/level/systems/contact_system.py`,
   exporte dans `systems/__init__.py`) : interface minimale
   `produce_boxes() -> Iterable[OffensiveBox]` avec
   `OffensiveBox(box, swept, hit, faction, owner_id, can_contact, record_contact)` ;
   une broadphase (`EntityGrid.near(swept)`), une narrowphase (sweep P1 +
   zones P2), une resolve (priorite/clash P3 puis `HitResolver`).
   Migration en 3 commits separes, chacun reversible : (a) melee deleguee
   (l ancien `CombatSystem.process_attacks` devient un adaptateur fin),
   (b) projectiles (`projectile_system.py:88-121`), (c) hazards
   (`hazard_damage.py:18-31`) + contact (`contact_damage.py` + seuil 300
   conserve). `gameplay_loop.py:157-171` appelle le systeme unifie ; les
   anciens systemes restent presents mais non appeles pendant une version
   (suppression au palier suivant, pas dans P4).
2. `attack_loading.py:11-30` (`load_attacks`, seule validation actuelle =
   `cancel_into`) : validateur strict — taille > 0, offset dans enveloppe
   sprite (marge 2x taille sprite 40x48 documentee `frame_data.py:191-201`),
   keyframes dans `0..startup+active` et strictement croissants (complete
   `__post_init__:247-253` avec messages nommant attaque + phase + champ),
   multi-phase sans `reset_targets: False` intermediaire => avertissement,
   `cooldown >= duree totale / FRAME_RATE`. Erreur au chargement via
   `GameplayDataError` (coherent `provider.py`), jamais de fallback silencieux.
3. Overlay `world_ui.py:291-322` : sweep (prev + fleche), timeline
   startup/active/recovery (`attack_state.py` expose deja `sub_state` +
   `frame_counter`), id par boite (`box_id` = index), compteurs
   `CombatMetrics` live, pause/step (reutiliser le flag FROZEN
   `gameplay_scene.py:120`). Commandes debug `F1-F6` : rejouer une attaque
   en boucle (`spawn_system.py:44` montre le cablage touches->attaques).
4. builtin `attack_data.py` conserve comme fallback documente (decision 2.3),
   couvert par le test de parite P0.2 (pas de suppression).

**Reception P4 :** `tests/unit/test_contact_unified.py` (parite exhaustive :
avec/sans unification, memes `DamageResult` + memes cibles touchees sur
scenarios melee + projectiles + hazards + contact) ;
`tests/unit/test_attack_validation.py` (chaque regle rejette un JSON invalide
avec message nommant attaque/phase/champ) ; gardes-fous :
`test_projectile_system.py`, `test_hazard_damage.py`,
`test_entity_pairing_systems.py`, `test_level_events.py` ;
`test_debug_commands.py` (commandes F1-F6) vert.

### P5 — Formes avancees capsule/cercle/OBB (optionnel, 1-2 sem.)

Seulement si le game-design l exige (armes rotatives, arcs verticaux). Cout eleve : narrowphase cercle/capsule + sweep oriente, migration des keyframes, re-tuning complet, debug specifique. Recommandation : ne pas engager sans besoin avéré, les axes A-D couvrent l essentiel pour un platform-fighter AABB.

### Ordre et jalons

```
P0 (gel + parite + bench) -> P1 (sweep ACTIVE) -> P2 (push/hurt/hit) -> P3t1 (priorite/clash/unblockable) -> [P3t2 hauteur quand accroupi] -> P4 (unification/debug) -> [P5 optionnel]
```

Chaque palier : 719 tests verts + nouveaux, `ruff check`, `mypy src`, golden trajectoires, bench 2.2 sur la meme machine, mise a jour de ce rapport (section recettage datee).

---

## 6. Modele cible (schemas et exemples)

### 6.1 Structures cibles (illustratif, pas de code a copier tel quel)

```python
@dataclass(frozen=True)
class HurtZone:
    name: str                # head | torso | legs
    inflate: tuple[float, float]
    damage_mult: float = 1.0
    invuln_tags: tuple[str, ...] = ()

@dataclass(frozen=True)
class HitboxSpecV2:
    shape: str               # aabb | circle | capsule (P5)
    size: tuple[float, float]
    offset: tuple[float, float]
    keyframes: tuple[HitboxKeyframe, ...] = ()  # P2 : par boite
    follow: str = "torso"    # point d ancrage

@dataclass(frozen=True)
class GrabSpec:
    # Reserve : spec detaillee dans un rapport grab dedie, pas dans ce chantier.
    # Pre-requis fournis ici : pushbox P2 + unblockable P3 temps 1.
    grab_range: float
    whiff_frames: int
    tech_window: float

@dataclass(frozen=True)
class HitPropertiesV2:
    damage: float
    knockback: KnockbackConfig
    damage_type: DamageType
    unblockable: bool = False           # P3 temps 1
    priority: int = 0                   # P3 temps 1
    clash: str = "trade"                # P3 temps 1 : trade | beat | lose | clash
    hit_level: str = "med"              # P3 temps 1 : light | med | heavy
    height: str = "mid"                 # P3 temps 2 (requiert etat accroupi)
    block_mask: str = "any"             # P3 temps 2
    # champs existants conserves : stagger, super_armor_break,
    # is_finisher, juggle_gravity_mult, otg_allowed
    # grab : hors chantier, rapport dedie (pre-requis = P2 pushbox + unblockable)
```

### 6.2 Exemple JSON migre (retro-compatible)

```json
{
  "light_attack": {
    "phases": [{
      "startup_frames": 3, "active_frames": 6, "recovery_frames": 3,
      "hitboxes": [
        {"shape": "aabb", "size": [40, 20], "offset": [24, -4],
         "keyframes": []}
      ],
      "hit": {"damage": 8, "damage_type": "slash", "stagger": 0.1,
              "priority": 0, "hit_level": "light"}
    }],
    "cooldown": 0.30
  }
}
```

Ancien format (`hitbox_size`/`hitbox_offset` uniques, `hurtbox_inflate` global) reste charge via normalisation vers le nouveau modele.

### 6.3 Narrowphase cible (pseudo-code)

```python
for attacker in actifs:
    for box in attacker.swept_boxes:          # union prev+cur, par box_id
        for target in grid.near(box):
            if not eligible(attacker, target): continue
            for zone in target.swept_zones:   # union prev+cur, par zone
                if box.shape_vs_zone(box, zone) and not invuln(zone, box):
                    emettre HitCandidate(attacker, target, box_id, zone, hit)
                    break  # une zone suffit par box
# puis passe hit-vs-hit (clash/priorite), puis hit-vs-hurt (degats)
```

---

## 7. Validation et reception

### 7.1 Commandes

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run pytest tests/unit/test_hitbox_pipeline.py -q
# Apres P1 :
uv run pytest tests/unit/test_hitbox_pipeline.py tests/unit/test_hitbox_sweep.py -q
```

### 7.2 Tests par palier

| Palier | Fichier | Cas |
|---|---|---|
| P0 | `test_hitbox_pipeline.py` (etendu P0.1) + parite (P0.2) | positions figees `dash_attack`, `sweeping_arc`, `sky_launcher` frame par frame ; parite JSON/builtin |
| P1 | `test_hitbox_sweep.py` (nouveau, spec en P1) | cas (a)-(i)+b'+b'' : saut 40 px, lunges seedes startup 1 et >= 2, transition de phase, rollback re-derive, parite grille, goldens revalides, dodge, teleport, double-sync, stationnaire, invariant MAX |
| P2 | `test_multi_hurtbox.py` (nouveau, spec en P2) | defaut byte-identique, tete x1.2, jambes invulnees en saut, squish dash |
| P3 | `test_priority_clash.py` (nouveau) | beat/trade/clash, attaques existantes inchangees (defaults) |
| P3t2 | `test_height_block.py` (reserve) | high/low, requiert l etat accroupi (non planifie ici) |
| P4 | `test_contact_unified.py`, `test_attack_validation.py` | 4 producteurs unifies, JSON invalide rejete avec message |
| Tous | golden + bench + gardes-fous | trajectoires inchangees a vitesse normale, bench 2.2 < +10 %, section 5 |

### 7.3 Criteres globaux

- 719 tests verts de reference (`pytest -q` : 719 passed le 2026-09-20), `ruff` et `mypy` propres.
- Aucune regression visuelle sur les 5 attaques vitrines (`twin_fangs`, `sweeping_arc`, `sky_launcher`, `otg_slam`, `special_attack`).
- Determinisme : deux runs meme seed = memes `CombatMetrics` et memes positions.
- Rollback : `save/load` + capture frontiere re-derive `prev` (aucun champ snapshot) et ne rate aucun contact au tick suivant.
- Mesures rejouables : l extrait 2.1 et la methode 2.2 restent valides a chaque palier.

---

## 8. Risques et non-objectifs

### Risques

| Risque | Mitigation |
|---|---|
| Sweep trop genereux (touches fantomes) | Seuils D1 (4 px) + D4 (cap 64 px, raz au reset), golden P0.1 + recensement >= 4 px, `QUERY_MARGIN_PX` inchange (regle D2), tests `test_dodge`/`test_teleport` |
| Explosion combinatoire (boxes x zones x cibles) | Break par box des la premiere zone touchee, broadphase sur swept, bench 8v8 |
| Migration JSON cassante | Test de parite P0.2, defaults = comportement actuel, roundtrip teste |
| Desync rollback silencieux | Re-derivation D3 (load-sync `cur` + capture `prev`, aucun champ), tests save/load P1(c), parite grille P1(d) |
| Refonte P2 qui touche physique + separation + plateformes | Alias `hitbox` conserve (aucun renommage appelant en P2), inventaire section P2.5 |

### Non-objectifs (sauf P5 valide)

- Netcode / rollback reseau (seule la proprete locale est visee).
- Capsules / OBB / polygones tant que le roster reste AABB.
- Editeur visuel complet (overlay + rejouabilite suffisent).
- Equilibrage des degats (les valeurs restent inchangees, seule la detection s ameliore).

---

## 9. Decision attendue

1. Valider l ordre P0 -> P1 -> P2 -> P3t1 -> P4, P3t2 et P5 optionnels.
2. Source de verite data : tranche (preuve 2.3) — JSON = source a l execution,
   builtin = fallback d absence ; P0 ajoute le test de parite et la docstring.
3. Grab : rapport dedie separe (P3 ne fournit que `unblockable` + pushbox P2).
4. Decisions P1 D1/D2/D4 : **validees le 2026-09-20**, **D3 snapshot abandonnee**
   (remplacee par capture frontiere + re-derivation — voir arbitrage).
   D1 seedee via starter seed (pool+prev) + capture explicite, D2 sans
   `pairs_tested` bloquant, D4 borne haute 64 px a dt fixe. Ne pas rouvrir
   sans arbitrage ; precisions normatives integrees ci-dessus avant
   lancement P1.

---

## 10. Recettage par palier (l agent y consigne date + resultats)

| Palier | Date | pytest | ruff | mypy | Repro 2.1 rejoué | Bench 2.2 (1v1/4v4/8v8) | Note |
|---|---|---|---|---|---|---|---|
| Ref (pre-P0) | 2026-09-20 | 719 passed | propre hors `main.py`* | propre (120 fichiers) | trou confirme | 0.003 / 0.029 / 0.075 ms | rapport takeover-ready, sans scripts |
| P0 | 2026-09-20 | 723 passed (719 + 4 P0.1) | propre (src+tests) | propre | trou confirme (`contacts=0 overlaps=0 pairs=1`, union -> True) | 0.002 / 0.016 / 0.056 ms (sans grille, meme machine, meme ordre de grandeur) | P0.1 goldens 3 attaques + census (aucun saut letal >= 4 px) ; P0.2 parite pre-existante (egalite complete 3 sets) ; P0.3 docstring source de verite |
| P1 | 2026-09-20 | 735 passed (724 + 3 debloques (b)/(b')/(b'') + 8 reception) | propre (src+tests) | propre (121 fichiers) | corrige — miss discret confirme, hit via sweep (contacts=1) | non rejoue (hors checklist P1) | commits P1.1-P1.5 : constantes D1/D4 + `src/combat/sweep.py` ; `HitboxManager` prev pool + seed starter + hygiene D3 ; `swept_hurtbox` Entity + capture frontiere dans `gameplay_loop.update` ; `CombatSystem` sur swept (grille D2 + contacts bilateraux) ; reception (a),(c),(d),(f),(g),(h),(h'),(i) + invariant borne MAX 64 px |
| P2 | | | | | | | |
| P3t1 | | | | | | | |
| P4 | | | | | | | |

\* `uv run ruff check .` signale 2 erreurs pre-existantes dans `main.py`
(imports, newline) : hors scope hitbox, ne pas les imputer au chantier.
