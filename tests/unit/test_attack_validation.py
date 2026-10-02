"""P4.2 reception: malformed frame data is rejected with a named message.

Each rule of the strict loader is exercised through the public entry points
(``validate_attacks`` / ``load_attacks``, reached by builtin tables and
gameplay JSON alike): the error must be a ``GameplayDataError`` naming the
attack, the phase index and the field at fault — never a silent fallback.
"""

import json
from dataclasses import replace

import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.attack_loading import (
    ENVELOPE_MARGIN,
    SPRITE_SIZE,
    load_attacks,
    validate_attacks,
)
from src.combat.frame_data import HitboxKeyframe, Stance, move_id
from src.data.attacks import attack_definition_to_dict, read_attack_definition, read_attacks_file
from src.data.errors import GameplayDataError
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _valid_attack():
    return attack(phase(startup=1, active=2, recovery=1, size=(30.0, 20.0), offset=(20.0, 0.0)))


class _CombatStub:
    """Minimal loader target: records registrations (``load_attacks`` only)."""

    def __init__(self) -> None:
        self.attacks: dict[str, object] = {}

    def add_attack(self, name: str, definition: object) -> None:
        self.attacks[name] = definition


def _raw_json_hit() -> dict[str, object]:
    return {
        "damage": 5.0,
        "damage_type": "blunt",
        "knockback": {"power": [100.0, 0.0]},
    }


def test_valid_table_loads_into_the_component() -> None:
    combat = _CombatStub()

    load_attacks(combat, {"kick": _valid_attack()})  # type: ignore[arg-type]

    assert "kick" in combat.attacks


def test_json_attack_outside_sprite_envelope_is_rejected() -> None:
    raw = {
        "phases": [
            {
                "startup_frames": 1,
                "active_frames": 2,
                "recovery_frames": 1,
                "hitbox_size": [30.0, 20.0],
                "hitbox_offset": [ENVELOPE_MARGIN * SPRITE_SIZE[0] + 1.0, 0.0],
                "hit": _raw_json_hit(),
            }
        ],
        "cooldown": 1.0,
    }
    definition = read_attack_definition(raw, "data/gameplay/attacks.json#player.kick")

    with pytest.raises(GameplayDataError, match=r"kick' phase 0 hitbox: offset"):
        validate_attacks({"kick": definition})


def test_json_attack_with_too_short_cooldown_is_rejected() -> None:
    raw = {
        "phases": [
            {
                "startup_frames": 10,
                "active_frames": 10,
                "recovery_frames": 10,
                "hitbox_size": [30.0, 20.0],
                "hitbox_offset": [20.0, 0.0],
                "hit": _raw_json_hit(),
            }
        ],
        "cooldown": 0.1,
    }
    definition = read_attack_definition(raw, "data/gameplay/attacks.json#player.slam")

    with pytest.raises(GameplayDataError, match=r"slam': cooldown"):
        validate_attacks({"slam": definition})


def test_non_positive_box_size_is_rejected_with_named_message() -> None:
    definition = _valid_attack()
    # Bypass the dataclass guard to exercise the loader's own naming.
    object.__setattr__(definition.phases[0], "hitbox_size", (0.0, 20.0))

    with pytest.raises(GameplayDataError, match=r"kick' phase 0 hitbox: size"):
        validate_attacks({"kick": definition})


def test_keyframe_outside_the_phase_span_is_rejected_with_named_message() -> None:
    definition = attack(phase(startup=2, active=2, recovery=1))
    # Bypass the dataclass guard to exercise the loader's own naming.
    object.__setattr__(
        definition.phases[0],
        "hitbox_keyframes",
        (HitboxKeyframe(frame=99, size=(10.0, 10.0), offset=(0.0, 0.0)),),
    )

    with pytest.raises(GameplayDataError, match=r"kick' phase 0 hitbox: keyframe 99"):
        validate_attacks({"kick": definition})


def test_keyframe_offset_outside_sprite_envelope_is_rejected() -> None:
    definition = attack(
        phase(
            startup=1,
            active=2,
            recovery=1,
            keyframes=((1, (10.0, 10.0), (ENVELOPE_MARGIN * SPRITE_SIZE[0] + 1.0, 0.0)),),
        )
    )
    with pytest.raises(GameplayDataError, match=r"kick' phase 0 hitbox: keyframe 1 offset"):
        validate_attacks({"kick": definition})


def test_a_cancel_naming_an_unregistered_attack_is_rejected() -> None:
    """Its own case: it was previously glued onto the envelope test above.

    A test named for the keyframe envelope should not also be the only place
    the ``cancel_into`` cross-reference is covered -- it makes the rule look
    untested when grepping by name, and the failure it reports when broken is
    two assertions and a scroll away from the assertion that broke.
    """
    broken_phase = replace(_valid_attack().phases[0], cancel_into=(move_id("nope"),))
    definition = replace(_valid_attack(), phases=(broken_phase,))

    with pytest.raises(GameplayDataError, match=r"kick' references unknown cancels: nope"):
        validate_attacks({"kick": definition})


def test_a_cancel_into_the_attack_itself_is_rejected() -> None:
    """It loads today and is dead in play.

    The cooldown gate runs before the cancel gate, and every move is still on
    cooldown at its own last frame -- so a self-cancel is accepted by the data
    and then never fires.
    """
    definition = replace(
        _valid_attack(),
        phases=(replace(_valid_attack().phases[0], cancel_into=(move_id("kick"),)),),
    )

    with pytest.raises(GameplayDataError, match=r"cancels into itself"):
        validate_attacks({"kick": definition})


def test_a_cancel_into_a_posture_it_cannot_be_thrown_from_is_rejected() -> None:
    """An air chain into a ground move was loadable, and playable.

    ``air_attack.cancel_into = ("light_attack",)`` passed every existing check
    for as long as it existed, and nothing stopped a fighter chaining from
    mid-air into a standing swing. The move's own ``stances`` are what make the
    crossing visible.
    """
    ground = _valid_attack()
    air_phase = replace(ground.phases[0], cancel_into=(move_id("jab"),))
    air = replace(ground, phases=(air_phase,), stances=(Stance.AIR,))
    jab = replace(_valid_attack(), phases=(replace(_valid_attack().phases[0], cancel_into=()),))

    with pytest.raises(GameplayDataError, match=r"not reachable from air"):
        validate_attacks({"punch": air, "jab": jab})


def test_a_mutual_cancel_is_allowed() -> None:
    """Refusing cycles between moves would reject a table that works.

    ``light_attack`` and ``dash_attack`` cancel into each other in the shipped
    data. What bounds the chain is the cooldown gate -- every move clears its
    cooldown before it can be thrown again -- not the shape of the graph, so a
    cycle check would have refused an ordinary table.
    """
    a = _valid_attack()
    b = replace(a, phases=(replace(a.phases[0], cancel_into=(move_id("kick"),)),))
    a_mutual = replace(a, phases=(replace(a.phases[0], cancel_into=(move_id("jab"),)),))

    validate_attacks({"kick": a_mutual, "jab": b})


def test_the_shipped_tables_satisfy_every_cancel_rule() -> None:
    """The shipped tables are checked by the same code that checks a bad one.

    Otherwise the rules above could be wrong in a way that only shows up on a
    table nobody validates -- which is exactly what happened to the air chain.
    """
    from src.combat.attack_data import GOBLIN_ATTACKS, PLAYER_ATTACKS, SLIME_ATTACKS

    validate_attacks(PLAYER_ATTACKS)
    validate_attacks(GOBLIN_ATTACKS)
    validate_attacks(SLIME_ATTACKS)


def _raw_json_attack() -> dict[str, object]:
    """A minimal attack block the strictness tests mutate one key at a time."""
    return {
        "phases": [
            {
                "startup_frames": 1,
                "active_frames": 2,
                "recovery_frames": 1,
                "hitbox_size": [30.0, 20.0],
                "hitbox_offset": [20.0, 0.0],
                "hit": _raw_json_hit(),
            }
        ],
        "cooldown": 1.0,
    }


def _mutated(path: tuple[str, int | str, ...], value: object) -> dict[str, object]:
    """``_raw_json_attack`` with ``path`` set to ``value``, indexes for lists."""
    raw = _raw_json_attack()
    node: object = raw
    for step in path[:-1]:
        node = node[step]  # type: ignore[index]
    assert isinstance(node, dict)
    node[path[-1]] = value
    return raw


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        pytest.param(
            ("lunge_speed_multiplar",),
            0.9,
            r"unknown field\(s\) 'lunge_speed_multiplar'",
            id="attack-typo",
        ),
        pytest.param(
            ("phases", 0, "recieve_targets"),
            False,
            r"phases\[0\]: unknown field\(s\) 'recieve_targets'",
            id="phase-typo",
        ),
        pytest.param(
            ("phases", 0, "hit", "stundr"),
            0.5,
            r"phases\[0\].hit: unknown field\(s\) 'stundr'",
            id="hit-typo",
        ),
        pytest.param(
            ("phases", 0, "hit", "knockback", "pwer"),
            [10.0, 0.0],
            r"knockback: unknown field\(s\) 'pwer'",
            id="knockback-typo",
        ),
    ],
)
def test_a_misspelled_field_is_refused_at_every_level(
    path: tuple[str, int | str, ...], value: object, expected: str
) -> None:
    """A typo must fail loudly rather than fall back to the default.

    Silently defaulting is the worst outcome available on a hand-edited balance
    file: the attack still exists, the field the designer meant to change simply
    has no effect, and the only symptom is a number that will not move. The
    three call sites that promised this behaviour (``attacks.py``,
    ``data/__init__.py``, ``README``) had no check behind them, so it is pinned
    per level -- attack, phase, hit, knockback -- rather than once.
    """
    with pytest.raises(GameplayDataError, match=expected):
        read_attack_definition(_mutated(path, value), "attacks.json#player.kick")


def test_the_refusal_names_the_allowed_fields() -> None:
    """The message has to say what *is* accepted, or it is a dead end.

    A designer who misspells ``hitbox_anchor`` needs the valid spellings in
    front of them; "unknown field" alone sends them to the source.
    """
    with pytest.raises(GameplayDataError, match=r"expected one of .*hitbox_anchor"):
        read_attack_definition(_mutated(("phases", 0, "hitbox_anchr"), "chest"), "t")


def _v2_attack(*extra: tuple[str, object]) -> dict[str, object]:
    """A phase in the ``hitboxes`` dialect, with the v1 geometry keys removed.

    ``extra`` adds legacy keys back alongside the list, which is the collision
    the guard exists to refuse.
    """
    raw = _raw_json_attack()
    block = raw["phases"][0]  # type: ignore[index]
    size = block.pop("hitbox_size")
    offset = block.pop("hitbox_offset")
    block["hitboxes"] = [{"size": size, "offset": offset}]
    for key, value in extra:
        block[key] = value
    return raw


def test_a_legacy_field_beside_a_hitboxes_list_is_refused_and_named() -> None:
    """The v1/v2 collision guard, which used to miss five of the nine keys.

    A ``hitboxes`` list carries shape, angle, easing and anchor per box, so a
    legacy key next to it is ambiguous rather than merely redundant. The guard
    named only the four geometry keys and silently dropped the other five --
    meaning the exact case it exists to catch, ``hitbox_shape`` beside
    ``hitboxes``, loaded without complaint and without the shape.
    """
    for legacy, value in (
        ("hitbox_shape", "circle"),
        ("hitbox_angle", 45.0),
        ("hitbox_easing", "ease_in"),
        ("hitbox_anchor", "chest"),
        ("hitbox_anchor_offset", [1.0, 2.0]),
    ):
        raw = _v2_attack((legacy, value))

        with pytest.raises(GameplayDataError, match=legacy):
            read_attack_definition(raw, "t")


def test_the_refusal_lists_the_conflicting_keys() -> None:
    """``cannot be combined`` alone does not say *which* keys collide.

    Naming them matters because the fix is a deletion and the collision can
    involve more than one key at a time -- a phase that was converted halfway
    keeps its geometry keys and gains a list.
    """
    raw = _raw_json_attack()
    block = raw["phases"][0]  # type: ignore[index]
    size = block["hitbox_size"]
    offset = block["hitbox_offset"]
    block["hitboxes"] = [{"size": size, "offset": offset}]
    block["hitbox_shape"] = "circle"

    with pytest.raises(GameplayDataError, match=r"hitbox_offset, hitbox_shape, hitbox_size"):
        read_attack_definition(raw, "t")


def test_the_legacy_anchor_spelling_still_loads() -> None:
    """``follow`` was the field's name before ``anchor``; it stays readable.

    Keeping it is a compatibility choice, not an oversight -- a file authored
    against the old name must keep working. The risk is that an alias nobody
    documented reads as a typo that happens to be tolerated, so the fact that it
    is deliberate is pinned here.
    """
    raw = _v2_attack()
    raw["phases"][0]["hitboxes"][0]["follow"] = "weapon"  # type: ignore[index]

    definition = read_attack_definition(raw, "t")

    assert definition.phases[0].hitbox_anchor.value == "weapon"


def test_a_comment_key_in_an_attack_set_is_dropped(tmp_path) -> None:
    """JSON has no comments; an ``_underscore`` key is the usual workaround.

    Refusing it would push designers to strip their own annotations before
    committing, and a data file nobody dares annotate is one nobody tunes.
    """
    path = tmp_path / "attacks.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sets": {
                    "player": {
                        "_comment": "tuned for the 2p pass, do not reorder",
                        "kick": attack_definition_to_dict(PLAYER_ATTACKS["light_attack"]),
                    }
                },
            }
        )
    )

    sets = read_attacks_file(path)

    assert list(sets["player"]) == ["kick"]


def test_intermediate_phase_without_target_reset_warns() -> None:
    definition = attack(
        replace(phase(startup=1, active=1, recovery=1), reset_targets=False),
        phase(startup=1, active=1, recovery=1),
    )

    with pytest.warns(UserWarning, match=r"kick' phase 0: reset_targets"):
        validate_attacks({"kick": definition})


def test_load_attacks_validates_before_registering() -> None:
    combat = _CombatStub()
    broken = replace(_valid_attack(), cooldown=0.0)

    with pytest.raises(GameplayDataError):
        load_attacks(combat, {"kick": broken})  # type: ignore[arg-type]

    assert combat.attacks == {}


def test_a_vertical_lunge_on_a_ground_only_move_is_refused() -> None:
    """It loads today and is never read.

    The impulse is applied on the airborne branch, so a move that cannot be
    thrown from the air carries a number nothing will ever look at. Same shape
    as the self-cancel: a balance change someone made to a move that will not
    run it, invisible until the stance list is edited and the number is found
    to have been a typo all along.
    """
    grounded = replace(
        _valid_attack().phases[0],
        cancel_into=(),
    )
    definition = replace(
        _valid_attack(), phases=(grounded,), stances=(Stance.GROUND,), vertical_lunge=0.6
    )

    with pytest.raises(GameplayDataError, match=r"which do not include 'air'"):
        validate_attacks({"kick": definition})


def test_a_vertical_lunge_stronger_than_a_jump_is_refused() -> None:
    """``vertical_lunge`` is a multiple of jump height, so 1.0 *is* a jump.

    Above that, the move out-launches the jump that put the fighter in the air:
    the jump becomes optional and the attack mandatory, which inverts what the
    jump is for. The bound is the only reason the field is safe to author in.
    """
    definition = replace(
        _valid_attack(),
        phases=(replace(_valid_attack().phases[0], cancel_into=()),),
        stances=(Stance.AIR,),
        vertical_lunge=1.4,
    )

    with pytest.raises(GameplayDataError, match=r"exceeds 1.0 jump heights"):
        validate_attacks({"kick": definition})


def test_a_vertical_lunge_of_exactly_one_jump_is_allowed() -> None:
    """The bound is inclusive, and the boundary is where an off-by-one hides.

    1.0 means "as much as a jump", which is a coherent aerial. A check written
    ``>=`` would refuse it and quietly push every future aerial down toward
    0.99 without anybody deciding to.
    """
    definition = replace(
        _valid_attack(),
        phases=(replace(_valid_attack().phases[0], cancel_into=()),),
        stances=(Stance.AIR,),
        vertical_lunge=1.0,
    )

    validate_attacks({"kick": definition})


def test_a_vertical_lunge_survives_the_round_trip() -> None:
    """The field is on the wire, so a data file has to be able to carry it.

    Checked separately from the other round-trips because a field that reads but
    does not write round-trips to a *default* and looks fine -- the failure
    being that the shipped JSON silently loses the value on the next
    regeneration.
    """
    definition = replace(
        _valid_attack(),
        phases=(replace(_valid_attack().phases[0], cancel_into=()),),
        stances=(Stance.AIR,),
        vertical_lunge=-0.4,
    )

    back = read_attack_definition(attack_definition_to_dict(definition), "test")

    assert back.vertical_lunge == pytest.approx(-0.4)


def test_the_shipped_aerials_carry_the_impulses_they_need() -> None:
    """The shipped data against the rule, which is the only place both exist.

    Each aerial is asserted against the direction its button already means on
    the floor: ATTACK_3 launches on the ground so it rises in the air, ATTACK_2
    is the heavy hit down here so it falls up there, and the neutral one leaves
    the arc alone. A table where all four had the same sign would satisfy the
    validation and be the missing feature replaced by a worse one.
    """
    player = PLAYER_ATTACKS
    from src.core.input.input_actions import InputAction
    from src.entities.attack_moves import BUTTON_MOVES

    aerial = {
        action.value: moves[Stance.AIR]
        for action, moves in BUTTON_MOVES.items()
        if Stance.AIR in moves
    }

    assert player[aerial[InputAction.ATTACK_3.value]].vertical_lunge > 0
    assert player[aerial[InputAction.ATTACK_2.value]].vertical_lunge < 0
    assert player[aerial[InputAction.ATTACK_1.value]].vertical_lunge == 0.0
