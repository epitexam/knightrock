# Rapport final — refactorisation de Knightrock

Étape B, 2026-11-12, branche `fix/remediation`, de `d718a8c` (point de départ
de l'audit) à la tête de branche. Seize commits, un par changement, chacun vert
sur `pytest`, `mypy` et `ruff`.

Décisions du développeur prises en compte : D1, D2 et D3 acceptés (« d'accord
avec tout ») ; D4, rollback **conservé** pour le multijoueur prévu ; D5
(interpolation) laissé en attente d'une observation à l'écran.

---

## 1. Résumé

- **Trois défauts de gameplay corrigés** (C1, C2, C5). Ce sont les seuls
  changements de comportement de toute l'étape.
- **Un bug latent du rollback corrigé** (C3), et un test d'invariant qui
  vérifie désormais 392 valeurs à chaque restauration.
- **Une seule source pour les valeurs des combattants** (C4) : les copies
  Python des ennemis et du joueur sont supprimées.
- **Le combat est mieux rangé, sans aucun changement d'issue** : direction du
  knockback unique, règle des parades sortie de `ContactSystem`, enchaînement
  complet d'un coup documenté au même endroit. Les 421 issues de coups de la
  matrice de caractérisation sont identiques.
- **Les effets visuels et les secousses ont un seul propriétaire**
  (`FeedbackSystem`), et `PhysicsSystem` ne fait plus que de la physique.
- **Le typage couvre enfin l'IA et la locomotion** (`State[Player]`,
  `State[Enemy]`), et le pipeline de contact lit des champs déclarés au lieu de
  tolérer des faux objets incomplets.
- **Aucun remplacement de sous-système, aucune réorganisation de dossiers,
  aucune nouvelle dépendance.**

## 2. Changements, par étape

| Étape | Commit | Ce qui a changé | Comportement |
|---|---|---|---|
| 0 | `7514383` | Matrice de caractérisation des coups (`tests/golden/hit_outcomes.json`, 421 issues) ; tests de séquence pour C1, C2, C5 (échecs attendus stricts) | Inchangé |
| 1 | `4bb5c8e` | **C1** : le niveau lit les entrées seulement sur les ticks simulés ; les boutons de manette sont verrouillés comme les touches | **Changé** |
| 1 | `a85a2ad` | **C2** : le délai de contact et de piège s'arme après un contact (`record_contact`), plus pendant le filtrage | **Changé** |
| 1 | `971ada4` | **C5** : la touche de réinitialisation n'agit qu'en mode debug ; ligne « Reset (debug) » dans l'écran des contrôles | **Changé** |
| 2 | `5eb8bfc` | **C4** : `enemies.json` et `player.json` obligatoires et seule source ; `shipped_gameplay_data()` ; banc de debug et `WorldBuilder` lisent la même table ; `types/`, `configs.py`, `is_enemy_type`, `DEFAULT_PLAYER_CONFIG` supprimés | Inchangé (valeurs comparées champ par champ) |
| 3 | `9df9efa` | **C3** : `Player.save_state` complète les instantanés ; test d'invariant du rollback ; le test bout en bout passe par un fournisseur d'entrées | Inchangé en jeu |
| 4 | `1af0b3e` | `push_direction()` remplace trois copies de la règle de direction | Inchangé (matrice) |
| 4 | `42a8382` | `Combatant.on_parried()` / `on_damage_landed()` ; `ContactSystem` n'importe plus `Enemy` ; enchaînement d'un coup documenté dans `hit_resolver.py` | Inchangé (matrice) |
| 5 | `5347aa3` | `FeedbackSystem` (FX de mouvement, anneaux de garde, secousses) ; `PhysicsSystem` réduit au transport et à la mise à jour ; `SpriteGroups.add_fighter` ; une seule fin de tick | Inchangé (goldens, tests FX) |
| 6 | `bc9cde1` | Le pipeline de contact et `GameplayScene` lisent les champs déclarés ; `BodyStub` et `game_shape()` dans `tests/fakes.py`, épinglés au protocole par `test_fakes.py` | Inchangé |
| 7 | `5542e55` | Les états ennemis renvoient l'état suivant au lieu d'appeler `change_state` | Inchangé (goldens) |
| 7 | `959c614` | Préchargement des clips au chargement du niveau ; caches d'`Animator` invalidés au changement de format d'affichage | Inchangé |
| 7 | `68b9460` | `State` générique sur le combattant ; `Player.combat` déclaré `CombatComponent` ; `Enemy.attack_name` en `MoveId` | Inchangé |
| 7 | `1ab85a8` | `Entity` appelle directement les fonctions de `physics/` ; `MovementComponent` ne garde que l'état cinématique | Inchangé |
| 7 | `7a4ef06` | `Clash`, `Height`, `HitLevel`, `BlockMask` en `StrEnum` ; erreur JSON localisée | Inchangé |
| 7 | `7626c6e` | 132 références d'audit orphelines retirées (AST du code identique) ; règles d'écriture dans le README | Inchangé |

## 3. Les trois changements de gameplay, à essayer à la main

1. **Enchaîner pendant le hit-stop (C1).** Frapper un gobelin et appuyer sur
   l'attaque suivante pendant le gel : l'attaque part au premier tick qui suit
   le gel. Même chose pour le saut et le dash, au clavier et à la manette. Le
   gel de parade (0,14 s) est le plus parlant.
2. **Contact et pièges (C2).** Marcher sur un pic : le dégât tombe au premier
   tick de contact, plus après un délai aléatoire (jusqu'à 0,4 s). Les pièges
   sont donc un peu plus durs qu'avant. Le rythme ensuite est inchangé (un
   dégât toutes les 24 frames sur un pic, 12 entre deux corps).
3. **Touche R / bouton View (C5).** Sans `--debug`, elle ne fait plus rien.
   Avec `--debug`, elle téléporte et soigne comme avant.

## 4. Systèmes préservés sans modification

Boucle de jeu et pacing, `SceneManager` et scènes de menu, fenêtre et
affichage (`Screen`, `core/display`), routeur d'évènements et bindings, caméra
et rendu, overlay de debug, HUD et menus, audio, physique et collisions
(`physics/`), frame data et `AttackStateMachine`, `HitboxManager`,
`CombatComponent`, `StateMachine`, chargement Tiled et `WorldBuilder` (hors
lecture de la table des ennemis), effets visuels (`core/fx`, seulement
déplacés d'appelant), sauvegarde et réglages.

## 5. Améliorés, simplifiés, supprimés, remplacés

- **Améliorés** : entrées (C1), contact et pièges (C2), rollback (C3 et test
  d'invariant), données (C4), typage des états, lectures typées dans le combat,
  animation (préchargement, invalidation).
- **Simplifiés** : `PhysicsSystem`, `MovementComponent`, fin de tick de
  `GameplayLoop`, enregistrement des combattants, transitions d'IA, direction du
  knockback, références d'audit dans la prose.
- **Supprimés** : `src/entities/enemies/types/` (5 fichiers),
  `src/entities/enemies/configs.py`, `is_enemy_type`, `DEFAULT_PLAYER_CONFIG`,
  `ContactSystem._maybe_parry_stun`, `GameplayLoop._emit_guard_fx` et ses
  auxiliaires (déplacés), le relais de `MovementComponent`.
- **Remplacés** : aucun.

## 6. Écarts par rapport à la feuille de route, et pourquoi

| Prévu | Fait | Raison |
|---|---|---|
| R5 étape 3 : déplacer la décision de garde de `Player.receive_damage` vers `HitResolver` | **Non** | Nouvelle preuve : les pièges et le contact appellent `receive_damage` sans passer par le résolveur, et un joueur en garde les bloque aujourd'hui. Déplacer la garde aurait changé ce comportement. La frontière « le défenseur décide s'il se défend » est la bonne ; elle est documentée dans `hit_resolver.py`. |
| R5 étape 4 : écrire une seule fois le choix de la réaction | **Non** | À la relecture, `combat.on_hit` n'est appelé qu'une fois par chemin (projection lourde dans `ReactionComponent`, blessure dans `_apply_post_effects`) ; l'apparent doublon est une annulation d'action volontaire. Documenté, pas changé. |
| R8 : rendre obligatoires les systèmes de `GameplayLoop` | **Non** | Coût élevé (réécriture de nombreux montages de test) pour un gain faible ; `_require` donne déjà une erreur claire. |
| R8 : remplacer les tests qui lisent le texte source | **Non** | À la relecture, ce sont des règles de convention (« pas de `getattr` dans le résolveur ») ou des lectures de fichiers de données, pas des substituts de tests de comportement. L'affirmation de l'audit (§3.20) était trop large. |
| R9 : alléger la prose en profondeur (`fx/tuning.py`, `entity.py`…) | **En partie** | Seules les références orphelines sont retirées ; la proportion de prose reste à 30 %. Une réécriture éditoriale demande une relecture humaine, fichier par fichier. |
| R11.7 : interpolation des entités | **Non** | En attente de D5 (observation à 120/144 Hz). |
| R7 : retirer le rollback | **Remplacé par R7-B** | Décision D4 : multijoueur prévu. |

## 7. Découvertes pendant la mise en œuvre

- **C1 a rendu muet un test de rollback.** `test_rollback_e2e` posait l'état de
  la manette avec `apply_remote_state`, puis appelait `level.update`. Depuis C1,
  le niveau relit son fournisseur, ce qui écrasait l'état : le test rejouait un
  joueur immobile et passait quand même. Il passe maintenant par un fournisseur
  d'entrées, et vérifie que le joueur a bougé. C'est aussi la bonne interface
  pour le futur multijoueur : une session réseau fournira un `InputProvider`.
- **Un `getattr` avalait une erreur réelle.** `getattr(target, "is_invincible",
  False)` attrapait une `AttributeError` levée *dans* la propriété, par la
  machine à états factice d'un test, et répondait `False`. C'est exactement le
  danger décrit au §3.20 de l'audit.
- **Comportement noté, non modifié** : une projection lourde utilise toujours la
  direction relative à la source, même pour un knockback en mode `fixed`,
  alors qu'une poussée simple respecte le mode. À décider si c'est voulu.
- **Test instable préexistant** : `test_frame_pacing.py::test_a_present_that_does_not_block_still_gets_a_speed_limit`
  mesure l'horloge réelle et échoue parfois quand la machine est chargée ; il
  passe seul, avant comme après les changements.
- **Mesures de l'audit corrigées** : le coût du tick et du dessin avait été
  mesuré sur une machine chargée (2,9 et 3,6 ms). Remesurés côte à côte, sur le
  commit de départ et sur le résultat : **1,9 ms par tick et 1,8 ms de dessin,
  identiques avant et après**.
- **README** : la section « Further notes » liste toujours les fichiers de
  `notes/` que vous avez supprimés dans l'arbre de travail (suppression non
  commitée). Je ne les ai pas retirés : la décision vous appartient.

## 8. Vérifications

| Vérification | Avant (`d718a8c`) | Après |
|---|---|---|
| `pytest` (headless, avec les assets) | 3 408 réussis, 1 ignoré | **3 438 réussis**, 1 ignoré |
| Couverture (instructions + branches, `pytest-cov`) | 94 % / 86 % (README) | **92 %** combiné |
| `mypy src main.py tools` | 0 erreur | **0 erreur** |
| `ruff check`, `ruff format --check` | propres | **propres** |
| Matrice des issues de coups (421) | enregistrée | **identique** après chaque étape |
| Empreintes de simulation (3 scénarios) | — | RESPAWN identique ; PHYSICS et RIDE réenregistrés **une fois**, pour C2, avec l'explication dans le test |
| Invariant du rollback (392 valeurs) | échoue (C3) | **passe** |
| Partie réelle sans écran, 600 frames, niveau 0, entrées clavier réelles | — | attaques et dashs déclenchés, aucune erreur d'abonné ; idem avec `DEBUG=1` |
| Tick / dessin, niveau 0, 1920×1080 | 1,9 ms / 1,8 ms | 1,9 ms / 1,8 ms |
| `getattr`/`hasattr` dans `src/` | 239 | 214 |
| `Any` dans `src/states/` | 68 | 38 |

**Non vérifié** (demande un écran et une manette) : jouer réellement les trois
changements du §3 ; le ressenti du verrou de manette ; D5 à 120/144 Hz ; la
construction PyInstaller (`knightrock.spec` ne référençait pas les modules
supprimés, mais le paquet n'a pas été construit ici).

## 9. Dette technique restante

Par priorité :

1. **P2 — Prose.** 30 % des lignes de `src/` restent des docstrings et des
   commentaires, dont beaucoup racontent l'historique. À réécrire au fil des
   modifications, selon la règle désormais écrite dans le README ; commencer par
   `core/fx/tuning.py` (190 lignes de code, 900 de prose).
2. **P2 — `getattr` restants.** 214, dont environ un tiers dans l'overlay de
   debug et une vingtaine sur des évènements pygame (légitimes). Le reste se
   traite comme à l'étape 6 : donner aux faux objets la forme réelle, puis lire
   directement.
3. **P3 — `GameplayLoop`** accepte encore ses systèmes en `Optional`.
4. **P3 — Interpolation** (D5), à observer d'abord.
5. **P3 — Direction de la projection lourde** en mode `fixed` (§7), à décider.
6. **P3 — Tuiles du niveau en cours** non reconverties après un changement de
   format d'affichage (lenteur de blit seulement).

## 10. Recommandations pour la suite

- **Pour le combat** : ajouter une règle (contre, coup critique, son de coup)
  en suivant l'ordre écrit en tête de `hit_resolver.py`. Après tout changement
  volontaire, régénérer la matrice (`UPDATE_GOLDENS=1`) et **lire le diff** du
  JSON : c'est le relevé exact de ce qui a changé.
- **Pour les sons de combat** : ils se branchent dans
  `FeedbackSystem.after_combat`, qui reçoit déjà les évènements de garde et
  l'impact du tick.
- **Pour le multijoueur** : tout nouvel état de simulation doit entrer dans les
  instantanés ; `test_rollback_invariant.py` échoue sinon et nomme le champ
  oublié. Les entrées distantes passent par un `InputProvider`.
- **Pour les tests** : partir de `tests/fakes.py` ; un faux objet qui manque un
  champ doit échouer, jamais être toléré par le code de production.
- **Ne pas** introduire d'ECS, de bus d'évènements général ni de réorganisation
  des dossiers : rien dans l'audit ni dans cette étape ne l'a justifié.
