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
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from src.core.display import detection
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy, picture
from src.core.display.monitors import MIN_WINDOW
from src.core.game import Game

#: The display states worth watching, in the order the acceptance run shows
#: them. The window geometry is checked after each one.
#:
#: There is no display mode to walk any more. The window is the source of truth,
#: so the states left are the ones the player chooses: how big the window opens,
#: and whether to trade filling it for whole-pixel art. The manual
#: ``set_mode`` in :func:`_drag_to` below is what stands in for a player dragging
#: the window edge, which the acceptance run cannot ask them to do on cue.
WALKTHROUGH = [
    ("the size the machine picked", None, FitPolicy.BARS),
    ("a chosen size, 1280x720", (1280, 720), FitPolicy.BARS),
    ("the same size, whole-pixel art", (1280, 720), FitPolicy.INTEGER),
    ("zoomed to fill", (1280, 720), FitPolicy.ZOOM),
    ("back to the machine's size", None, FitPolicy.BARS),
]

#: Sizes a player would drag to, applied by hand to stand in for a drag.
DRAG_SIZES = [(1920, 1080), (1280, 720), (800, 600), (2560, 1440)]


def _report(game: Game) -> None:
    settings = game.settings
    stage, presentation = game.stage, game.presentation
    assert stage is not None and presentation is not None
    desktop = detection.desktop_size()
    # Re-read rather than trust the cache: the whole point of this run is to
    # watch the window follow a display, so a stale list would report the desk as
    # it was rather than as it is.
    topology = game.topology(refresh=True)
    print("\n" + "=" * 72)
    print("WHAT THE GAME DECIDED ABOUT THIS MACHINE")
    print("=" * 72)
    print(f"  displays found        {len(topology.monitors)}  (names: {topology.named})")
    for monitor in topology.monitors:
        left, top = monitor.bounds[0], monitor.bounds[1]
        print(
            f"    [{monitor.index}] {monitor.name or 'unnamed'!r} "
            f"{monitor.size[0]}x{monitor.size[1]} at ({left}, {top}) "
            f"usable {monitor.usable_size} scale {monitor.scale}"
        )
    held = game.window_monitor()
    on = f"[{held.index}] {held.name or 'unnamed'}" if held is not None else "unknown"
    print(f"  window is on          {on}")
    print(f"  desktop reported      {desktop[0]} x {desktop[1]}")
    print(f"  refresh rates         {detection.desktop_refresh_rates() or 'unknown'}")
    print(f"  window size chosen    {settings.window_size or 'the machine picks'}")
    print(f"  window granted        {stage.size[0]} x {stage.size[1]}")
    print(f"  window position       {pygame.display.get_window_position()}")
    print(f"  render target         {presentation.surface.get_size()}")
    print(f"  framing (world units) {DEFAULT_FRAMING.size[0]:.0f} x {DEFAULT_FRAMING.height:.0f}")
    print(f"  fit policy            {presentation.fit.value}")
    source = presentation.picture.source
    print(
        f"  pixel density         {presentation.density:.3f}   whole-pixel {settings.pixel_perfect}"
    )
    print(f"  presented rect        {tuple(presentation.rect)}")
    print(f"  shown from target     {tuple(source)}")
    # What the framing contract is about, printed in the units it is stated in:
    # world units of visible level, rather than pixels of target.
    print(
        f"  world visible         "
        f"{source.width / presentation.density:.0f} x "
        f"{source.height / presentation.density:.0f} of "
        f"{DEFAULT_FRAMING.width:.0f} x {DEFAULT_FRAMING.height:.0f}"
    )
    bars = presentation.bars
    print(f"  letterbox bars        {len(bars)}  {[tuple(b) for b in bars] or 'none'}")
    follows = _picture_matches_the_window(game)
    print(f"  picture follows window {'yes' if follows else 'NO -- THE FRAME IS STALE'}")
    if not follows:
        print("     ^ the render target did not move with the window; check whether the")
        print("       resize reached the game at all. It has to be read off the window.")
    print(f"  interface scale       {game.ui_scale:.3f}  (preference {settings.ui_scale})")
    print(f"  vsync requested       {settings.vsync}   driver reports {pygame.display.is_vsync()}")
    print(f"  frame limit           {settings.frame_limit or 'uncapped'}")
    print()
    print("  CHECK BY HAND:")
    print("   - the window opened centred on the primary display")
    print("   - the image keeps its shape, with black bars and no stretch")
    print("   - the picture is sharp: no soft edges, no doubled pixels")
    print("   - the menus are readable and the gauges sit where they should")
    print("   - dragging the window edge does NOT change how much world you see")
    print("   - dragged onto another panel, the VSync row's rate follows it")


def _apply(game: Game, window_size: tuple[int, int] | None, fit: FitPolicy) -> None:
    game.apply_settings(
        game.settings.with_video(
            window_size=window_size,
            pixel_perfect=fit is FitPolicy.INTEGER,
            fit=fit,
        )
    )


def _picture_matches_the_window(game: Game) -> bool:
    """Whether the picture on screen is the one this window calls for.

    The claim the whole display system rests on, and the one a resize that goes
    unnoticed breaks: the fitted picture is a function of the window's size and the
    fit policy, so a target that disagrees with them is a frame drawn at a
    density nobody asked for. Measured when it was last ignored: a 1000x562
    picture blitted into a 640x500 window, clipped at the right and the bottom,
    with no error and nothing on screen to say so.
    """
    presentation = game.presentation
    assert presentation is not None
    expected = picture(presentation.window_size, DEFAULT_FRAMING, presentation.fit)
    return tuple(presentation.picture.target.size) == tuple(expected.target.size) and tuple(
        presentation.picture.dest.size
    ) == tuple(expected.dest.size)


def _snap_to(game: Game, size: tuple[int, int]) -> None:
    """Stand in for the window manager resizing behind the game's back.

    This is the step the walkthrough was missing, and it is missing it for a
    reason worth writing down: every resize here used to go through
    ``set_mode``, which is the one path that both produces a ``VIDEORESIZE`` and
    lets the run perform the reaction itself. A snap arrives as something else --
    measured, ``WINDOWSIZECHANGED`` and nothing more -- so the run could not see
    the defect it was written to catch.

    So: no ``set_mode``, no posted event, just the window resized the way a
    window manager resizes it, and then a frame. The reaction has to come from
    reading the window.
    """
    assert game.presentation is not None
    try:
        window = pygame.Window.from_display_module()
    except pygame.error, AttributeError:
        print("   no Window handle on this build; the snap cannot be run")
        return
    window.size = size
    # Let the platform settle before the game looks, the way it would between two
    # of its own frames.
    for _ in range(10):
        pygame.event.pump()
        time.sleep(0.03)
    for _ in range(3):
        game.step()


def _drag_to(game: Game, size: tuple[int, int]) -> None:
    """Stand in for a player dragging the window edge.

    Kept as it was -- ``set_mode`` and the reaction by hand -- because it is the
    only way to compare the two: :func:`_snap_to` is the same gesture done by the
    platform, and the two have to end up at the same place.
    """
    assert game.stage is not None and game.presentation is not None
    game.stage.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
    game.presentation.retarget(game.stage.surface)
    game._retarget()
    pygame.event.post(pygame.event.Event(pygame.VIDEORESIZE, w=size[0], h=size[1], size=size))


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

    for index, (title, window_size, fit) in enumerate(WALKTHROUGH):
        if index:
            print(f"\n--- {title} : {arguments.hold:.0f}s, watch the window ---")
            time.sleep(arguments.hold)
        _apply(game, window_size, fit)
        _report(game)

    for size in DRAG_SIZES:
        print(f"\n--- dragging the window to {size[0]} x {size[1]} ---")
        time.sleep(arguments.hold)
        _drag_to(game, size)
        _report(game)

    print("\n\n==== the same sizes, snapped by the window manager ====")
    print("(Super+Left/Right, maximise, restore: no set_mode, no posted event)")
    _apply(game, None, FitPolicy.BARS)
    _report(game)
    for size in DRAG_SIZES:
        print(f"\n--- snapping to {size[0]} x {size[1]} ---")
        _snap_to(game, size)
        _report(game)
    print("\n--- snapping to half of what the window is now ---")
    half = (max(MIN_WINDOW[0], game.presentation.window_size[0] // 2), MIN_WINDOW[1])  # type: ignore[union-attr]
    _snap_to(game, half)
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
