# Ecarts ouverts — rework hitbox (re-audit 2026-09-23)

> Fichier independant. Source amont : `notes/hitbox_amelioration.md` (row §10
> « Re-audit doc », 2026-09-23). Aucun code modifie pour produire ce document.
>
> Etat de la suite apres application : **861 passed**, `ruff` propre hors
> `main.py`*, `mypy src` succes (127 fichiers).

---

## Tableau recapitulatif

| ID | Titre | Catategorie | Effet si non clos | Prochaine action |
|---|---|---|---|---|
| O1 | `block_mask` implemente | Clos | Masque de posture cable dans la garde | Aucun |
| O2 | Tags de coup et zones immunes | Clos | Tags de coup transmis et E2E multi-zone couvert | Aucun |
| O3 | `hit_level` light/med/heavy | Clos | Effet de pression de garde defini et teste | Aucun |
| O4 | Bench 2.2 | Clos | Mesure reproductible sur `ContactSystem.resolve` disponible | Rejouer sur chaque palier |
| O5 | Export JSON editeur | Clos | F9 exporte l attaque selectionnee dans un JSON relisible | Merge + redemarrage apres export |
| O6 | Axe H perf/determinisme | Clos | Buffers de broadphase et checksum geometrique | Mesurer sur la machine de reference |
| O7 | Sweep melee-only | Clos | CCD bilatéral limite au melee | Aucun |
| O8 | Offset des keyframes | Clos | Enveloppe sprite appliquee aux courbes | Aucun |
| O9 | Forme des indices debug | Clos | Points vectoriels ●/○ acceptes comme spec | Aucun |

**CATEGORIES**

- **Decision produit** : un choix de gameplay/design doit etre pris avant (ou a la place de) toute code.
- **Technique** : implementation mecanique, contenu decide ou decision optionnelle en amont.
- **Hors-plan** : explicitement hors P0–P5 ; demande une re-entrée au plan.
- **Forme** : ecart de presentation, pas de comportement.

---

## Detail par ecart

### O1 — `block_mask` non implemente malgre P3t2 / accroupi livres

**Etat :** clos. `block_mask` accepte `any`, `stand` et `crouch`; il est
transmis de `HitProperties` jusqu a `Guard.take_hit`, puis combine avec la
contrainte `height`.

**Preuves code :**

- `HitProperties` (`src/combat/frame_data.py:49-128`) se termine sur
  `hit_level` (ligne 112) ; **aucun champ `block_mask` dans `src/`** (grep
  repo : seulement `notes/` + docstring aspirante de
  `tests/unit/test_height_block.py`).
- `Guard` / `GuardSettings.take_hit`
  (`src/entities/player_controllers.py:164-189`) : parametres
  `unblockable`, `height`, `crouching` uniquement ; test via
  `HEIGHT_BLOCK.get((height, crouching), True)` (ligne 174).
- Table `HEIGHT_BLOCK` : `src/core/settings.py:140-149` (4 hauteurs ×
  bool crouch).
- `HitResolver` ne transmet que `unblockable` / `height` a `receive_damage`
  (`src/combat/hit_resolver.py:184-185`).

**Pourquoi ouvert :** le prerequisite (accroupi) est desormais satisfait ;
seul le masque lui-meme manque. Spec reprise dans le rapport
(`block_mask: str = "any"` commente `NON IMPLEMENTE`, §6).

**Prochaine action :** aucune. Tests dans `tests/unit/test_height_block.py`.

---

### O2 — Tags du coup non portes ; E2E « jambes invulnees en saut » ouvert

**Etat :** clos. `HitProperties.tags` est lu, serialise et transmis au matcher;
les zones taguees sont ignorees et la zone suivante peut absorber le coup. Le
joueur expose aussi `invuln_states=("airborne",)` pour les jambes en vol.

**Preuves code :**

- `HitProperties` sans champ `tags` (`frame_data.py:49-112`).
- Matcher present mais inert :
  `_zone_vulnerable(zone_tags, hit_tags)`
  (`src/core/level/systems/contact_system.py:111-119`) — docstring :
  *« No hit carries tags yet (P3t1), so every zone is vulnerable by
  construction »*. Appel avec tuple vide :
  `if not _zone_vulnerable(zone_tags, ()):` (ligne 197), dans
  `_first_vulnerable_zone` (`:182-200`).
 Cote zone : `Entity.hurtbox_tags`
  (`src/entities/entity.py:453-456`),
  `HurtboxZoneDef.tags`
  (`src/entities/hurtbox_zones.py:34-42`).
- Donnees : zones goblin avec `"tags": []`
  (`data/gameplay/enemies.json:34,43,52`) — multiplicateurs x1.5 / x1.0 /
  x0.8 ajoutes en `6129613` (exception « JSON inchanges »).
- `zone_mult` fonctionne deja sur la branche damage :
  `ZoneContact` (`contact_system.py:101-108`), formule
  `final_damage = hit.damage * charge_multiplier * zone_mult * type_mult *
  juggle_scale` (`hit_resolver.py:155`).

**Pourquoi ouvert :** jamais schedule comme tache de palier avec test E2E.
Sans `tags` sur le coup, le matcher ne peut pas rendre une zone (ex. jambes)
invulnerable en saut.

**Prochaine action :** aucune. E2E dans `tests/unit/test_multi_hurtbox.py`.

---

### O3 — `hit_level` reserve ; validateur n accepte que `"med"`

**Etat :** clos. `light`, `med` et `heavy` sont acceptes; `heavy` applique une
pression de posture 1,25x, `light` et `med` restant a 1,0x.

**Preuves code :**

- Champ + docstring : `frame_data.py:96-97` (*« Reserved label for the future
  crouch-height pass (`"med"` today) »*), default ligne 112.
- Validateur : `frame_data.py:127-128` —
  `if self.hit_level not in ("med",): raise ValueError(...)`.
- Lecteur JSON : `src/data/attacks.py:86`
  (`hit_level=str(raw.get("hit_level", "med"))`) ; serializeur `:244`.
- `attacks.json` ne porte pas `hit_level` (coherent avec le rapport).

**Pourquoi ouvert :** ouvrir `light|heavy` exige une semantique produit
(quoi que ce soit qui change le gameplay entre niveaux) — jamais tranchee.

**Prochaine action :** aucune. Tests dans `tests/unit/test_height_block.py`.

---

### O4 — Bench 2.2 non rejoue apres P0 ; aucun harness dans le repo

**Etat :** clos. Le harness `tests/benchmarks/contact_benchmark.py` rejoue
`ContactSystem.resolve` sur 1v1, 4v4 et 8v8, en mode grille et exhaustif, avec
sortie JSON et 300 iterations par defaut.

**Ce qu est le bench 2.2 :** methode du rapport §2.2 — roster
`entity_at` + `make_attack`, 300 iterations de detection seule ;
valeurs de reference ~0.003 ms/tick (1v1), ~0.029 (4v4), ~0.075 (8v8).
Cible historique `_collect_candidates` retiree par P4.1 — rejouer sur
`contact_system.resolve`.

**Preuves (absence) :**

- Glob `**/*bench*` → 0 fichier ; pas de dossier `scripts/`.
- Aucun test ne mesure ms/tick ni ne rejoue les 300 iterations
  (greps `1v1|4v4|8v8`, `time.perf_counter` en `tests/` sans lien).
- Seule mention code : docstring `src/core/level/systems/combat_trace.py:7`
  (*« hot path stays allocation-free … (bench 2.2) »*).
- Lignes recettage : tous les paliers P1+ marques `non rejoue` (§10) ;
  note §5 : *« effectif P0 seul — non rejoue ensuite »*.

**Pourquoi ouvert :** trou d outil/process, pas un bug de gameplay.

**Prochaine action :** rejouer la commande sur la machine de reference a chaque
palier; la suite CI ne compare pas une duree absolue.

---

### O5 — Axe F export JSON non livre (F8 replay seul)

**Etat :** clos. F9 exporte l attaque selectionnee vers un document JSON
versionne et relisible, sans modifier `data/gameplay/attacks.json`.

**Ce qui existe :**

- Replay F8 : `src/application/scenes/gameplay_scene.py:130-134`
  (`_REPLAY_KEY` → `toggle_attack_replay`, gated `Debug.is_enabled()`) ;
  implementation `src/core/level/systems/spawn_system.py:152-174`.
- Serializer (pas un export editeur) :
  `attack_definition_to_dict` (`src/data/attacks.py:218-259`) — utilise par
  les tests, pas par un writer fichier.
- Pas de code qui ecrit `attacks.json` (seuls writers `src/` : save game,
  combat trace JSONL).

**Prochaine action :** merger l export puis redemarrer le jeu; la source runtime
reste le fichier JSON valide.

---

### O6 — Axe H non planifie ; `sorted()` par tick chaud, pas de checksum

**Etat :** clos. Le broadphase reutilise les buffers de requete et de tri;
`CombatSnapshot` porte un checksum geometrique quantifie, verifie lors du
chargement d une entite.

**Preuves code :**

- Tri chaud : `src/core/level/systems/contact_system.py:321-323` —
  `sorted(nearby, key=lambda member: order[id(member)])` dans `_candidates`
  (`:302-324`), execute par `OffensiveBox` a chaque tick ; plus allocs
  `list`/`set` fraiches `:312-320`.
- **Pas de checksum geometrie** dans le code (grep `checksum` → seulement
  `notes/hitbox_amelioration.md`). Snapshots logiques uniquement ;
  geometrie re-derivee (§2.4, D3 abandonnee).

**Prochaine action :** comparer les mesures du harness sur la machine de
reference; le checksum detecte les desync de restauration, pas les divergences
multi-plateformes.

---

### O7 — Sweep bilatéral melee seul ; projectiles / hazards / contact discrets

**Etat :** clos par decision produit. Le sweep bilateral reste limite au
chemin melee; projectiles, hazards et contact conservent une collision discrete.

**Preuves code :**

- Melee porte la sweep whole-tick :
  `src/core/level/systems/combat_system.py:137-161`
  (`swept=entry.swept_boxes`).
- Narrowphase melee = swept vs zones :
  `contact_system.py:254-259` (`kind == "melee"` →
  `_first_vulnerable_zone(target, box.swept)` ; test
  `colliderect` sur rects swept, ligne 194).
- Narrowphase non-melee = discret :
  `contact_system.py:260-267` — branche `else` utilise `box.box`
  (pas `box.swept`) contre `hurtbox` (projectiles) ou `hitbox`
  (hazards/contact).
- Producteurs emettent sweep triviale :
  `projectile_system.py:126` (`swept=(projectile.hitbox,)`) ;
  `hazard_damage.py:46` ; `contact_damage.py:63`.

**Prochaine action :** aucune; le contrat melee-only est normatif.

---

### O8 — Offset des keyframes jamais valide dans `attack_loading`

**Etat :** clos. `_validate_keyframes` applique la meme enveloppe 2x sprite aux
offsets de chaque keyframe, primaire et extra.

**Preuves code :**

- `_validate_keyframes` (`src/combat/attack_loading.py:56-76`) : frames
  strictement croissantes + dans `0..startup+active` ; **aucune verif
  d offset**.
- Enveloppe sprite appliquee seulement a l offset **statique** :
  `_validate_phase` (`:79-96`) — `_box_entries` (`:49-53`) yield
  `phase.hitbox_offset` / `spec.offset` ; test
  `abs(offset) > ENVELOPE_MARGIN * SPRITE_SIZE` (`:90-95`).
- Dataclass : `HitboxKeyframe.__post_init__`
  (`frame_data.py:157-161`) — `frame >= 0` et `size > 0` seulement ;
  offset (`:155`) non borne.
- Constantes : `SPRITE_SIZE = (40.0, 48.0)` (`attack_loading.py:40-41`) ;
  `ENVELOPE_MARGIN = 2.0` (`:43-44`) → enveloppe 80×96 px.
- La docstring du validateur (`:7-9`) parle d « offset inside the
  documented sprite envelope » — vrai uniquement pour les offsets statiques.

**Prochaine action :** aucune; les tests couvrent le message nomme et le cas hors
enveloppe.

---

### O9 — Libelle debug `bN` remplace par points `●` / `○` (forme)

**Etat :** clos par decision de forme. Les points vectoriels ●/○ sont la
specification finale; le libelle texte `bN` n est pas restaure.

**Preuves code :**

- Index in-situ : `src/ui/world_ui.py:860-888` — docstring `:862-864` :
  haloed `●` coin haut-gauche de chaque boite, `○` apres la premiere ;
  `filled=index == 0` (`:886`).
- Geometrie des points (pas des glyphes police) :
  `world_ui.py:295-305` (`BOX_DOT_RADIUS/RIM/CORE/INSET`) ;
  dessin `_in_situ_dot` ~`:1176-1180`.
- `bN` texte fusionne dans le header :
  `world_ui.py:1182-1219` `_attack_header_rect` — docstring `:1191` :
  *« Merges the scattered ATK pill + b{i} ids + gold badges into a single
  header »* ; tokens = nom attaque + `phase:frame` + badges (`:1208-1213`).
- Plus aucune chaine `bN` dans `src/`.

**Prochaine action :** aucune; le point plein/creux reste attache a chaque boite.

---

## Annexe — Glossaire

### Geometrie / detection

| Terme | Definition | Ancre |
|---|---|---|
| **Swept AABB / sweep CCD** | Union `prev.union(cur)` d un rectangle sur un tick (ou geometrie bornee) pour eviter le tunneling ; si deplacement sous min ou au-dela max → `cur` seul | `src/combat/sweep.py:1-16`, `swept_box` `:30-62` |
| **D1 (borne basse)** | `SWEEP_MIN_DISPLACEMENT_PX = 4.0` — sous 4 px de deplacement, pas de sweep (seed starter 4 px) | `src/core/settings.py:110-113` |
| **D2 (grille sur swept)** | Broadphase `EntityGrid.near()` interrogee avec le `swept_box` (pas `attack_box`) ; `QUERY_MARGIN_PX` inchange | rapport §D2 ; `contact_system.py:314-315` |
| **D3 (snapshot prev)** | Abandonnee : pas de champ `prev` dans les snapshots ; `load_state` reset `_prev_hurtboxes` | rapport D3 ; `entity.py:715,1017` |
| **D4 (borne haute)** | `SWEEP_MAX_DISPLACEMENT_PX = 64.0` — sweep tronquee a 64 px, raz au reset | `settings.py:114-119` |
| **QUERY_MARGIN_PX** | Marge d inflation 32 px des requetes broadphase ; faux positifs acceptes (filtre narrowphase) | `src/physics/spatial_hash.py:53`, docstring `:20,182-193` |
| **Broadphase** | Filtre grossier (grille / hash spatial) qui candidate les entites proches avant test de rectangles | `entity_grid.py`, `spatial_hash.py` |
| **Narrowphase** | Test exact `colliderect` (ou swept) des boxes candidates ; produit contacts | `contact_system.py:251-300` |
| **pushbox** | Boite de collision physique corps-a-corps (poussee), pas de degats | `entity.py:424` |
| **hitbox (legacy)** | Alias historique = zone offensive unique ; conserve en P2 (pas de renommage appelant) | `entity.py:429` |
| **hurtbox** | Union de toutes les zones vulnerables (legacy = zone unique) | `entity.py:439` |
| **hurtboxes[]** | Liste des zones individuelles (tete / torse / jambes…) issues de `hurtbox_zones` | `entity.py:448` |
| **hurtbox_tags** | Tags par zone pour le matcher d invulnerabilite (cote defense) | `entity.py:453-456` |
| **swept_hurtbox(s)** | Hurtbox swept sur le tick courant (capture frontiere dans `gameplay_loop`) | `entity.py:474,489` |
| **startup telegraph** | Phase d attaque non letale (telegraphe) avant la frame active | rapport §1.4 ; `combat_system.py:38-54` |

### Semantique des hits

| Terme | Definition | Ancre |
|---|---|---|
| **HitProperties** | Dataclass des proprietes d un coup : damage, type, height, priority, clash, hit_level… | `frame_data.py:49-128` |
| **HitboxSpec / PhaseDefinition** | Boite offensive + keyframes par phase (startup/active/recovery) | `frame_data.py:219-253`, `:257+` |
| **HitboxKeyframe** | Instantane taille/offset d une boite a une frame `frame` (frames croissantes) | `frame_data.py:132-161` |
| **height** | Hauteur de la garde visee : `high`/`mid`/`low`/`overhead` | `frame_data.py:93-95,111` |
| **HEIGHT_BLOCK** | Table (height × crouch) → le coup est-il bloque par cette posture | `settings.py:140-149`, consom. `player_controllers.py:174` |
| **Guard.take_hit** | Resolution de garde : `none`/`parry`/`break`/`guard` + chip + flag | `player_controllers.py:164-189` |
| **hit_level** | Niveau du coup (reserve) ; validateur n accepte que `"med"` | `frame_data.py:96-97,127-128` — **O3** |
| **block_mask** | Masque de postures bloquees (spec P3 temp 2) ; **absent du code** | notes seulement — **O1** |
| **unblockable** | Contourne garde et dash-parry | `frame_data.py:86-90,108` |
| **priority / clash** | Priorite hit-vs-hit ; resultats `beat`/`trade`/`clash` (pas des valeurs de champ height) | `frame_data.py:91-92,121-124` ; `combat_system.py:170-211` |
| **zone_mult** | Multiplicateur de degats par zone (ex. tete x1.5) — damage-only, pas invulnerabilite | `contact_system.py:101-147` ; `hit_resolver.py:155` |
| **zone_index** | Index de la zone qui a absorbe le contact (P2.4, expose pour debug/trace) | `contact_system.py:101-108` |
| **matcher tags** | `_zone_vulnerable(zone_tags, hit_tags)` — rend une zone invulnerable si aucun tag commun ; **inert** tant que les coups n ont pas de tags | `contact_system.py:111-119,197` — **O2** |
| **hit-stop / HITSTOP** | Freeze bref a l impact (base + facteurs damage/knockback) | `settings.py:78-79,97` |
| **juggle / OTG / super armor** | Mecaniques de combo / relance au sol / armure pendant les hits | `frame_data.py:73-85` ; `settings.py:101-109` |
| **charge multiplier** | Multiplicateur de degats selon la charge de l attaque | formule `hit_resolver.py:155` |

### Pipeline / systems

| Terme | Definition | Ancre |
|---|---|---|
| **OffensiveBox** | Candidat boite offensive du tick : `box` (discret), `swept` (whole-tick), `kind` = melee/projectile/hazard/contact | `contact_system.py:48-70` |
| **ContactSystem** | Systeme unifie broadphase/narrowphase/resolve partage par les 4 producteurs | `contact_system.py:203+` ; `resolve` `:251-300` |
| **CombatMetrics** | Compteurs `pairs_tested`/`overlaps`/`contacts` par tick (panneau debug) | `contact_system.py:73-79` |
| **ZoneContact** | Contact atterri + zone absorbeuse (index + mult) | `contact_system.py:100-108` |
| **ContactOutcome** | Resultat structure d une resolution de contact | `contact_system.py:90-97` |
| **GuardEvent** | Evenement de garde render-only, vide chaque tick | `contact_system.py:82-87` |
| **HitCandidate / CombatTrace** | Enregistrement debug d un candidat de hit ; ring 256 + drain JSONL si `DEBUG_COMBAT_DUMP=1` | `src/core/level/systems/combat_trace.py:23-38,41-94` |
| **HitResolver** | Applique degats/knockback/garde ; formule multiplieurs (`zone_mult`, type, juggle) | `hit_resolver.py:99-202` |
| **EntityGrid / SpatialHash** | Grille par tick rebuild O(n) / hash spatial avec marge de requete | `entity_grid.py:32-76` ; `spatial_hash.py:53` |
| **Combatant protocol** | Protocole duck-type (rects, swept, tags, `cancel_attack`…) partage par joueur/ennemis | `combatant_protocol.py` |
| **Bench 2.2** | Micro-bench detection seule 1v1/4v4/8v8 (300 it.) ; ref avant/apres | rapport §2.2 — **O4** |
| **F6 / F7 / F8** | Debug : freeze / step 1 tick / replay attaque en boucle | `gameplay_scene.py:123-134` ; `spawn_system.py:152-174` |
| **Overlay `●`/`○`** | Index de boite dessine in-situ (remplace le libelle `bN` texte) | `world_ui.py:295-305,860-888` — **O9** |
| **Parite JSON/builtin** | Test P0.2 : data JSON == fallback builtin pour les 3 sets | rapport §2.3 ; `provider.py:93-100` ; `test_gameplay_data.py` |
| **validateur P4.2** | Regles au chargement attaques : taille, offset enveloppe, keyframes, cooldown, `GameplayDataError` | `attack_loading.py:40-44,121-162` — **O8** |
| **DEBUG_COMBAT_DUMP** | Env var : active le drain JSONL de `CombatTrace` → `logs/combat_trace.jsonl` | `combat_trace.py:57-60,80-94` |

### Plan / decisions

| Terme | Definition | Ancre |
|---|---|---|
| **Paliers P0–P5** | Ordre de livraison du rework : P0 goldens/parite → P1 sweep → P2 zones/keyframes → P3t1 hit-vs-hit → P3t2 hauteur → P4 unif/debug → P5 optionnel | rapport §5 |
| **Axes A–H** | Dimensions du plan (A detection … F authoring, G trace, H perf) ; F partiel, G livre, H hors-plan | rapport §4 |
| **P0.1-bis** | Goldens multi-phases `special_attack` / `claw_swipe` (chantier audit) | commit `5db47ad` |
| **F8 replay** | Replay d attaque en boucle (option DEBUG) | commit `b9a9133` — **O5** (export JSON non livre) |
| **Axe H** | Perf / determinisme / rollback — non engage | rapport L9/Axe H — **O6** |
| **6129613** | Commit zones goblin (x1.5/x1.0/x0.8) — exception aux non-objectifs d equilibrage | rapport §8/§10 |
| **Convention bench** | Regle interne : bench 2.2 rejoue a chaque palier — non tenue apres P0 | rapport §5/§7.3 — **O4** |

---

*Derniere mise a jour : 2026-09-23 (re-audit doc). Ecarts numerotes O1–O9
stables tant que `hitbox_amelioration.md` §10 « Re-audit doc » n est pas
revisee.*
