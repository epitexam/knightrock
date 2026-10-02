"""The ground pivot: shared by every fighter's state machine.

The pivot is a **state**, and that is the whole design. A delay is a value that
has to be undone by everyone who can interrupt the thing holding it -- an
attack, a dash, a guard, a hit -- and each of those has to know the rule exists
and to call something to release it. A state is the machine's own answer: it is
entered and exited, so anything that interrupts it leaves through
:meth:`TurnState.exit`, which is where the facing is finally committed. "An
attack pressed inside the pivot still comes out the way the fighter is
pointing" is not a special case anyone has to remember; it is what exiting the
state means.

That is also why this lives in its own module rather than in one fighter's
states. The hold is identical for all of them -- arm it, keep the fighter
moving, hold the mirror, apply it on the way out -- and only two things differ:
where the fighter goes when the hold ends, and how it is asked for the pivot in
the first place. Both are the subclass's job. What is shared is the part that
has to be *right*, because getting the commit wrong means a fighter attacking
the wrong way and nothing else would notice.

**Why enemies needed a state of their own to take this.** The player freezes
its mirror with a tag, because the player's input is read outside the state
machine and would otherwise re-mirror every tick. An enemy does not have that
problem, and for the opposite reason: it sets its facing *inside* its own
state, from the axis it just chose. In ``EnemyTurnState`` no such code runs, so
nothing writes the facing at all and it stays where the pivot left it. The tag
is still set, because it costs nothing and because a subclass that starts
writing the facing from outside would silently need it.
"""

from typing import Any

from src.core.settings import Locomotion, Turn
from src.states.state_machine import State

#: The tag that stops a state from re-writing the fighter's facing.
#:
#: Named rather than a boolean on the entity because it is a property of the
#: state the fighter is in, and the state machine already answers "which is
#: this" through tags (``busy``, ``invincible``, ``attack``). A caller holding
#: either machine asks one question and needs to know nothing about the fighter's
#: states or their names.
FACING_LOCKED = "facing_locked"


def request_turn(entity: Any) -> bool:
    """Enter this fighter's pivot state if its axis is a ground reversal.

    Asked from wherever the fighter decides its ``move_axis``, in place of
    writing the facing, and it has to be there rather than inside a state's
    ``update`` for a reason the loop's order decides. The player reads input in
    ``_pre_update``, which runs **before** the state machine; any decision taken
    from a state's own ``update`` would be one frame too late to stop the
    mirror, because by then the facing has already been written and the sprite
    already drawn that way. An enemy sets its axis inside its state and has the
    same constraint one step later.

    Four ways to say no, each a different reason rather than a fallback:

    * the fighter has not opted in (``turn_enabled``) or its delay is 0;
    * there is no input to turn towards -- the deadzone, so releasing the stick
      does not count as a reversal;
    * the fighter is not on the floor, so this is a jump turn and the arc
      already reads it;
    * there is no speed behind it. ``turn_min_speed_px_s`` is the floor, and a
      fighter shuffling under a raised guard is above it.

    The last two are what make this a pivot rather than a slow response to a
    tap, and the speed one is why a fighter who lets go and immediately presses
    the other way from a standstill turns instantly: there is nothing to throw
    around yet.
    """
    if not entity.turn_enabled or entity.turn_delay_s <= 0.0:
        return False
    axis = float(entity.move_axis)
    if abs(axis) <= Locomotion.TURN_DEADZONE:
        return False
    if not entity.on_surface["floor"]:
        return False
    if abs(entity.velocity.x) < entity.turn_min_speed_px_s:
        return False
    target = axis > 0.0
    if target == entity.facing_right:
        return False
    entity.state_machine.change_state(Turn.STATE, target=target)
    # Asked, then confirmed. A fighter whose machine has no pivot registered --
    # one with no AI at all, whose ``state_machine`` is the null machine -- has
    # a ``change_state`` that silently does nothing, and reporting "entered"
    # there would tell the caller a hold is running when no state is. Reading
    # the machine back is the only honest answer, and it costs one comparison.
    return bool(entity.state_machine.current_state_name == Turn.STATE)


class TurnState(State):
    """A fighter mid-pivot: feet turned, head still catching up.

    It is a locomotion state in every other respect. The fighter keeps its
    momentum -- ``apply_horizontal_movement`` runs every tick, which is the
    point, since the velocity is bleeding to a plant while the facing still
    points the other way.

    Subclasses must implement :meth:`resume_state`, which answers the only
    question this class cannot: where does this fighter go when the hold ends.
    For the player that is a locomotion tier, and it has to be the tier the pivot
    interrupted rather than the live one -- the hold spans the frames where the
    velocity sweeps through every tier, and resuming from ``turn`` would drop
    the hysteresis and flicker the boundaries at the fastest moment. For an
    enemy it is a decision about the player, not about speed.
    """

    def __init__(self, entity: Any, tags: list[str] | None = None):
        super().__init__(entity, [*(tags or []), FACING_LOCKED])
        #: The facing held for the duration, restored if the pivot is dropped.
        self.held: bool = True
        #: The facing to commit on a completed pivot.
        self.target: bool = True
        #: Remaining hold, in seconds.
        self.timer: float = 0.0
        #: Whatever :meth:`resume_state` needs to return, captured on entry.
        self.resume: str = ""
        #: Whether leaving should apply ``target``.
        self.commit: bool = True

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Arm the hold from the requested direction and freeze the mirror."""
        self.resume = previous or ""
        self.target = bool(kwargs.get("target", self.entity.facing_right))
        self.held = self.entity.facing_right
        self.timer = self.entity.turn_delay_s
        self.commit = True
        self.entity.turn_ratio = 1.0

    def exit(self, next_state: str | None = None) -> None:
        """Release the mirror, applying the pivot unless it was abandoned.

        Every exit goes through here -- an attack, a dash, a jump, and the
        ordinary return to locomotion alike -- so this is the single place the
        facing catches up. Clearing the render hint belongs here too, or the
        sprite would stay leaned for as long as it took the next state to
        overwrite it.
        """
        if self.commit:
            self.entity.facing_right = self.target
        self.entity.turn_ratio = 0.0

    def update(self, delta_time: float) -> str | None:
        """Keep rolling, hold the facing, and hand back to the fighter's own
        states when the hold is over."""
        leave = self._before_move(delta_time)
        if leave is not None:
            return leave

        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.on_surface["floor"]:
            return self._lost_the_ground()

        if self._pointed_back():
            self.commit = False
            return self.resume_state()

        self.timer -= delta_time
        # Published as a ratio rather than recomputed by the renderer from the
        # timer: this is the one place that knows both ends of it.
        delay = self.entity.turn_delay_s
        self.entity.turn_ratio = max(0.0, self.timer / delay) if delay > 0.0 else 0.0
        if self.timer <= 0.0:
            return self.resume_state()
        return None

    def resume_state(self) -> str:
        """Where this fighter goes when the hold ends.

        The one thing the shared body cannot answer, because "back to what" is a
        question about the fighter and not about pivoting.
        """
        raise NotImplementedError

    def _before_move(self, delta_time: float) -> str | None:
        """Whatever this fighter's own states do before the movement step.

        A hook because the answer is not shared: the player can jump out of a
        hold, and an enemy -- which has no air states at all -- cannot, so the
        player's override runs ``handle_jump`` and leaves for ``jump``.
        Returning a state name ends the hold; ``None`` carries on with it.
        """
        return None

    def _lost_the_ground(self) -> str:
        """Where to go when the fighter is no longer on a floor.

        Also not shared. The player has a ``fall`` state to be sent to; an enemy
        has no air states, so dropping the hold is the whole of it and it
        resumes as if the timer had run out.
        """
        return self.resume_state()

    def _pointed_back(self) -> bool:
        """Whether the input went back to the facing being held.

        Pointing *at* ``held``, which is not the same as pointing away from the
        target: during a left pivot the fighter is already holding right, so the
        two are the same direction, and asking for the former is what makes the
        feint work.

        Releasing the stick does **not** cancel. A fighter who lets go mid-pivot
        is coming to a stop, and cancelling would leave him standing still
        facing the direction he was running before he turned -- the
        facing-wrong-at-rest case the pivot is meant to be an improvement on. A
        cancelled pivot still releases through :meth:`exit`; only *which* facing
        it applies differs.
        """
        axis = float(self.entity.move_axis)
        if self.held:
            return axis > Locomotion.TURN_DEADZONE
        return axis < -Locomotion.TURN_DEADZONE
