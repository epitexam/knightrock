# Design — le monde en matrice

> **Statut : proposition, rien d'implémenté.** Aucune modification de code n'accompagne
> cette note. Les décisions marquées **[arbitrer]** sont à l'auteur du projet.

---

## 1. Le problème

Le système de niveaux actuel est **linéaire**, et c'est un choix encodé à cinq endroits :

| Où | Ce que ça dit |
|---|---|
| `data/gameplay/levels.json` | `{"0": "assets/data/levels/1.tmx"}` — un id → un fichier |
| `level_manager.LEVEL_PATHS` | la même table, en dur |
| `LevelConfig.level_unlock` | « la salle N débloque N+1 » |
| `gameplay_scene._advance_level()` | `next_id()` ; `None` → `VictoryScene` |
| `save_game.last_level_id: int` | un entier |

Huit cartes existent sur le disque, une seule est enregistrée. La conséquence n'est pas
cosmétique : c'est **la structure même du jeu** qui est linéaire, et un Metroidvania ne l'est pas.

## 2. Ce qu'on veut

Une **matrice** : chaque coordonnée `(col, row)` désigne un fichier `.tmx`, et l'ensemble
des coordonnées habitables forme un seul grand niveau. Le joueur traverse d'une salle à
la voisine en sortant par un bord ; il n'y a pas d'écran de sélection de niveau, il y a un
monde.

---

## 3. Ce qui ne change pas — et c'est l'essentiel

C'est le point le plus important de cette note, parce qu'il délimite le chantier réel.

**Toute la simulation est indépendante de la topologie.** Une salle est un `Level`, rien de
plus. Ce qui est déjà acquis et ne bouge pas :

- `Level` est une façade sur `GameplayLoop`, la pipeline déterministe complète
  (physics, combat, contact, hazards, caméra, rollback) — tout est **par salle**, déjà.
- `LevelManager.get(clé)` met en cache par clé : une coordonnée est juste une autre clé.
- `Camera`/`viewport` produit **déjà un viewport fixe par cible** (`framing.py`,
  `viewport.py`) : un écran par salle ne demande aucun travail de caméra.
- `SpatialHash` est construit par salle. Idem `TileChunkIndex`, le culling, l'affichage.
- Le rollback, les snapshots, le déterminisme, les tests headless : **aucun impact**.

**Le chantier se limite à la couche *progression***, soit environ cinq fichiers.

---

## 4. Le modèle de données

### 4.1 Le manifeste existe déjà — il faut l'étendre, pas en créer un

`data/levels_manifest.json` énumère **les 9 cartes** avec leur taille en tuiles et en pixels
(il sert aujourd'hui à `test_framing_contract.py`). C'est le bon support : il est déjà
complet, déjà utile, et il est déjà lu.

Proposition — ajouter une coordonnée à chaque entrée :

```json
{
  "version": 2,
  "levels": [
    {
      "file": "assets/data/levels/1.tmx",
      "tiles": [60, 20],
      "tile_size": [64, 64],
      "world": [3840, 1280],
      "col": 0,
      "row": 0
    }
  ]
}
```

`version: 2` plutôt qu'un nouveau fichier, parce que `test_framing_contract.py:27`
**assertit la version** : changer de format est donc détecté par un test, pas découvert en
production. C'est exactement le filet qu'on veut.

⚠️ **`assets/` n'est pas versionné** (décision du projet). Ce manifeste est donc la **seule**
source de vérité sur la géométrie du monde pour tout ce qui n'a pas les fichiers sous la
main — c'est-à-dire pour la CI. Et `test_levels_manifest.py` **re-dérive** le manifeste
depuis les `.tmx` dès qu'ils sont là. La coordonnée, elle, ne peut pas être re-dérivée : elle
est une **décision d'auteur**. Il faut donc la traiter comme telle.

### 4.2 La destination d'une sortie

Je recommande des propriétés sur l'objet `flag` dans Tiled, dans l'esprit data-driven du
projet :

```
flag (x=1856, y=326, w=68, h=186)
  to_col   = 1      # coordonnée de destination
  to_row   = 0
  entry    = left   # par où le joueur apparaît dans la salle d'arrivée
```

Pourquoi sur l'objet plutôt que dans le manifeste : la sortie est un **objet du monde**, et
son appartenance est locale. Un manifeste qui liste les sorties duplique la carte.

L'objet `flag` porte déjà `width`/`height`, et le correctif de placement récent
(`7875d42`) fait que la zone de sortie épouse exactement ce rectangle. Le drapeau est donc
**déjà** le déclencheur naturel.

### 4.3 La sauvegarde

```python
@dataclass
class SaveGame:
    col: int = 0
    row: int = 0
    visited: set[tuple[int, int]] = field(default_factory=set)
    abilities: set[str] = field(default_factory=set)   # voir §7
```

`last_level_id: int` disparaît. La migration d'une sauvegarde existante (un entier) peut se
faire en l'ignorant : une sauvegropy linéaire n'a pas de sens dans une matrice, et
`save_game.py` gère déjà un JSON illisible en repartant des défauts.

---

## 5. Ce qui change, fichier par fichier

| Fichier | Changement | Risque |
|---|---|---|
| `level_data.py` | `LevelConfig.level_unlock` → rien ; ajouter `LevelExitData` (destination, côté d'entrée) lu depuis l'objet | FAIBLE |
| `level_manager.py` | clé `int` → `(col, row)` ; `LEVEL_PATHS` → le manifeste ; `next_id()` **supprimé** | MOYEN |
| `world_builder.py` | `_build_exit` pose la destination sur le `LevelExit` | FAIBLE |
| `gameplay_scene._advance_level()` | au lieu de `next_id()` : lire la destination de la sortie touchée, et charger cette coordonnée. Plus de `VictoryScene` | MOYEN |
| `save_game.py` | coordonnée + salles visitées + capacités | FAIBLE |
| `level_select_scene.py` | **[arbitrer]** écran de carte, ou suppression au profit de la traversée en monde | — |
| `data/levels_manifest.json` | `version: 2` + coordonnées | FAIBLE |

**Supprimer `VictoryScene` mérite une décision** : un Metroidvania n'a pas de fin unique, il a
une fin « quand tu as libéré le monde ». Je recommande de le **garder** mais de le déclencher
depuis un objet dédié (`end_game` dans la carte finale), pas depuis l'absence de suivant.

---

## 6. Le placement du joueur entre deux salles

Un point que le système actuel ne traite pas du tout : quand on sort de la salle (0,0) par la
droite, il faut apparaître dans (1,0) **par la gauche**, pas à son point de spawn.

Je propose : la propriété `entry` sur la sortie dit par quel côté on entre, et le builder
place le joueur au bord correspondant de la salle d'arrivée (avec une marge d'une tuile).
C'est le même mécanisme que la sortie, en miroir.

---

## 7. Le vrai chantier : le gating par capacité

**Une matrice de salles connectées donne un donjon. Ce qui donne un Metroidvania, ce sont
les portes fermées derrière des capacités.**

Le projet a déjà dash, guard, charge, coyote time, jump buffer — mais **aucun système de
capacité** : rien qui dise « le joueur possède le double saut », et rien qu'un objet de carte
puisse interroger.

Forme minimale que je recommande :

- `save_game.abilities: set[str]` (§4.3)
- un objet de capacité dans Tiled : `pickup_ability = double_jump`
- un objet de barrière : `needs_ability = double_jump` — le builder le construit en
  collision solide, et le retire quand la capacité est acquise
- les barrières sont donc **statiques au chargement de la salle**, pas dynamiques : la
  salle se recharge quand on revient, et la capacité est lue à ce moment. Simple, et
  cohérent avec le cache par salle déjà en place.

C'est un chantier à part entière (mécanique nouvelle + données + UI), et il est **la**
différence entre les deux genres. À arbitrer s'il entre dans le périmètre.

---

## 8. Séquence proposée

Chaque étape est livrable seule et vérifiable ; aucune ne casse la précédente.

1. **La grille sur le papier.** Poser les 9 cartes sur une grille sur papier (ou dans le
   manifeste), avec les handlers de couche qui vont avec. Ne touche à rien.
2. **Le manifeste v2 + coordonnées.** Version bumpée, `test_framing_contract` adapté.
   Le jeu continue de tourner sur `levels.json`.
3. **La clé du gestionnaire en coordonnée.** `LevelManager((col,row) -> fichier)`.
   `next_id()` supprimé, remplacé par l'adjacence.
4. **Sortie → destination.** Le `flag` porte `to_col`/`to_row`/`entry` ; traverser un bord
   charge la voisine. C'est **là** que le monde devient continu.
5. **Sauvegarde par coordonnée.**
6. **Écran de carte** (optionnel, §5).
7. **Capacités et barrières** (§7) — le chantier qui fait le Metroidvania.

---

## 9. Décisions à prendre avant d'écrire du code

| # | Question | Ma recommandation |
|---|---|---|
| 1 | Manifeste : étendre `levels_manifest.json` (v2) ou nouveau fichier ? | **Étendre**, parce que la liste des cartes y est déjà et que le test de version détecte le changement |
| 2 | La destination se lit sur l'objet `flag` ou dans le manifeste ? | **Sur l'objet** : la sortie est locale au monde, pas une table centrale |
| 3 | Où poser les 9 cartes existantes sur la grille ? | **Arbitrage auteur.** Aucune règle ne s'en déduit : les cartes ont des tailles différentes (60×20, 40×30, 24×30) et aucune n'a de coordonnée. C'est une décision de level design |
| 4 | `LevelSelectScene` : écran de carte ou traversée seule ? | **Traversée seule** au début ; l'écran de carte est un cran de confort après |
| 5 | Le gating par capacité est-il dans le périmètre ? | **Oui**, sinon on livre un donjon et pas un Metroidvania — mais en dernier (§8 étape 7) |
| 6 | `VictoryScene` survit ? | **Oui**, déclenché par un objet `end_game`, pas par l'absence de suivant |
