"""Where the frame went, and what is holding it back.

Five numbers, and the point of showing all of them is that a frame rate on its
own cannot tell a slow game from a paced one. "100 fps" reads as a problem; the
same 100 fps with the limit set to 100 is the game doing exactly what it was
asked. So the readout carries the pacer next to the timings, and the timings are
a median rather than an instantaneous value, because a single frame is a
sample of nothing.

The measurement is **always on** and the display is a setting. That split is
deliberate: two ``perf_counter`` calls per frame cost about a tenth of a
microsecond, and a number that is only collected when something is watching it
is a number you cannot compare afterwards. What is gated is the painting, and
that is the whole difference between a tool and a debug overlay.

The four terms, in the order they happen:

``tick``
    Fixed-timestep simulation. Grows with entity count and never with window
    size.
``world``
    The world pass: background, terrain, entities, FX. A function of the
    target's pixels, so it grows with the window.
``ui``
    HUD, health bars, overlays and panels on top of the world.
``present``
    The 1:1 blit onto the window and the flip. Also a function of the window,
    and the term the dummy driver cannot measure honestly: a real compositor
    does work the headless one does not.
"""

from collections import deque
from dataclasses import dataclass, field

#: How many frames the medians are taken over. Long enough that one hitch does
#: not move the number, short enough to follow a change: at 60fps this is a
#: second, at 240fps a quarter of one.
SAMPLE_WINDOW = 60

#: The labels, in drawing order. Short on purpose -- this is a readout, and a
#: readout that has to be read is a readout nobody reads.
_TERMS = (
    ("tick", "sim"),
    ("world", "monde"),
    ("ui", "ui"),
    ("present", "pres"),
)


@dataclass
class FrameCounter:
    """Rolling medians of one frame's terms, plus the pacer that shaped it."""

    samples: dict[str, deque[float]] = field(
        default_factory=lambda: {name: deque(maxlen=SAMPLE_WINDOW) for name, _ in _TERMS}
    )
    frame_samples: deque[float] = field(default_factory=lambda: deque(maxlen=SAMPLE_WINDOW))
    #: What the loop is pacing to, in words. Set once per frame by the caller,
    #: which is the only place that knows both the settings and the clock.
    pacer: str = ""

    def sample(
        self,
        frame_ms: float,
        tick_ms: float,
        world_ms: float,
        ui_ms: float,
        present_ms: float,
    ) -> None:
        """Record one frame. Cheap enough to leave on for the whole session."""
        self.frame_samples.append(frame_ms)
        self.samples["tick"].append(tick_ms)
        self.samples["world"].append(world_ms)
        self.samples["ui"].append(ui_ms)
        self.samples["present"].append(present_ms)

    def median(self, name: str) -> float:
        """The median of one term, 0.0 before a full window has been seen.

        A median and not a mean on purpose: the frame that matters is the one
        the player sees, and one 40ms hitch in a window of 60 should not move a
        number that is meant to describe the other fifty-nine.
        """
        values = sorted(self.samples[name]) or [0.0]
        return values[len(values) // 2]

    @property
    def frame_ms(self) -> float:
        """Median whole-frame time."""
        values = sorted(self.frame_samples) or [0.0]
        return values[len(values) // 2]

    def fps(self) -> float:
        """Frames per second implied by the median frame time."""
        return 1000.0 / self.frame_ms if self.frame_ms > 0.0 else 0.0

    def lines(self) -> tuple[str, ...]:
        """The readout, one string per line.

        Two lines: the answer, then the evidence. Everything else about a frame
        budget is a guess until you can see which of the four terms is large.
        """
        total = self.frame_ms
        return (
            f"{self.fps():5.1f} fps  {total:5.2f} ms" + (f"  {self.pacer}" if self.pacer else ""),
            "  ".join(f"{label} {self.median(name):4.2f}" for name, label in _TERMS),
        )
