"""
Combo counter and window tracking.

A combo increments when attacks are executed within the combo window.
The counter resets when the window expires, enabling the UI and other
systems to react to combo chains.
"""


class ComboTracker:
    """Tracks the combo counter and combo window timer.

    Parameters
    ----------
    window_duration : float
        Duration in seconds during which a subsequent attack continues
        the combo chain.  If the window expires, the counter resets.

    Attributes
    ----------
    count : int
        Current number of consecutive hits in the combo.  0 when idle.
    """

    def __init__(self, window_duration: float) -> None:
        self._window_duration: float = window_duration
        self.count: int = 0
        self._timer: float = 0.0

    @property
    def is_active(self) -> bool:
        """Whether a combo is currently in progress (timer > 0)."""
        return self._timer > 0

    def on_attack_started(self, resets_combo: bool) -> None:
        """Notify the tracker that a new attack has been started.

        If the attack resets the combo, the counter is zeroed.
        Otherwise, the counter increments (or starts at 1 if the window
        had expired) and the window timer is refreshed.

        Parameters
        ----------
        resets_combo : bool
            Whether this attack resets the combo counter.
        """
        if resets_combo:
            self.count = 0
            self._timer = 0.0
        else:
            if self._timer > 0:
                self.count += 1
            else:
                self.count = 1
            self._timer = self._window_duration

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