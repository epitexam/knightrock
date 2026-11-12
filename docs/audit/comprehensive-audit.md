# Audit technique — Knightrock

Audit du 2026-11-12, branche `fix/remediation`, commit `d718a8c`.
Architecture décrite dans `current-architecture.md`.

## Légende

- **Avéré** : reproduit par un script ou mesuré.
- **Probable** : établi par lecture du code, non reproduit.
- **Risque** : plausible, sans défaut observé aujourd'hui.

Classement de chaque sous-système : **KEEP**, **KEEP WITH MINOR
IMPROVEMENTS**, **REFACTOR**, **SIMPLIFY**, **REMOVE**, **REPLACE**.

---

## 1. Résumé exécutif

La base est **saine et au-dessus de la moyenne**. La boucle à pas fixe, l'ordre
du tick, le modèle de combat (frame data, phases explicites, coups balayés,
hurtboxes par zone), la physique de plateforme et le chargement des données sont
bien conçus. **Aucun sous-système ne justifie un remplacement.** Aucun ECS, bus
d'événements général ou réorganisation des dossiers n'est recommandé.

Les problèmes réels sont de quatre ordres :

1. **Trois défauts de gameplay avérés**, tous dans le combat :
   - un appui pendant le hit-stop est perdu (C1), ce qui casse l'enchaînement
     des combos au moment où le joueur appuie le plus ;
   - le délai des dégâts de contact et des pièges dépend de la phase d'un
     compteur, et non du contact (C2) : jusqu'à 0,2 s de retard pour un corps à
     corps, 0,4 s pour un pic ;
   - la touche `R` (bouton View à la manette) téléporte le joueur au départ et
     **lui rend toute sa vie**, en jeu normal (C5).
2. **Les règles qui décident de l'issue d'un coup sont dispersées** dans cinq
   endroits (`HitResolver`, `Entity`, `Player`, `ReactionComponent`,
   `ContactSystem`). Le calcul de la direction du knockback est écrit trois
   fois. C'est le principal frein à l'évolution du combat.
3. **Du code préparatoire n'est vérifié par rien** : le rollback (prévu pour
   le multijoueur) est désactivé en jeu, chaque nouvel état doit y être ajouté,
   et il contient déjà un bug latent (C3).
4. **Le code est noyé dans sa propre prose** : 30 % des lignes de `src/` sont
   des docstrings ou des commentaires, souvent l'historique d'un changement et
   des références à des notes d'audit qui ne sont plus dans le dépôt.

---

## 2. Constats vérifiés (défauts)

### C1 — Les appuis faits pendant le hit-stop sont perdus — **Élevé, avéré, change le ressenti**

- **Où :** `GameplayScene.update` (`src/application/scenes/gameplay_scene.py:111`)
  lit les entrées à chaque tick ; `GameplayLoop.update`
  (`src/core/level/systems/gameplay_loop.py:164-179`) ne lance
  `PhysicsSystem.process`, donc `Entity.update` et `PlayerInputHandler`, que si
  le delta simulé est positif.
- **Mécanisme :** `InputManager.just_pressed` vaut vrai pendant **un seul**
  tick. Pendant un gel (au moins 0,05 s, soit 3 ticks ; 0,14 s soit 8 ticks
  pour une parade), ce tick est consommé sans que le joueur soit mis à jour. Un
  bouton encore tenu à la fin du gel ne produit pas non plus de front montant.
- **Reproduction :** même appui sur ATTACK_1 (ticks 12 et 13). Hors gel :
  attaque lancée au tick 12. Avec un gel des ticks 11 à 14 : **aucune
  attaque**.
- **Conséquence :** dans un hack and slash, le joueur appuie précisément
  pendant le gel qui suit un coup réussi pour enchaîner. L'appui disparaît sans
  trace, et le jeu paraît « manger » des entrées de façon irrégulière. Le saut,
  le dash et le relâchement du saut (jump cut) sont touchés de la même façon.
- **Correction :** voir R1 dans `architectural-recommendations.md`. C'est un
  changement de comportement : à valider par le développeur.

### C2 — Le délai de recharge des contacts s'arme sans contact — **Moyen, avéré, change le ressenti**

- **Où :** `ContactDamageSystem._can_contact`
  (`src/core/level/systems/contact_damage.py:74`) et
  `HazardDamageSystem._can_contact`
  (`src/core/level/systems/hazard_damage.py:50`).
- **Mécanisme :** `can_contact` arme le délai de recharge (12 ticks pour le
  contact, 24 pour les pièges). Or `ContactSystem` l'appelle dans
  `_is_valid_target` (`contact_system.py:202`), **avant** la porte de vitesse et la narrowphase, pour
  chaque cible candidate. Sous 8 entités, la grille n'est pas indexée et
  toutes les cibles de la carte sont candidates.
- **Reproduction :**
  - deux corps éloignés, un tick : délai armé (11 ticks restants) sans aucun
    contact. Puis un vrai contact à 500 px/s : **0 dégât pendant 12 ticks** ;
  - joueur loin d'un pic, un tick, puis debout sur le pic : **24 ticks avant le
    premier dégât** ;
  - deux corps qui se touchent trop lentement pour la règle : délai armé quand
    même.
- **Conséquence :** le premier dégât d'un contact ou d'un pic arrive après un
  délai aléatoire, de 0 à 0,2 s (contact) ou de 0 à 0,4 s (pic), selon la phase
  du compteur. Un joueur peut traverser un pic sans dommage.
- **Pourquoi les tests passent :** ils placent toujours les deux objets déjà en
  contact au premier tick.
- **Correction :** armer le délai dans `record_contact` (après un contact
  résolu), comme le font déjà la mêlée et les projectiles. C'est un changement
  de comportement.

### C3 — Le rollback du joueur efface les timers de jonglage et les compteurs de parade — **Faible aujourd'hui, avéré**

- **Où :** `Player.save_state` (`src/entities/player.py:423`) remplace
  `snapshot.extra` au lieu de le compléter. `Entity.load_state` lit alors des
  valeurs par défaut pour `gravity_scale`, `juggle_timer`, `otg_timer`,
  `parries_given`, `parries_taken` et `parry_stun_*`.
- **Reproduction :** joueur avec `juggle_timer=0.3`, `otg_timer=0.4`,
  `gravity_scale=0.5`, `parries_given=2` ; sauvegarde puis restauration →
  `0.0, 0.0, 1.0, 0`.
- **Conséquence :** aucune en jeu, car le rollback n'y est jamais activé. Mais
  c'est la preuve que ce code n'est pas entretenu par son usage : voir §3.16.

### C4 — Deux sources de vérité pour les ennemis et le joueur — **Moyen, risque avéré**

- **Où :** `src/entities/enemies/types/*.py` et `player_config.py`
  (`DEFAULT_PLAYER_CONFIG`) dupliquent `data/gameplay/enemies.json` et
  `player.json`.
- **Ce qui est vrai aujourd'hui :** les deux copies sont identiques (comparaison
  champ par champ, exécutée pendant l'audit).
- **Ce qui lit quoi :**
  - les ennemis des niveaux lisent le JSON (`WorldBuilder`, ligne 407) ;
  - `is_enemy_type` lit la copie Python (`ENEMY_CONFIGS`) : **un ennemi ajouté
    seulement au JSON est ignoré** au chargement, avec un simple avertissement ;
  - le banc de debug (`SpawnSystem._spawn_enemy`, `spawn_juggle_dummy`) crée
    ses ennemis **sans** passer la configuration JSON.
- **Conséquence :** modifier la vie du gobelin dans `enemies.json` change les
  gobelins du niveau, pas ceux du banc de test, qui sert justement à régler
  l'équilibrage. C'est le même problème que les attaques avaient avant d'être
  ramenées à une seule copie.

### C5 — La touche de réinitialisation rend toute la vie en jeu normal — **Moyen, avéré, décision de design**

- **Où :** `PlayerInputHandler._read_input` (`src/entities/player_input.py:89`)
  → `Entity.reset_position` → `Vitals.reset` (santé au maximum). Liée par
  défaut à `R` et au bouton View (`src/core/input/input_bindings.py:55,72`).
- **Conséquence :** hors mode debug, le joueur peut se soigner entièrement à
  volonté, sans que cela compte comme une mort.
- **À décider :** soit la réserver au mode debug, soit la transformer en
  « recommencer depuis le point de départ » qui compte une mort. Le code ne dit
  pas laquelle des deux était voulue.

---

## 3. Analyse par sous-système

### 3.1 Boucle de jeu et timing — **KEEP**

**Forces.** Pas fixe à 60 Hz avec accumulateur borné (0,1 s) et 6 ticks au
plus par frame, le surplus étant abandonné : pas de spirale de la mort. Rendu
séparé, `render_alpha` à 1 quand une scène fige le monde (pas de tremblement
derrière la pause). Pacing distinct avec et sans vsync, documenté et mesuré.
Le pas fixe est le bon choix pour ce jeu : la frame data du combat est exprimée
en frames à 60 Hz, et la physique dépend de sous-pas réguliers.

**Faiblesse — probable, à vérifier à l'écran.** Seule la **caméra** est
interpolée (`Camera.begin_frame`) ; les sprites sont dessinés à leur position
du dernier tick. Sur un écran à plus de 60 Hz, la caméra qui suit le joueur
glisse en continu tandis que le joueur avance par pas de 1/60 s : le
personnage peut trembler autour du centre de l'écran (environ 6 px de monde par
tick à la course). Le docstring de `Game.render_alpha` affirme le contraire
(« blends each sprite »). À observer sur un écran 120/144 Hz avant toute
décision.

### 3.2 Application et scènes — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** Pile de scènes simple (`switch`, `push`, `pop`), seule la scène du
haut est mise à jour, la pile visible est dessinée, transitions en fondu.
`Game` est redevenu une racine de composition après l'extraction de `Screen`.

**Faiblesses.**
- `GameplayScene` interroge `self.game` avec `getattr(self.game, "ui", None)`,
  `getattr(self.game, "render_alpha", None)`, `getattr(self.game, "notice", None)`
  parce que des tests la pilotent avec un faux `Game` incomplet
  (`gameplay_scene.py:214,288,322,337`). Le code de production se plie aux faux
  objets des tests (voir §3.20).
- `Game` garde une couche de propriétés qui relaient `Screen` (`stage`,
  `presentation`, `window`, `surface`, `topology`, `monitor`…) pour la
  compatibilité des tests. Sans danger, mais du bruit.

### 3.3 Fenêtre et affichage (`core/display`, `application/screen.py`) — **KEEP**

Environ 2 000 lignes pour la fenêtre, les écrans multiples, le letterbox et la
mise à l'échelle. C'est beaucoup pour un jeu de plateforme, mais le sous-système
est cohérent, isolé du gameplay, testé, et a fait l'objet d'une passe récente
avec des essais réels. **Recommandation : ne plus y investir** sans problème
rapporté par un joueur.

### 3.4 Entrées — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** Séparation nette : `EventRouter` (menus, rebinding) d'un côté,
`LocalInputProvider` → `InputState` immuable → `InputManager` de l'autre. Le
verrou des appuis courts (`note_event`) est juste. Les actions d'interface ne
peuvent pas entrer dans la simulation (`_require_discrete`).

**Faiblesses.** C1 (la cause est dans l'ordre du tick, pas dans les entrées) et
C5. `InputManager.apply_remote_state` n'a aucun appelant en production (réseau
spéculatif).

### 3.5 Niveau et systèmes du tick — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** `Level` construit, `GameplayLoop` ordonne, chaque système reçoit
ses collaborateurs : l'ordre du tick se lit dans un seul fichier.
`WorldBuilder` utilise deux registres (couches, objets) : ajouter un type
d'objet Tiled ne demande pas de toucher au constructeur. Les erreurs de carte
sont localisées.

**Faiblesses.**
- **`PhysicsSystem` porte mal son nom.** La physique est dans
  `Entity.update` ; ce système transporte les passagers des plateformes, appelle
  `entity_sprites.update`, puis consacre 90 % de son code à décider des
  particules (poussière, sueur, étourdissement) à partir des noms d'état
  (`physics_system.py`). Un lecteur qui cherche la physique arrive dans les
  effets visuels.
- **Les effets de retour du combat sont déclenchés à trois endroits :**
  `GameplayLoop._emit_guard_fx` (arcs de garde, secousses),
  `GameplayLoop.update` (secousse d'impact lourd, secousse de dash),
  `PhysicsSystem` (effets de mouvement), plus des drapeaux posés sur l'entité
  (`RenderHints.flash_timer`, `Player.dash_started_this_frame`). Ajouter un son
  de coup demanderait de toucher plusieurs de ces endroits.
- `GameplayLoop` accepte tous ses systèmes en `Optional` et les vérifie avec
  `_require`, uniquement pour que les tests puissent construire une boucle
  partielle (`combat_only`). Le type ment au lecteur : en production rien n'est
  optionnel.
- L'enregistrement d'un ennemi dans les groupes (`all_sprites`,
  `entity_sprites`, `combat_sprites`) est écrit trois fois (`WorldBuilder`,
  deux fois dans `SpawnSystem`).
- La fin du tick (caméra, notifications, compteur) est dupliquée entre la
  branche normale et la branche « gel » de `GameplayLoop.update`.

### 3.6 Entités (`Entity`) — **REFACTOR (ciblé)**

**Forces.** Patron `update` lisible avec des hooks clairs ; composants
extraits là où ils portent un état réel (`Vitals`, `ReactionComponent`,
`CombatComponent`, `RenderHints`) ; géométrie physique séparée de l'image ;
hurtboxes par zone dérivées en un seul point (`sync_rects`).

**Faiblesses.**
- **Taille :** 1 214 lignes, environ 80 méthodes. Une grande partie est de la
  délégation : une vingtaine de propriétés relaient `Vitals`
  (`health`, `is_dead`, `invincibility_timer`, `stagger_timer`,
  `super_armor`…), et quatre méthodes relaient `MovementComponent`, qui
  lui-même relaie des fonctions de `physics/` sans rien ajouter
  (`entities/components/movement.py`). Trois couches pour un appel.
- **Les états ne sont pas typés :** `State.entity` est `Any`, comme les
  fonctions de `player_states.py` et `enemy_states.py`. Le code d'IA et de
  locomotion, qui lit le plus d'attributs, est celui que mypy ne vérifie pas
  (272 `Any` dans `src/`).
- Les paramètres du virage (`turn_*`, 8 attributs) et de mouvement
  (11 attributs) sont des champs plats copiés depuis les réglages ; ils
  gagneraient à être deux petites dataclasses.

**Ce qu'il ne faut pas faire :** éclater `Entity` en un ECS ou en une dizaine
de composants. Le patron actuel est le bon ; il faut seulement retirer la
délégation inutile et typer les états.

### 3.7 Joueur — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** Découpage déjà fait et juste : `PlayerInputHandler` (lecture des
entrées), contrôleurs `JumpController` / `GuardController` / `DashController`,
`CrouchPosture`, machine à états construite dans `player_states.py`. Le
`stance` est calculé en un seul endroit. Les noms d'état sont un `Enum`.

**Faiblesses.** `Player.receive_damage` et `_apply_guard_reaction` contiennent
des règles de combat (parade par dash, garde, chip, bris) qui devraient vivre
avec les autres règles d'issue d'un coup (§3.9). La direction du knockback y
est recalculée une troisième fois.

### 3.8 Ennemis et IA — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** Une seule classe `Enemy` pilotée par `EnemyConfig` : aucun
sous-type qui ne différerait que par des nombres. La machine à états couvre
patrouille, poursuite, bords, sauts calculés à partir de la physique réelle et
réactions partagées avec le joueur (`reaction_states.py`). Pour la taille du
jeu, c'est le bon niveau d'abstraction.

**Faiblesses.**
- Deux façons de changer d'état coexistent : `change_state(...)` appelé dans
  `update` (`EnemyIdleState`, `EnemyPatrolState`, `EnemyChaseState`) et le nom
  d'état retourné (`EnemyDizzyState`, états du joueur). Les deux marchent, mais
  il faut lire chaque état pour savoir laquelle il utilise.
- Une seule attaque par type (`attack_name`). Suffisant aujourd'hui ; un
  ennemi à plusieurs coups demandera un choix d'attaque. Pas d'action avant ce
  besoin.
- C4 (configuration en double).

### 3.9 Combat — **KEEP le cœur, REFACTOR la résolution des coups**

C'est le sous-système le plus important et le mieux conçu du projet. Il faut
le dire avant d'en lister les défauts.

**Représentation des attaques — KEEP.**
`AttackDefinition` → `PhaseDefinition` (startup / active / recovery en
frames, `cancel_into`, `reset_targets`) → `HitProperties` (dégâts, knockback,
type, stagger, priorité, clash, hauteur, tags) et `HitboxSpec` (forme, ancre,
keyframes). Dataclasses gelées, validées au chargement, venant du JSON. La
définition est séparée de l'exécution (`AttackStateMachine`). Cooldowns par
attaque dans `CombatComponent`, combos par `ComboTracker`, charge par
`ChargeHandler`.

**Hitboxes et hurtboxes — KEEP.**
Indépendantes des sprites. Formes avancées avec boîte englobante pour la
broadphase, balayage entre deux ticks (pas de traversée), une seule touche par
cible et par phase (`targets_hit`), zones de hurtbox avec multiplicateur et
invulnérabilités. Broadphase par `EntityGrid`, qui renonce à s'indexer quand
ce n'est pas rentable (mesuré par un benchmark dédié).

**Pipeline de contact unifié — KEEP WITH MINOR IMPROVEMENTS.**
`ContactSystem` sert les quatre producteurs. Bonne idée, bien exécutée. Mais
il porte deux règles de jeu qui n'ont rien à y faire :
`_maybe_parry_stun` (importe la classe concrète `Enemy` et change son état) et
la remise à zéro de `parries_taken` (`hasattr`). Et il contient C2 par la façon
dont il appelle `can_contact`.

**Résolution d'un coup — REFACTOR.** C'est le vrai problème du combat. Ce qui
arrive quand un coup touche est décidé en **cinq** endroits, dans un ordre
implicite :

| Décision | Où |
|---|---|
| Dégâts (charge, zone, type, jonglage, étourdi), invincibilité, OTG, finisher | `HitResolver.resolve` |
| Parade par dash, garde, chip, bris de garde | `Player.receive_damage`, `_apply_guard_reaction` |
| Points de vie, flash, knockback, i-frames, knockback lourd → état KNOCKBACK | `Entity.receive_damage`, `ReactionComponent` |
| Bris d'armure, jonglage, combo, recharge du dash, état HURT, stagger | `HitResolver._apply_post_effects` |
| Étourdissement après N parades, remise à zéro du compteur | `ContactSystem._maybe_parry_stun`, `_resolve_melee` |

Conséquences concrètes :
- La direction du knockback (« fixe » ou « relative à la source ») est calculée
  dans `ReactionComponent.apply_knockback`, `ReactionComponent.note_guard_push`
  et `Player._apply_guard_reaction`.
- `combat.on_hit` est appelé depuis `ReactionComponent.handle_heavy_knockback`
  **et** depuis `_apply_post_effects`, avec un `reset_hurt_state` pour défaire
  le premier ; l'ordre est porteur et n'est écrit nulle part.
- `HitResolver` lit `getattr(target, "state_machine")`, `getattr(attacker,
  "dash")` : il ne fait pas confiance au type `Combatant` qu'il reçoit.
- Ajouter une règle (contre, armure partielle, coup critique, son de coup)
  demande d'abord de trouver lequel des cinq endroits est le bon.

**États de combat — KEEP.**
Deux machines coopèrent : la machine d'état de l'entité (ATTACK, HURT,
KNOCKBACK…) et `AttackStateMachine` (phases). La première entre en ATTACK par
interruption quand la seconde attaque ; sortir d'ATTACK termine l'attaque ;
une blessure annule l'attaque. C'est un découpage classique et sain. Les
interruptions et annulations passent toutes par `start_attack`, ce qui évite
les règles contradictoires.

**Synchronisation avec l'animation — limite de conception.**
Le clip d'attaque est joué à une cadence fixe (`ATTACK_FRAME_DURATION`),
indépendante des frames de startup, active et recovery. La plupart des
attaques jouent le même clip `attack`. Ce n'est pas un bug (les hitboxes
suivent la frame data, pas l'image), mais le geste à l'écran et la fenêtre
active peuvent ne pas coïncider. À traiter quand l'art de chaque attaque
existera.

**Hit-stop.** Global, calculé par coup, borné par la parade. Correct, à C1 près.

### 3.10 Physique et collisions — **KEEP**

Résolution AABB par axe avec sous-pas (16 px, 8 au plus par axe), marche,
correction de coin, plateformes à sens unique, collage au sol, détection et
annulation d'écrasement, spatial hash pour le décor. Gravité de montée et de
chute distinctes, coyote time, tampon de saut, jump cut. Géométrie physique
séparée de l'image. C'est ce qu'on attend d'un jeu de plateforme réactif ;
aucun défaut trouvé. Le seul reproche est la couche `MovementComponent` (§3.6).

### 3.11 Animation — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** `Animator` simple, données déclaratives (`AnimationSpec`), cache
des images mises à l'échelle et retournées.

**Faiblesses.**
- **Chargement au premier usage :** les PNG d'un clip sont lus et convertis la
  première fois que le clip joue, en plein combat. Risque d'à-coup au premier
  coup ou à la première apparition d'un ennemi. Non mesuré.
- **Cache par entité, sans borne :** la clé contient la taille ; l'accroupi
  (fondu de hauteur) et l'écrasement du dash produisent une taille par tick
  pendant la transition, donc une mise à l'échelle et une entrée de cache par
  taille. Borné en pratique, à surveiller.
- Synchronisation avec la frame data : voir §3.9.

### 3.12 Rendu et caméra — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** Cible de rendu de taille fixe, culling par blocs pour les tuiles
statiques (gain mesuré : 62 % du culling sur le niveau livré, 97 % à 10 000
tuiles), mises à l'échelle en cache, afterimages et flashs isolés dans le
rendu, monde, HUD et overlay séparés. Caméra à zone morte avec secousse par
« trauma ».

**Faiblesses.** Interpolation de la seule caméra (§3.1). Après un changement de
format d'affichage, `Game._invalidate_assets` vide les caches globaux mais pas
ceux des `Animator` ni les tuiles du niveau en cours : leurs surfaces restent à
l'ancien format, ce qui ralentit les blits sans erreur. Mineur.

### 3.13 Effets visuels (`core/fx`) — **KEEP (gel) ; SIMPLIFY la prose**

4 175 lignes pour des particules décoratives, plafonnées à 64 sprites, sans
effet sur la simulation (jamais incluses dans les instantanés). Le
sous-système est isolé et fonctionne. `fx/tuning.py` compte 190 lignes de code
pour 901 lignes de prose. **Ne pas y investir davantage** ; voir §3.21 pour la
prose.

### 3.14 Ressources — **KEEP WITH MINOR IMPROVEMENTS**

`AssetLibrary` unique, `convert`/`convert_alpha`, chemins compatibles
PyInstaller, repli explicite pour les deux clips manquants (`dash`, `crouch`).
Faiblesses : chargement au premier usage (§3.11), caches non invalidés
(§3.12).

### 3.15 Données de jeu (`data/`, JSON) — **KEEP ; REFACTOR la duplication**

**Forces.** Lecteurs stricts avec emplacement de l'erreur, attaques validées
(cohérence des keyframes, annulations vers des attaques connues), répertoire
de données surchargeable (`KNIGHTROCK_DATA_DIR`).

**Faiblesse.** C4.

### 3.16 Rollback et déterminisme — **KEEP WITH MINOR IMPROVEMENTS** (décision D4 : multijoueur prévu)

- `Level(rollback_enabled=False)` par défaut, et aucun appelant ne passe
  `True` ; `rollback_to` n'est appelé que par les tests ;
  `InputManager.apply_remote_state` n'a aucun appelant.
- Coût : `save_state`/`load_state` dans `Entity`, `Player`, `CombatComponent`,
  `AttackStateMachine`, `ChargeHandler`, `Vitals`, `StateMachine` (qui capture
  par introspection les scalaires de chaque état), les contrôleurs, la posture,
  `Level` ; plus `core/rollback/`, `combat/determinism.py`, `LevelSnapshot`.
  Plusieurs centaines de lignes, et une obligation pour chaque nouvel état.
- Preuves que ce code n'est pas maintenu par l'usage : C3, et un commentaire
  dans `Player.save_state` qui raconte un oubli précédent (`down_held`).
- Le déterminisme n'est d'ailleurs pas complet : `_ENTITY_ID_SEQUENCE` n'est
  jamais remis à zéro entre niveaux, et le `random.Random()` d'une entité n'est
  pas semé.
- **Décision du développeur (D4, 2026-11-12)** : un mode multijoueur est
  prévu, le rollback est donc conservé. Conséquence : corriger C3 et ajouter
  un test « sauvegarder, restaurer, rejouer N ticks, comparer » en CI, faute de
  quoi ce code continuera de se dégrader sans que personne ne le voie.

### 3.17 Interface, HUD et overlay de debug — **KEEP (gel)**

HUD et menus : vues séparées des modèles (`MenuModel`, `MenuView`), captures
de référence au pixel. L'overlay de debug compte environ 4 400 lignes, plus
6 200 lignes de tests, et concentre un tiers des `getattr` restants (il reçoit
tous les sprites du niveau, de types différents). Il n'a aucun effet sur le jeu.
**Ne pas le refactorer** : c'est un outil, il marche, et son coût d'entretien
est déjà payé.

### 3.18 Audio — **KEEP**

`AudioBus` abonné au bus d'événements, jamais fatal sans carte son, volumes par
catégorie. Seuls des sons d'interface existent. Il n'y a aucun son de combat,
ce qui est une lacune de contenu plutôt qu'un défaut d'architecture ; mais
l'absence d'un point unique de « retour de combat » (§3.5) rendra leur ajout
plus coûteux qu'il ne devrait.

### 3.19 Configuration (`core/settings.py`) — **KEEP WITH MINOR IMPROVEMENTS**

Classes-espaces de noms de constantes, lues partout, jamais modifiées. Simple
et adapté. Quelques réglages de gameplay coexistent avec leurs équivalents JSON
(par exemple `Physics.PLAYER_SPEED` et `player.json`) ; préciser lequel fait foi
pendant le traitement de C4.

### 3.20 Tests et fiabilité — **KEEP WITH MINOR IMPROVEMENTS**

**Forces.** 3 408 tests en 26 s, couverture de 94 % selon le README, tests
unitaires des règles (dégâts, jonglage, garde, priorité, frame data,
collisions), tests sans tête de la boucle, captures de référence, benchmarks
reproductibles, test des frontières de couches.

**Faiblesses.**
- **Le code de production se plie aux faux objets des tests.** Exemples :
  `contact_system.py` (« `getattr` remains for stubs »), `_is_valid_target`
  (« exercised with minimal stubs »), `GameplayScene` (§3.2), `GameplayLoop`
  (§3.5). On compte 529 `SimpleNamespace` et 523 accès à des attributs privés
  dans les tests. Chaque tolérance ajoutée pour un faux objet affaiblit un
  contrat, et c'est exactement par là qu'un bug passe inaperçu : le verrou du
  saut mural, corrigé le 2026-11-11, était invisible parce que les tests
  utilisaient des substituts.
- **Les scénarios testés commencent tous « en contact ».** C2 a échappé aux
  tests pour cette raison. Il manque des tests de séquence : approche, contact,
  premier tick de dégâts.
- Huit fichiers de test lisent le texte source (`read_text`, `inspect`) : ces
  tests cassent sur un renommage sans changement de comportement.

### 3.21 Documentation dans le code — **SIMPLIFY**

- 30 % des lignes de `src/` sont de la prose (25 % de docstrings, 5 % de
  commentaires). 157 passages racontent l'historique (« used to », « measured
  … »). 130 références renvoient à des identifiants d'audit (`audit F1.2`,
  `Phase 3 #4`, `P4.1`, `PERF-02`) dont les documents ont été supprimés de
  `notes/` (supprimé depuis ; ce qui restait ouvert est repris dans
  `final-report.md` §12).
- Pour un développeur qui découvre le jeu, ces textes sont précieux quand ils
  expliquent **pourquoi** une règle existe ; ils deviennent du bruit quand ils
  racontent **comment** on en est arrivé là. L'historique a sa place dans les
  messages de commit, qui sont d'ailleurs déjà très détaillés.
- Le rapport code/prose rend les gros fichiers plus longs à lire qu'ils ne le
  sont : `Entity` fait 1 214 lignes, mais beaucoup moins de code.

---

## 4. Pratiques Python

| Sujet | Constat | Avis |
|---|---|---|
| Annotations | mypy strict, bloquant, sans erreur | Très bien |
| `Any` | 272, concentrés dans les états et les FX | Typer les états (§3.6) |
| Dataclasses | gelées pour les données (`HitProperties`, `PhaseDefinition`, `InputState`), validées en `__post_init__` | Très bien |
| Enums | `PlayerState`, `EnemyState` en `(str, Enum)`, `Stance`, `PhaseState`, `Refusal` | Bien. `HitProperties.clash`, `height`, `hit_level`, `block_mask` et `GuardEvent.kind` restent des chaînes validées à la main : des `StrEnum` les rendraient vérifiables par mypy. |
| Protocols | Nombreux, structurels, jamais testés par `isinstance` | Bien ; quelques-uns servent surtout aux faux objets des tests |
| `getattr`/`hasattr` | 239 dans `src/`, environ 1 200 appels par tick mesurés | Légitimes pour les événements pygame et les groupes hétérogènes ; injustifiés sur des types connus (`HitResolver`, `ContactSystem`, `GameplayScene`) |
| Héritage | Court : `Sprite → Entity → Player / Enemy` ; états en classes | Adapté |
| Exceptions | Dix `except Exception`, tous commentés et justifiés (matériel, écran d'erreur, isolement des abonnés) | Bien |
| Nommage | Clair, sauf `PhysicsSystem` (§3.5) et `hitbox` qui désigne la pushbox | Mineur |
| Duplication | Direction du knockback (3×), enregistrement des ennemis (3×), configuration ennemis/joueur (2×) | À traiter |

## 5. Pratiques Pygame

- **Bon usage.** `FRect` partout pour les positions flottantes ;
  `convert`/`convert_alpha` au chargement ; `smoothscale` et `flip` mis en
  cache ; `Group.update` pour les FX ; `Clock.tick` comme seul pacer sans vsync ;
  file d'événements vidée une fois par frame ; cible de rendu fixe puis mise à
  l'échelle.
- **À surveiller.** `dash_frame` crée une surface mise à l'échelle par frame
  pendant le dash (5 ticks, sans conséquence aujourd'hui). Chargement des clips
  au premier usage (§3.11). Les `pygame.sprite.Group` mélangent des objets de
  types différents (tuiles, plateformes, entités), ce qui explique une partie
  des `getattr` ; c'est l'usage normal de pygame et ce n'est pas à changer.

## 6. Performances

Mesures sans tête (pilote SDL `dummy`, donc CPU seul), niveau 0 réel :
12 entités, 35 pièges, cible 1920×1080.

| Mesure | Médiane | 99e centile |
|---|---|---|
| Tick de simulation | 2,87 ms | 3,69 ms |
| Dessin du monde | 3,62 ms | 5,75 ms |

> **Correction (étape B).** Ces valeurs ont été prises sur une machine chargée.
> Remesurées côte à côte sur le commit de départ et après refactorisation : tick
> **1,9 ms**, dessin **1,8 ms**, identiques avant et après. Les conclusions
> ci-dessous ne changent pas ; le budget utilisé est d'environ 22 % à 60 Hz.

- **Confirmé :** environ 6,5 ms par frame à 60 Hz dans la mesure initiale
  (3,7 ms remesuré, voir la correction ci-dessus). Aucun goulot unique : le profil du tick se répartit entre la
  résolution des collisions, le spatial hash, `sync_rects` et `getattr`
  (≈ 1 200 appels par tick).
- **Probable :** le tick croît à peu près linéairement avec le nombre
  d'entités ; avec 40 à 50 ennemis actifs, on approcherait 10 ms. La grille
  d'entités évite tout coût quadratique.
- **Risque :** à-coup au premier usage d'un clip (§3.11). À mesurer avec un
  journal du temps de frame pendant la première minute d'un niveau.
- **Pas d'optimisation recommandée maintenant.** Le jeu tient dans son budget ;
  les gains disponibles sont dispersés et faibles.

## 7. Dette technique résumée

| # | Sujet | Classement | Gravité |
|---|---|---|---|
| C1 | Appuis perdus pendant le hit-stop | Correctif | Élevée |
| C2 | Délai de contact armé sans contact | Correctif | Moyenne |
| C5 | Réinitialisation qui soigne, en jeu normal | Décision | Moyenne |
| C4 | Configuration ennemis/joueur en double | REFACTOR | Moyenne |
| §3.9 | Issue d'un coup décidée en cinq endroits | REFACTOR | Moyenne |
| §3.5 | Retour de combat (FX, secousses) dispersé, `PhysicsSystem` mal nommé | REFACTOR | Moyenne |
| §3.16 | Rollback non exercé en jeu, bug latent C3 | KEEP + test d'invariant | Moyenne |
| §3.20 | Production qui tolère les faux objets des tests | KEEP WITH MINOR | Moyenne |
| §3.21 | 30 % de prose, références d'audit orphelines | SIMPLIFY | Faible à moyenne |
| §3.6 | Délégation `Entity` → composants, états typés `Any` | REFACTOR | Faible |
| §3.1 | Interpolation de la caméra seule | À vérifier | Faible à moyenne |
| §3.11 | Clips chargés au premier usage | KEEP WITH MINOR | Faible |

## 8. Classement complet

| Sous-système | Classement |
|---|---|
| Boucle et timing | KEEP |
| Application, scènes | KEEP WITH MINOR IMPROVEMENTS |
| Fenêtre et affichage | KEEP |
| Entrées | KEEP WITH MINOR IMPROVEMENTS |
| Niveau, `GameplayLoop`, systèmes | KEEP WITH MINOR IMPROVEMENTS |
| `Entity` | REFACTOR (ciblé) |
| `Player` | KEEP WITH MINOR IMPROVEMENTS |
| Ennemis et IA | KEEP WITH MINOR IMPROVEMENTS |
| Combat : définition des attaques, frame data | KEEP |
| Combat : hitboxes, hurtboxes, balayage | KEEP |
| Combat : `ContactSystem` | KEEP WITH MINOR IMPROVEMENTS |
| Combat : résolution d'un coup | REFACTOR |
| Combat : états (deux machines) | KEEP |
| Physique et collisions | KEEP |
| Animation | KEEP WITH MINOR IMPROVEMENTS |
| Rendu et caméra | KEEP WITH MINOR IMPROVEMENTS |
| Effets visuels (code) | KEEP |
| Effets visuels (prose de `tuning.py`) | SIMPLIFY |
| Ressources | KEEP WITH MINOR IMPROVEMENTS |
| Données JSON | KEEP ; REFACTOR la duplication |
| Rollback, déterminisme réseau | KEEP WITH MINOR IMPROVEMENTS (multijoueur prévu) |
| HUD et menus | KEEP |
| Overlay de debug | KEEP (gel) |
| Audio | KEEP |
| `settings.py` | KEEP WITH MINOR IMPROVEMENTS |
| Tests | KEEP WITH MINOR IMPROVEMENTS |
| Prose dans le code | SIMPLIFY |
| **Aucun** | REPLACE |
