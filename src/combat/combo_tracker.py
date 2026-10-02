"""
Combo counter and window tracking.

A combo increments when an attack *lands*, not when it is thrown: the counter is
armed by an attack starting and only spent by a confirmed hit, so swinging at
thin air costs nothing. The counter resets when the window expires, enabling the
UI and other systems to react to combo chains.
"""


class ComboTracker:
    """Tracks the combo counter and combo window timer.

    The counter has two halves, deliberately kept apart: an attack starting
    *arms* it, and the first confirmed hit *spends* the arming by incrementing.
    Nothing observable happens in between, which is what stops a whiffed swing
    from inflating a combo the player never landed.

    Parameters
    ----------
    window_duration : float
        Duration in seconds during which a subsequent attack continues
        the combo chain.  If the window expires, the counter resets.

    Attributes
    ----------
    count : int
        Current number of consecutive landed hits in the combo.  0 when idle.
    air_count : int
        Hits landed on an airborne victim in the current window (Phase 5 #4).
    """

    def __init__(self, window_duration: float) -> None:
        self._window_duration: float = window_duration
        self.count: int = 0
        self.air_count: int = 0
        self._timer: float = 0.0
        self._armed: bool = False

    @property
    def is_armed(self) -> bool:
        """Whether an attack is waiting to be confirmed into the counter.

        True between the first startup frame of an attack and either its first
        hit or its recovery, so a whiffed swing is spent without counting.
        """
        return self._armed

    @property
    def timer(self) -> float:
        """Remaining combo window, exposed for deterministic snapshots."""
        return self._timer

    def restore(
        self,
        count: int,
        timer: float,
        air_count: int = 0,
        armed: bool = False,
    ) -> None:
        """Restore deterministic combo state from a validated snapshot."""
        self.count = max(0, count)
        self._timer = max(0.0, timer)
        self.air_count = max(0, air_count)
        self._armed = bool(armed)

    def on_attack_started(self, resets_combo: bool) -> None:
        """Notify the tracker that a new attack has been started.

        Starting an attack does not touch the counter: it only arms it, and the
        increment is spent by the first confirmed hit in :meth:`on_hit_landed`.
        An attack that resets the combo drops the count first, so the next hit
        opens a fresh chain at 1.

        Parameters
        ----------
        resets_combo : bool
            Whether this attack resets the combo counter.
        """
        if resets_combo:
            self.count = 0
            self._timer = 0.0
        self._armed = True

    def disarm(self) -> None:
        """Spend an arming without counting, as an unreached attack ends.

        Called when the attack stops being live without having landed: the
        player swung, nothing connected, and the next hit must belong to the
        next attack rather than retroactively completing this one.
        """
        self._armed = False

    def reset(self) -> None:
        """Drop the combo entirely, keeping no window and no arming."""
        self.count = 0
        self._timer = 0.0
        self._armed = False

    def update(self, delta_time: float) -> None:
        """Tick the combo window timer.

        When the timer reaches zero the combo counter is reset.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds.
        """
        if self._timer > 0:
            self._timer -= delta_time
            if self._timer <= 0.0:
                self._timer = 0.0
                self.count = 0
                self.air_count = 0
                # The arming is deliberately left alone here. An expiry means
                # the chain lapsed, not that the swing in flight never landed:
                # a hit arriving on the active frame after the window closed
                # must still open a fresh chain at 1 rather than count for
                # nothing. Dropping a stale arming is the attack-end
                # disarming's job, which is driven off the attack actually being
                # live rather than off the clock.

    def on_hit_landed(self, airborne: bool) -> None:
        """Record a connected hit, counting air juggles separately (Phase 5 #4).

        This is the only site that increments the combo counter. A hit that no
        armed attack vouches for -- contact damage, a projectile drifting into
        someone -- still tallies the air juggle but leaves the counter alone, so
        the combo stays a count of attacks that actually reached something.
        """
        if airborne:
            self.air_count += 1
        if not self._armed:
            return
        self._armed = False
        self.count = self.count + 1 if self._timer > 0 else 1
        self._timer = self._window_duration
