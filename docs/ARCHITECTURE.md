# Architecture cible — Knightrock

> **Statut : proposition.** Ce document décrit l'organisation que le projet devrait
> adopter **après** un futur refactoring autorisé. Rien de ce qui est décrit ici n'est
> implémenté aujourd'hui ; l'état réel est documenté dans
> [`ARCHITECTURE_AUDIT.md`](ARCHITECTURE_AUDIT.md) et la trajectoire dans
> [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md).

---

## 1. Principe directeur

L'architecture actuelle est **saine et ne doit pas être remplacée** : huit couches à
direction vérifiée, une boucle fixe à accumulateur, un bus d'évènements synchrone à
isolation d'abonnés, des données JSON à source unique, un rollback déterministe, une CI
bloquante. L'audit n'a trouvé **aucun constat critique ni majeur** et l'audit précédent
concluait déjà : *« ne pas introduire d'ECS, de bus d'évènements général ni de
réorganisation des dossiers »*.

L'architecture cible est donc la même architecture, **consolidée** sur quatre axes :

1. **Persistance durable** (F1) — un seul protocole d'écriture atomique.
2. **Cohésion des modules** (F3, F4) — éclater les deux derniers gros fichiers sans
   changer les Points d'entrée publics.
3. **Contrats typés** (F5, F15) — réduire les `getattr`, typer le snapshot.
4. **Présentation maîtrisée** (F8) — pré-rendu des tuiles, invalidation complète.

Aucun ECS, aucun bus généralisé, aucun service locator, aucune réécriture.

---

## 2. Vue d'ensemble cible

```
src/
├── application/          Composition root (inchangé)
│   ├── game.py           Affichage, entrées, pile de scènes, boucle à accumulateur
│   ├── persistence.py    [NOUVEAU] écriture atomique JSON partagée (F1)
│   ├── save_game.py      Progression — utilise persistence.py
│   ├── settings_store.py Réglages — utilise persistence.py
│   └── scenes/           Menu, sélection, options, vidéo, contrôles, gameplay,
│                          pause, game over, victoire (inchangé)
├── combat/               Frame data, résolution, knockback, charge, combo (inchangé)
├── core/
│   ├── settings/         [RESTRUCTURÉ, F3] package, un module par domaine :
│   │   ├── __init__.py   ré-exporte l'intégralité des noms actuels (compat import)
│   │   ├── display.py    physics.py  combat.py  camera.py  ai.py
│   │   └── input.py      audio.py    animation.py  simulation.py  gameplay.py
│   ├── level/            Façade niveau + systèmes ordonnés à tick fixe (inchangé,
│   │                     GameplayLoop à systèmes requis — F6)
│   ├── events.py         Bus synchrone ordonné (inchangé)
│   └── …                 display/, fx/, input/, rendering/, rollback/ (inchangés)
├── data/                 Chargeurs JSON stricts, source unique (inchangé)
├── entities/
│   ├── entity.py         [ALLÉGÉ, F4] identité, vitals, délégation aux composants
│   ├── hurtbox_geometry.py  [NOUVEAU, F4a] zones, tags, multiplicateurs, sweep hurtbox
│   └── …                 player, ennemis, projectiles (inchangés)
├── physics/              Collisions, gravité, mouvement, hachage spatial (inchangé)
├── states/               Machines à états (inchangées)
└── ui/                   HUD, panneaux, overlay debug (inchangé, moins de getattr — F5)
```

Légende : `[NOUVEAU]` = fichier ajouté ; `[RESTRUCTURÉ]` / `[ALLÉGÉ]` = déplacement pur
sans changement de comportement ; tout le reste est **inchangé**.

---

## 3. Frontières et dépendances autorisées

Les règles actuelles, déjà vérifiées par AST (`tests/unit/test_layer_boundaries.py`),
restent la colonne vertébrale :

| Règle | Statut cible |
|---|---|
| `core` n'importe ni `ui` ni `application` | conservée, testée |
| L'interface atteint le monde par injection (`rendering/overlay.py`) | conservée |
| La simulation publie des faits sur `core.events`, ne connaît pas l'application | conservée |
| PyTMX encapsulé dans `core/level/level_manager.py` + `level_data.py` | conservée |
| `pygame.mixer` touché par `core/audio.py` seul | conservée |
| `data/` = source unique des valeurs de gameplay | conservée |
| `application` est le seul lieu où `ui` et `core` se rencontrent nommément | conservée |

Ajouts cibles (mêmes mécanismes, nouvelles précisions) :

- **`application/persistence.py`** : les deux seuls écrivains de fichiers utilisateur
  (`SaveGame`, `SettingsStore`) passent par une fonction unique
  « écrire du JSON de façon atomique avec backup ». Direction : `application/* →
  application/persistence` uniquement. Aucune autre couche n'écrit sur disque.
- **`core/settings/`** : les importeurs continuent d'écrire
  `from src.core.settings import X`. Le package ajoute une règle interne : un module de
  domaine n'importe pas un autre module de domaine (pas d'accouplement caché entre
  `combat.py` et `ai.py`, par exemple) ; les références croisées passent par
  `__init__.py` ou par des valeurs littérales dupliquées assumées.
- **`entities/hurtbox_geometry.py`** : dépend vers `combat/shapes.py` et
  `entities/hurtbox_zones.py` ; `Entity` délègue. Rien d'autre ne change.

---

## 4. Communication entre systèmes

Inchangée, car elle fonctionne et est testée :

- **Bus synchrone ordonné** (`core/events.py`) pour les faits simulation → interface
  (audio, HUD, sauvegarde). Isolation par abonné, échecs journalisés et listés.
- **Injection** pour les dépendances structurelles (`WorldOverlay` port, `InputProvider`,
  systèmes du `GameplayLoop`).
- **Machine à états** pour joueur/ennemis, réactions partagées, turn.
- **Pas d'event bus global au-delà de `core.events`**, pas de service locator, pas de
  singletons nouveaux. Les états process-wide existants (F14) sont acceptés, documentés
  dans les standards, avec hooks de reset quand un cache existe.

---

## 5. Gestion des ressources

| Aspect | Cible |
|---|---|
| Chargement | Centralisé (`AssetLibrary`, préchargement des clips au chargement du niveau) — inchangé |
| Caches | Bornés et invalidés explicitement (`SCALE_CACHE_MAX`, `clear_frame_cache`) — inchangé |
| **Tuiles** (F8) | Calques de tuiles statiques pré-rendus par blocs depuis `TileChunkIndex`, invalidés au changement d'échelle **et** de format d'affichage — supprime la non-reconversion B4 |
| Écritures disque (F1) | Un seul utilitaire atomique (`application/persistence.py`) |
| Lifecycle | Aucune fuite (mesuré : 12 000 ticks, mémoire constante) — inchangé |

---

## 6. Encapsulation de Pygame et PyTMX

- **PyTMX** : déjà confiné à deux modules ; la cible n'ajoute rien, elle **interdit** tout
  nouvel import `pytmx` ailleurs (règle à écrire dans les standards, vérifiable par le
  même mécanisme AST que `test_layer_boundaries.py`).
- **Pygame** : l'accès est déjà sectorisé (`core/audio.py` pour le mixer,
  `core/display/*` pour la fenêtre, `core/rendering/*` pour le dessin). La cible n'introduit
  pas de couche d'abstraction supplémentaire — le coût serait supérieur au bénéfice pour
  un jeu mono-moteur. Les standards listent simplement les modules autorisés à importer
  `pygame` directement.

---

## 7. Trajectoire : de l'état actuel à la cible

| Étape | Contenu | Constat(s) | Risque comportemental |
|---|---|---|---|
| 1 | Écriture atomique de la sauvegarde | F1 | nul |
| 2 | CI sur la branche (PR draft ou dispatch) | F13 | nul |
| 3 | Package `core/settings/` à ré-export identique | F3 | nul (mypy + tests) |
| 4 | Contrats typés : snapshot, lots de `getattr` | F15, F5 | faible |
| 5 | Géométrie de hurtbox extraite d'`Entity` | F4a | faible à moyen (matrice de coups) |
| 6 | Pré-rendu des tuiles + invalidation format | F8 | moyen (comparaison au pixel) |
| 7 | `GameplayLoop` requis, prose, standards, Bandit | F6, F7, F14, F16 | nul à faible |

Le détail exécutable (tâches, preuves, tests, critères d'acceptation, préservation du
comportement) est dans [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md).

---

## 8. Ce que l'architecture cible n'est **pas**

- Pas un ECS, pas un event bus supplémentaire, pas de service locator, pas de conteneur
  d'injection.
- Pas de réorganisation des dossiers au-delà de `settings/` (package) et de deux fichiers
  nouveaux (`persistence.py`, `hurtbox_geometry.py`).
- Pas de changement de gameplay, de rééquilibrage, de nouvelle fonctionnalité.
- Pas de réécriture de la boucle, du combat, de la physique ou du rollback : ces systèmes
  sont mesurés, testés et gelés par la matrice de caractérisation.
