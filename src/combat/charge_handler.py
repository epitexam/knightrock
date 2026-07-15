"""
Charge attack mechanics.

When an attack is marked as chargeable, the player can hold the attack
button to build up charge, increasing the damage multiplier up to 2×
at maximum charge time.
"""

from __future__ import annotations

from src.combat.frame_data import AttackDefinition


class ChargeHandler:
    """Manages the charging state for chargeable attacks.

    Parameters
    ----------
    attacks : dict[str, AttackDefinition]
        Shared reference to the attack registry (same instance as the
        one owned by ``CombatComponent``).

    Attributes
    ----------
    is_charging : bool
        Whether a charge is currently in progress.
    charge_timer : float
        Seconds elapsed since the charge started.
    """

    def __init__(self, attacks: dict[str, AttackDefinition]) -> None:
        self._attacks: dict[str, AttackDefinition] = attacks
        self.is_charging: bool = False
        self.charge_timer: float = 0.0
        self._attack_name: str | None = None

    @property
    def attack_name(self) -> str | None:
        """Name of the attack currently being charged, or ``None``."""
        return self._attack_name

    def start_charge(self, name: str) -> bool:
        """Begin charging an attack.

        Parameters
        ----------
        name : str
            Name of the attack to charge.

        Returns
        -------
        bool
            ``True`` if the charge started successfully; ``False`` if
            already charging, the attack doesn't exist, or it isn't
            chargeable.
        """
        if self.is_charging:
            return False
        if name not in self._attacks:
            return False
        if not self._attacks[name].chargeable:
            return False

        self.is_charging = True
        self.charge_timer = 0.0
        self._attack_name = name
        return True

    def update(self, delta_time: float) -> None:
        """Advance the charge timer up to the attack's max charge time.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds.
        """
        if not self.is_charging or self._attack_name is None:
            return
        max_time = self._attacks[self._attack_name].max_charge_time
        self.charge_timer = min(self.charge_timer + delta_time, max_time)

    def release_charge(self) -> tuple[str, float] | None:
        """Release the charge and return the attack name and multiplier.

        The damage multiplier scales linearly from 1.0 (no charge) to
        2.0 (full charge at ``max_charge_time``).

        Returns
        -------
        tuple[str, float] | None
            A ``(attack_name, multiplier)`` tuple, or ``None`` if not
            currently charging.
        """
        if not self.is_charging or self._attack_name is None:
            return None

        name = self._attack_name
        max_time = max(self._attacks[name].max_charge_time, 0.001)
        multiplier = 1.0 + (self.charge_timer / max_time)

        self._reset()
        return (name, multiplier)

    def cancel(self) -> None:
        """Cancel the current charge without releasing (e.g. on hit-stun)."""
        self._reset()

    def _reset(self) -> None:
        """Reset all charging state."""
        self.is_charging = False
        self.charge_timer = 0.0
        self._attack_name = None