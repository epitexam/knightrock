# Audit du combat : pourquoi il manque de dynamisme

2026-11-12, branche `fix/remediation`. Demande du développeur : « pour un hack
and slash, ce n'est pas assez dynamique ».

**Méthode.** Les chiffres viennent du jeu lui-même, pas d'une lecture du code
seule : frame data de `data/gameplay/attacks.json`, réglages de
`core/settings.py` et `enemies.json`, et des duels simulés sans écran dans une
arène plate (vrai `Player`, vrais ennemis, manette scriptée). Le ressenti à la
manette reste à confirmer par vous.

---

## 1. Verdict

Le **moteur** de combat est de bonne facture : frame data à 60 Hz, phases
explicites, annulations déclarées, coups balayés, hurtboxes par zone, priorité
et clash, jonglage, OTG, parade. Rien de tout cela n'est à refaire.

Le manque de dynamisme vient de **quatre causes**, presque toutes réglables
dans les données ou dans le retour :

1. **Le rythme d'attaque est bridé par des cooldowns** plus longs que les
   attaques elles-mêmes : on ne peut pas enchaîner deux coups légers.
2. **Il n'y a pas de chaînes** (léger → léger → léger → finisher) : un bouton
   donne toujours le même coup, et six attaques déjà conçues ne sont
   accessibles qu'au banc de debug.
3. **Chaque coup repousse l'ennemi hors de portée** : il faut avancer après
   chaque frappe pour que la suivante porte (voir la correction au §8 sur
   l'ampleur de l'effet).
4. **Un coup se voit et s'entend à peine** : aucun son de combat, aucune
   étincelle d'impact, la même animation de 3 images pour les 17 attaques, et
   des ennemis qui disparaissent à la mort sans réaction.

Côté ennemis, s'ajoute un problème de **lisibilité** : leurs attaques partent
sans préavis lisible, ce qui transforme garde et parade en paris.

## 2. Mesures

### Le joueur

| Mesure (arène plate) | Résultat |
|---|---|
| Coups légers par seconde, en martelant, cible passive | **2,4** (plafond imposé par le cooldown) |
| Coups lourds par seconde, cible passive | 1,2 lancés, **0,6 portés** |
| Meilleur enchaînement existant (léger ↔ attaque en avant) | 2,0 coups/s |
| Contre un gobelin (60 PV), en martelant le léger | tué en **4,1 s** ; 5 coups portés sur 13 *(voir la correction au §8)* |
| Contre un slime, une « dent », une « coquille » | 5,2 s, 3,8 s, 6,3 s (et 54 PV perdus contre la coquille, qui a de la super-armure) |
| Le même gobelin, avec l'enchaînement léger ↔ attaque en avant | tué en **1,2 s** : l'élan de l'attaque en avant garde le contact |

### Les ennemis

| Mesure | Résultat |
|---|---|
| Préavis de l'attaque du gobelin (startup) | **4 frames = 67 ms** (slime : 100 ms) |
| Rythme du gobelin au contact d'un joueur immobile | 0,67 attaque/s ; **82 PV perdus en 10 s** |
| Pause après chaque attaque ennemie | `idle_duration` : 0,35 à 1,2 s, puis retour en poursuite |
| Attaques par type d'ennemi | **une seule** (`attack_name`) |

À titre de repère, un temps de réaction humain est de l'ordre de 200 à 250 ms :
une attaque de 67 ms ne se voit pas venir, elle se devine.

## 3. Diagnostic, cause par cause

### A. Le rythme d'attaque est plafonné par les cooldowns

- **Où :** `cooldown` de chaque attaque dans `attacks.json` ; vérifié par
  `CombatComponent.start_attack` **avant** l'annulation.
- **Données :**

  | Attaque | Durée totale | Cooldown | Écart |
  |---|---|---|---|
  | léger | 12 frames (0,20 s) | 0,30 s | +0,10 s |
  | lourd | 22 frames (0,37 s) | 0,80 s | +0,43 s |
  | uppercut | 19 frames (0,32 s) | 0,90 s | +0,58 s |
  | aérien | 15 frames (0,25 s) | 0,35 s | +0,10 s |

- **Conséquence :** après chaque coup, le joueur attend sans rien pouvoir
  faire. Le hit-stop gèle aussi le cooldown, d'où 0,4 s par coup léger.
  L'appui fait trop tôt est mis en tampon, puis souvent refusé une seconde fois
  à la sortie de l'attaque.
- **Ce qui est sain :** le cooldown est le bon outil pour un coup spécial
  (`special_attack` : 2 s). Il est inadapté aux coups de base, dont le rythme
  devrait être réglé par leur propre frame data (startup, recovery, fenêtres
  d'annulation).

### B. Pas de chaînes, et du contenu inutilisé

- **Un bouton = un coup** (`BUTTON_MOVES`, `entities/attack_moves.py`).
  `light_attack` ne peut pas s'annuler en lui-même (`cancel_into` : attaque en
  avant, lourd, uppercut).
- **Annulations seulement en recovery** (`AttackStateMachine.can_cancel_into`
  exige `RECOVERY`) : impossible d'enchaîner sur une touche, dans la fenêtre
  active.
- **Six attaques conçues sont hors de portée du joueur** : `twin_fangs`,
  `sweeping_arc`, `sky_launcher`, `otg_slam`, `p5_shapes`, `circle_burst`. Elles
  ne sont liées qu'aux touches du banc de debug.
- **Le compteur de combo ne récompense rien** : il s'affiche et sert à réduire
  les dégâts en jonglage, rien de plus. La fenêtre de riposte après une parade
  (`riposte_timer`) est décomptée et affichée, mais n'a **aucun effet** de jeu.
- **Pas de saut pendant une attaque** : l'état `ATTACK` n'écoute pas le saut, et
  l'appui mis en tampon (0,1 s) expire. Seul le dash annule une attaque.

### C. Le contact se perd après chaque coup

- **Knockback du léger : 150 px/s vers l'arrière, contre une avancée de
  122 px/s** pour l'élan du joueur (0,35 × 350), et le joueur est ralenti à 50 %
  pendant l'attaque (`attack_move_multiplier`).
- **Conséquence mesurée :** 5 coups portés sur 13 contre un gobelin. Tout coup
  qui porte éloigne la cible du suivant.
- **Contre-exemple déjà dans le jeu :** l'attaque en avant (élan 1,0, rythme
  plus lent) tue le même gobelin en 1,2 s, parce qu'elle garde le contact.

### D. Le retour d'un coup est pauvre

| Élément | État actuel |
|---|---|
| Son | **Aucun son de combat.** Les seuls sons du jeu sont ceux des menus. |
| Étincelle ou trace au point d'impact | **Aucune** pour un coup normal (seulement pour garde, parade, bris, étourdissement) |
| Secousse de caméra | Seulement à partir d'un knockback de 400 : le léger et le lourd n'en ont pas |
| Hit-stop | Global, 5 à 10 frames selon les dégâts : correct pour un lourd, long pour un léger qu'on martèle |
| Flash de la cible | Oui (`HitFlash`) |
| Animation | **La même animation de 3 images pour les 17 attaques** (`attack`, 0,07 s par image), sans lien avec leur startup/active/recovery. Un lourd de 22 frames finit son geste à la frame 12. |
| Mort d'un ennemi | **Il disparaît au tick suivant**, sans projection, flash, fondu ni particules |

C'est le poste qui pèse le plus sur le ressenti, et le moins sur le code :
`FeedbackSystem.after_combat` reçoit déjà les faits du tick, et
`ContactSystem.zone_contacts` donne chaque coup porté avec sa zone.

### E. Des ennemis peu lisibles et monotones

- **Préavis trop court :** 67 à 100 ms de startup, sans animation dédiée. Garde
  et parade (fenêtre de 0,15 s) deviennent des paris.
- **Une seule attaque** par type, toujours la même distance (`attack_range`).
- **Réactions identiques** : tout coup non lourd met l'ennemi en « blessé »
  0,4 s et le repousse. Pas de petite secousse sans recul pour les coups de
  chaîne, pas de vulnérabilité après une attaque ratée.
- **Dégâts de contact** : foncer dans un ennemi blesse (5 PV) au-delà de
  300 px/s, ce qui pénalise un style agressif (le dash va à 1 100 px/s).
- **Aucune gestion de groupe** : à plusieurs, tous les ennemis à portée
  attaquent en même temps.

### F. La mobilité de combat est courte

- **Dash : 80 ms, environ 88 px.** Il se lit comme un clignement plus que comme
  un déplacement ; 5 charges en compensent la brièveté.
- **Aérien :** cooldown de 0,35 s pour 15 frames d'attaque : pas de chaîne en
  l'air, malgré un système de jonglage complet (gravité de jonglage, OTG,
  réduction des dégâts).

## 4. Ce qu'il faut garder

La frame data et `AttackStateMachine` ; `CombatComponent.start_attack` comme
seul point de refus ; les annulations déclarées par phase ; le balayage et les
hurtboxes par zone ; la priorité et le clash ; le jonglage et l'OTG ; la garde
et la parade ; le hit-stop global (à régler, pas à retirer) ; la matrice
`tests/golden/hit_outcomes.json`, qui montrera chaque effet d'un réglage.

## 5. Axes d'amélioration

Classés par rapport impact / effort. « Données » veut dire `attacks.json` ou
`enemies.json` seulement.

### Axe 1 — Rendre le martèlement possible (données + un peu de code)

| Changement | Où | Effort |
|---|---|---|
| Cooldown à 0 pour les coups de base (léger, lourd, aériens, accroupis) ; le garder pour les coups spéciaux | Données | Très faible |
| Ouvrir les annulations dès la fin de la fenêtre active (« on hit » et en recovery), pas seulement en recovery | `AttackStateMachine.can_cancel_into` : ajouter une option par phase (`cancel_from: "active" \| "recovery"`) | Faible |
| Chaînes sur un même bouton : `light_1 → light_2 → light_3`, le dernier coup plus lourd (projette ou étourdit) | Données (nouveaux coups) + résolution du coup selon l'attaque en cours, dans `PlayerInputHandler._start` | Moyen |
| Brancher les six attaques existantes dans ces chaînes (`twin_fangs` en 2e coup, `sweeping_arc` en finisher, `sky_launcher` en lourd chargé…) | Données | Faible |

**Cible :** 5 à 6 coups par seconde dans une chaîne légère, avec un finisher
toutes les 3 ou 4 frappes.

### Axe 2 — Garder le contact

| Changement | Où | Effort |
|---|---|---|
| Knockback quasi nul sur les coups de chaîne (≈ 30 à 50) ; le recul réservé au finisher et aux lourds | Données | Très faible |
| Élan d'attaque plus fort sur les coups de chaîne (`lunge_speed_multiplier` ≈ 0,6 à 0,8) et moins de ralentissement (`attack_move_multiplier` ≈ 0,8) | Données | Très faible |
| Réaction ennemie « flinch » (petit gel, sans recul) pour les coups légers, « blessé » pour les lourds | `HitProperties` (champ de réaction) + `HitResolver` | Faible à moyen |

**Cible :** au moins 80 % des coups d'une chaîne portent contre un ennemi en
mouvement.

### Axe 3 — Faire sentir chaque coup (impact le plus fort sur le ressenti)

| Changement | Où | Effort |
|---|---|---|
| Sons de combat : élan (swing), impact par niveau (léger, lourd, finisher), garde, parade, mort | `FeedbackSystem.after_combat` + `AudioBus` (catégorie SFX existante) ; il faut des fichiers son | Faible côté code |
| Étincelle d'impact au point de contact, orientée selon le coup | `core/fx` (même famille que les arcs de garde) | Faible |
| Hit-stop par niveau : ≈ 3 frames léger, 6 lourd, 10 finisher | `ContactSystem._resolve_melee` (formule) ou champ `hit_stop` par coup | Très faible |
| Petite secousse sur chaque coup porté, proportionnelle | `FeedbackSystem` | Très faible |
| Mort : projection, flash blanc, gel court, fondu ou éclatement, au lieu d'une disparition | `remove_dead_entities` (garder le corps quelques frames) + FX | Faible à moyen |
| Une animation par attaque, calée sur sa frame data (images de startup, d'active, de recovery) | Art + `Animator` (vitesse dérivée de la durée du coup) | Élevé (dépend de l'art) |

### Axe 4 — Des ennemis lisibles et punissables

| Changement | Où | Effort |
|---|---|---|
| Préavis de 18 à 30 frames (300 à 500 ms) avec un signal (flash, pose, petit son) | Données (startup) + FX de préavis | Faible |
| Recovery longue après une attaque ennemie ratée : la fenêtre où le joueur punit | Données | Très faible |
| Deux ou trois attaques par type, choisies selon la distance | `EnemyConfig` (liste) + `EnemyChaseState` | Moyen |
| Jetons d'attaque : un ou deux ennemis attaquent à la fois, les autres tournent autour | Un petit coordinateur dans le niveau | Moyen |
| Dégâts de contact désactivés pendant le dash du joueur, ou supprimés | `ContactDamageSystem` / données | Très faible |

### Axe 5 — Mobilité de combat

| Changement | Où | Effort |
|---|---|---|
| Dash plus long : ≈ 0,15 s, 180 à 220 px, invincible, 2 ou 3 charges | `player.json` / `settings.Physics` | Très faible |
| Saut qui annule une attaque qui a touché (pour monter un jonglage) | `PlayerAttackState.update` | Faible |
| Chaîne aérienne (`air_1 → air_2 → air_3`), cooldown aérien à 0 | Données + chaînes de l'axe 1 | Faible une fois l'axe 1 fait |

### Axe 6 — Récompenser le style

| Changement | Où | Effort |
|---|---|---|
| Riposte après une parade : prochain coup garanti, bonus de dégâts ou étourdissement | `GuardController.riposte_timer` existe déjà, il suffit de le lire dans `HitResolver` | Faible |
| Combo qui donne quelque chose (bonus de dégâts progressif, recharge du dash, jauge de spécial) | `ComboTracker` | Faible à moyen |

## 6. Ordre proposé

1. **Réglages purs** (axes 1, 2, 5 côté données, et les hit-stops) : une
   journée, aucun risque pour le moteur. Ils suffisent à vérifier la direction.
2. **Retour** (axe 3, sauf l'animation) : sons, étincelles, secousses, mort.
3. **Chaînes et annulations « on hit »** (axe 1, partie code).
4. **Ennemis** (axe 4).
5. **Animation calée sur la frame data**, quand l'art suit.

Chaque étape se mesure avec l'arène de cet audit (script de duel), qu'il vaut la
peine d'ajouter au dépôt comme benchmark :
- coups par seconde dans une chaîne ;
- part des coups portés ;
- temps pour tuer chaque ennemi ;
- PV perdus contre chacun.

La matrice des issues de coups montrera, réglage par réglage, ce qui a changé.

## 7. Ce qui dépend de vous

Le dynamisme ne se règle pas sans une direction :

- **Rapide et aérien** : longues chaînes, jonglages, beaucoup d'annulations,
  ennemis qui encaissent beaucoup. Tous les axes, chaînes en tête.
- **Nerveux mais pesé** : peu de coups mais très lisibles, esquive et punition,
  ennemis aux préavis clairs. Axes 2, 3, 4 et 5 en tête, chaînes courtes
  (deux ou trois coups).

Les deux corrigent les quatre causes du §1. Ils divergent sur la longueur des
chaînes, la place du jonglage et le nombre de PV des ennemis.

## 8. Étape 1 réalisée : les réglages (2026-11-12)

Direction retenue par le développeur : **No More Heroes, Katana ZERO, Dead
Cells**, soit « nerveux mais pesé », avec un retour très appuyé et des chaînes
courtes plutôt que de longs jonglages.

**Correction de mesure.** Le « 5 coups portés sur 13 » du §2 venait en partie
de mon script : le joueur scripté ne recollait à l'ennemi qu'au-delà de 34 px,
alors que le léger porte à une quinzaine de pixels. Remesuré avec un joueur qui
reste au contact (`tests/benchmarks/combat_feel.py`, `KEEP_PX = 8`), l'ancien
réglage portait déjà 83 % de ses coups contre un gobelin. Le recul (cause C)
reste un défaut pour un joueur humain, qui doit avancer après chaque coup, mais
il est moins grave que je ne l'avais écrit. Les causes A, B, D et E ne changent
pas.

**Réglages appliqués** (`data/gameplay/attacks.json`, `core/settings.py`) :

| Réglage | Avant | Après |
|---|---|---|
| Cooldown : léger, aérien, accroupi | 0,30 / 0,35 / 0,28 s | **0** |
| Cooldown : lourd, uppercut, attaque en avant, aérien avant | 0,80 / 0,90 / 0,50 / 0,40 s | 0,15 / 0,40 / 0,25 / 0,20 s |
| Le léger, l'aérien et la frappe accroupie s'annulent en eux-mêmes | non | **oui** (chaîne en recovery) |
| Recul du léger / de la frappe accroupie / de l'aérien | 150 / 120 / 180 | **40 / 40 / 60** |
| Élan du léger (`lunge`), ralentissement pendant le léger | 0,35 ; 0,50 | **0,60 ; 0,80** |
| Élan du lourd | 0,35 | 0,50 |
| Hit-stop : base de la formule | 50 ms | **30 ms** (le lourd et le finisher restent longs : la formule dépend des dégâts et du recul) |
| Préavis / récupération du coup de griffe (gobelin, dent, coquille) | 4 / 5 frames | **16 / 16** |
| Préavis / récupération du coup du slime | 6 / 7 frames | **20 / 18** |
| Dash | 80 ms, 1 100 px/s, 5 charges | **140 ms, 1 350 px/s (189 px), 3 charges** |

Deux règles du moteur ont été assouplies pour cela, parce qu'elles écrivaient
l'ancienne conception : le cooldown n'a plus à durer au moins autant que
l'attaque, et une attaque peut s'annuler en elle-même si son cooldown est écoulé
avant sa dernière frame (sinon le refus reste). La traînée du dash passe de 6 à
9 images au plus, pour couvrir un dash de 140 ms.

**Résultats** (arène, joueur au contact) :

| Mesure | Avant | Après |
|---|---|---|
| Coups légers portés par seconde (cible passive) | 2,3 | **4,3** |
| Temps pour tuer : gobelin / slime / dent / coquille | 2,05 / 1,88 / 2,15 / 4,55 s | **1,05 / 0,98 / 1,42 / 2,68 s** |
| PV perdus contre la coquille | 36 | 18 |
| Préavis des attaques ennemies | 67 / 100 ms | **267 / 333 ms** |
| Part du temps en hit-stop en martelant le léger | 23 % | 29 % (plus de coups, chacun plus court) |

La matrice des issues de coups change sur trois champs seulement : hit-stop
(371 issues), recul et impact (les coups au knockback réduit). Aucun dégât,
aucun état, aucune issue de garde ou de parade n'a bougé.

**Reste à faire, dans l'ordre :** le retour (axe 3 : sons, étincelles,
secousses, mort), puis les chaînes à finisher (axe 1, partie code), puis les
ennemis (axe 4).

## 9. Étape 2 réalisée : deux boutons et un catalogue en chaînes (2026-11-12)

Décisions du développeur : passer de quatre boutons d'attaque à deux (léger,
lourd), et retirer les coups de test du catalogue de jeu en les gardant dans les
tests.

### Le catalogue (14 coups)

| Entrée | Coup |
|---|---|
| Léger, léger, léger | `light_attack` → `twin_fangs` → `sweeping_arc` (finisher : pousse, étourdit) |
| Lourd pendant la chaîne légère | `uppercut` (lanceur) |
| Lourd | `heavy_attack` (chargeable) |
| Dash puis léger | `dash_attack`, qui se prolonge dans la chaîne |
| Bas + léger / lourd au sol | `crouch_slash` (se répète) / `crouch_sweep` |
| Léger, léger en l'air | `air_attack` → `air_forward` |
| Lourd en l'air | `air_rise` |
| Bas + lourd en l'air | `air_sweep` (plongeon) |
| Léger ou lourd juste après une parade | `riposte` : rapide, imblocable, 30 dégâts, une par parade |
| Spécial | `special_attack`, inchangé |

Sortis du catalogue vers `tests/data/showcase_attacks.json` : `p5_shapes`,
`circle_burst`, `sky_launcher`, `otg_slam`. Aucun n'était relié à un bouton en
jeu.

**Écarts avec la proposition du §5**, et pourquoi :
- « Haut + lourd » n'existe pas : le jeu n'a pas d'entrée « haut ».
  L'uppercut est le lourd *pendant* la chaîne légère.
- Le plongeon est `air_sweep`, qui en était déjà un, et non `otg_slam`.
- Le lourd chargé reste le lourd avec multiplicateur, et non `sky_launcher` :
  un coup différent selon la charge demande un mécanisme de plus, pour un gain
  incertain.

### Le moteur

- **Données** : `follow_ups` sur une attaque (le coup suivant par bouton), et
  `cancel_on_hit` sur une phase (la chaîne continue dès que le coup a touché).
  Le chargeur refuse un maillon qui ne nomme rien, ou qu'aucune phase ne laisse
  passer.
- **Choix du coup** (`resolve_move`) : riposte, puis maillon suivant de la
  chaîne, puis dash, puis plongeon, puis le coup de la posture.
- **Tampon** : le *bouton* pressé est gardé `ATTACK_BUFFER_WINDOW` et retenté à
  chaque tick ; le coup est choisi au moment où il part. `NO_CANCEL` est
  désormais un refus « à retenter », comme `COOLDOWN`.
- **Élan par maillon** : un compteur d'attaques lancées
  (`CombatComponent.attacks_started`, inclus dans les instantanés de rollback)
  permet à l'état d'attaque de rejouer l'élan à chaque nouveau maillon.
- **Deux boutons** : `ATTACK_3` et `ATTACK_4` sont retirés. Un fichier de
  réglages qui les lie encore est lu sans eux, au lieu d'être rejeté.

### Ce que la mise en œuvre a révélé

- **Une charge pouvait rester bloquée.** Un lourd mis en tampon partait en
  charge alors que le bouton était déjà relâché, et la charge attendait un
  relâchement passé. On ne charge plus que si le bouton est tenu.
- **Les petits sauts déclenchaient l'OTG.** Le léger, le deuxième maillon et le
  finisher avaient un léger recul vers le haut. L'ennemi blessé retombait, et
  sa protection au sol (0,5 s) faisait rebondir la suite de la chaîne : 39 % de
  coups portés contre une cible passive. Les maillons poussent maintenant à
  l'horizontale : 97 %.
- **Un test bouclait indéfiniment.** Le test de la relecture d'attaque du banc
  de debug comptait sur un cooldown pour s'arrêter ; il compte maintenant les
  attaques lancées.

### Mesures (`tests/benchmarks/combat_feel.py`)

| Mesure | Avant l'audit | Étape 1 | Étape 2 |
|---|---|---|---|
| Coups légers portés par seconde (cible passive) | 2,3 | 4,3 | 3,9 (en chaîne, finisher compris) |
| Part des coups portés (cible passive) | 96 % | 100 % | 97 % |
| Temps pour tuer : gobelin | 2,05 s | 1,05 s | **0,95 s** |
| slime | 1,88 s | 0,98 s | 1,07 s |
| dent | 2,15 s | 1,42 s | 2,45 s |
| coquille | 4,55 s | 2,68 s | **2,12 s** |

La dent recule parce que, dans ce duel, elle frappe le joueur et l'envoie en
l'air : ses coups suivants sont aériens, et `air_forward` la repousse loin.
C'est le combat qui joue, pas une chaîne qui rate.

**À essayer à la manette :** la chaîne léger ×3 sur un gobelin ; léger, lourd
(lanceur) ; dash puis léger ; parade puis riposte ; bas + lourd en l'air.

## 10. Étape 3 réalisée : retour, ennemis, récompenses (2026-11-14)

Demande du développeur : tout le reste de l'audit, sauf les sons et ce qui
touche aux assets. Une étincelle d'impact et une étoile de préavis au-dessus
des ennemis ont été essayées puis **retirées** à la demande du développeur
(« c'est assez moche ») : aucun effet visuel nouveau n'est livré.

### Ce qui change en jeu

| Axe | Changement | Où |
|---|---|---|
| 2 | **Coups « flinch »** : le léger, `twin_fangs` et la frappe accroupie ne repoussent plus une cible au sol (ni un joueur qui garde) ; une cible en l'air est poussée comme avant | `flinch` dans `attacks.json`, `HitResolver` |
| 3 | **Secousse à chaque coup porté**, plus forte sur un coup fatal ; la forte secousse des coups lourds reste | `CameraShake.HIT_*`, `FeedbackSystem.after_combat` |
| 3 | **Hit-stop par coup** : un coup peut fixer le sien (`hit_stop`, 0,16 s sur `sweeping_arc`) ; un coup fatal gèle au moins `Combat.KILL_HITSTOP` (0,1 s) | `ContactSystem._hit_stop` |
| 4 | **Deux attaques par type** : `claw_reach` (griffe longue et basse) pour le gobelin et la dent, `slime_splash` (éclaboussure basse) pour le slime ; choisies à l'entrée en poursuite selon un poids | `moves` dans `enemies.json`, `Enemy.plan_move` |
| 4 | **Jetons d'attaque** : deux ennemis au plus attaquent le joueur à la fois, les autres attendent à portée | `AI.MAX_ATTACKERS`, `Enemy.attack_slot_free` |
| 5 | **Saut qui annule une attaque qui a touché** | `PlayerAttackState._jump_cancel` |
| 6 | **Combo récompensé** : tous les 4 coups d'un combo rendent une charge de dash | `Combat.COMBO_DASH_REFILL_HITS`, `Player.on_hit_confirmed` |

Les attaques basses se bloquent en garde accroupie ou s'évitent en sautant ;
une parade debout ne les arrête pas.

### Déjà en place, vérifié

Les dégâts de contact pendant le dash : le dash est invincible, et une entité
invincible ne produit ni ne reçoit de contact. Un test le fixe
(`test_dashing_through_an_enemy_costs_the_player_nothing`).

### Non fait

- Sons de combat, animation par attaque : demandent des assets.
- Signal visuel de préavis : essayé, retiré. Le préavis reste porté par la
  durée du startup (267 à 400 ms).

### Mesures (`tests/benchmarks/combat_feel.py`)

| Mesure | Étape 2 | Étape 3 |
|---|---|---|
| Coups légers portés par seconde (cible passive) | 3,9 | 3,8 |
| Part des coups portés (cible passive) | 97 % | 100 % |
| Temps pour tuer : gobelin | 0,95 s | 0,87 à 0,95 s (selon le tirage de ses attaques) |
| slime | 1,07 s | **0,87 s** |
| dent | 2,45 s | **1,17 s** |
| coquille | 2,12 s | 2,33 s |
| Part du temps en hit-stop en martelant | 29 % | 35 à 41 % |

La matrice des issues de coups change sur trois points seulement : le hit-stop
des coups fatals et de `sweeping_arc`, la vitesse (nulle) après un coup
« flinch » au sol, et 20 issues nouvelles pour `claw_reach` et `slime_splash`.

## 11. Rework : une boucle de hack 'n' slash (2026-11-14)

Demande du développeur : un rework complet du combat, pour un hack 'n' slash
nerveux en 2D, inspiré de No More Heroes, Killer is Dead et Dead Cells. Ses
quatre décisions : le combat d'abord (les niveaux ne bougent pas), la défense
par l'esquive et la parade (plus de garde tenue), les quatre mécaniques
proposées, et aucun effet visuel nouveau. Le ressenti passe par le temps
(gel, ralenti), la caméra et le HUD.

### La boucle

| Mécanique | Règle | Où |
|---|---|---|
| **Chaîne de sabre** | Quatre coups sur le bouton léger : `light_attack` → `twin_fangs` → `cross_cut` (nouveau) → `sweeping_arc`. Les trois premiers ne repoussent pas la cible et ne gèlent le monde que deux ticks. | `attacks.json` |
| **Tempo** | Le compteur de combo accélère les attaques du joueur : ×1,15 à 6 coups, ×1,3 à 14, ×1,45 à 24. Seuls le startup et la recovery raccourcissent ; une frame active n'est jamais sautée. Le combo tient 2 s sans coup et tombe quand le joueur est touché ; aucun coup ne le remet à zéro. | `Tempo.STEPS`, `AttackStateMachine.speed`, `Player.tempo` |
| **Étourdissement** | Chaque coup porte une valeur `stun` ; la jauge de la cible la cumule, tient 2 s puis fond. Pleine, l'ennemi est sonné pour `stun_duration` : il encaisse sans être poussé ni interrompu, à ×1,5 dégâts. | `HitProperties.stun`, `Entity.add_stun`, `stun_max` dans `enemies.json` |
| **Exécution** | Tout coup du bouton lourd (`execute`) tue net un ennemi sonné : gel de 0,22 s, la plus forte secousse, dash rechargé, +20 de sang, tout le rally rendu. | `HitResolver`, `Combat.EXECUTION_HITSTOP` |
| **Parade** | Un tap ouvre 0,15 s de fenêtre et annule l'attaque en cours ; un coup reçu de face y est paré, ajoute 45 à la jauge d'étourdissement de l'attaquant et ouvre la riposte. Un tap dans le vide coûte 0,25 s avant le suivant. | `GuardController`, `PlayerGuardState`, `Stun.PARRY` |
| **Esquive parfaite** | Un dash lancé moins de 0,15 s avant qu'un coup n'arrive ralentit tout sauf le joueur à 25 % pendant 1,2 s, rend le dash et donne 10 de sang. Le coup doit atteindre le joueur ou l'endroit que le dash vient de quitter. | `Rush`, `Player.dodge_ghost`, `ContactSystem._resolve_ghosts`, `PhysicsSystem.process` |
| **Sang et frénésie** | Les dégâts infligés remplissent la jauge (×0,35), un coup reçu en retire 15. Pleine, l'accord léger + lourd la dépense : 6 s d'attaques à ×1,5, de course à ×1,2 et de dash illimité. | `BloodGauge`, `Blood` |
| **Rally** | 75 % des dégâts d'un coup reçu restent récupérables : chaque coup porté en rend 0,6 PV par point de dégât. La réserve tient 0,8 s puis fond à 20 PV/s. | `RallyReserve`, `Rally` |

Le lourd reste chargeable, en 0,6 s au lieu de 1 s : à pleine charge il double
dégâts et étourdissement, et sonne d'un coup un gobelin, un slime ou une dent.

### Ce qui disparaît

- La garde tenue, la posture, les dégâts de chip et le bris de garde.
- `special_attack` (110 frames) : il sort du catalogue vers
  `tests/data/showcase_attacks.json`, et son accord lance la frénésie.
- Le compteur de parades consécutives (`parry_stun_threshold`) : la parade
  nourrit la même jauge que les coups.
- La parade par le dash (`DASH_PARRY_WINDOW`), remplacée par l'esquive parfaite.

### Ce que la mise en œuvre a révélé

- **La fenêtre d'esquive parfaite ne faisait que 3 ticks.** Détectée seulement
  sur le corps en dash, elle était bornée par la géométrie : le dash sort de la
  boîte du coup en deux ou trois ticks. Elle se mesure maintenant aussi à
  l'endroit quitté (le « fantôme »), et vaut ce que dit `Rush.WINDOW`.
- **Un ennemi projeté était intouchable 0,5 s à l'atterrissage** (protection
  OTG) : le lourd suivant le traversait. Les ennemis n'ont plus cette
  protection, le joueur la garde (`ENEMY_OTG_INVULN_DURATION`).
- **Un coup paré touchait quand même son pareur** sur le tick où la riposte
  portait : l'attaque annulée oubliait qui elle avait touché, alors que sa
  boîte du tick était déjà produite. Défaut antérieur au rework ; corrigé dans
  `combat_system._contact_gate`, avec un test qui échoue sans la correction.
- **Le lourd envoyait sa cible hors de portée** (300 px/s et une projection) :
  30 % des lourds portaient en martelant. Il pousse maintenant à 160 px/s, sans
  projection ; le lanceur reste l'uppercut.
- **Une parade debout échouait une fois sur trois** contre un gobelin, parce
  que `claw_reach` était un coup bas et que rien à l'image ne le distingue. Les
  deux coups bas des ennemis (`claw_reach`, `slime_splash`) sont passés à
  mi-hauteur : ils se parent debout et se sautent toujours. Les règles de
  hauteur restent dans le moteur.
- **Un ennemi sans IA n'a pas d'état « sonné »** : il n'a donc pas de jauge.

### Réglages des ennemis

| Type | PV | Jauge d'étourdissement | Sonné pendant |
|---|---|---|---|
| gobelin | 60 → 80 | 60 | 1,8 s |
| slime | 40 → 55 | 40 | 2,0 s |
| dent | 50 → 65 | 50 | 1,5 s |
| coquille | 90 → 140 | 100 | 1,6 s |

Leurs coups font 10 à 14 dégâts au lieu de 6 à 9.

### Mesures (`tests/benchmarks/combat_feel.py`)

| Mesure | Étape 3 | Rework |
|---|---|---|
| Coups légers portés par seconde (cible passive) | 3,8 | **6,0** |
| Part du temps en hit-stop en martelant le léger | 35 à 41 % | 33 % |
| Temps pour tuer au léger : gobelin / slime / dent / coquille | 0,87 à 0,95 / 0,87 / 1,17 / 2,33 s | 0,98 / 0,98 / 1,12 / 2,55 s (avec les PV relevés) |
| Au lourd : sonné, puis exécuté — gobelin, slime, dent | — | 0,62 s, puis 1,08 s |
| Au lourd : sonné, puis exécuté — coquille | — | 1,08 s, puis **1,55 s** |
| Part des lourds portés en martelant | 24 % (avant le réglage du recul) | 100 % |
| Fenêtre d'esquive parfaite | — | 10 ticks avant le coup |

Les trois empreintes de `test_simulation_golden.py` ont été recapturées. Avec
les PV et les dégâts ennemis d'avant, les trois anciennes sont reproduites au
bit près : rien d'autre dans le rework ne déplace la simulation.

### Non fait, à décider après essai à la manette

- **Code devenu inatteignable**, laissé en place tant que la direction n'est
  pas validée en jeu : l'anneau de garde simple et l'arc de bris de garde
  (`spawn_guard_arc(parried=False)`, `spawn_shatter_arc`, `ShatterArcParticle`),
  et le champ `hit_level` des coups, qui ne réglait que le coût en posture.
- **Aucun ennemi ne porte plus de coup bas** : la parade accroupie et
  `Guard.HEIGHT_BLOCK` n'ont plus d'usage en jeu.
- **Frénésie au clavier** : l'accord est resté `G` + `H` ; `A` + `S`
  correspondrait à la manette (`X` + `Y`).
- Sons de combat et animation par attaque : toujours en attente d'assets.

**À essayer à la manette :** marteler le léger jusqu'au troisième `!` du
compteur ; lourd, lourd, lourd sur un gobelin (le troisième exécute) ; lourd
chargé puis lourd ; dasher au dernier moment sous une griffe, puis frapper
pendant le ralenti ; parade puis riposte ; remplir le sang et lancer la
frénésie ; se faire toucher puis récupérer les PV en frappant.

## 12. Rework complet : No More Heroes 2 en 2D (2026-11-15)

Retour du développeur sur le §11 : « tu itères sur un système de combat que
j'estime mauvais. Je veux un rework complet pour un vrai hack 'n' slash à la
No More Heroes (surtout le gameplay du 2) mais en 2D. » Le kit du §11 (chaîne
légère et lourde, parade en tap, sang, rally, tempo, posture accroupie) est
**remplacé**, pas réglé. Le moteur dessous (frame data, résolution des coups,
gel d'image, horloges par entité, rollback) est gardé.

### Le kit

| Mécanique | Règle | Où |
|---|---|---|
| **Deux boutons, haut ou bas** | Le sabre et le corps ; Bas tenu au sol donne la garde basse. La posture accroupie n'existe plus. | `attack_moves.py`, `AttackButton` |
| **Chaînes de sabre** | 4 coups, haut ou bas à chaque maillon (`slash_high_*`, `slash_low_*`). Tenu, le sabre charge `charged_slash`, qui brise la garde. | `attacks.json` |
| **Batterie** | Chaque coup de sabre coûte 2 % ; vide, il ne fait que 30 % de ses dégâts. Garde + Bas la recharge, debout et à découvert. La garde coûte 4 % par coup arrêté. | `Battery`, `PlayerRechargeState` |
| **Gardes ennemies** | Le gobelin et la coquille tiennent une garde haute ou basse et en changent toutes les 1,2 à 2,6 s ; un trait sur leur flanc montre la moitié gardée. Un coup de sabre à cette hauteur est arrêté ; un coup de poing, de pied ou un coup chargé brise la garde pour 2,5 s. | `Enemy.guards_against`, `world_overlay_bars.guard_mark_rect` |
| **Garde du joueur** | Tenue, elle arrête tout coup de face ; un coup qui brise la garde le fait chanceler. | `Player.guards_against` |
| **Coup de grâce** | Un coup de sabre qui devrait tuer laisse l'ennemi condamné à 1 PV. Le combat ralentit à 5 % et une direction est demandée (1,6 s) : donnée à temps, le coup de grâce part (invulnérable) et lance la machine à sous ; manquée, l'ennemi meurt seul, sans rien rapporter. | `Finish.DOOM`, `PromptController`, `EnemyDoomedState` |
| **Étourdissement et prise** | Les coups de poing et de pied remplissent la jauge (la série de trois poings sonne un gobelin). Sur un ennemi sonné, le bouton du corps l'attrape : deux directions, puis la projection, qui tue. Une erreur laisse le joueur à découvert. | `try_grab`, `Throw` |
| **À terre** | Un ennemi projeté reste au sol 1,2 s ; un coup de sabre bas au-dessus de lui est l'estoc qui l'achève. | `EnemyDownedState`, `stab` |
| **Duel de lames** | Deux lames qui se croisent (`clash` des deux côtés : le sabre et la griffe du gobelin) se bloquent : 6 appuis en 1,4 s sonnent l'ennemi ; perdu, il coûte 12 PV. | `combat_system._blades_lock`, `Player.on_clash` |
| **Pas sombre** | L'esquive parfaite du §11, gardée : le monde ralentit, et les coups de sabre y sont gratuits et rapides. | `Rush` |
| **Furie** | Remplie en touchant, perdue en étant touché ; trois paliers accélèrent le sabre. Pleine, l'accord ouvre le côté sombre : 8 s invulnérable, plus rapide, chaque coup tue. | `FuryGauge`, `Fury` |
| **Machine à sous** | Chaque coup de grâce la lance ; trois symboles identiques (15 %) donnent un pouvoir pour 8 s : stase (le monde ralentit, chaque coup tue), blitz (plus rapide, chaque coup tue), tranchant (sabre ×2). | `SlotMachine`, `Slot` |

### Mesures (`tests/benchmarks/combat_feel.py`, joueur scripté qui répond aux invites)

| Mesure | Résultat |
|---|---|
| Coups de sabre portés par seconde (cible passive) | 5,6 |
| Sabre jusqu'au coup de grâce : gobelin / slime / dent | 1,12 / 1,12 / 1,25 s |
| Sabre contre la coquille (garde, super-armure) | 3,05 s |
| Poings jusqu'à la prise : gobelin / slime / dent | sonné à 0,37 s, mort à 0,65 s |
| Poings contre la coquille | sonnée à 1,22 s, morte à 1,52 s |
| Fenêtre du pas sombre | 10 ticks avant le coup |

### À régler à la manette

- **La prise est plus rapide que le sabre** (0,65 s contre 1,12 s sur un
  gobelin). C'est le cœur de NMH2 de mêler les deux ; si la prise écrase le
  sabre, relever `stun_max` ou baisser le `stun` des coups de poing.
- ~~Un appui pendant un gel d'image est perdu~~ : faux, voir plus bas ; la
  perte venait de la manette scriptée des tests.
- Les fenêtres des invites (1,6 s pour le coup de grâce, 0,9 s par direction
  de prise), le coût de la batterie et la vitesse de recharge sont des
  premières valeurs.
- Sons, animations par coup et effet visuel du duel de lames : en attente
  d'assets. Le seul ajout visuel est le trait de garde des ennemis, sans lequel
  on ne peut pas savoir où frapper.

### Retour du développeur : « il suffit de marteler A » (2026-11-15)

Mesuré : un joueur qui ne fait que marteler A, sans répondre aux invites,
battait les quatre ennemis en 3,8 à 6,7 s sans perdre un PV. Deux causes : chaque
coup de sabre faisait chanceler l'ennemi, et une garde ne se lève qu'au repos,
donc le premier coup placé enfermait l'ennemi ; et un coup de grâce raté tuait
quand même.

| Correction | Où |
|---|---|
| Un ennemi qui garde **se cabre** au 3e coup parable reçu d'affilée (fenêtre de 1 s) : il sort du chancellement, lève sa garde à la hauteur du coup et l'arrête. Les coups de dos et les coups du corps ne comptent pas. | `Enemy.guards_against`, `Guard.BLOCK_AFTER_HITS` |
| Un coup arrêté ouvre une **contre-attaque** (0,6 s pour la lancer), portée derrière la garde : rien de parable ne l'interrompt, un coup du corps si. | `Enemy._tick_counter`, `countering` |
| Un **coup de grâce raté** ou laissé sans réponse relève l'ennemi à 25 % de sa vie. | `Entity.recover_from_doom` |
| La dent garde aussi. Le slime reste sans garde : c'est le seul ennemi qu'on peut marteler, mais il se relève à chaque coup de grâce raté. | `enemies.json` |

| Mesure (12 s de duel) | Marteler A | Lire la garde et répondre aux invites |
|---|---|---|
| Gobelin | pas de victoire, 52 PV perdus | mort en 1,15 s, 12 PV perdus |
| Slime | pas de victoire | 1,12 s |
| Dent | pas de victoire, 52 PV perdus | 1,15 s |
| Coquille | pas de victoire, 12 PV perdus | 1,15 s |

### Hitbox : arcs de lame et zones haut/bas (2026-11-15)

**Le moteur n'est pas refait.** Il savait déjà faire des boîtes orientées, des
cercles, des capsules, des hitbox animées, plusieurs boîtes par coup et la
détection balayée ; les données n'en utilisaient rien. Une seule lacune réelle :
les zones de dégâts étaient toutes centrées sur le corps, si bien que la « tête »
du gobelin était une bande au milieu. Les zones ont désormais un `offset_y`.

| Changement | Où |
|---|---|
| Les 12 coups de lame (sabre haut et bas, chargé, aérien, estoc, coup de grâce) sont des **arcs** : une boîte orientée qui tourne autour de l'épaule pendant la fenêtre active, coup droit puis revers. | `attacks.json` |
| La détection balayée tourne la lame entre deux images : une cible prise entre deux positions successives est touchée (testé). | `test_the_sweep_catches_a_target_between_two_poses_of_a_turning_blade` |
| Gobelin, dent, coquille : **tête** en haut (×1,25), **corps**, **jambes** en bas (×0,9). | `enemies.json`, `HurtboxZoneDef.offset_y` |

Effets mesurés (10 graines par ennemi, joueur scripté) :

- Un arc touche 1 à 3 images plus tard qu'un rectangle fixe : la lame doit
  arriver. Le combat est plus lent qu'avec les rectangles (gobelin 3,4 s contre
  1,2 s pour le joueur qui lit la garde), plus proche des combats de NMH2.
- La lame haute passe au-dessus de la griffe du gobelin et le coupe ; c'est la
  lame basse qui la croise. Le duel de lames dépend donc de la position des
  armes, plus seulement du moment.
- Mesurer a fait apparaître un défaut de la contre-attaque : elle protégeait
  l'ennemi jusqu'à la fin de sa récupération. Elle cesse maintenant à la
  récupération, qui redevient l'ouverture à punir.

| 10 duels de 12 s | Marteler A | Lire la garde |
|---|---|---|
| Gobelin | 0 victoire | 10 victoires, 3,4 s, 26 PV perdus |
| Slime | 0 | 10, 1,4 s, 0 PV |
| Dent | 0 | 10, 2,9 s, 26 PV |
| Coquille | 0 | 10, 2,8 s, 24 PV |

**Appuis pendant un gel d'image** : vérifié, aucun n'est perdu dans le jeu. Le
niveau ne lit pas l'entrée pendant un gel et le fournisseur garde l'appui
jusqu'au tick suivant. La perte observée venait de la manette scriptée des tests.
`test_press_during_freeze.py` le fixe avec le vrai fournisseur, et échoue si le
niveau lit l'entrée pendant le gel.

**Reste** : les durées varient d'une partie à l'autre parce que les ennemis
tirent leur garde au hasard sans graine fixe ; les hitbox ne seront calées sur
un geste qu'avec une animation par coup.

### Les autres attaques mises au niveau des coups de lame (2026-11-15)

Les douze coups de lame balayaient un arc animé ; tout le reste était un
rectangle fixe à une phase. Mis au même niveau, à dégâts et étourdissement
inchangés (répartis sur les phases quand il y en a deux) :

| Attaque | Forme et mouvement |
|---|---|
| `punch_1`, `punch_2` | Jab et direct : une capsule qui s'allonge vers l'avant (ralenti en fin de geste) |
| `punch_3` | Deux phases : un crochet qui tourne, puis un coup qui remonte |
| `kick_1` | Un balayage bas, du sol vers l'avant |
| `kick_2` | Deux phases : un balayage au sol, puis le pied qui remonte et projette |
| `throw` | Deux phases : l'ennemi soulevé, puis plaqué, avec une onde qui s'élargit au sol |
| `air_kick` | Un pied pointé vers le bas et l'avant, qui s'allonge pendant la chute |
| `claw_swipe` | Deux griffes en arc : de haut en bas, puis en revers |
| `claw_reach` | Une griffe qui s'étire au ras du sol |
| `body_slam` | Le slime qui gonfle |
| `slime_splash` | Une éclaboussure qui s'étale au sol |

Effets : les poussées portent plus loin à mesure qu'elles s'allongent ; le
troisième poing et le second coup de pied touchent deux fois ; la prise plaque
à l'image 15 au lieu de 5 (invulnérable tout du long). La griffe arrivant d'en
haut, c'est maintenant la lame haute qui la croise en duel. Sur 10 duels par
ennemi, le joueur qui lit la garde bat le gobelin en 1,35 s (3,4 s avant), la
coquille en 1,33 s, la dent en 3,0 s ; le marteleur ne gagne toujours aucun duel.
L'ancienne griffe à deux rectangles reste dans les données de test, où elle
fixe la transition d'une phase à l'autre.

### Marteler A en répondant aux invites gagnait encore (2026-11-15)

Les mesures précédentes faisaient marteler A **sans répondre aux invites**. En
jeu, on y répond, et ce joueur-là gagnait tous ses duels, aussi vite que celui
qui lit la garde (gobelin 2,48 s contre 2,43 s). Chaque partie suivait le même
chemin : le sabre martelé croisait la contre-attaque de l'ennemi, le duel de
lames se gagnait en martelant, l'ennemi sortait sonné et encaissait 69 %
(gobelin) à 93 % (coquille) des dégâts sans rien pouvoir faire. Les coups
bloqués ne coûtaient presque rien.

Trois règles changent :

- **Rebond sur la garde.** Un coup bloqué met fin au coup ; le joueur est
  repoussé (`Guard.DEFLECT_PUSH`), chancelle `Guard.DEFLECT_STAGGER` et paie
  `Battery.DEFLECT_COST`, assez longtemps pour que la contre-attaque porte.
- **La contre-attaque ne se croise pas.** Portée derrière la garde, elle fait
  rebondir une lame qui la rencontre au lieu d'ouvrir un duel de lames.
- **Un duel gagné ouvre, il ne sonne plus.** L'ennemi est déséquilibré
  (`Clash.WIN_STAGGER`) et sa garde tombe `Clash.WIN_OPEN` (0,8 s), moins
  longtemps qu'un bris au poing (`Guard.BROKEN_TIME`, 2,5 s).

10 duels de 12 s par ennemi, joueurs scriptés qui répondent aux invites ; le
lecteur frappe à la hauteur libre et garde pendant les attaques ennemies :

| Ennemi | Martèle A | Lit la garde |
|---|---|---|
| Gobelin | 0/10, 87 PV perdus | 10/10, 3,6 s, 21 PV perdus |
| Dent | 0/10, 87 PV perdus | 10/10, 3,8 s, 22 PV perdus |
| Coquille | 0/10, mort | 7/10, 9,3 s, 73 PV perdus |
| Slime (ne garde pas) | 10/10, 2,1 s | 10/10, 2,4 s |

Testé dans `tests/headless/test_combat_loop.py` : le marteleur qui répond aux
invites perd contre le gobelin, la dent et la coquille sur trois graines (il en
gagnait 8 sur 9 sans ces règles), le rebond, la lame qui rencontre la
contre-attaque et l'ouverture courte d'un duel gagné. Le lecteur scripté
n'utilise ni poing ni pied ; la coquille (140 PV) reste longue pour lui, à
juger à la manette.

### Catalogue refait : des gestes à l'échelle du personnage, un tir, des charges à paliers (2026-11-15)

Retour du développeur : les coups se ressemblaient, beaucoup n'avaient pas de
sens, ils étaient surdimensionnés et partaient dans tous les sens, peu
utilisaient les systèmes en place (charge…), et un coup chargé ne se
distinguait pas d'un coup normal. Il voulait aussi exploiter B à la manette
pour des projectiles.

Mesuré avant : le personnage dessiné fait ~24 × 33 dans sa boîte de 40 × 56,
mais les lames faisaient 58 à 92 unités et portaient jusqu'à 108 ;
`slash_high_4` tournait de −100° à 230° ; les deux chaînes de sabre étaient
identiques (3/5/4 images, 7 dégâts, poussée 30) ; un seul coup était
chargeable ; la dent et la coquille utilisaient le jeu de coups du gobelin.

Ce qui change :

- **Gabarit.** Chaque coup part d'une articulation (épaule, hanche) : lame
  ~28, poing ~22, jambe ~26 ; portée ≤ 48, balayage ≤ 150°, coups hauts
  au-dessus des hanches, coups bas qui partent en dessous, et pas deux coups
  identiques par combattant (`tests/unit/test_move_proportions.py`).
- **Un rôle par coup.** Sabre haut : taille, revers, estoc qui avance, coupe
  verticale. Sabre bas : genou, revers bas, estoc bas (achève au sol), coupe
  montante qui projette. Corps : jab, direct, uppercut qui projette ; balayage,
  circulaire qui envoie au mur.
- **Charges à paliers, sur les trois boutons** (`CHARGES`,
  `src/entities/attack_moves.py`). Sabre lâché tôt : `charged_slash`, plus fort
  avec le temps tenu ; tenu à fond : `charged_slash_full`, prioritaire, brise
  l'armure et lance un croissant. Corps tenu : `charged_kick`. Tir tenu :
  `piercing_shot`.
- **Tir (B / D).** Une phase peut lancer un projectile en devenant active
  (`launches`, `src/entities/shots.py`) ; sa boîte ne touche jamais. Le tir
  coûte `Battery.SHOT_COST`, casse une préparation ennemie à distance ; le
  slime crache une boule en cloche qui retombe bas.
- **Ennemis.** Dent : morsure haute, coup aux chevilles. Coquille : coup
  d'épaule, roulade au sol que rien ne garde (à sauter), 120 PV.
- **Prise.** On n'attrape qu'un ennemi au sol, et la prise l'immobilise : un
  ennemi sonné par l'uppercut se jongle.
- **Effets.** Un style par famille (sabre, coup lourd, chargé, chargé à fond,
  coup de grâce, corps, ennemi, imparable), un liseré sombre pour le contraste,
  la charge qui se rassemble à la main, le chevron d'alerte des ennemis à la
  hauteur du coup, un dessin par projectile.

10 duels de 12 s par ennemi, joueurs scriptés qui répondent aux invites (le
lecteur frappe à la hauteur libre, casse la garde au poing, garde pendant les
attaques, saute la roulade, recharge la batterie) :

| Ennemi | Martèle A | Lit la garde |
|---|---|---|
| Gobelin | 0/10, 88 PV perdus | 10/10, 4,2 s, 3 PV perdus |
| Dent | 0/10, 86 PV perdus | 10/10, 2,8 s |
| Coquille | 0/10, mort | 10/10, 4,0 s, 6 PV perdus |
| Slime | 10/10, 1,4 s | 10/10, 1,8 s |

Les empreintes PHYSICS et RIDE de `test_simulation_golden.py` sont
recapturées ; l'ancien catalogue ayant été écrasé avant, la preuve « seule
cause » des recaptures précédentes n'a pas pu être refaite. À noter : les
pieds du personnage dessiné sont ~8 unités au-dessus du bas de sa boîte, donc
du sol -- à vérifier côté sprite.

### La charge fait grandir le coup ; X et Y deviennent deux familles (2026-11-15)

Retour du développeur : aucune différence entre les coups de X et de Y, et la
charge n'influence ni la taille ni la portée du coup. Vérifié dans l'historique :
la charge n'a jamais agi que sur les dégâts, la poussée et l'étourdissement
(`HitResolver`) ; jamais sur la forme. Et une charge pleine relançait son coup
de palier à ×1, donc parfois moins fort qu'une charge presque pleine.

- **La charge fait grandir le coup.** `HitboxManager` met à l'échelle toute la
  forme (taille et décalage) de `1 + Combat.CHARGE_REACH_GAIN × (m − 1)` : à
  pleine charge, la lame est 1,5 fois plus longue et porte 1,5 fois plus loin.
  Les tirs aussi (`charged`, `src/entities/shots.py`) : plus gros, dégâts,
  poussée et étourdissement multipliés.
- **Le palier plein garde la puissance de la charge** et ajoute son extra
  (croissant, perçage) ; `charged_slash_full` repart de la même base que
  `charged_slash`.
- **X et Y.** Le corps démarre plus tard (4 à 7 images contre 3), gèle plus
  longtemps à l'impact (0,07 à 0,12 s contre 0,03), pousse fort (110 à 480
  contre 30) ; le sabre reste rapide et long. À l'image : entaille nette pour
  la lame, gerbe orange pour le corps, flash pour un coup chargé, dessinés
  au-dessus du flash de l'ennemi touché (avant, ils étaient dessous).

Équilibre inchangé dans le fond (10 duels de 12 s) : le marteleur ne gagne
contre aucun ennemi qui garde, le lecteur bat gobelin, dent et coquille en
3,1 à 3,6 s.
