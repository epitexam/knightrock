"""The air kit: four buttons, four directions, and the impulse that carries you.

The table had one airborne move on one button, so every aerial press did the
same thing and three of the four buttons did nothing at all. ``uppercut`` and
``sky_launcher`` launched enemies and there was no attack that could follow,
because everything else in the game is ground-only.

Two things are asserted here, and they are not the same claim. The *table* is
one move per button and per posture, so the buttons mean four things in the air
the way they already did on the floor. The *impulse* is the mechanic that did not
exist before: an aerial attack can now carry the fighter vertically, which is the
only reason a rising aerial can be the answer to a launcher rather than a poke
that happens to point up.

The impulse is asserted relatively, against an airborne fighter using the move
that has none. Exact equality would be asserting gravity's contribution too,
and gravity is applied later in the same tick, which makes the comparison a
statement about two systems at once. What is checked exactly is the bound --
never stronger than the jump that put the fighter in the air -- because that is
the property the loader refuses to let the data break.
"""

import os

import pygame
import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.frame_data import Stance, move_id
from src.combat.refusal import Refusal
from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState
from src.entities.attack_moves import BUTTON_MOVES, move_for_button
from src.entities.player import Player

TICK = 1 / 60
FLOOR_TOP = 56.0


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


class Solid(pygame.sprite.Sprite):
    """A slab of level geometry, spanning the given vertical band."""

    def __init__(self, top: float, height: float, *, width: float = 2000.0):
        super().__init__()
        self.rect = pygame.FRect(-500.0, top, width, height)
        self.hitbox = self.rect


def _player(input_manager: InputManager | None = None) -> Player:
    """A fighter landed on a real floor, so the harness is not what is measured."""
    collision = pygame.sprite.Group()
    collision.add(Solid(FLOOR_TOP, 400.0))
    manager = input_manager or InputManager()
    player = Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=collision,
        moving_platforms=[],
        input_manager=manager,
    )
    _hold(player, manager, frames=3)
    assert player.on_surface["floor"], "the fixture is not standing on the floor"
    return player


def _hold(player: Player, manager: InputManager, *held: InputAction, frames: int = 1) -> None:
    """Tick the fighter with ``held`` pressed, as a real input frame would.

    The actions are a varargs of :class:`InputAction`, not a ``**kwargs``. The
    kwargs version read as the obvious thing to write -- ``down=True``,
    ``JUMP=True`` -- and put the *string* into the ``frozenset``, which
    ``InputState.__post_init__`` then rejects with "only accepts gameplay
    actions": a message naming a rule the caller never heard of, several frames
    away from the call that broke it. Nothing caught it because no test here
    passed an action to it, so the whole parameter was dead.

    A varargs of the members themselves cannot be misread that way, and the
    signature says what it wants instead of implying it.
    """
    actions = frozenset(held)
    for _ in range(frames):
        manager.apply_remote_state(InputState(held_actions=actions))
        player.update(TICK)
        if player.on_surface["floor"]:
            player.hitbox.bottom = FLOOR_TOP
            player.sync_rects()


def _airborne(player: Player, *, vertical: float = -300.0) -> None:
    """Put the fighter off the floor with the given vertical speed.

    The speed is a parameter because the impulse is a floor rather than a
    replacement, so "already rising faster than the move lifts" is a case with
    its own answer and needs to be asked about from a known speed.
    """
    player.on_surface["floor"] = False
    player.hitbox.bottom = 10.0
    player.sync_rects()
    player.velocity.y = vertical


# --- the table --------------------------------------------------------------


def test_every_aerial_button_throws_something() -> None:
    """Three of the four used to answer ``None`` in the air.

    A missing entry is not an error: it is a refusal the player reads as a dead
    button. Asserting the four exist is the claim that the air is playable at
    all.
    """
    thrown = {
        action: move_for_button(action, Stance.AIR)
        for action in (
            InputAction.ATTACK_1,
            InputAction.ATTACK_2,
            InputAction.ATTACK_3,
            InputAction.ATTACK_4,
        )
    }

    assert all(move is not None for move in thrown.values()), thrown
    assert len(set(thrown.values())) == 4, "two buttons throw the same aerial"


def test_the_aerial_on_each_button_is_the_answer_to_its_grounded_counterpart() -> None:
    """The design claim, stated as a table rather than as a comment.

    ``ATTACK_3`` is the launcher on the floor, so it rises in the air;
    ``ATTACK_2`` is the heavy hit down here, so it falls up there; ``ATTACK_4``
    is the forward reach on the ground, so it reaches forward from the air. Four
    identical aerials would have satisfied the test above and been the missing
    feature replaced by a worse one.
    """
    rises = PLAYER_ATTACKS[move_for_button(InputAction.ATTACK_3, Stance.AIR)]
    dives = PLAYER_ATTACKS[move_for_button(InputAction.ATTACK_2, Stance.AIR)]
    reaches = PLAYER_ATTACKS[move_for_button(InputAction.ATTACK_4, Stance.AIR)]
    neutral = PLAYER_ATTACKS[move_for_button(InputAction.ATTACK_1, Stance.AIR)]

    assert rises.vertical_lunge > 0 > dives.vertical_lunge
    assert rises.phases[0].hitbox_offset[1] < neutral.phases[0].hitbox_offset[1]
    assert dives.phases[0].hitbox_offset[1] > neutral.phases[0].hitbox_offset[1]
    # Forward reach is measured from the sprite, so the aerial's box sits
    # further out than the neutral one's rather than merely being longer.
    assert reaches.phases[0].hitbox_offset[0] > neutral.phases[0].hitbox_offset[0]


def test_the_ground_height_is_kept_unless_the_direction_of_the_move_is_the_point() -> None:
    """The guard height of a grounded counterpart is inherited, with one exception.

    ``air_rise`` shipped as ``"high"`` while the ``uppercut`` it answers was
    ``"mid"``, and that is not a subtlety: ``("high", True)`` is False in
    ``Guard.HEIGHT_BLOCK``, so the aerial rose *hit crouching targets* while the
    grounded launcher could not touch them. Same button, same gesture, opposite
    answer to the same defensive input -- and nothing in the suite noticed,
    because every other parallel between the two columns was checked and this one
    was not.

    ``air_sweep`` is the exception, and it is an exception rather than an
    oversight: a dive descends onto a crouched target, so ``"overhead"`` is the
    height that makes it land. Asserting a blanket rule would have thrown that
    away; asserting nothing let ``air_rise`` drift. So the rule is the rule plus
    the one name it does not apply to, which is a statement that can be read and
    has to be changed on purpose.
    """
    grounded_height = {
        action: PLAYER_ATTACKS[moves[Stance.GROUND]].phases[0].hit.height
        for action, moves in BUTTON_MOVES.items()
        if Stance.GROUND in moves
    }

    diverging = {
        action.value: PLAYER_ATTACKS[moves[Stance.AIR]].phases[0].hit.height
        for action, moves in BUTTON_MOVES.items()
        if Stance.GROUND in moves
        and Stance.AIR in moves
        and PLAYER_ATTACKS[moves[Stance.AIR]].phases[0].hit.height != grounded_height[action]
    }

    assert diverging == {InputAction.ATTACK_2.value: "overhead"}


@pytest.mark.parametrize("height", ["mid", "low", "high", "overhead"])
def test_only_two_of_the_four_heights_reach_a_crouching_target(height: str) -> None:
    """Why ``overhead`` is load-bearing for the dive, read off the table.

    A dive whose height let a crouching target block it would not punish one,
    and the reason it is ``"overhead"`` rather than ``"low"`` is that
    ``("low", True)`` is True in ``Guard.HEIGHT_BLOCK`` -- ``low`` is blocked by
    crouching and *not* by standing, which is the opposite of what a descending
    attack wants. Exactly two of the four heights get past a crouching guard, so
    the choice was between them and not a matter of taste.

    Read from ``Guard`` rather than restated, so a change to that table is
    caught here instead of silently turning the dive into a move a crouching
    fighter blocks on sight.
    """
    from src.core.settings import Guard as GuardSettings

    reaches_crouching = not GuardSettings.HEIGHT_BLOCK.get((height, True), True)

    assert reaches_crouching is (height in ("high", "overhead"))


def test_an_aerial_move_is_refused_on_the_floor_and_the_neutral_one_in_the_air() -> None:
    """Both directions of the gate, on real entities.

    The stance check is the only thing keeping ``air_rise`` from being a free
    extra launcher on the ground, and ``air_attack`` is the one move that exists
    in both readings of the table -- so it is also the one that would hide a
    missing refusal.
    """
    manager = InputManager()
    player = _player(manager)

    assert player.combat.start_attack(move_id("air_rise")) is Refusal.STANCE
    assert player.combat.start_attack(move_id("air_sweep")) is Refusal.STANCE
    assert player.combat.start_attack(move_id("air_attack")) is Refusal.STANCE

    manager = InputManager()
    player = _player(manager)
    _airborne(player)

    for name in ("air_attack", "air_forward", "air_rise", "air_sweep"):
        assert player.combat.has_attack(name), f"{name} was never registered"

    # A fresh fighter per move: starting one on top of another is refused as
    # ``NO_CANCEL``, which would make four attempts report the same thing about
    # a move that was never even reached.
    for name in ("air_attack", "air_forward", "air_rise", "air_sweep"):
        airborne = _player()
        _airborne(airborne)
        assert airborne.combat.start_attack(move_id(name)) is Refusal.NONE, name


def test_the_special_is_still_ground_only() -> None:
    """The one button with no aerial, and deliberately.

    110 frames of commitment is a ground decision. Giving it an aerial would be
    a balance change nobody asked for.
    """
    assert move_for_button(InputAction.SPECIAL_ATTACK, Stance.AIR) is None


# --- the impulse ------------------------------------------------------------


def test_a_rising_aerial_lifts_the_fighter_and_a_neutral_one_does_not() -> None:
    """The mechanic that did not exist, observed against the move that has none.

    The fighter is released falling slowly here so the move has something to
    improve on: a rise is a floor on momentum, so a fighter already rising faster
    than the move lifts is deliberately left alone -- which is the next test.
    """
    manager = InputManager()
    rising = _player(manager)
    _airborne(rising, vertical=-40.0)
    rising.combat.start_attack(move_id("air_rise"))
    _hold(rising, manager, frames=1)

    manager = InputManager()
    neutral = _player(manager)
    _airborne(neutral, vertical=-40.0)
    neutral.combat.start_attack(move_id("air_attack"))
    _hold(neutral, manager, frames=1)

    assert rising.velocity.y < neutral.velocity.y, "the rising aerial did not rise"


def test_a_rising_aerial_never_slows_a_jump_that_already_carries_higher() -> None:
    """The one that matters, and the reason the impulse is a floor not a
    replacement.

    ``vertical_lunge`` is 0.62 jump heights. Pressing the move a frame after a
    full jump must not rewrite ``-750`` into ``-465``: an attack that made the
    fighter rise more slowly than the jump that put them in the air would mean
    the follow-up was the wrong button to press, and it would do so silently --
    the move still hits, just later and lower than it should.
    """
    manager = InputManager()
    player = _player(manager)
    jump_height = player.jump_height
    _airborne(player, vertical=-jump_height)
    player.combat.start_attack(move_id("air_rise"))
    _hold(player, manager, frames=1)

    gravity = 1500.0 * TICK
    assert player.velocity.y == pytest.approx(-jump_height + gravity, rel=1e-2)


def test_a_dive_does_not_catch_a_fighter_already_falling_faster_than_it() -> None:
    """The same floor on the other sign.

    A dive pushes downward. A fighter already plummeting is going down faster
    than the move would send them, and slowing them to match it would be the
    dive cancelling the thing the dive is for.
    """
    manager = InputManager()
    player = _player(manager)
    dive = PLAYER_ATTACKS["air_sweep"].vertical_lunge
    plummet = -player.jump_height * dive * 3.0
    _airborne(player, vertical=plummet)
    player.combat.start_attack(move_id("air_sweep"))
    _hold(player, manager, frames=1)

    assert player.velocity.y > plummet, "the dive slowed a faster fall"


def test_a_descending_aerial_pushes_the_fighter_down() -> None:
    """The sign is shared, so a dive is a negative lunge rather than a second rule.

    Getting this wrong is not a subtle balance point: it is a move called a dive
    that throws the fighter upward, and nothing else in the data would say so.
    """
    manager = InputManager()
    diving = _player(manager)
    _airborne(diving, vertical=-40.0)
    diving.combat.start_attack(move_id("air_sweep"))
    _hold(diving, manager, frames=1)

    manager = InputManager()
    neutral = _player(manager)
    _airborne(neutral, vertical=-40.0)
    neutral.combat.start_attack(move_id("air_attack"))
    _hold(neutral, manager, frames=1)

    assert diving.velocity.y > neutral.velocity.y, "the dive went the wrong way"


def test_a_rising_aerial_still_leaves_the_fighter_going_up() -> None:
    """The observable half of the bound: after one tick, still rising.

    The exact half is a property of the table rather than of one tick, and is
    checked below over every move. Gravity is applied after the impulse in the
    same tick, so the speed observed here is the impulse *plus* one tick of
    falling -- the reason the comparison is a direction and not a number.
    """
    manager = InputManager()
    player = _player(manager)

    _airborne(player, vertical=0.0)
    player.combat.start_attack(move_id("air_rise"))
    _hold(player, manager, frames=1)

    assert player.velocity.y < 0.0, "the rising aerial left the fighter falling"


def test_no_aerial_out_lifts_the_fighter_harder_than_a_jump() -> None:
    """The bound as a property of the whole table, which is where it can break.

    ``vertical_lunge`` is a multiple of jump height, so 1.0 *is* a jump. A move
    above that makes the jump optional and the attack mandatory, which inverts
    what the jump is for. The loader refuses such a value; asserting it here as
    well means the refusal and the shipped data are checked against each other,
    so a future bound change cannot quietly invalidate a move.
    """
    jump_height = _player().jump_height

    offenders = {
        name: attack.vertical_lunge
        for name, attack in PLAYER_ATTACKS.items()
        if abs(attack.vertical_lunge) * jump_height > jump_height
    }

    assert offenders == {}
    assert max((abs(a.vertical_lunge) for a in PLAYER_ATTACKS.values()), default=0.0) <= 1.0


def test_a_neutral_aerial_leaves_the_arc_alone() -> None:
    """``vertical_lunge = 0`` must mean "no impulse", not "a small one".

    Worth its own test because the field is read on the same airborne branch as
    the ones that do move, and a default that nudged the arc would be invisible
    in play and would compound across a juggle.
    """
    manager = InputManager()
    plain = _player(manager)
    _airborne(plain, vertical=-300.0)
    plain.combat.start_attack(move_id("air_attack"))
    _hold(plain, manager, frames=1)

    manager = InputManager()
    bare = _player(manager)
    _airborne(bare, vertical=-300.0)
    _hold(bare, manager, frames=1)

    assert plain.velocity.y == pytest.approx(bare.velocity.y, rel=1e-6), (
        "the neutral aerial moved the arc at all"
    )
    assert plain.velocity.y < 0.0, "the fixture is not rising, so it proves nothing"


def test_an_impulse_needs_an_attack_to_come_from() -> None:
    """The field is read off the live definition, so an idle fighter is untouched.

    Without this the impulse could be read from a finished attack and applied to
    whatever state the fighter fell into -- the hazard of reading it eagerly at
    construction rather than at the transition.
    """
    manager = InputManager()
    player = _player(manager)
    _airborne(player, vertical=-300.0)
    before = player.velocity.y

    _hold(player, manager, frames=3)

    assert player.velocity.y == pytest.approx(before + 1500.0 * TICK * 3, rel=1e-2)


def test_the_impulse_does_not_fire_from_the_ground() -> None:
    """The airborne branch is where it lives, and the floor is not that branch.

    A fighter who walks into ``air_rise`` -- as opposed to being refused by the
    stance gate -- would be thrown upward by a move whose whole premise is that
    the fighter is above the ground.
    """
    manager = InputManager()
    player = _player(manager)
    player.on_surface["floor"] = True
    rest = player.velocity.y

    _hold(player, manager, frames=2)

    assert player.velocity.y >= rest
    assert not player.combat.is_attacking, "a ground-only move ran from the floor"


def test_only_the_designated_move_pokes_a_downed_enemy() -> None:
    """OTG is scarce by construction, and the dive was quietly making it common.

    A hurt enemy that lands is invulnerable for ``OTG_INVULN_DURATION`` (0.5s)
    to every move without ``otg_allowed`` -- so the flag is what a knockdown buys
    you, and one move owning it is what makes that window worth planning around.
    ``otg_slam`` owns it and pays for it: 1.2s of cooldown and a walk across the
    room to the downed enemy.

    The dive cost 0.6s and no positioning at all, since being airborne above
    someone who just fell is exactly the situation it is thrown in. That is a
    two-times-more-available OTG for free, which erodes the scarcity without
    anyone having decided to erode it. So the dive keeps the identity that does
    not need the flag -- ``height: "overhead"`` punishes the crouch, the
    downward knockback drops them -- and OTG stays singular.
    """
    from src.combat.attack_data import GOBLIN_ATTACKS, SLIME_ATTACKS

    carriers = {
        name
        for table in (PLAYER_ATTACKS, GOBLIN_ATTACKS, SLIME_ATTACKS)
        for name, attack in table.items()
        if any(phase.hit.otg_allowed for phase in attack.phases)
    }

    assert carriers == {"otg_slam"}


def test_the_aerial_kit_has_three_roles_and_each_move_has_exactly_one() -> None:
    """The kit is two extenders bracketing a launcher and a terminator.

    ``air_forward`` arrived with ``juggle_gravity_mult: 0.8`` and ``air_attack``
    with the default 1.0, which left the fastest aerial in the game -- 0.35s of
    cooldown over 15 frames, against the forward one's 0.40s over 16 -- unable to
    keep a juggle alive while a marginally costlier move could. Nobody decides
    that; it is what happens when a value is set on one move and not reasoned
    about across the set.

    So the role follows the reach. The two cheap moves extend a juggle, because
    extending one means re-reaching the target and those are the two that can be
    thrown again soonest. The two expensive ones do not: ``air_rise`` launches
    and ``air_sweep`` drops them, and neither is a tool for staying on top of a
    target that is already going up.

    Read as a role per move and asserted as a partition, so a fifth aerial has to
    declare which of the three it is instead of inheriting whichever defaults it
    was built with.
    """
    roles = {
        name: (
            "extend"
            if attack.phases[0].hit.juggle_gravity_mult != 1.0
            else ("launch" if attack.vertical_lunge > 0 else "drop")
        )
        for name, attack in PLAYER_ATTACKS.items()
        if Stance.AIR in attack.stances
    }

    assert roles == {
        "air_attack": "extend",
        "air_forward": "extend",
        "air_rise": "launch",
        "air_sweep": "drop",
    }


def test_the_extenders_are_the_aerials_that_can_be_thrown_again_soonest() -> None:
    """The reason the roles fall that way, so re-sorting them needs a reason.

    An extender is worth its cooldown only if it comes back fast, so the rule
    is checked against the numbers instead of trusted: every extender must be
    cheaper than every non-extender. If someone makes the rise the extender, or
    stretches the neutral aerial past the dive, this is what says no.
    """
    aerial = {
        name: attack for name, attack in PLAYER_ATTACKS.items() if Stance.AIR in attack.stances
    }
    extenders = [a.cooldown for a in aerial.values() if a.phases[0].hit.juggle_gravity_mult != 1.0]
    others = [a.cooldown for a in aerial.values() if a.phases[0].hit.juggle_gravity_mult == 1.0]

    assert extenders and others
    assert max(extenders) < min(others), (
        f"an extender ({max(extenders)}s) is no cheaper than a bookend ({min(others)}s)"
    )


def test_an_extender_is_a_slowing_multiplier_over_a_juggle_who_has_a_floor() -> None:
    """What the flag actually does, pinned against the gate rather than the table.

    ``hit_resolver`` applies it only when the target was already airborne, and
    only for ``JUGGLE_GRAVITY_TIME``. So the value is a claim about a juggle in
    progress -- against a grounded target it is inert, which is why the
    extenders need no special handling for a knockdown. That half is covered
    where the gate lives; what is asserted here is the value's own contract,
    because a number above 1.0 would be a *shortener* wearing an extender's name.
    """
    from src.combat.hit_resolver import _juggle_scale
    from src.core.settings import Combat as CombatSettings

    extenders = [
        attack.phases[0].hit.juggle_gravity_mult
        for attack in PLAYER_ATTACKS.values()
        if Stance.AIR in attack.stances and attack.phases[0].hit.juggle_gravity_mult != 1.0
    ]

    assert extenders, "nothing in the air kit extends a juggle any more"
    assert all(value < 1.0 for value in extenders), "a multiplier above 1.0 is not an extender"

    # The floor is what stops a juggle draining to nothing, so an extender is
    # worth having rather than strictly less damage for longer. Stated as the
    # shape rather than a number: strictly decreasing until it stops, and stopping
    # at the floor. The floor is five hits in at JUGGLE_DECAY_STEP 0.1, not
    # three, which is the kind of thing an off-by-two makes look like a bug.
    scales = [_juggle_scale(n) for n in range(1, 12)]
    floor = CombatSettings.JUGGLE_DAMAGE_FLOOR

    assert scales[-1] == floor
    assert all(
        later < earlier for earlier, later in zip(scales, scales[1:], strict=False) if later > floor
    )
    assert all(scale >= floor for scale in scales)


def test_a_rise_cannot_be_chained_so_it_needs_no_claim_on_the_midair_jump() -> None:
    """Why ``air_rise`` does not spend ``midair_jumps_left``.

    Consuming the jump is the usual answer to "can this be spammed into a climb",
    and the question was left open because the climb had not been ruled out.
    It can be, arithmetically: a fighter rises at
    ``jump_height * vertical_lunge`` and decelerates at ``GRAVITY``, so the
    impulse lasts until the apex, and a second impulse cannot be requested until
    the cooldown is up. Bounding the one by the other bounds the climb.

    ``air_rise`` is 0.31s of lift against 0.70s of cooldown, so more than half
    the window is spent falling back down before the move is available again.
    Spending the midair jump on top would cost the player their remaining air
    mobility to prevent something the numbers already prevent, and would do it
    in the case where it matters least -- having jumped already leaves no
    midair jumps to spend, so the consumption would only ever bite a fighter who
    walked off a ledge.

    Read off the constants rather than asserted as literals, so a change to
    gravity or to jump height is checked here instead of quietly reintroducing
    the climb.
    """
    from src.core.settings import Physics

    jump_height = _player().jump_height

    unclimbable = {
        name: (jump_height * attack.vertical_lunge / Physics.GRAVITY, attack.cooldown)
        for name, attack in PLAYER_ATTACKS.items()
        if Stance.AIR in attack.stances and attack.vertical_lunge > 0
    }

    assert unclimbable, "no aerial rises, so this says nothing about climbing"
    for name, (time_to_apex, cooldown) in unclimbable.items():
        assert cooldown >= time_to_apex, (
            f"{name} spends {time_to_apex:.3f}s rising but only {cooldown}s before it "
            "can be thrown again, so two impulses overlap and the climb is unbounded"
        )


def test_the_harness_actually_holds_what_it_is_told() -> None:
    """The helper's action parameter was dead, and this is what killed it.

    ``_hold`` took ``**held`` and put the attribute *names* into the frozenset, so
    ``JUMP=True`` handed ``InputState`` the string ``"JUMP"`` and was rejected
    with a message about gameplay actions. No test in the file passed an action
    to it, so the parameter was never exercised and nothing caught it -- a
    helper that only ever ran its default path, one call away from a
    baffling error.

    So this drives a real jump through it. If the harness stops holding what it
    is given, every test in the file is measuring a fighter nobody is pressing
    anything on, and this is the one that says so.
    """
    manager = InputManager()
    player = _player(manager)
    assert player.on_surface["floor"]

    _hold(player, manager, InputAction.JUMP, frames=6)

    assert not player.on_surface["floor"], "holding jump never left the ground"
    assert player.velocity.y < 0.0, "and the fighter is not rising"


def test_the_harness_reports_a_bad_action_at_the_call_rather_than_deeper_in() -> None:
    """A varargs of members can still be handed a string by mistake.

    Worth keeping because the failure is now immediate and local: the type error
    belongs to the line that made it, not to an ``InputState`` construction three
    frames into a loop the caller did not write.
    """
    manager = InputManager()
    player = _player(manager)

    with pytest.raises(ValueError, match="gameplay actions"):
        _hold(player, manager, "JUMP", frames=1)  # type: ignore[arg-type]
