"""Why an attack was refused, as a value instead of a shrug.

``start_attack`` used to answer ``bool``, and all four of its callers threw the
answer away. That is fine for a press that either happens or does not, and wrong
for a press that can be retried: an attack refused on cooldown should be buffered
and thrown the moment it comes off, while one refused because the fighter is in
the wrong posture should be forgotten, and one refused because the fighter was
hit should be forgotten too. A ``bool`` cannot tell those three apart, which is
most of why the input buffer misbehaves.

The enum exists so the decision is a value the caller can act on. It is not a
refusal *log* -- nothing consumes it for diagnostics yet -- it is the answer to
"and now what", which the boolean could not give.
"""

from enum import Enum


class Refusal(Enum):
    """Why an attack was not started.

    The split that matters is retryable versus not. ``COOLDOWN`` and
    ``NO_CANCEL`` are worth retrying: in both, the same press, unchanged, would
    succeed once a timer runs down or the running attack reaches its cancel
    window. Everything else describes a situation the fighter has to *change*
    -- a different posture, a different state -- or one where the request was
    simply not a real attack request.
    """

    NONE = "none"
    """The attack started. Not a refusal; the success case."""

    COOLDOWN = "cooldown"
    """This move is still on cooldown.

    Retryable, like ``NO_CANCEL``. The press is worth keeping: throw it again
    once the timer runs down and it lands.
    """

    STANCE = "stance"
    """The fighter is not in a posture this move is thrown from.

    Not retryable as-is. It becomes possible again only if the fighter moves to
    one of the move's stances, which is a decision rather than a delay -- so a
    buffered press must not survive the fighter standing up.
    """

    UNKNOWN = "unknown"
    """No such move is registered.

    A data error rather than a gameplay one: the move was asked for by name and
    the table does not carry it. A designer sees this; a player never should.
    """

    BUSY = "busy"
    """The fighter is hurt, knocked back, staggered or dizzy.

    Not retryable: the fighter has to recover, and by then the intent behind the
    press is gone.
    """

    CHARGING = "charging"
    """A charge is in progress. Releasing it is how this press is answered."""

    NO_CANCEL = "no_cancel"
    """An attack is running and this move cannot cancel out of it.

    Retryable: the same press succeeds once the running attack reaches its
    cancel window, which is the case the buffer exists for -- a chain input
    made before that window opens. Kept distinct from the other retryable
    member so the caller can still tell a timer from a cancel window.
    """

    def __bool__(self) -> bool:
        """Whether the attack started.

        Truthy on success, so every existing ``if
        player.combat.start_attack(x):`` and ``assert
        combat.start_attack(x)`` site keeps meaning what it meant when this
        returned ``bool``. That is what lets the enum be introduced without
        rewriting forty-odd call sites at once; the sites that need to know *why*
        can compare against a member instead.
        """
        return self is Refusal.NONE

    @property
    def is_retryable(self) -> bool:
        """Whether the same press, unchanged, could succeed later.

        A move on cooldown will be ready; a move refused because the running
        one cannot be cancelled yet will be, once its cancel window opens --
        that is how a press made during one link of a chain becomes the next.
        """
        return self in (Refusal.COOLDOWN, Refusal.NO_CANCEL)
