"""What the player fights with besides the blade: battery, fury, slot machine, prompts.

Every one of them is simulation state -- a slash on an empty battery is weak,
a full fury opens the dark side, a slot jackpot grants a power, a prompt
freezes the fight until a direction is given -- so each has a snapshot, and
the player's snapshot carries them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from src.core.settings import Battery as BatterySettings
from src.core.settings import Clash as ClashSettings
from src.core.settings import Finisher as FinisherSettings
from src.core.settings import Fury as FurySettings
from src.core.settings import Slot as SlotSettings
from src.core.settings import Throw as ThrowSettings

# -- battery -------------------------------------------------------------------


class Battery:
    """The blade's charge: every slash spends some, and it is recharged by hand."""

    def __init__(self) -> None:
        self.amount: float = BatterySettings.MAX

    @property
    def ratio(self) -> float:
        return self.amount / BatterySettings.MAX

    @property
    def is_empty(self) -> bool:
        return self.amount <= 0.0

    def spend(self, cost: float) -> bool:
        """Take ``cost`` from the battery; False if it was already empty."""
        if self.is_empty:
            return False
        self.amount = max(0.0, self.amount - cost)
        return True

    def recharge(self, delta_time: float) -> None:
        self.amount = min(
            BatterySettings.MAX, self.amount + BatterySettings.RECHARGE_PER_S * delta_time
        )

    def reset(self) -> None:
        self.amount = BatterySettings.MAX


# -- fury ----------------------------------------------------------------------


@dataclass(frozen=True)
class FurySnapshot:
    amount: float
    decay_delay: float
    dark_timer: float


class FuryGauge:
    """Fury: filled by hitting without being hit, spent whole on the dark side.

    The gauge's level speeds the slashes up in tiers (``Fury.TIERS``). The dark
    side empties it over its length, so the gauge is also its clock on screen;
    nothing fills or drains it otherwise while it lasts.
    """

    def __init__(self) -> None:
        self.amount: float = 0.0
        self.decay_delay: float = 0.0
        self.dark_timer: float = 0.0

    @property
    def ratio(self) -> float:
        return self.amount / FurySettings.MAX

    @property
    def is_full(self) -> bool:
        return self.amount >= FurySettings.MAX

    @property
    def in_dark(self) -> bool:
        return self.dark_timer > 0.0

    @property
    def tier(self) -> int:
        """How many tiers of ``Fury.TIERS`` the gauge has reached."""
        return sum(1 for level, _ in FurySettings.TIERS if self.amount >= level)

    @property
    def speed(self) -> float:
        """The slash speed of the tier reached; 1.0 below the first."""
        speed = 1.0
        for level, step in FurySettings.TIERS:
            if self.amount >= level:
                speed = step
        return speed

    def gain(self, amount: float) -> None:
        if self.in_dark or amount <= 0.0:
            return
        self.amount = min(FurySettings.MAX, self.amount + amount)
        self.decay_delay = FurySettings.DECAY_DELAY

    def lose(self, amount: float) -> None:
        if self.in_dark or amount <= 0.0:
            return
        self.amount = max(0.0, self.amount - amount)

    def start_dark(self) -> bool:
        """Spend a full gauge on the dark side; False if not full or already in it."""
        if self.in_dark or not self.is_full:
            return False
        self.dark_timer = FurySettings.DARK_DURATION
        return True

    def update(self, delta_time: float) -> None:
        if self.in_dark:
            self.dark_timer = max(0.0, self.dark_timer - delta_time)
            self.amount = FurySettings.MAX * self.dark_timer / FurySettings.DARK_DURATION
            return
        if self.decay_delay > 0.0:
            self.decay_delay = max(0.0, self.decay_delay - delta_time)
            return
        self.amount = max(0.0, self.amount - FurySettings.DECAY_PER_S * delta_time)

    def reset(self) -> None:
        self.amount = 0.0
        self.decay_delay = 0.0
        self.dark_timer = 0.0

    def save_state(self) -> FurySnapshot:
        return FurySnapshot(self.amount, self.decay_delay, self.dark_timer)

    def load_state(self, snapshot: FurySnapshot) -> None:
        self.amount = snapshot.amount
        self.decay_delay = snapshot.decay_delay
        self.dark_timer = snapshot.dark_timer


# -- slot machine --------------------------------------------------------------


class Power(StrEnum):
    """What three of a kind on the slot machine grants."""

    STASIS = "stasis"
    """The world slows; every blow kills."""
    BLITZ = "blitz"
    """The player runs and slashes faster; every blow kills."""
    CLEAVE = "cleave"
    """Slashes hit ``Slot.CLEAVE_MULT`` times harder."""


#: The reels' symbols: the three powers, then two that pay nothing.
SYMBOLS: tuple[str, ...] = (*(power.value for power in Power), "bell", "cherry")


@dataclass(frozen=True)
class SlotSnapshot:
    reels: tuple[int, int, int] | None
    spin_timer: float
    show_timer: float
    power: str | None
    power_timer: float


class SlotMachine:
    """Spun by every death blow; three of a kind grants a power for a while.

    The reels are drawn when the spin starts, from the player's own random
    stream, so a rollback replays the same draw; they are only *shown* turning
    until ``Slot.SPIN_TIME`` has run.
    """

    def __init__(self) -> None:
        self.reels: tuple[int, int, int] | None = None
        self.spin_timer: float = 0.0
        self.show_timer: float = 0.0
        self.power: Power | None = None
        self.power_timer: float = 0.0

    @property
    def spinning(self) -> bool:
        return self.spin_timer > 0.0

    def active(self, power: Power) -> bool:
        return self.power is power and self.power_timer > 0.0

    def spin(self, rng: random.Random) -> bool:
        """Start a spin; False while one is already turning."""
        if self.spinning:
            return False
        if rng.random() < SlotSettings.JACKPOT_CHANCE:
            symbol = rng.randrange(len(Power))
            self.reels = (symbol, symbol, symbol)
        else:
            reels = (rng.randrange(len(SYMBOLS)), rng.randrange(len(SYMBOLS)), 0)
            last = rng.randrange(len(SYMBOLS) - 1)
            # Never three of a kind outside the jackpot draw.
            if reels[0] == reels[1] and last >= reels[0]:
                last += 1
            self.reels = (reels[0], reels[1], last)
        self.spin_timer = SlotSettings.SPIN_TIME
        self.show_timer = 0.0
        return True

    def update(self, delta_time: float) -> Power | None:
        """Advance the spin and the power; the power granted on the tick a spin stops."""
        granted: Power | None = None
        if self.power_timer > 0.0:
            self.power_timer = max(0.0, self.power_timer - delta_time)
            if self.power_timer == 0.0:
                self.power = None
        if self.show_timer > 0.0:
            self.show_timer = max(0.0, self.show_timer - delta_time)
        if self.spin_timer > 0.0:
            self.spin_timer = max(0.0, self.spin_timer - delta_time)
            if self.spin_timer == 0.0:
                granted = self._stop()
        return granted

    def _stop(self) -> Power | None:
        self.show_timer = SlotSettings.SHOW_TIME
        reels = self.reels
        if reels is None or len(set(reels)) != 1 or reels[0] >= len(Power):
            return None
        self.power = list(Power)[reels[0]]
        self.power_timer = SlotSettings.POWER_DURATION
        return self.power

    def reset(self) -> None:
        self.reels = None
        self.spin_timer = 0.0
        self.show_timer = 0.0
        self.power = None
        self.power_timer = 0.0

    def save_state(self) -> SlotSnapshot:
        return SlotSnapshot(
            self.reels,
            self.spin_timer,
            self.show_timer,
            None if self.power is None else self.power.value,
            self.power_timer,
        )

    def load_state(self, snapshot: SlotSnapshot) -> None:
        self.reels = snapshot.reels
        self.spin_timer = snapshot.spin_timer
        self.show_timer = snapshot.show_timer
        self.power = None if snapshot.power is None else Power(snapshot.power)
        self.power_timer = snapshot.power_timer


# -- prompts -------------------------------------------------------------------


class PromptKind(StrEnum):
    """What a prompt is for: the death blow, a throw, or a blade lock."""

    DEATH_BLOW = "death_blow"
    THROW = "throw"
    CLASH = "clash"


class Direction(StrEnum):
    """A direction the player is asked for, as the screen shows it."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class PromptOutcome(StrEnum):
    SUCCESS = "success"
    FAIL = "fail"


@dataclass(frozen=True)
class PromptSnapshot:
    kind: str | None
    target_id: str
    steps: tuple[str, ...]
    step: int
    timer: float
    presses: int


class PromptController:
    """The prompt in progress: the directions still to give, or the presses to mash.

    The fight around it runs slowed (:attr:`time_scale`) and the player stands
    still; the timer counts the player's own clock. A wrong direction, or a
    timer that runs out, fails it.
    """

    def __init__(self) -> None:
        self.kind: PromptKind | None = None
        self.target_id: str = ""
        self.steps: tuple[Direction, ...] = ()
        self.step: int = 0
        self.timer: float = 0.0
        self.presses: int = 0

    @property
    def active(self) -> bool:
        return self.kind is not None

    @property
    def expected(self) -> Direction | None:
        """The direction asked for now, or ``None`` during a blade lock."""
        if self.kind is None or self.kind is PromptKind.CLASH or self.step >= len(self.steps):
            return None
        return self.steps[self.step]

    @property
    def window(self) -> float:
        """The length of the current timer, for its gauge on screen."""
        if self.kind is PromptKind.DEATH_BLOW:
            return FinisherSettings.WINDOW
        if self.kind is PromptKind.THROW:
            return ThrowSettings.STEP_WINDOW
        return ClashSettings.WINDOW

    @property
    def time_scale(self) -> float:
        """The clock of the world while the prompt is up; 1.0 without one."""
        if self.kind is PromptKind.DEATH_BLOW:
            return FinisherSettings.TIME_SCALE
        if self.kind is PromptKind.THROW:
            return ThrowSettings.TIME_SCALE
        if self.kind is PromptKind.CLASH:
            return ClashSettings.TIME_SCALE
        return 1.0

    def open(self, kind: PromptKind, target_id: str, rng: random.Random) -> None:
        self.kind = kind
        self.target_id = target_id
        self.step = 0
        self.presses = 0
        directions = tuple(Direction)
        if kind is PromptKind.DEATH_BLOW:
            self.steps = (directions[rng.randrange(len(directions))],)
        elif kind is PromptKind.THROW:
            self.steps = tuple(
                directions[rng.randrange(len(directions))] for _ in range(ThrowSettings.STEPS)
            )
        else:
            self.steps = ()
        self.timer = self.window

    def give(self, direction: Direction) -> PromptOutcome | None:
        """A direction given: the outcome if it settles the prompt."""
        expected = self.expected
        if expected is None:
            return None
        if direction is not expected:
            return self._close(PromptOutcome.FAIL)
        self.step += 1
        if self.step >= len(self.steps):
            return self._close(PromptOutcome.SUCCESS)
        self.timer = self.window
        return None

    def press(self) -> PromptOutcome | None:
        """A slash pressed during a blade lock: the outcome if it wins it."""
        if self.kind is not PromptKind.CLASH:
            return None
        self.presses += 1
        if self.presses >= ClashSettings.PRESSES:
            return self._close(PromptOutcome.SUCCESS)
        return None

    def update(self, delta_time: float) -> PromptOutcome | None:
        if self.kind is None:
            return None
        self.timer -= delta_time
        if self.timer <= 0.0:
            return self._close(PromptOutcome.FAIL)
        return None

    def _close(self, outcome: PromptOutcome) -> PromptOutcome:
        self.kind = None
        self.steps = ()
        self.timer = 0.0
        return outcome

    def reset(self) -> None:
        self.kind = None
        self.target_id = ""
        self.steps = ()
        self.step = 0
        self.timer = 0.0
        self.presses = 0

    def save_state(self) -> PromptSnapshot:
        return PromptSnapshot(
            None if self.kind is None else self.kind.value,
            self.target_id,
            tuple(step.value for step in self.steps),
            self.step,
            self.timer,
            self.presses,
        )

    def load_state(self, snapshot: PromptSnapshot) -> None:
        self.kind = None if snapshot.kind is None else PromptKind(snapshot.kind)
        self.target_id = snapshot.target_id
        self.steps = tuple(Direction(step) for step in snapshot.steps)
        self.step = snapshot.step
        self.timer = snapshot.timer
        self.presses = snapshot.presses
