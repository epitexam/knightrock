"""P4.2 reception: malformed frame data is rejected with a named message.

Each rule of the strict loader is exercised through the public entry points
(``validate_attacks`` / ``load_attacks``, reached by builtin tables and
gameplay JSON alike): the error must be a ``GameplayDataError`` naming the
attack, the phase index and the field at fault — never a silent fallback.
"""

from dataclasses import replace

import pytest

from src.combat.attack_loading import (
    ENVELOPE_MARGIN,
    SPRITE_SIZE,
    load_attacks,
    validate_attacks,
)
from src.combat.frame_data import HitboxKeyframe
from src.data.attacks import read_attack_definition
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


def test_unknown_cancel_is_rejected() -> None:
    broken_phase = replace(_valid_attack().phases[0], cancel_into=("nope",))
    definition = replace(_valid_attack(), phases=(broken_phase,))

    with pytest.raises(GameplayDataError, match=r"kick' references unknown cancels: nope"):
        validate_attacks({"kick": definition})


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
