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
