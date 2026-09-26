"""Manual acceptance run for the display rework.

Opens the game on the real session, reports what it decided about the machine,
and walks the display states on its own so the window can be watched. Nothing
here is a test: under the dummy driver every one of these questions is
unanswerable, which is why ``notes/audit_dimensions_fenetre.md`` §8 lists it as
still owed.

Run it from the repo root::

    uv run python tools/display_acceptance.py            # menu, 12 seconds
    uv run python tools/display_acceptance.py --hold 30  # longer
    uv run python tools/display_acceptance.py --debug    # with the F-keys live
    uv run python tools/display_acceptance.py --real-settings

Close the window early to stop it; the report prints either way.

**It does not touch your settings.** The walkthrough applies real display
changes, and the game writes its settings on the way out, so by default the run
gets a throwaway settings file in a temporary directory. The first version of
this script did write the real one -- which is how a machine ended up with
``borderless 1280x720`` it had never chosen. ``--real-settings`` opts back in.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from src.core.display import detection
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.mode import DisplayMode
from src.core.game import Game

#: The display states worth watching, in the order the acceptance run shows
#: them. The window geometry is checked after each one.
WALKTHROUGH = [
    ("borderless, whatever the machine picked", DisplayMode.BORDERLESS, None),
    ("window, auto size", DisplayMode.WINDOW, None),
    ("window, manual size", DisplayMode.WINDOW, (1280, 720)),
    ("borderless again", DisplayMode.BORDERLESS, None),
]


def _report(game: Game) -> None:
    settings = game.settings
    stage, viewport, presentation = game.stage, game.viewport, game.presentation
    assert stage is not None and viewport is not None and presentation is not None
    desktop = detection.desktop_size()
    print("\n" + "=" * 72)
    print("WHAT THE GAME DECIDED ABOUT THIS MACHINE")
    print("=" * 72)
    print(f"  desktop reported      {desktop[0]} x {desktop[1]}")
    print(f"  refresh rates         {detection.desktop_refresh_rates() or 'unknown'}")
    print(f"  display mode          {settings.display.value}")
    print(
        f"  window size           {settings.width} x {settings.height} ({settings.size_mode.value})"
    )
    print(f"  window granted        {stage.size[0]} x {stage.size[1]}")
    print(f"  window position       {pygame.display.get_window_position()}")
    print(
        f"  render target         {viewport.size[0]} x {viewport.size[1]} (scale {viewport.scale})"
    )
    print(f"  framing (world units) {DEFAULT_FRAMING.size[0]:.0f} x {DEFAULT_FRAMING.height:.0f}")
    print(f"  presented rect        {tuple(presentation.rect)}")
    print(f"  presentation scale    {presentation.scale:.3f}   smoothing {settings.smoothing}")
    bars = presentation.bars
    print(f"  letterbox bars        {len(bars)}  {[tuple(b) for b in bars] or 'none'}")
    print(f"  vsync requested       {settings.vsync}   driver reports {pygame.display.is_vsync()}")
    print(f"  frame limit           {settings.frame_limit or 'uncapped'}")
    print()
    print("  CHECK BY HAND:")
    print("   - the window is centred on the primary screen")
    print("   - the image keeps its shape, with black bars and no stretch")
    print("   - the menus are readable and the gauges sit where they should")
    print("   - dragging the window edge does NOT change how much world you see")


def _apply(game: Game, mode: DisplayMode, size: tuple[int, int] | None) -> None:
    changes: dict[str, object] = {"display": mode}
    if size is not None:
        changes.update(width=size[0], height=size[1])
    game.apply_settings(game.settings.with_video(**changes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=12.0, help="seconds per state")
    parser.add_argument("--debug", action="store_true", help="enable the debug overlay")
    parser.add_argument(
        "--once",
        action="store_true",
        help="print the walkthrough and exit, instead of staying open",
    )
    parser.add_argument(
        "--real-settings",
        action="store_true",
        help="read and write the real settings file instead of a throwaway one",
    )
    arguments = parser.parse_args()
    if arguments.debug:
        import os

        os.environ["DEBUG"] = "1"

    if arguments.real_settings:
        settings_path = None
        print("using the REAL settings file; the walkthrough will be saved to it")
    else:
        scratch = tempfile.TemporaryDirectory(prefix="knightrock-acceptance-")
        settings_path = Path(scratch.name) / "settings.json"
        print(f"using a throwaway settings file ({settings_path}); your own is untouched")

    game = Game(bindings_path=settings_path)
    # The real path, not ``initialize_display`` on its own: the automatic
    # resolution of the window size happens in ``_initialize``, and skipping it
    # would report a configuration the player never gets.
    game._initialize()
    _report(game)

    import time

    for index, (title, mode, size) in enumerate(WALKTHROUGH):
        if index:
            print(f"\n--- {title} : {arguments.hold:.0f}s, watch the window ---")
            time.sleep(arguments.hold)
        _apply(game, mode, size)
        _report(game)

    if arguments.once:
        print("\nDone (--once).")
        game.flush_settings()
        pygame.quit()
        return

    print("\nDone. Ctrl-C or close the window to finish.")
    try:
        while True:
            time.sleep(0.02)
            game.step()
    except KeyboardInterrupt:
        print()
    finally:
        game.flush_settings()
        pygame.quit()


if __name__ == "__main__":
    main()
