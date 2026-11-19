# PR — fix/hitbox-fluidity

Titre proposé : `hitbox: fluidify combos and make one phase one movement`

## Résumé

Investigation complète du système de hitbox d'un hack'n'slash 2D, puis
corrections du ressenti et clarification du catalogue d'attaques.

- **Instrumentation** : benchmark rendu déterministe (RNG semé), nouvelles
  métriques de ressenti (frame advantage, taux de cancel, hit-stop par move,
  combo) avec valeurs de référence qui peuvent échouer.
- **Ressenti** : hit-stop ennemi ~0,088 → 0,04 s ; terminaux de chaîne en
  `cancel_on_hit` avec recovery 14 → 11 ; latence du lien 9 → 7 ticks.
- **Input** : press fantôme corrigé après un prompt death blow/clash et au
  démarrage d'une charge ; conventions voulues documentées.
- **Animation** : la pose d'attaque du joueur suit la frame data et les
  multiplicateurs de vitesse, au lieu d'un timer mural de 0,07 s.
- **Sweep** : fantômes de sweep affichés dans l'overlay, divergence des deux
  mécanismes caractérisée, plafond ajouté au sweep hit-vs-hit.
- **Catalogue** : une phase = un mouvement. Deux règles de validation ;
  `PhaseDefinition.auto_into` enchaîne automatiquement sur un autre move sans
  payer de second cooldown/batterie/combo ; le croissant du full charge est
  devenu `crescent_wave`.
- **Debug** : une touche de banc pressée dans la mauvaise posture n'aborte plus
  la partie et nomme la posture attendue.

## Preuves

- 8 commits, branche `fix/hitbox-fluidity` depuis `master` (`5c88305`).
- `pytest -q` : 3774 passed, 1 skipped.
- `DEBUG=1 pytest -q` : 3772 passed, 3 skipped.
- `mypy src` : 197 fichiers, aucune erreur. `ruff check .` : propre.
- Goldens : 35 lignes recapturées pour le hit-stop ennemi (valeurs seules),
  22 clés renommées pour le croissant (noms seuls, aucune valeur modifiée).
  Digests de simulation : preuve de cause unique à chaque recapture.
- Benchmark comparé au baseline : swings/s et taux de touche en hausse, part de
  freeze en baisse.

## Plan de test manuel

Voir `docs/playtest-2026-11-18.md`. Capturer l'overlay avec
`uv run python tools/capture_debug_overlay.py`.

## Risques / décisions

- Cancel pré-hit écarté : `can_cancel_into` n'a qu'un appelant et le lock en
  STARTUP est un choix de commitment documenté.
- Séparation totale des moves composés écartée : elle remplacerait une suite
  garantie par les frames par un input avec risque de drop ; `auto_into` donne
  l'atomicité d'authoring sans ce coût.
- « Dernier press gagnant » écarté : le provider stocke des sets, l'ordre
  d'arrivée n'existe pas ; cela demanderait une refonte de l'API d'input et des
  snapshots rollback.

## Checklist avant merge

- [ ] Playtest manuel selon `docs/playtest-2026-11-18.md`.
- [ ] Pousser la branche puis ouvrir la PR avec ce texte.
- [ ] Vérifier que CI reprend les mêmes chiffres de recette.
