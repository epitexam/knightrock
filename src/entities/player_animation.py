"""Sprite-sheet animations of the player (audit F4.1, Phase 2 #1/#3)."""

from src.core.animation.animator import AnimationSpec
from src.core.settings import Animation as AnimationSettings

PLAYER_ANIMATIONS: dict[str, AnimationSpec] = {
    spec.name: spec
    for spec in (
        AnimationSpec(
            "idle", "assets/graphics/player/idle", AnimationSettings.FRAME_DURATION * 1.2
        ),
        AnimationSpec("run", "assets/graphics/player/run", AnimationSettings.RUN_FRAME_DURATION),
        AnimationSpec(
            "jump", "assets/graphics/player/jump", AnimationSettings.FRAME_DURATION, loop=False
        ),
        AnimationSpec("fall", "assets/graphics/player/fall", AnimationSettings.FRAME_DURATION),
        AnimationSpec("wall", "assets/graphics/player/wall", AnimationSettings.FRAME_DURATION),
        AnimationSpec(
            "attack",
            "assets/graphics/player/attack",
            AnimationSettings.ATTACK_FRAME_DURATION,
            loop=False,
        ),
        AnimationSpec(
            "air_attack",
            "assets/graphics/player/air_attack",
            AnimationSettings.ATTACK_FRAME_DURATION,
            loop=False,
        ),
        AnimationSpec(
            "hit", "assets/graphics/player/hit", AnimationSettings.HIT_FRAME_DURATION, loop=False
        ),
    )
}
"""Sprite-sheet animations shipped under ``assets/graphics/player/``.

States without dedicated art (block, charge, dash, stagger) keep playing
the previous animation: :meth:`Player._animation_name` returns None for
them.  The animator is attached in ``Player.__init__`` so the hundred
shipped artworks are actually rendered (audit F4.1, Phase 2 #1).
"""
