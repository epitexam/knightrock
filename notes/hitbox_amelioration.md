# Rapport Hitbox — Audit et plan de refonte / implementation

- **Date :** 2026-09-20 (ameliore 2026-09-20 preuves ; 2026-09-22 gap audit ; **2026-09-23 re-audit doc** ; **2026-09-24 conformite partielle**)
- **Perimetre :** `src/combat/`, `src/physics/`, `src/entities/entity.py` + `hurtbox_zones.py`, `src/core/level/systems/combat_system.py` + `contact_system.py`, `src/core/level/systems/projectile_system.py`, `src/core/level/systems/hazard_damage.py`, `data/gameplay/attacks.json`, `data/gameplay/enemies.json` (zones goblin P2), `src/ui/world_ui.py` (debug)
- **Methode :** lecture du code + greps + mesures executees (repro tunneling, bench detection sec 2.2, parite JSON/builtin) ; suite de reference evolvee 719 -> **910** (voir §10)
- **Statut grab (rappel) :** aucun systeme de grab/throw/command-grab n existe. Seul faux positif : `generator.throw()` dans un test.
- **Base de tests :** **910 tests verts** (`pytest -q` le 2026-09-24), `ruff check .` propre, `mypy src` propre (128 fichiers) — detail §10.
- **Lecture du diagnostic :** §3 decrit l etat **pre-P0** ; chaque item clos porte une balise `**[clos Pn]**` (etat actuel = code + §10). Ne pas re-traiter un item balise clos sans nouveau repro.

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

### 1.1 Architecture actuelle (etat 2026-09-24, post P0-P5)

```
AttackDefinition (frame_data.py)
  └─ phases: PhaseDefinition[startup | active | recovery]
       ├─ hitbox_size / hitbox_offset (boite primaire, AABB ou forme P5)
       ├─ extra_hitboxes: HitboxSpec[] (secondaires ; keyframes par boite P2.3)
       ├─ hitbox_keyframes: HitboxKeyframe[] (primaire + extras si declares)
       └─ hit: HitProperties (damage, knockback, unblockable, priority,
             clash, height, hit_level, block_mask, tags)

CombatComponent (combat_component.py)
  ├─ AttackStateMachine (frame_counter, facing locke, targets_hit, charge)
  ├─ HitboxManager (pool de pygame.FRect, rect = rects[0], prev + swept P1)
  ├─ ComboTracker / ChargeHandler
  └─ is_hurt / hurt_timer / cooldowns

CombatSystem (combat_system.py) — P4.1 : producteur + hit-vs-hit
  └─ ContactSystem (contact_system.py) — moteur unifie 4 producteurs
       1. _candidates : requete EntityGrid autour de chaque swept (melee)
          ou box discrete (projectile/hazard/contact), eligibilite, ordre
       2. _resolve_melee/_resolve_generic : HitResolver.resolve()
          + record_contact + hit-stop + ZoneContact(zone_index/zone_mult)

Entity (entity.py + hurtbox_zones.py)
  ├─ pushbox   : collision corps-a-corps / separation (P2.1)
  ├─ hitbox    : alias legacy = ancrage offensif / collider env.
  └─ hurtboxes[]: zones derivees dans sync_rects (P2.1)
       + tags/mult/noms (P2.2) + swept par zone (P2) + union legacy `hurtbox`
```

### 1.2 Fichiers de reference

| Fichier | Role | Points cles |
|---|---|---|
| `src/combat/frame_data.py:49-367` | `HitProperties`, `PhaseDefinition`, `HitboxSpec`, `HitboxKeyframe` | Formes AABB/cercle/capsule/OBB ; keyframes, easings et anchors par boite ; `reset_targets=True` par defaut |
| `src/combat/hitbox_manager.py:13-205` | Positionnement offensif | Pool sans alloc, AABB/formes, easings/anchors, keyframes, `prev`/`swept` (P1/P5) |
| `src/combat/combat_component.py:123-162,406` | Orchestrateur par entite | `attack_box` (legacy) + `attack_boxes` (tuple), `can_contact` / `record_contact` via `targets_hit` |
| `src/core/level/systems/contact_system.py:54-432` | Pipeline unifié | `OffensiveBox`, broadphase, narrowphase AABB/formes, zones, résolution, trace et checksums |
| `src/combat/hit_resolver.py:99-202` | Degats, knockback, stagger, finisher, dizzy, invincibilite | Passe `unblockable`/`height`/`zone_mult` (P2/P3) ; priority/clash resolus en amont (`_resolve_hit_vs_hit`) |
| `src/entities/entity.py:186-547` + `src/entities/hurtbox_zones.py` | `pushbox` / `hitbox` / `hurtboxes[]` | pushbox + zones derivees `sync_rects` (P2.1), tags/mult (P2.2), union legacy `hurtbox` |
| `src/physics/collisions.py:68-76` | `hitbox_collide` | `colliderect` instantane, pas de sweep |
| `src/physics/spatial_hash.py:53,182-193` | Grille environnement | `QUERY_MARGIN_PX=32`, requete enflee, faux positifs OK |
| `src/physics/entity_grid.py:32-76` | Grille entites | Rebuild O(n) par tick, ordre legacy preserve |
| `src/combat/attack_data.py:18-310` | `PLAYER_ATTACKS` en dur = **fallback** | 10 attaques (light/heavy/uppercut/dash/air + 5 vitrines Phase 5) ; utilise seulement si le JSON est absent |
| `data/gameplay/attacks.json` | **Source de verite a l execution** | `provider.py:93-100` : JSON present et valide => utilise ; JSON malforme => erreur forte ; JSON absent => fallback builtin. Noms et valeurs verifies identiques (10/10 attaques, ex. `light_attack.cooldown=0.3`, `dash_attack=[70,24]`). Risque restant : drift silencieux si on edite un seul des deux => recommandation : test de parite en P0 |
| `src/combat/attack_state.py:91-93,263-278` | Fenetre de frappe discrete | `is_active` = sous-etat ACTIVE uniquement ; `update()` avance **au plus 1 frame par tick** (garde-fou anti-saut de fenetre). La detection ne voit donc que la geometrie finale du tick |
| `src/physics/movement.py:228-280` | Mouvement environnement **substeppe** | Decoupage `ceil(|v|.dt / SUB_STEP_SIZE)` plafonne par `MAX_SUBSTEPS_PER_AXIS`, `old_hitbox` mis a jour par sous-pas. Le tunneling environnement est donc deja traite ; **seule la detection offensive est discrete** (1 passe/tick sur les boites finales) |
| `src/core/level/systems/projectile_system.py:76-137` | Pipeline projectiles | emet `OffensiveBox` vers `ContactSystem.resolve` (P4.1) |
| `src/core/level/systems/hazard_damage.py:44-60` | Pipeline hazards | emet `OffensiveBox` vers `ContactSystem.resolve` (P4.1) |
| `src/ui/world_ui.py:340-391,831-1310` | Debug overlay | Sweep fantome pointille + fleche, timeline phases, index par boite (`●`/`○`), compteurs `CombatMetrics` live, panneaux (P4.3) |

### 1.3 Flux par tick (melee)

1. `CombatComponent.update(dt)` : timers hurt/cooldown/combo/charge, `resolve_facing`, `state.update(dt)`.
2. `CombatComponent.sync_attack_box()` : `HitboxManager.update(state)` repositionne les `FRect` depuis `hitbox.center + offset`.
3. `EntityGrid.rebuild(entities)` : re-bucket O(n).
4. `CombatSystem.process_attacks` -> `ContactSystem.resolve` (P4.1) :
   - `_attacker_ready` (`combat_system.py:38-54`) : vivant + `state.is_active` + boxes non vides + phase non nulle.
   - `_candidates` (`contact_system.py:302`) : requete par `swept`, filtre faction/self/mort/`can_contact`, tri par ordre de groupe.
   - test `swept.colliderect(swept_zone)` (`_first_vulnerable_zone`) puis `OffensiveBox` gele ; `zone_index`/`zone_mult` propages (P2.4).
   - `_resolve_melee`/`_resolve_generic` : `HitResolver`, `record_contact`, `guard_events`, hit-stop global, `ZoneContact` + `HitCandidate` (Axe G).
5. `update_timer(dt)` : decremente le hit-stop (simulation suspendue pendant `in_hit_stop`).

### 1.4 Startup vs ACTIVE : telegraph visuel non letal

Point de precision important (corrige une lecture trop rapide de la v1) :
`HitboxManager.update()` positionne la geometrie des `startup` **et** `active`
(commentaire `hitbox_manager.py:36-58`), mais `_attacker_ready`
(`combat_system.py:38-54`) exige `combat.state.is_active`, c est-a-dire le
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

### 2.2 Benchmark de contact — méthode reproductible

Le benchmark historique de broadphase a été remplacé par une mesure de `ContactSystem.resolve` avec le même roster dense et les mêmes densités 1v1, 4v4 et 8v8, en mode exhaustif puis avec `EntityGrid`.

Commande :

```bash
uv run python tests/benchmarks/contact_benchmark.py --iterations 300 --repeats 5
```

Chaque itération remet les cibles à leur état de départ avant la résolution afin de mesurer un contact réel à chaque passage. Le harness produit 1, 16 et 64 contacts respectivement pour 1v1, 4v4 et 8v8, avec les mêmes comptes de paires testées en grille et en exhaustif.

Les temps varient selon la machine et la charge système ; la comparaison doit donc utiliser la même machine, le même ordre de grandeur et le même nombre d’itérations. Le résultat n’est pas une mesure de temps absolu bloquante en CI.

### 2.3 Parité JSON / builtin

`load_gameplay_data` (`provider.py:93-100`) : JSON present et valide => JSON ;
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
  (`entity.py:963` save / `:1002-1017` load ; `combat_component.py:341` save / `:360` load).
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

> **Historique :** etat d avant le chantier P0-P5 (2026-09-20). Les items
> clos sont balises `**[clos Pn]**` ; l etat actuel est le code + §10.
> Un item non balise reste ouvert ou hors scope (cf. §10 ecarts).

### L1 — Detection offensive discrete, tunneling (prouve en 2.1)

**[clos P1 — sweep CCD bilatéral melee]** Seule la detection **offensive**
etait discrete : le mouvement environnement est
substeppe (`movement.py:228-280`), et la machine d attaque ne saute jamais une
fenetre ACTIVE (`attack_state.py:263-278`). Trou d origine : une seule
geometrie offensive testee par tick (post-mouvement), sans union prev+cur —
repro 2.1 (`contacts=0` puis hit via sweep apres P1).
Cas a risque d origine : `dash_attack` (lunge frame 1, boite 70x24, offset 42 px),
keyframes `sweeping_arc` (28 -> 70 px en 6 frames), chutes ~25 px/tick
(1500 px/s a 60 Hz) contre cibles fines. `QUERY_MARGIN_PX=32` protege la
 broadphase (requete elargie), pas la narrowphase.
**Sweep actif :** la swept geometry est utilisée par la melee, les projectiles AABB et les hazards mobiles. Les hazards statiques restent discrets, et le contact damage conserve sa collision discrete. Les projectiles et hazards swept leur broadphase, leur narrowphase et leurs collisions contre les murs ou les cibles.

Symptomes d origine : coups rapides qui passent au travers, whiffs visuels
injustes sur lunge et cibles fines.

### L2 — Geometrie et formes avancées

**[clos P2.3/P5 — keyframes, easings, anchors et formes avancées]**
- Formes offensives disponibles : AABB, cercle, capsule et OBB ; rotation, broadphase AABB et narrowphase exacte sont implémentés.
- `extra_hitboxes` et `hitbox_keyframes` acceptent des courbes par boîte, avec interpolation de taille, offset et angle.
- Le sweep CCD bilatéral reste melee-only par décision produit ; les formes avancées utilisent le chemin narrowphase prévu.
- Tests : `tests/unit/test_hitbox_shapes.py` et `tests/unit/test_p5_integration.py`.

### L3 — Une seule hurtbox globale

**[clos P2.1/P2.2 — multi-zone]**
`hurtbox = hitbox.inflate(...)` centree etait l unique reception. Depuis P2 :

- zones `hurtboxes[]` + tags/mult/noms (`hurtbox_zones.py`, `entity.py:448-464`) ;
  multiplicateurs locauxises (ex. goblin head x1.5 — `enemies.json:26-54`,
  commit `6129613`).
- Le `dash` qui ecrase la hitbox (`apply_squish`) n elargit plus la
  vulnerabilite au-dela des zones (test squish).
- Invulnerabilite partielle par tags : `HitProperties.tags` et
  `HurtboxZoneDef.invuln_states` sont portes ; une zone dont les tags
  correspondent est ignoree, y compris les jambes en vol. E2E couvert dans
  `tests/unit/test_multi_hurtbox.py`.

### L4 — Pas de distinction push / hurt / hit

**[clos P2.1 — pushbox + hurtboxes[] + hitbox[] (boxes emettrices)]**

`hitbox` servait a la fois de corps physique, d ancrage des attaques et de
reference hurtbox. Standard versus-fighter attendu :

- `pushbox` (collision corps-a-corps, separation) — **livre** `entity.py:424`,
- `hurtbox[]` (zones recevant) — **livre** `entity.py:448`,
- `hitbox[]` (zones emettrices) — `attack_boxes` + `extra_hitboxes` (depuis v1/P2).

Sans ca (avant P2) : cross-up aleatoires, separation qui pousse pendant un
hit-stop, grab impossible a specifier proprement. Grab reste **hors chantier**
(§9-3).

### L5 — Semantique de coup minimale

**[clos P3t1/P3t2 — priorité, clash, hauteur, block_mask et hit_level]**

`HitProperties` = degats + knockback + stagger + armor-break + finisher + juggle + OTG.
Depuis P3 (etat actuel `frame_data.py:108-112`) :

- hauteur `height` (`high/mid/low/overhead`) + table `Guard.HEIGHT_BLOCK` **[clos P3t2]**,
- `unblockable` (bypass garde — chemin `Player.receive_damage`) **[clos P3t1]**,
- `priority` + `clash` (`trade|clash`) via `_resolve_hit_vs_hit` **[clos P3t1]**,
- `hit_level` : `light/med/heavy`, avec `heavy` a 1,25x de pression de
  garde **[clos O3]**,
- `block_mask` : `any/stand/crouch`, combine a `height` dans la garde
  **[clos O1]**,
- `whiff` vs `blocked` vs `hit` : feedback via `GuardEvent` (partiel, pas d enum dediee).

### L6 — Quatre pipelines divergents

**[clos P4.1 — `ContactSystem` unifie]**
Melee (`combat_system.py`), projectiles (`projectile_system.py`), degats de
hazards (`hazard_damage.py`) **et** degats de contact (`contact_damage.py`,
seuil `CONTACT_DAMAGE_THRESHOLD=300`) avaient quatre conventions de test.
Depuis P4.1 les quatre emettent `OffensiveBox` vers **une seule**
`ContactSystem.resolve` (instance partagee `level.py:125`). Ordre par tick
(fichier `gameplay_loop.py:163-210`, load-bearing) : spawn -> plateformes ->
hazards -> physique -> combat+separation (rebuild grille,
separation, sync boxes, `process_attacks` `:313`) -> projectiles (`:190`) ->
contact (`:196`) -> hazard-damage (`:197`) -> morts -> respawn.
Les producteurs historiques restent presents **en tant que producteurs**
(ils ne resolvent plus localement).

### L7 — Authoring : source connue, drift possible, validation faible

**[clos P0.2/P0.3/P4.2/O8 — parite, docstring, validateur strict et offsets
de keyframes dans l enveloppe]**
Corrige (v1 disait "sans source de verite", c est faux) : a l execution, le
JSON prime (`provider.py:93-100`), le code en dur est un fallback documente
(`provider.py:1-26`). Parite verifiee en 2.3 **et en CI** (P0.2).
Validateur P4.2 (`attack_loading.py`) : taille et offsets statiques ou de
keyframes dans l enveloppe, keyframes croissantes dans `0..startup+active`,
cooldown, `cancel_into`, warning `reset_targets`.
Restent (ouverts, hors plan P0-P4) :

- `cancel_into` : pas de controle de cycle / auto-reference,
- sous-remplissage data (1 extra keyframe, 1 extras hitboxes dans tout le JSON) —
  item `audit_consolide` R-8.2 non repris ici,
- export JSON : F9 ecrit un document relisible dans
  `KNIGHTROCK_EXPORT_DIR`; le merge puis le redemarrage restent une operation
  de l auteur.

### L8 — Debug limite

**[clos P4.3 + gap audit + Axe G]**
Overlay d origine : boites instantanees. Livres depuis : trajectoire sweep
(prev->cur + fleche), timeline startup/active/recovery, identifiants de boite
in-situ par points vectoriels `●`/`○`, paires testees/overlaps/contacts live,
dump JSONL `logs/combat_trace.jsonl` si `DEBUG_COMBAT_DUMP=1` (**Axe G**),
pause F6 + step F7, replay F8, export F9.

### L9 — Perf et determinisme sous pression (mesure en 2.2)

**[clos O4/O6 — harness O4, contacts réels, buffers broadphase et checksum géométrique]**
Le harness `tests/benchmarks/contact_benchmark.py` se lance directement depuis la racine, remet les cibles à leur état de départ à chaque itération et rejoue les trois densités en mode grille et exhaustif. Il produit 1, 16 et 64 contacts pour 1v1, 4v4 et 8v8. `ContactSystem` réutilise les buffers de broadphase et le snapshot conserve un checksum géométrique quantifié pour vérifier la restauration.

---

## 4. Axes d amelioration (meme refontes profondes)

> **Etat 2026-09-24 :** A–H livrés dans le périmètre P0–P5 ; F et H validés par leurs réceptions ; G livré ; O1–O9 clos. Le sweep reste melee-only pour les producteurs non-melee. Grab hors chantier (§9).

### Axe A — CCD / sweep continu (anti-tunneling, prouve en 2.1) **[livre P1, melee]**

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

### Axe B — Vrai modele push / hurt / hit **[livre P2.1]**

- `pushbox` = ancien `hitbox` physique (murs, sols, separation).
- `hurtbox[]` = 1..n zones vulnérables derivees du pushbox + inflate par zone + tags.
- `hitbox[]` = zones offensives (existant, a etendre).
- Migration : `sync_rects()` derive les trois, `separation_system` et `platform_system` n utilisent que `pushbox`, le combat n utilise que `hurtbox[]`.
- Pre-requis du grab (attrape = test pushbox-vs-pushbox a courte portee, pas hit-vs-hurt).

### Axe C — Hurtboxes multiples + hitboxes expressives **[livre P2 ; tags du coup livres ; shapes non]**
- Hitbox : `shape in (aabb, circle, capsule)`, `keyframes` par boite (pas que primaire), easing, suivi d un point d ancrage (hanche, epee).
- Extension `PhaseDefinition` / `HitboxSpec` + migration JSON avec defaults (compat ascendante).

### Axe D — Hauteur, garde, priorite, clash **[livre P3t1+P3t2 + O1/O3]**

- `HitProperties += height, block_mask, unblockable, grab_spec, priority, clash, hit_level`.
- Resolution hit-vs-hit avant hit-vs-hurt : si deux actives se chevauchent, `priority` decide (beat/trade/clash), sinon les deux passent en whiff-clash avec hit-stop court.
- Hauteur : `high` bloque debout, `low` bloque accroupi (necessite un etat accroupi, absent aujourd hui), `mid`/`overhead` selon design.
- Ouvre la porte au grab : `grab_spec(range, whiff_time, tech_window)` + etats `grabbed/throw`.

### Axe E — Pipeline de contact unifie (4 producteurs, voir L6) **[livre P4.1]**

Un seul `ContactSystem` : melee, projectiles, hazards **et contact** produisent
des `OffensiveBox(box, swept, hit, faction, owner_id)` ; une seule broadphase
`EntityGrid`, une seule narrowphase (sweep + formes + zones), une seule passe
resolve. Supprime la quadruple maintenance. Inventaire et migration en 3
commits : voir P4.

### Axe F — Authoring data-driven + validation **[livre P0.2/P0.3/P4.2 + F8/F9]**

- Source de verite : `data/gameplay/attacks.json` (supprimer le doublon en dur ou le generer).
- Validateur au chargement : taille > 0, offset dans une enveloppe sprite, keyframes tries dans `0..startup+active`, `reset_targets` exige sur multi-phase, cooldown >= duree totale,Facing lock coherent.
- Editeur minimal : overlay qui rejoue une attaque en boucle avec trajectoire
  + export JSON F9 dans `KNIGHTROCK_EXPORT_DIR`.

### Axe G — Debug temps reel **[livre P4.3 + gap audit + CombatTrace]**

- Overlay : sweep (rect prev + fleche), timeline phase, id par boite, paires testees/overlaps/contacts en direct, mode pause + step frame.
- Dump : log binaire ou JSON des `HitCandidate` par tick pour rejouer un whiff suspect.

### Axe H — Perf / determinisme / rollback **[livre O6]**

- Buffers de broadphase reutilises, tri par ordre de cible preserve.
- Checksum geometrique quantifie dans `CombatSnapshot`.
- Fixed-point ou quantification multi-plateforme reste hors scope.

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
`tests/unit/test_hitbox_pipeline.py`, `tests/unit/test_hitbox_sweep.py`,
`tests/unit/test_combat_behaviors.py`,
`tests/unit/test_damage_resolution.py`, `tests/unit/test_rollback_snapshots.py`,
`tests/unit/test_rollback_system.py`, `tests/headless/test_rollback_e2e.py`,
`tests/headless/test_simulation_golden.py`, `tests/unit/test_gameplay_data.py`,
`tests/unit/test_multi_hurtbox.py`, `tests/unit/test_priority_clash.py`,
`tests/unit/test_height_block.py`, `tests/unit/test_contact_unified.py`,
`tests/unit/test_attack_validation.py`, `tests/unit/test_hit_resolver_limits.py`,
`tests/unit/test_combat_contracts.py`, `tests/unit/test_combat_trace.py`,
`tests/unit/test_debug_commands.py`, `tests/unit/test_debug_overlay.py`,
`tests/unit/test_entity_grid.py`, `tests/unit/test_spatial_hash.py`,
`tests/unit/test_combat_component.py`, `tests/unit/test_movement_collision_cache.py`.

### P0 — Gel et filet de securite (0.5 j, sans casse)

Objectif : pouvoir mesurer avant/apres. Aucun changement de comportement.

| # | Tache | Ancres exactes | Reception |
|---|---|---|---|
| P0.1 | Test golden trajectoires | Etendre `tests/unit/test_hitbox_pipeline.py` (helpers : `tests/unit/helpers.py:29-71` `make_phase`/`make_attack`, `:115-142` `entity_at`/`activate`) | `dash_attack`, `sweeping_arc`, `sky_launcher` issus de `src/combat/attack_data.py:87-225` : centres/tailles de boites figes par frame d animation (`animation_frame`, `attack_state.py:125-140`) + recenser pour les 10 attaques le deplacement de centre startup->active (seed) et par frame (keyframes) : lister celles >= 4 px (sweep attendu en P1, ex. `sweeping_arc` ~7 px/frame) pour revalider le golden simulation comme changement voulu, pas regression. Etendre aux transitions de phase (`special_attack` 5 phases, `claw_swipe` 2) : premier ACTIVE de phase N balaie depuis son propre startup (continuite assuree par capture — pas d invalidation de `prev` au changement de phase, qui recrerait un tick discret) |
| P0.2 | Test de parite JSON/builtin | Nouveau cas dans `tests/unit/test_gameplay_data.py` ; sources : `src/data/provider.py:93-100`, `data/gameplay/attacks.json` (`sets.player`, 10 attaques), `src/combat/attack_data.py:18-310` | Noms + `cooldown` + `hitbox_size`/`hitbox_offset` des 10 attaques player identiques ; echoue si drift |
| P0.3 | Doc source de verite | Etendre la docstring `src/data/provider.py:1-26` | Phrase : JSON = source a l execution, builtin = fallback d absence uniquement |
| P0.4 | Bench de reference | Methode section 2.2 (300 iterations, roster ACTIVE) | Valeurs notees en recettage (ref 2026-09-20 : 0.003 / 0.029 / 0.075 ms) |
| P0.5 | Repro de reference | Rejouer l extrait section 2.1 dans un test temporaire | Trou confirme (`contacts=0`, union -> True), note en recettage |

### P1 — Sweep CCD borne (1-2 j, faible casse)

Objectif : capturer le cas repro 2.1 sans changer le format JSON. Scope :
geometrie ACTIVE uniquement (startup = telegraph non letal, voir 1.4).

**Decisions tranchees (ne pas rouvrir sans arbitrage) — version finale normative :**

- D1 — Seuil en deplacement mesure, pas en vitesse : nouvelle constante
  `Combat.SWEEP_MIN_DISPLACEMENT_PX = 4.0` (`src/core/settings.py:72-119`,
  classe `Combat`). Distance euclidienne des centres, par index de boite.
  Si < 4.0 px depuis le tick precedent, `swept = cur` (golden stables).
  Sinon `swept = prev.union(cur)`. Justification : deterministe (pas derive
  de `velocity` annulable par `separation_system.py:8-50`), 4 px < cible
  fine ~10 px. Si `prev` vide/`None` (spawn, premier tick) ou deplacement >
  `SWEEP_MAX_DISPLACEMENT_PX` (D4) : `swept = cur`. Starter seed normatif
  (contre-avis 3e/4e LLM, trace verifiee code) : `CombatComponent.start_attack`
  positionne en cas de succes la geometrie startup frame 0 dans `_pool` ET
  `_prev_pool`. Indispensable, pas optionnel : tous les starts ont lieu
  pendant `Entity.update`, donc APRES la capture (input joueur dans
  `_pre_update`, `player.py:235` ; enchainements `player_states.py` ;
  IA `enemy_states.py`). Un sync seul ne seederait jamais `prev` en
  production — la capture aurait deja copie un `_pool` vide. Le seed couvre
  le tick de transition (`startup=1` : `update()` bascule en ACTIVE avant le
  premier sync, `entity.py` update), c est-a-dire exactement le lunge
  (`dash_attack`) ; la capture couvre les ticks suivants. Chaine verifiee
  code, meme tick : input -> `start_attack` -> interrupt synchrone
  (`state_machine.py` interrupt synchrone, `enter()` immediat) ->
  `PlayerAttackState.enter()` pose la vitesse lunge
  (`player_states.py:237`) -> `combat.update` -> `move` -> `sync` ->
  detection. Le mouvement suit donc bien le seed avant le sync : le test
  (b) reflete l ordre reel et « indispensable » est justifie (le repli
  « mouvement au tick suivant » n existe pas dans ce code). Prix documente :
  touche possible 1 tick depuis une position non letale. Resize
  (`len(prev) != len(cur)`) : `swept = cur` pour ces index. `update()` ne
  touche JAMAIS a `prev` (positionnement pur, idempotent par construction —
  le double-sync `Entity.update` + `gameplay_loop.py:176-179` devient
  inoffensif) ; seul `clear()` vide les deux (fin d attaque). Capture
  explicite : `HitboxManager.capture_origin()` (copie profonde `_pool` ->
  `_prev_pool`), appelee une fois en frontiere de tick par `gameplay_loop`
  avant `platform.process`, dans la meme boucle que
  `Entity.capture_sweep_origin()` (D3). Aucun etat cache, aucun cas tordu
  tick-sans-avance : la capture copie la fin du tick precedent dans tous
  les cas. dt sim FIXE (`game.py:117-119` : boucle a pas fixe `TIMESTEP`,
  propage inchange `level.py:211` jusqu a la boucle ; `MAX_FRAME_TIME`
  jette du temps en slow-mo, ne gonfle jamais dt — mesure : 0 tick sans
  avance sur 3000 a `dt=1/60`).
- D2 — Grille : requeter `EntityGrid.near()` avec le `swept_box` (pas
  `attack_box`). `QUERY_MARGIN_PX` inchange. Invariant bloquant : ensemble
  des candidats + contacts identiques avec/sans grille (`pairs_tested`
  non bloquant : incremente apres elagage `contact_system.py:253`, donc
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
   - `update:61-81` : positionnement pur, NE TOUCHE JAMAIS a `_prev_pool`
     (idempotent par construction ; le seed et la capture en sont les seuls
     ecrivains avec `clear()`).
   - ajouter `capture_origin()` (copie profonde `_pool` -> `_prev_pool`),
     `prev_rects` (tuple, copie) + `swept_rects` (par index : `cur` si `prev`
     vide, taille differente (resize), ou deplacement < MIN ou > MAX (D4),
     sinon union prev+cur).
   - `clear:83-87` : vider aussi `_prev_pool`.
   - `rects:36-39` inchange (contrat `attack_boxes` preserve).
   - `combat_component.start_attack` (`:211-260`) : en cas de succes, seeder
     `_pool` ET `_prev_pool` avec la geometrie startup frame 0 (starter seed
     D1 : positionner via `sync_attack_box()` puis copier vers `prev`).
     Sans le seed de `prev`, le 1er tick ACTIVE serait discret en production
     (tous les starts ont lieu apres la capture).
3. `src/entities/entity.py` + `gameplay_loop.py:176-179` :
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
    - `reset_position:703-715` : raz `_prev_hurtbox` (= `None`) pour
      respawn/teleport sans smear (D4).
    - Snapshots (`entity.py:963-1017`, `combat_component.py:341-360`) :
     AUCUN champ ajoute (D3 abandonnee) ; `load_state` remet `prev` a
     vide/None (hygiene, jamais observe avant la capture suivante).
4. `src/core/level/systems/combat_system.py` (producteur) + `contact_system.py` (P4.1) :
    - `ContactSystem._candidates:302-324` : boite de requete = swept (pas
      `attack_box` brut) ; tri par `order` inchange.
    - `CombatSystem.process_attacks:90-160` (emission `OffensiveBox:149`) :
      zipper `attack_boxes` + `combat.hitbox.swept_rects` (acceder via
      `CombatPort` etendu ou `getattr` documente — voir note contrats
      ci-dessous) ; requete grille sur le swept dans `_candidates` ; test
      `swept.colliderect(target.swept_hurtbox())` (`_first_vulnerable_zone:182`).
   - Note contrats : le chantier R-3 (`notes/audit_consolide.md`) veut zero
     `getattr` dans `hit_resolver.py` uniquement. Ici, etendre
     `CombatPort`/`Combatant` (`combatant_protocol.py`) avec
     `swept_attack_boxes` + `swept_hurtbox()` + `capture_attack_origin()`
     plutot qu un `getattr` sauvage ; `CombatComponent` implemente
     `capture_attack_origin()` (delegue a `hitbox.capture_origin()`),
     `NullCombatComponent`/`_NullHitboxManager` en no-op exposant
      `swept/prev = ()` ; les doubles `tests/unit/helpers.py:142-162`
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
KB_MAX * 2.0) * TIMESTEP * 1.5` avec KB_MAX = magnitude max des
`power` de `attacks.json` (constante `CHARGE_MAX` **inexistante** dans le
code — formule historique du plan, borne retenue empiriquement 64 px ;
le knockback vitesse REMPLACE la velocite, `reaction.py:183-190`, donc pas
d addition de termes — juggle <= 1, finisher/dizzy = degats seuls) :
max(1500, 1100, 750, 1082*2) / 60 * 1.5 = 54.1 <= 64. dt sim fixe
`TIMESTEP`, pas de spike possible).
Bench : la méthode 2.2 est rejouée par `tests/benchmarks/contact_benchmark.py`, avec contacts réels et comparaison grille/exhaustive sur la même machine.
Gardes-fous transverses verts.

### P2 — Push / hurt / hit + multi-hurtbox (3-5 j, refonte moyenne)

Objectif : separer corps physique et vulnerabilite, supporter zones multiples. Compatible ancien JSON via defaults.

Pre-requis : P1 vert (le sweep s applique ensuite par zone : `swept` par
hurtbox, break des la premiere zone touchee).

**Checklist d implementation (ordre impose) :**

1. `src/entities/entity.py` (ancres actuelles : `__init__` `:186-200`,
   `pushbox` `:424`, `hitbox` `:429-437`, `hurtbox` `:439-445`,
   `hurtboxes` `:448`, `sync_rects:526-547`, snapshots `:963-1038`) :
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
   - `src/entities/player_config.py:94` (`hurtbox_inflate`) et
     `src/entities/enemies/schema.py:19` : ajouter `hurtbox_zones` optionnel
     `[{name, inflate, mult, tags}]`, defaut `None` => 1 zone legacy.
     Implementation livree : module central `src/entities/hurtbox_zones.py`
     (`HurtboxZoneDef`, `read_hurtbox_zones`, `hurtbox_zones_to_dict`).
   - `src/data/player.py:84-85` + `src/data/enemies.py:96-97` (parsers
     `hurtbox_inflate`) : parser le nouveau champ, fallback sur l ancien.
   - `data/gameplay/player.json` + `enemies.json` : defaults legacy.
     **Exception consignee :** commit `6129613` ajoute les zones de test
     **goblin** dans `enemies.json:26-54` (head x1.5 / torso x1.0 /
     legs x0.8) — donnees d accueil P2, multiplicateurs de degats reels.
3. `src/combat/hitbox_manager.py` : keyframes par boite (P2.3 de la checklist
   P1 etendue) : `HitboxSpec` (`frame_data.py:106-130`) +=
   `keyframes: tuple[HitboxKeyframe, ...] = ()` ; `_position_rects:59-82`
   interpole chaque box via sa propre courbe (`hitbox_at` factorise en
   fonction utilitaire prenant `keyframes`). Primaire inchange si pas de
   keyframes extras (golden P0.1).
4. `HitCandidate` (`src/core/level/systems/combat_trace.py:24-38`) :
    - `HitCandidate:24-38` += `zone_index: int = 0`, `zone_mult: float = 1.0`
      (champs deja presents depuis P2.4).
    - `ContactSystem._candidates` + `_first_vulnerable_zone:182-201` :
      boucle zones (swept par zone), break a
      la premiere zone touchee non invulnerable (`invuln_tags` vs tags du
      coup — tags du coup : aucun en P2, champ reserve).
    - `ContactSystem._resolve_melee:327-370` : `HitResolver.resolve(..., zone_mult)`
      (choix retenu a l implementation : multiplication dans le resolver).
    - Doubles `tests/unit/helpers.py:142-162` : zones par defaut.
5. Migration appelants (alias `hitbox` => aucun changement fonctionnel
   requis a ce palier ; verifier par grep `\.hitbox` dans `src/` que seuls
   ces systemes touchent au corps physique, tous conservent l alias) :
   - `separation_system.py:21-67` (corps-a-corps + `sync_rects:66-67`),
   - `platform_system.py` (carry `hitbox`/`old_hitbox`),
   - `hazard_damage.py:44-60` (emmet `OffensiveBox` vers `ContactSystem.resolve`),
   - `contact_damage.py` (`hitbox.colliderect`, seuil 300),
   - `physics/movement.py:228-280` + `collisions.py` (inchanges).
6. Debug : `src/ui/world_ui.py:340+` — une couleur par zone + label
   (`head/torso/legs`), sweep P1 dessine en pointille.

**Reception P2 :** `tests/unit/test_multi_hurtbox.py` (1 zone par defaut =
byte-identique au legacy ; tete x1.2 via `hurtbox_mult` ; jambes/zone tags
**matcher unitaire** — E2E invuln saut **reporte/non clos**, cf. §10 ;
squish dash `player.py` n elargit pas la vulnerabilite) ;
roundtrip JSON ancien/nouveau champ ; goldens P0.1 + sweep P1 verts ;
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

1. `frame_data.py` (temps 1) : `HitProperties += unblockable: bool=False, priority: int=0, clash: str=trade, hit_level: str=med` (   `HitProperties:49-112`, quantites validees en `__post_init__:121-127` — ajouter `priority >= 0`, `clash in (...)`, `hit_level in (...)`). Lecteurs JSON : `src/data/attacks.py` (`read_attacks_file:201`, utilise par `provider.py:100`) : defaults identiques (test P0.2 etendu aux nouveaux champs).
2. `CombatSystem` : passe hit-vs-hit avant hit-vs-hurt, dans
   `process_attacks` (`combat_system.py:116-117`, via
   `_collect_ready:163` + `_resolve_hit_vs_hit:170-211` — collecter aussi
   les paires box-vs-box ennemies actives) puis delegation a
   `ContactSystem.resolve` (`contact_system.py:230+`). Deux boxes actives
   ennemies qui se chevauchent : priorite superieure gagne (l autre candidat
   est retire avant resolve), egalite = clash (les deux attaques s annulent
   via `combat.state.end()` + `hitbox.clear()` + hit-stop court
   `Combat.HITSTOP_BASE` + event `GuardEvent("clash", ...)` draine par
   `gameplay_loop` comme les autres), sinon trade (les deux
   resolvent, ordre deterministe existant).
   Ancres hit-stop : `combat_system.py:202-211` ; trauma :
   `gameplay_loop.py:275-280` (`_trauma_for_event` : ajouter
   `clash` ->
   `GUARD_TRAUMA`, pas de nouvelle constante).
3. Grab : **hors chantier, rapport dedie.** La base requiert etat `grabbed`,
   lock des deux cotes, whiff recovery, tech window, invuln de chope et
   distinction push-vs-hit (depend de P2) : trop pour 4 lignes de spec.
   P3 ne fournit que le pre-requis (`unblockable` + pushbox P2).
4. `Guard` (`player_controllers.py:164-183` + `player.py:272+`
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

Inventaire des producteurs a unifier (ordre tick `gameplay_loop.py:163-210`) :
`combat_system.process_attacks(:273)` <- `sync_attack_box(:272)` ;
`projectile_system.process(:163-164, entity_grid)` ;
`contact_damage.process(:170, entity_grid)` ; `hazard_damage.process(:171)`.
Enregistrement : `level.py:123-160` ; re-export `systems/__init__.py:17-41`.

**Checklist :**

1. Nouveau `ContactSystem` (fichier `src/core/level/systems/contact_system.py`,
   exporte dans `systems/__init__.py`) : interface minimale
   `produce_boxes() -> Iterable[OffensiveBox]` avec
   `OffensiveBox(box, swept, hit, faction, owner_id, can_contact, record_contact)` ;
   une broadphase (`EntityGrid.near(swept)`), une narrowphase (sweep P1 +
   zones P2), une resolve (priorite/clash P3 puis `HitResolver`).
   Migration en 3 commits separes, chacun reversible : (a) melee deleguee
   (l ancien `CombatSystem.process_attacks` devient un adaptateur fin),
   (b) projectiles (`projectile_system.py:76-137`), (c) hazards
   (`hazard_damage.py:44-60`) + contact (`contact_damage.py` + seuil 300
   conserve). `gameplay_loop.py:189-197` appelle le systeme unifie ; les
   anciens systemes restent presents mais non appeles pendant une version
   (suppression au palier suivant, pas dans P4).
2. `src/combat/attack_loading.py` (`load_attacks`, seule validation actuelle =
   `cancel_into`) : validateur strict — taille > 0, offset dans enveloppe
   sprite (marge 2x taille sprite 40x48 documentee `frame_data.py:284` +
   `attack_loading.py:40`),
   keyframes dans `0..startup+active` et strictement croissants (complete
   `__post_init__:246-253` avec messages nommant attaque + phase + champ),
   multi-phase sans `reset_targets: False` intermediaire => avertissement,
   `cooldown >= duree totale / FRAME_RATE`. Erreur au chargement via
   `GameplayDataError` (coherent `provider.py`), jamais de fallback silencieux.
3. Overlay `world_ui.py:340-1310` : sweep (prev + fleche), timeline
   startup/active/recovery (`attack_state.py` expose deja `sub_state` +
   `frame_counter`), id par boite (`box_id` = index), compteurs
   `CombatMetrics` live, pause/step (reutiliser le flag FROZEN
   `gameplay_scene.py:66`, handler F6/F7 `:123-131`). Commandes debug
   `F1-F8` : rejouer une attaque
   en boucle (F8 ; cablage `spawn_system.py:42-59`/`_trigger_attacks:117`).
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

### P5 — Formes avancées capsule/cercle/OBB (implémenté)

P5 est livré : formes cercle, capsule et OBB, rotation, easing, anchors, keyframes par boîte, broadphase AABB et narrowphase exacte. Le sweep CCD bilatéral conserve volontairement son périmètre melee-only.

### Ordre et jalons

```
P0 (gel + parite + bench) -> P1 (sweep ACTIVE) -> P2 (push/hurt/hit) -> P3t1 (priorite/clash/unblockable) -> P3t2 (hauteur + block_mask) -> P4 (unification/debug) -> P5 (formes avancées)
```

Chaque palier : suite complète verte (base 719 au 2026-09-20, **905 au 2026-09-24** — voir §10) + nouveaux tests, `ruff check`, `mypy src`, goldens et bench 2.2 reproductible ; mise à jour de ce rapport (section recettage datée).

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
    unblockable: bool = False           # P3 temps 1 [livre]
    priority: int = 0                   # P3 temps 1 [livre]
    clash: str = "trade"                # P3 temps 1 : ENUM REEL ("trade","clash")
                                        # beat/lose = RESULTATS de priority,
                                        # pas des valeurs de champ
    hit_level: str = "med"              # light | med | heavy
                                        # n accepte que "med" (light/heavy non)
    height: str = "mid"                 # high | mid | low | overhead
    block_mask: str = "any"             # any | stand | crouch
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
              "priority": 0, "hit_level": "med"}
    }],
    "cooldown": 0.30
  }
}
```

Ancien format (`hitbox_size`/`hitbox_offset` uniques, `hurtbox_inflate` global) reste charge via normalisation vers le nouveau modele.

**Note enums vs §6 :** exemples alignés sur les validateurs réels
(`frame_data.py:121-142`) : `clash in ("trade","clash")`,
`hit_level in ("light","med","heavy")`, `height in ("high","mid","low","overhead")`,
`block_mask in ("any","stand","crouch")`. `beat` et `lose` restent des résultats
de priorité et ne sont pas des valeurs de champ.

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
| P0 | `test_hitbox_pipeline.py` (etendu P0.1 + goldens phases P0.1-bis) + parite (P0.2) | positions figees `dash_attack`, `sweeping_arc`, `sky_launcher` + `special_attack`/`claw_swipe` transitions de phase ; parite JSON/builtin |
| P1 | `test_hitbox_sweep.py` (nouveau, spec en P1) | cas (a)-(i)+b'+b'' : saut 40 px, lunges seedes startup 1 et >= 2, transition de phase, rollback re-derive, parite grille, goldens revalides, dodge, teleport, double-sync, stationnaire, invariant MAX |
| P2 | `test_multi_hurtbox.py` (nouveau) | defaut byte-identique, tete x1.2, matcher zone tags, E2E invuln saut, squish dash |
| P3t1 | `test_priority_clash.py` (nouveau) | beat/trade/clash + unblockable, attaques existantes inchangees (defaults) |
| P3t2 | `test_height_block.py` (livre `aec4969`) | high/mid/low/overhead vs etat accroupi (`Guard.HEIGHT_BLOCK`) |
| P4 | `test_contact_unified.py`, `test_attack_validation.py` | 4 producteurs unifies, JSON invalide rejete avec message |
| Debug | `test_debug_commands.py`, `test_debug_overlay.py` | F6 freeze, F7 step, F8 replay, panneaux overlay |
| P5 | `test_hitbox_shapes.py`, `test_p5_integration.py` | AABB/cercle/capsule/OBB, rotation, easings, anchors, narrowphase, sweep de forme et roundtrip JSON |
| Trace | `test_combat_trace.py` | `CombatTrace` ring + JSONL gate `DEBUG_COMBAT_DUMP` |
| Tous | golden + gardes-fous §5 | trajectoires inchangées à vitesse normale ; benchmark 2.2 rejoué avec contacts réels |

### 7.3 Criteres globaux

- **910 tests verts** de référence (`pytest -q` le 2026-09-24 ; base historique 719 le 2026-09-20), `ruff check .` propre, `mypy src` propre sur 128 fichiers.
- Aucune regression visuelle sur les 5 attaques vitrines (`twin_fangs`, `sweeping_arc`, `sky_launcher`, `otg_slam`, `special_attack`).
- Determinisme : deux runs meme seed = memes `CombatMetrics` et memes positions.
- Rollback : `save/load` + capture frontiere re-derive `prev` (aucun champ snapshot) et ne rate aucun contact au tick suivant.
- Mesures rejouables : l’extrait 2.1 reste valide ; la méthode 2.2 est rejouée par le harness `tests/benchmarks/contact_benchmark.py` avec contacts réels.

---

## 8. Risques et non-objectifs

### Risques

| Risque | Mitigation |
|---|---|
| Sweep trop genereux (touches fantomes) | Seuils D1 (4 px) + D4 (cap 64 px, raz au reset), golden P0.1 + recensement >= 4 px, `QUERY_MARGIN_PX` inchange (regle D2), tests `test_dodge_within_one_tick_stays_hittable` / `test_teleport_beyond_max_yields_no_phantom_contact` |
| Explosion combinatoire (boxes x zones x cibles) | Break par box des la premiere zone touchee, broadphase sur swept, bench 8v8 |
| Migration JSON cassante | Test de parite P0.2, defaults = comportement actuel, roundtrip teste |
| Desync rollback silencieux | Re-derivation D3 (load-sync `cur` + capture `prev`, aucun champ), tests save/load P1(c), parite grille P1(d) |
| Refonte P2 qui touche physique + separation + plateformes | Alias `hitbox` conserve (aucun renommage appelant en P2) ; inventaire checklist P2 ci-dessus + commit `271f513` |

### Non-objectifs (hors extension méta reseau et rollback réseau)

- Netcode / rollback reseau (seule la proprete locale est visee).
- Extensions de gameplay au-dela de P5 (multi-hit auto, grab,throw) : hors chantier.
- Editeur visuel complet (overlay + rejouabilite suffisent).
- Equilibrage des degats (valeurs d attaque `attacks.json` inchangees ;
  **exception :** zones goblin `enemies.json` mult x1.5/x1.0/x0.8 ajoutees
  en P2 — `6129613`, cf. §10).

---

## 9. Decision attendue

1. Le plan P0 → P1 → P2 → P3t1 → P3t2 → P4 → P5 est implémenté et recetté.
2. Source de verite data : JSON = source a l’execution, builtin = fallback d’absence ; parité P0 maintained.
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
| **Recette courante** | **2026-09-24** | **910 passed** | **ruff check . propre** | **mypy src propre (128 fichiers)** | **couvert** | **contacts 1 / 16 / 64** | Sweep projectile AABB, sweep hazard mobile, murs et cibles balayées ; tests UI hermétiques |

Les lignes P0–Re-audit ci-dessous sont conservées comme historique de chantier et ne décrivent pas l’état courant.
| Ref (pre-P0) | 2026-09-20 | 719 passed | propre hors `main.py`* | propre (120 fichiers) | trou confirme | 0.003 / 0.029 / 0.075 ms | rapport takeover-ready, sans scripts |
| P0 | 2026-09-20 | 723 passed (719 + 4 P0.1) | propre (src+tests) | propre | trou confirme (`contacts=0 overlaps=0 pairs=1`, union -> True) | 0.002 / 0.016 / 0.056 ms (sans grille, meme machine, meme ordre de grandeur) | P0.1 goldens 3 attaques + census (aucun saut letal >= 4 px) ; P0.2 parite pre-existante (egalite complete 3 sets) ; P0.3 docstring source de verite. Goldens multi-phases (`special_attack`/`claw_swipe`) livres plus tard en P0.1-bis (`5db47ad`, 2026-09-23) |
| P1 | 2026-09-20 | 735 passed (723 + 1 goldens phases non recenses + 3 debloques (b)/(b')/(b'') + 8 reception = base intermediaire 724 non listee) | propre (src+tests) | propre (121 fichiers) | corrige — miss discret confirme, hit via sweep (contacts=1) | non rejoue (hors checklist P1 effective — **ecart convention**) | commits P1.1-P1.5 : constantes D1/D4 + `src/combat/sweep.py` ; `HitboxManager` prev pool + seed starter + hygiene D3 ; `swept_hurtbox` Entity + capture frontiere dans `gameplay_loop.update` ; `CombatSystem` sur swept (grille D2 + contacts bilateraux) ; reception (a),(c),(d),(f),(g),(h),(h'),(i) + invariant borne MAX 64 px |
| P2 | 2026-09-20 | 746 passed (735 + 2 extra-keyframes + 3 hurtbox-zones-data + 6 multi-hurtbox) | propre (src+tests) | propre (122 fichiers) | corrige (heritage P1, revalide via goldens + `test_hitbox_sweep.py` verts) | non rejoue (hors checklist P2 effective — **ecart convention**) | commits P2.1-P2.5 + **`6129613`** (zones goblin `enemies.json` head x1.5 / legs x0.8 — exception « JSON inchanges ») : pushbox + `hurtboxes[]` derives dans `sync_rects` (alias `hitbox` conserve) + sweep par zone ; data `hurtbox_zones` (`src/entities/hurtbox_zones.py`, parse JSON + roundtrip, fallback `hurtbox_inflate`) ; keyframes par boite (`HitboxSpec.keyframes`, `interpolate_keyframes` factorisee, `extra_box_at`, parse+serialize `keyframes`) ; `CombatSystem` par zones (premier contact vulnerable, `zone_mult` damage-only dans `HitResolver.resolve`, `_zone_vulnerable` unitaire — tags du coup : **non portes**, E2E jambes **ouvert/O2**) ; debug 1 couleur/zone + reception `test_multi_hurtbox.py` (legacy, tete x1.2, matcher, squish, swept P1xP2) |
| P3t1 | 2026-09-20 | 750 passed (746 + 4 priority/clash/unblockable) | propre (src+tests) | propre (122 fichiers) | n/a | non rejoue (hors checklist P3) | commit `5ce0295` : HitProperties unblockable/priority/clash + hit_level reserved ; `_resolve_hit_vs_hit` (beat/trade/clash, HITSTOP_BASE, GuardEvent clash) avant hit-vs-hurt ; `cancel_attack` sur CombatPort/CombatComponent/Null ; unblockable -> receive_damage (bypass dash-parry + garde) ; reception `test_priority_clash.py` |
| P3t2 | 2026-09-20 | 755 passed (750 + 5 crouch/height) | propre (src+tests) | propre (122 fichiers) | n/a | non rejoue (hors checklist P3t2) | commit `aec4969` : PlayerState.CROUCH tenu (`_wants_crouch`, interrupt prio 30, squish vertical ancré pieds CROUCH_HEIGHT_FACTOR=0.6, anti-écrasement au relever) ; `HitProperties.height` (high/mid/low/overhead) + table `Guard.HEIGHT_BLOCK` (overhead standard : traverse la garde accroupie) ; reception `test_height_block.py` |
| P4 | 2026-09-22 | 777 passed (755 + 8 validator + 14 debug overlay) | propre (src+tests) | propre (123 fichiers) | corrige (heritage P1-P3, revalide via goldens + sweep + multi-hurtbox + priority/clash + height verts) | non rejoue (hors checklist P4) | commits P4.1-P4.3 : `ContactSystem` unifie (melee/projectile/hazard/contact, hit-vs-hit melee-only) ; validateur strict `attack_loading` (taille/offset/keyframes/cooldown/cancel_into, `GameplayDataError` nommee + avertissement `reset_targets`) ; overlay debug (sweep fantome pointille + fleche, timeline startup/active/recovery, id `bN` par boite, panneau `CombatMetrics` live) |
| Gap audit | 2026-09-22 | 782 passed (777 + 5) | propre (src+tests) | propre (123 fichiers) | corrige (heritage) | non rejoue | Ecarts mineurs d audit refermes (`f7c4a29`) : F7 step cabled (`gameplay_scene`, 1 tick while frozen) + F6 freeze deja present ; `hurtbox_zone_names` exposee sur Entity (labels `head/torso/legs` rendus) ; `hurtbox` singulier = union des zones (legacy = zone unique byte-identique) ; protocole `Combatant` etendu (`swept_hurtboxes`/`swept_hurtbox`/`capture_sweep_origin`/`hurtbox_*`) ; cas (e) P1 ajoute (`test_case_e_p0_goldens_and_census_revalidate`) ; instance `ContactSystem` partagee par les 4 producteurs (`Level` + `tick_metrics` accumule, reset dans `begin_tick`) ; helpers doubles equipes des membres zones |
| Chantier audit 5 ecarts | 2026-09-23 | 856 passed (782 + 74 suite + nouveaux goldens/replay/zone/trace) | propre hors `main.py`* | propre (125 fichiers) | corrige (heritage) | non rejoue | Commits `5db47ad` goldens P0.1-bis (`special_attack` 5 phases + `claw_swipe` 2) ; `b9a9133` replay F8 (`toggle_attack_replay`/`tick_attack_replay`, option `DEBUG`) ; `413b582`+`8a25359` `ZoneContact.zone_index` stocke + expose (P2.4 boucle) ; `3d5cbc8`+`f65e4db` Axe G : `CombatTrace`/`HitCandidate` JSONL `logs/combat_trace.jsonl` si `DEBUG_COMBAT_DUMP=1` ; ecarts mineurs H1-H4 du re-audit clos (ancres, goldens phases, F8, zone_index, trace). Hors scope consignes : `9387b84`, `5b22925`, `1f5e3fa`, `a6d20f8` |
| Re-audit doc | 2026-09-23 | 856 passed (inchangé) | propre hors `main.py`* | propre (125 fichiers) | corrige (heritage) | non rejoue | Passe documentaire seule (aucun code) : historisation §1/§3/§4 balises `[clos Pn]` ; en-tête 719->856 ; arithmetique P0/P1 ; enums §6 alignes validateur ; §7.2 complete (debug/trace/P3t2) ; `6129613` + exception zones goblin ; gardes-fous etendus ; reference `P2.5` morte retiree. **Ecarts ouverts consignes (non clos) :** (O1) `block_mask` non implemente malgre P3t2/accroupi ; (O2) E2E jambes invulnees / tags du coup non portes (`HitProperties` sans tags, matcher inert) ; (O3) `hit_level` reserve (`"med"` seul) ; (O4) bench 2.2 non rejoue apres P0 — pas de harness dans le repo (convention de plan non tenue) ; (O5) Axe F export JSON non livre (F8 seul) ; (O6) Axe H non planifie (`sorted()` toujours par tick, pas de checksum) ; (O7) sweep bilatéral melee seul — projectiles/hazards/contact = `colliderect` discret (vouu, non documente avant) ; (O8) offset des keyframes jamais valide dans `attack_loading` ; (O9) libelle `bN` remplace par points `●/○` fusionnes (forme). `868d081` re-ancrage + `f7c4a29` gap audit P0-P4 (contenu dans row Gap audit) |

\* `uv run ruff check .` est désormais propre ; la modification hors périmètre de `src/core/settings.py` reste visible dans le diff de travail.
