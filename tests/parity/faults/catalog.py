"""Twelve live simulation faults used to prove the parity suite can fail.

Each fault replaces exactly one string in the legacy tree. A fault is "killed"
when at least one parity scenario produces a different digest; a survivor
means the scenarios are not actually observing that behavior.

Faults that survived an early version of this catalogue were removed rather
than kept as false positives:

* ``DASH_GRAVITY_MULT`` — assigned to ``DashController.gravity_mult`` in
  ``player_controllers.py:140`` but never read afterwards (dead configuration);
* ``HITSTOP_BASE`` and attack ``hit_stop`` — every shipped hit carries its own
  ``hit_stop`` in ``data/gameplay/attacks.json`` and overrides the formula;
* ``INVINCIBILITY_DURATION``, ``CONTACT_DAMAGE_AMOUNT`` and ``NULL_KNOCKBACK`` —
  real settings, but no parity scenario produces a contact hit today. They are
  pinned by ``test_contact_unified.py``, ``test_knockback_feel.py`` and
  ``test_knockback_weight.py`` instead of being duplicated here.

The twelve retained faults all lie on paths the seven scenarios do exercise.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Fault", "FAULTS"]


@dataclass(frozen=True)
class Fault:
    name: str
    path: str
    old: str
    new: str
    scenario: str


FAULTS: tuple[Fault, ...] = (
    Fault(
        "gravity_scale",
        "src/simulation/physics/gravity.py",
        "grav *= entity.gravity_scale",
        "grav *= entity.gravity_scale * 1.1",
        "idle",
    ),
    Fault(
        "player_speed",
        "src/core/settings.py",
        "PLAYER_SPEED = 350",
        "PLAYER_SPEED = 385",
        "run_jump_dash",
    ),
    Fault(
        "gravity_constant", "src/core/settings.py", "GRAVITY = 1500.0", "GRAVITY = 1650.0", "idle"
    ),
    Fault(
        "max_fall_speed",
        "src/core/settings.py",
        "MAX_FALL_SPEED = 1500.0",
        "MAX_FALL_SPEED = 1650.0",
        "long_fall",
    ),
    Fault(
        "jump_force",
        "src/core/settings.py",
        "JUMP_FORCE = 750.0",
        "JUMP_FORCE = 900.0",
        "run_jump_dash",
    ),
    Fault(
        "dash_speed",
        "src/core/settings.py",
        "DASH_SPEED = 1350",
        "DASH_SPEED = 1500",
        "run_jump_dash",
    ),
    Fault(
        "walk_promote",
        "src/core/settings.py",
        "WALK_PROMOTE = 0.80  # walk -> run",
        "WALK_PROMOTE = 0.95  # walk -> run",
        "melee",
    ),
    Fault(
        "floor_control",
        "src/core/settings.py",
        "FLOOR_CONTROL = 25.0",
        "FLOOR_CONTROL = 40.0",
        "melee",
    ),
    Fault(
        "jump_cut",
        "src/core/settings.py",
        "JUMP_CUT_DIVISOR = 2.5",
        "JUMP_CUT_DIVISOR = 1.0",
        "run_jump_dash",
    ),
    Fault(
        "apex_gravity",
        "src/core/settings.py",
        "APEX_GRAVITY_DIVISOR = 2.0",
        "APEX_GRAVITY_DIVISOR = 1.0",
        "idle",
    ),
    Fault(
        "fast_fall",
        "src/core/settings.py",
        "FAST_FALL_GRAVITY_MULTIPLIER = 1.5",
        "FAST_FALL_GRAVITY_MULTIPLIER = 3.0",
        "run_jump_dash",
    ),
    Fault(
        "initial_facing",
        "src/entities/entity.py",
        "self.facing_right: bool = True",
        "self.facing_right: bool = False",
        "melee",
    ),
)
