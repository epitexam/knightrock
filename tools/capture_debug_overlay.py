"""Capture one debug-geometry frame of a real fight, headless.

F1 in the game draws these outlines; this script freezes the same geometry of
a real slash against a real foe into a PNG, so a change in sweep ghosts or hurt
zones can be looked at without launching the window. Art is intentionally
absent: the point is the boxes the contact pipeline tests.

    uv run python tools/capture_debug_overlay.py [output.png]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from src.core.display.framing import Framing  # noqa: E402
from src.core.rendering.camera import Camera  # noqa: E402
from src.ui.panel_renderer import PanelRenderer  # noqa: E402
from src.ui.world_ui import WorldUI  # noqa: E402
from tests.headless.arena import DT, SLASH, arena, foe  # noqa: E402

SIZE = (1152, 648)


def main() -> None:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/debug-overlay.png")
    pygame.init()
    surface = pygame.display.set_mode(SIZE)

    level, pad, player = arena()
    for _ in range(60):  # let the fighter settle on the floor before swinging
        level.update(DT)
    foe(level, "goblin", player.hitbox.centerx + 40.0, guards=False, vision_range=0.0)
    pad.held = frozenset({SLASH})
    for _ in range(5):
        level.update(DT)

    overlay = WorldUI(PanelRenderer(surface))
    camera = Camera(Framing(float(SIZE[0]), float(SIZE[1])))
    surface.fill((0, 0, 0))
    for entity in level.groups.entity_sprites:
        overlay._geo.draw_boxes(entity, camera)

    destination.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, destination)
    print(destination)


if __name__ == "__main__":
    main()
