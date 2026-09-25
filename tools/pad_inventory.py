"""Print what your gamepad actually exposes, so bindings are not guessed.

Run it on the machine where the game runs::

    uv run python tools/pad_inventory.py

It only reads the device; it never writes a binding.
"""

from __future__ import annotations

import pygame

# SDL_GameControllerButton enum (SDL2/SDL_gamecontroller.h), the indices
# pygame reports on JOYBUTTONDOWN events.
BUTTON_NAMES = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "View (Affichage)",
    5: "Guide (logo Xbox)",
    6: "Menu (3 traits)",
    7: "clic stick gauche",
    8: "clic stick droit",
    9: "LB",
    10: "RB",
    11: "dpad haut",
    12: "dpad bas",
    13: "dpad gauche",
    14: "dpad droite",
    15: "Share",
}
AXIS_NAMES = {
    0: "stick gauche X",
    1: "stick gauche Y",
    2: "stick droit X",
    3: "stick droit Y",
    4: "LT (gâchette gauche)",
    5: "RT (gâchette droite)",
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
