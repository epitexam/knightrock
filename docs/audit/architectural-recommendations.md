# Recommandations architecturales — Knightrock

Suite de `comprehensive-audit.md`. Chaque recommandation part d'un constat
référencé (C1 à C5, §x.y), compare les options et retient la moins
perturbatrice qui règle le problème.

**Principe directeur :** l'architecture actuelle est bonne. Les
recommandations corrigent des défauts localisés ; aucune ne déplace de dossier
ni n'introduit de nouveau paradigme (ECS, bus général, gestionnaires).

---

## R1 — Ne plus perdre les appuis pendant le hit-stop (C1)

**Problème.** Les entrées sont lues à chaque tick (`GameplayScene.update`),
mais le joueur n'est mis à jour qu'en dehors du gel (`GameplayLoop.update`).
Le front montant d'un appui fait pendant le gel est perdu.

**À préserver.** Le gel global (toute la simulation s'arrête), le calcul de sa
durée, le tampon d'attaque de `StateMachine`, le verrou des appuis courts de
`LocalInputProvider.note_event`.

**Options.**

| Option | Principe | Avis |
|---|---|---|
| A. Lire les entrées seulement sur les ticks simulés | Déplacer `input_manager.update()` de la scène vers le niveau, après la décision de gel. Le verrou `note_event` garde les appuis clavier faits pendant le gel jusqu'au premier tick simulé. Étendre ce verrou aux boutons de manette (`JOYBUTTONDOWN`). | **Retenue.** Petit changement, au bon endroit : un tick gelé n'existe pas pour le joueur, il ne doit donc pas consommer ses entrées. |
| B. Faire tourner `PlayerInputHandler` pendant le gel | Le joueur lit et met en tampon, sans bouger. | Rejetée : `start_attack` démarrerait une attaque pendant le gel, et l'ordre lecture → machine à états serait différent selon le gel. |
| C. Accumuler les fronts dans `InputManager` jusqu'à leur consommation | Ensemble « appuyé depuis la dernière lecture simulée ». | Possible, mais duplique le rôle du verrou existant. |

**Plus petite amélioration.** Option A en deux commits : (1) le niveau lit les
entrées quand il simule, (2) le verrou couvre les boutons de manette.

**Risques.** Change le ressenti : un appui pendant le gel part au premier tick
après le gel, ce qui est le comportement attendu d'un hack and slash, mais qui
doit être validé à la manette. Le mode debug « figé » (F6/F7) lit aussi les
entrées : garder la même règle.

**Vérification.** Test sans tête avec `ScriptedInputProvider` : appui pendant
un gel de 4 ticks → attaque lancée au premier tick dégelé ; même chose pour le
saut et le dash. Puis essai à la manette.

---

## R2 — N'armer le délai de contact qu'après un contact (C2)

**Problème.** `ContactDamageSystem` et `HazardDamageSystem` arment leur délai
de recharge dans `can_contact`, appelé pendant le filtrage, avant tout test de
recouvrement.

**À préserver.** Le pipeline commun `ContactSystem`, les délais de 12 et 24
ticks, la porte de vitesse (`MomentumGate`).

**Plus petite amélioration.** `can_contact` ne fait que lire le délai ;
l'armement passe par `record_contact`, que `ContactSystem` appelle déjà après
un contact résolu (c'est ce que font la mêlée et les projectiles). Le
commentaire de `HazardDamageSystem._can_contact` (ne pas donner « une seconde
réponse » dans le même tick à une cible invincible) reste satisfait : une cible
invincible ne produit pas de contact, elle est simplement réévaluée au tick
suivant.

**Risques.** Change le ressenti : le premier dégât arrive au premier tick de
contact, au lieu d'un délai aléatoire. Les pièges deviennent plus « justes »,
donc un peu plus durs. À valider.

**Vérification.** Nouveaux tests de séquence : approche puis contact → dégât au
premier tick de contact ; contact lent → aucun délai armé ; cible invincible
puis vulnérable → dégât dès la fin de l'invincibilité.

---

## R3 — Décider du rôle de la touche de réinitialisation (C5)

**Options.**
- Réservée au mode debug (lue seulement si `Debug.is_enabled()`, retirée des
  bindings par défaut). **Recommandée** : c'est un outil de test.
- Garder pour le joueur, mais comme « recommencer au départ » qui compte une
  mort et ne rend pas la vie.

**Vérification.** Test : sans debug, l'action ne change ni la position ni la vie.

---

## R4 — Une seule source de vérité pour les ennemis et le joueur (C4)

**Problème.** `enemies.json` / `player.json` et `entities/enemies/types/*.py` /
`DEFAULT_PLAYER_CONFIG` décrivent les mêmes valeurs. `is_enemy_type` et le banc
de debug lisent la copie Python.

**Options.**

| Option | Avis |
|---|---|
| A. JSON seul, comme les attaques depuis leur unification | **Retenue.** Cohérent avec la décision déjà prise pour `attacks.json` : démarrer sur des valeurs non relues est pire que refuser de démarrer. |
| B. Garder Python comme repli | Rejetée : c'est la situation actuelle, et la divergence est silencieuse. |

**Changement.** `create_enemy` et `is_enemy_type` reçoivent la table chargée
(`GameplayData.enemies`) ; `SpawnSystem` la reçoit à sa construction ;
`types/*.py` et le repli de `provider.py` disparaissent, ou deviennent des
données de test. Préciser lequel, de `settings.Physics` ou de `player.json`,
fait foi pour les valeurs communes.

**Risques.** Faibles. Les tests qui importent `GOBLIN_CONFIG` passent par un
chargement JSON (fixture).

**Vérification.** Ajouter un ennemi uniquement au JSON (fixture temporaire) →
il est créé par `WorldBuilder` et par le banc de debug.

---

## R5 — Regrouper la décision « que fait ce coup » (§3.9)

C'est la recommandation structurelle la plus importante.

**Problème.** L'issue d'un coup est décidée dans `HitResolver`,
`Entity.receive_damage`, `Player.receive_damage` / `_apply_guard_reaction`,
`ReactionComponent` et `ContactSystem` (étourdissement par parades). La
direction du knockback est calculée trois fois ; `combat.on_hit` est appelé
deux fois et défait une fois ; l'ordre ne se lit nulle part.

**À préserver absolument.** La définition des attaques, la frame data, les
hitboxes, le balayage, `ContactSystem` comme pipeline de détection,
`CombatComponent.start_attack` comme point unique de refus, `DamageResult`,
toutes les valeurs numériques.

**Options.**

| Option | Principe | Avis |
|---|---|---|
| A. Documenter l'ordre et ne rien déplacer | Un commentaire et un test d'ordre. | Insuffisant : le prochain ajout (contre, coup critique, son) reste à placer au hasard. |
| B. `HitResolver` devient le seul décideur ; les entités exposent des opérations élémentaires | La défense (`GuardController.take_hit`, parade par dash) est appelée par le résolveur via un petit protocole `Defender` ; le résolveur choisit la réaction (repoussé, projeté, blessé, chancelant) et appelle `Vitals`, `ReactionComponent`, `CombatComponent` ; l'étourdissement par parades est un effet côté attaquant, décidé au même endroit. Une seule fonction de direction de knockback. | **Retenue.** Même architecture, responsabilités rassemblées. Aucune nouvelle couche. |
| C. Pipeline de dégâts en étapes configurables | Liste d'étapes enregistrées. | Rejetée : abstraction sans besoin, l'ordre redevient implicite. |

**Mise en œuvre incrémentale (chaque étape à comportement constant) :**

1. Écrire d'abord une **matrice de caractérisation** : pour chaque attaque
   livrée et chaque situation de la cible (au repos, en garde face / dos, dash
   dans la fenêtre de parade, en l'air, accroupie, super-armure, étourdie,
   presque morte), enregistrer le `DamageResult`, la vie, la vitesse et l'état
   obtenus avec le code actuel. Ce test doit passer avant et après chaque étape.
2. Une seule fonction `knockback_direction(...)` remplace les trois calculs.
3. L'étourdissement par parades quitte `ContactSystem` (et son
   `isinstance(attacker, Enemy)`) pour le résolveur, sur un champ déclaré par
   `Combatant`.
4. La décision de garde et de parade quitte `Player.receive_damage` pour le
   résolveur, qui interroge le défenseur. `Player` garde ses contrôleurs.
5. Le choix de la réaction (knockback lourd ou blessure, puis stagger) est
   écrit une seule fois, dans l'ordre actuel.

**Risques.** Moyens : c'est le cœur du jeu. Ils sont couverts par l'étape 1.
Ne pas mélanger ce chantier avec R1 et R2, qui changent le comportement.

**Bénéfice.** Une règle de combat nouvelle se place à un seul endroit, testable
sans `Level`.

---

## R6 — Un seul point pour le retour de combat, et une physique qui s'appelle physique (§3.5)

**Problème.** `PhysicsSystem` fait surtout des particules ; les secousses et
les FX de garde sont dans `GameplayLoop` ; les flashs sont posés par
`Entity.receive_damage`. Pas d'endroit naturel pour un son de coup.

**Options.**

| Option | Avis |
|---|---|
| A. Une étape `FeedbackSystem` dans le tick, qui lit les faits du tick (contacts, événements de garde, impact, atterrissages, dash commencé) et produit FX, secousses et, plus tard, sons | **Retenue.** C'est une étape de plus dans `GameplayLoop`, pas un mécanisme nouveau. Les listes par tick existent déjà (`guard_events`, `zone_contacts`, `impact`). |
| B. Publier les coups sur `EventBus` | Rejetée : le bus sert à l'application, ses abonnés sont isolés et ne doivent pas toucher au monde ; il disperserait les effets au lieu de les rassembler. |

**Changement.** `PhysicsSystem` garde le transport par plateforme et
`entity_sprites.update` ; les fonctions FX de `physics_system.py` et
`GameplayLoop._emit_guard_fx` passent dans `FeedbackSystem`. Les drapeaux
`dash_started_this_frame` et `landed_impact` deviennent des faits du tick lus
par cette étape.

**Risques.** Faibles ; ordre des FX à conserver (le test des FX le vérifie).

**Vérification.** Suite existante des FX et des secousses, captures de
référence.

---

## R7 — Garder le rollback, mais le vérifier (§3.16, C3)

**Décision du développeur (D4) : option B**, un mode multijoueur est prévu.

**Options.**

| Option | Quand |
|---|---|
| A. Retirer `core/rollback/`, les instantanés (`save_state`/`load_state`, `*Snapshot`), `combat/determinism.py`, `InputManager.apply_remote_state`, l'enregistrement de `TickSystem` | **Recommandée** si aucun mode réseau ni rembobinage n'est prévu dans les prochains mois. |
| B. Garder, corriger C3, et ajouter un test d'invariant « sauvegarder, restaurer, rejouer N ticks, comparer » sur un vrai niveau | Si le réseau est un objectif réel. Le test doit tourner en CI, sinon le code se dégradera à nouveau. |

Le compteur `Level.tick` reste utile (trace de combat) dans les deux cas.

**Risques.** A : faible, aucun appelant en production. B : coût continu.

---

## R8 — Des tests qui utilisent les vrais types (§3.20)

**Problème.** Le code de production garde des `getattr` « pour les stubs »
(`ContactSystem`, `HitResolver`, `GameplayScene`) et `GameplayLoop` accepte des
systèmes absents pour un montage de test.

**Changement, progressif :**
- tests de combat : `tests/fakes.py` et `helpers.make_entity` (de vrais
  `Entity`) plutôt que `SimpleNamespace` ; puis retirer les tolérances de
  production correspondantes, un module à la fois ;
- `GameplayScene` : un faux `Game` complet unique dans les tests ;
- `GameplayLoop` : systèmes obligatoires, et un constructeur de test qui monte
  la boucle complète avec de vrais systèmes ;
- ajouter des **tests de séquence** (approche, contact, sortie) pour le contact,
  les pièges et le hit-stop : c'est la famille de tests qui aurait détecté C1 et
  C2 ;
- remplacer les tests qui lisent le texte source par des tests de comportement.

**Risques.** Faibles ; la tentative précédente a cassé 14 tests à stubs, ce qui
indique l'ordre : réécrire les tests d'abord, retirer la tolérance ensuite.

---

## R9 — Alléger la prose du code (§3.21)

**Règle proposée**, à écrire dans le README (section contribution) :
- un docstring dit ce que fait la fonction et pourquoi la règle existe ;
- l'historique (« used to », mesures d'une session, identifiants d'audit) va
  dans le message de commit ou dans `docs/` ;
- un commentaire dans le corps explique un invariant ou un choix non évident.

**Changement.** Une passe mécanique sur les fichiers les plus chargés
(`fx/tuning.py`, `entity.py`, `game.py`, `physics_system.py`), puis la règle au
fil de l'eau. Retirer les 130 identifiants d'audit orphelins.

**Risques.** Aucun sur le comportement ; relecture attentive pour ne pas
supprimer une explication utile. Ne pas modifier de code dans les mêmes
commits.

---

## R10 — Alléger `Entity` et typer les états (§3.6)

- `MovementComponent` n'ajoute rien : soit `Entity` appelle directement les
  fonctions de `physics/`, soit le composant garde `velocity`/`on_surface` mais
  les appels ne passent plus par trois couches.
- Les propriétés qui relaient `Vitals` peuvent être lues sur `entity.vitals`
  par les systèmes ; garder seulement celles du protocole `Combatant`.
- `State` générique sur le type d'entité (`State[Player]`, `State[Enemy]`) :
  mypy vérifie enfin l'IA et la locomotion.
- Réglages de mouvement et de virage regroupés en deux dataclasses.

Faible priorité, mais forte valeur pour mypy. **Ne pas** découper `Entity`
davantage.

---

## R11 — Petites corrections

| # | Sujet | Changement |
|---|---|---|
| R11.1 | Enregistrement des ennemis en trois endroits | `SpriteGroups.add_fighter(entity)` |
| R11.2 | Fin de tick dupliquée dans `GameplayLoop.update` | Une seule fin de tick après la branche simulée |
| R11.3 | Chaînes validées à la main (`clash`, `height`, `hit_level`, `block_mask`, `GuardEvent.kind`) | `StrEnum` |
| R11.4 | Transitions d'IA par `change_state` dans `update` | Retourner le nom d'état, comme le joueur |
| R11.5 | Clips chargés au premier usage | Précharger les clips du joueur et des ennemis présents au chargement du niveau |
| R11.6 | Caches d'`Animator` et tuiles non invalidés au changement de format | Vider les caches des animateurs dans `_invalidate_assets`, ou recharger le niveau |
| R11.7 | Interpolation de la caméra seule (§3.1) | **D'abord observer** sur un écran à 120/144 Hz. Si le joueur tremble, interpoler aussi la position dessinée des entités (origine capturée au début du tick, déjà disponible). Corriger le docstring de `render_alpha` dans tous les cas. |

---

## Ce qui n'est pas recommandé, et pourquoi

| Idée | Pourquoi non |
|---|---|
| ECS | Un joueur et quelques dizaines d'ennemis ; le coût est dans les collisions et le dessin, pas dans l'organisation des données. La composition existante suffit. |
| Bus d'événements général | Le bus actuel a un rôle précis (simulation → application). Les effets de combat ont besoin d'être rassemblés (R6), pas diffusés. |
| Réorganiser les dossiers (`core/level` → `world/`…) | Le nom `core` est imparfait (§2.1 de l'architecture), mais le renommage toucherait des centaines d'imports et de tests sans corriger un seul défaut. |
| Remplacer `StateMachine` | Elle fait ce qu'il faut : interruptions à priorité, tags, tampon. |
| Optimiser maintenant | 40 % du budget à 60 Hz, aucun goulot. Mesurer à nouveau quand un niveau dépassera 30 ennemis. |
| Refactorer l'overlay de debug ou l'affichage | Gros mais isolés, testés, sans effet sur le jeu. |
| Sous-classes d'ennemis | La configuration couvre les différences actuelles. |

---

## Architecture cible

La structure reste celle d'aujourd'hui. Seuls changent les points ci-dessous.

```
src/
├── application/        inchangé (GameplayScene ne lit plus les entrées : R1)
├── core/
│   ├── input/          verrou des appuis étendu aux boutons de manette (R1)
│   ├── level/
│   │   ├── level.py    lit les entrées sur les ticks simulés (R1)
│   │   └── systems/
│   │       ├── gameplay_loop.py     systèmes obligatoires, une seule fin de tick (R8, R11.2)
│   │       ├── physics_system.py    transport + update des entités seulement (R6)
│   │       ├── feedback_system.py   NOUVEAU : FX, secousses, plus tard sons de combat (R6)
│   │       ├── contact_system.py    détection seulement ; plus de règle de parade (R5)
│   │       ├── contact_damage.py    délai armé après contact (R2)
│   │       └── hazard_damage.py     délai armé après contact (R2)
│   └── rollback/       conservé ; test d'invariant en CI (R7-B)
├── combat/
│   └── hit_resolver.py seul décideur de l'issue d'un coup (R5)
├── entities/
│   ├── entity.py       opérations élémentaires, moins de délégation (R10)
│   ├── player.py       garde ses contrôleurs, plus de règle de garde dans receive_damage (R5)
│   └── enemies/        configuration lue depuis le JSON uniquement (R4) ; types/ retiré
├── states/             états typés par entité (R10)
└── data/               source unique des valeurs de jeu (R4)
```

Tick cible (les étapes changées sont en gras) :

```
spawner de debug
hit-stop → si gel : caméra, notifications, compteur ; fin
**lecture des entrées**
capture des origines de balayage
plateformes → pièges → **PhysicsSystem (transport + Entity.update)**
séparation → mêlée → projectiles → contact → pièges   (détection : ContactSystem ;
                                                      issue : **HitResolver seul**)
**FeedbackSystem (FX, secousses, sons)**
retrait des morts → réapparition → progression
caméra → notifications → compteur
```

### Raisons de chaque décision

- **R1 dans le niveau, pas dans la scène :** c'est le niveau qui sait si le
  tick est gelé.
- **R2 dans `record_contact` :** c'est déjà le contrat des deux autres
  producteurs ; on aligne, on n'invente pas.
- **R4 sur JSON :** même décision que pour les attaques, déjà justifiée dans
  `provider.py`.
- **R5 dans `HitResolver` :** il est déjà le point d'entrée de la résolution,
  testé seul ; il lui manque seulement les décisions qui ont fui ailleurs.
- **R6 comme étape du tick :** l'ordre du tick est la grande force du projet ;
  un effet doit y avoir sa place comme le reste.
- **R7 :** du code non exécuté en jeu ne reste correct que si un test
  l'exécute ; le multijoueur étant prévu, c'est le test qu'on ajoute.
