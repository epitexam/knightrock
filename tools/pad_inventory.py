"""Print what your gamepad actually exposes, so bindings are not guessed.

Run it on the machine where the game runs::

    uv run python tools/pad_inventory.py

It only reads the device; it never writes a binding.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from src.core.input.input_bindings import (
    XBOX_A,
    XBOX_B,
    XBOX_LB,
    XBOX_RB,
    XBOX_START,
    XBOX_VIEW,
    XBOX_X,
    XBOX_Y,
)

# The names the game itself gives these indices, so the tool and the default
# bindings cannot disagree. ``JOYBUTTONDOWN`` reports SDL's *joystick* numbers,
# not the ``SDL_GameControllerButton`` enum: the table used to follow the enum
# and called button 4 "View" where the game -- correctly -- reads LB.
BUTTON_NAMES = {
    XBOX_A: "A",
    XBOX_B: "B",
    XBOX_X: "X",
    XBOX_Y: "Y",
    XBOX_LB: "LB",
    XBOX_RB: "RB",
    XBOX_VIEW: "View (Affichage)",
    XBOX_START: "Menu / Start (3 traits)",
}
# Only the left stick is numbered the same on every platform; the triggers and
# the right stick move between drivers, which is what this tool is for finding.
AXIS_NAMES = {
    0: "stick gauche X",
    1: "stick gauche Y",
}


def main() -> int:
    pygame.init()
    pygame.joystick.init()
    # ``pygame.event.get`` pulls from the SDL queue, which needs the video
    # subsystem up. A 1x1 window is enough and keeps the tool usable headless
    # (``SDL_VIDEODRIVER=dummy``).
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    # pygame-ce dropped ``joystick.get_all()``; the way to enumerate the
    # connected devices is the count plus an indexed lookup.
    pads = [pygame.joystick.Joystick(index) for index in range(pygame.joystick.get_count())]
    if not pads:
        print("Aucune manette detectee. Branche-la et relance le script.")
        return 1
    for pad in pads:
        print(f"\n=== {pad.get_name()} ===")
        print(f"  boutons : {pad.get_numbuttons()}")
        for index in range(pad.get_numbuttons()):
            print(f"    {index:2d} -> {BUTTON_NAMES.get(index, 'inconnu')}")
        print(f"  axes    : {pad.get_numaxes()}")
        for index in range(pad.get_numaxes()):
            print(f"    {index:2d} -> {AXIS_NAMES.get(index, 'inconnu')}")
        print(f"  hats    : {pad.get_numhats()}")
        print("\n  Appuie sur chaque bouton : le script affiche son index.")
        print("  (Ctrl+C pour quitter)")
        seen: set[int] = set()
        clock = pygame.time.Clock()
        while len(seen) < pad.get_numbuttons():
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    index = event.button
                    if index not in seen:
                        seen.add(index)
                        print(f"    -> bouton {index:2d} ({BUTTON_NAMES.get(index, 'inconnu')})")
            clock.tick(60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
