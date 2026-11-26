"""The simulation no longer needs a display, an art cache or effects.

These tests pin the promises ADR 0002 makes about the completed migration:
the ports are real, the tuning is owned per world, and rollback can grow
without editing its snapshot dataclass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

import pygame

from src.platform.input.input_manager import InputManager
from src.platform.input.input_provider import InputProvider
from src.shared.contracts import NullAssetPort, NullFx, NullWorldRenderer
from src.shared.input_state import InputState
from src.simulation.level.level import Level
from src.simulation.level.level_data import LevelConfig, LevelData, ObjectData, ObjectLayerData
from src.simulation.settings import Tuning, TurnProfile

_HEADLESS = r"""
import sys
import pygame
from src.shared.contracts import NullAssetPort, NullFx, NullWorldRenderer
from src.shared.input_state import InputState
from src.platform.input.input_manager import InputManager
from src.platform.input.input_provider import InputProvider
from src.simulation.level.level import Level
from src.simulation.level.level_data import LevelData, LevelConfig, ObjectData, ObjectLayerData

class Still(InputProvider):
    def poll(self): return InputState()

obj = ObjectData(name="player", x=100.0, y=100.0, width=0.0, height=0.0,
                 gid=None, image=None, points=None, properties={})
data = LevelData(width=20, height=10, tile_size=64,
                 object_layers={"E": ObjectLayerData(name="E", objects=[obj])},
                 config=LevelConfig(death_border_bottom=0.0))
level = Level(pygame.Surface((1152, 648)), data, InputManager(Still()),
              renderer=NullWorldRenderer(), asset_port=NullAssetPort(), fx_port=NullFx())
for _ in range(10):
    level.update(1 / 60)
level.draw(60.0)
assert level.tick == 10
assert len(level.groups.fighters) == 1
assert not [m for m in sys.modules if m.startswith("src.presentation")], [
    m for m in sys.modules if m.startswith("src.presentation")
]
print("headless-ok")
"""


def test_a_level_ticks_and_draws_without_importing_presentation() -> None:
    env = dict(os.environ)
    # CI also runs the suite with DEBUG=1; the debug spawn bench then reads the
    # keyboard, which a headless subprocess does not have.
    env["DEBUG"] = "0"
    result = subprocess.run(
        [sys.executable, "-c", _HEADLESS],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "headless-ok" in result.stdout


def _headless_level() -> Level:
    class Still(InputProvider):
        def poll(self) -> InputState:
            return InputState()

    player = ObjectData(
        name="player",
        x=100.0,
        y=100.0,
        width=0.0,
        height=0.0,
        gid=None,
        image=None,
        points=None,
        properties={},
    )
    data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={"E": ObjectLayerData(name="E", objects=[player])},
        config=LevelConfig(death_border_bottom=0.0),
    )
    return Level(
        pygame.Surface((1152, 648)),
        data,
        InputManager(Still()),
        renderer=NullWorldRenderer(),
        asset_port=NullAssetPort(),
        fx_port=NullFx(),
    )


@dataclass
class _ExtraState:
    value: int = 0


class _ExtraProvider:
    def __init__(self) -> None:
        self.state = _ExtraState(7)

    def save_state(self) -> _ExtraState:
        return _ExtraState(self.state.value)

    def load_state(self, state: _ExtraState) -> None:
        self.state = state


def test_a_new_subsystem_joins_rollback_without_editing_the_snapshot() -> None:
    level = _headless_level()
    extra = _ExtraProvider()
    level.register_snapshot_provider("extra", extra)

    snapshot = level.save_state()
    assert snapshot.parts["extra"].value == 7
    extra.state.value = 99
    level.load_state(snapshot)
    assert extra.state.value == 7


def test_tuning_is_owned_per_world() -> None:
    from tests.unit.helpers import make_entity

    turned_on = Tuning(
        profiles={
            "default": TurnProfile(),
            "player": TurnProfile(inherits="default", enabled=True, brake_control=12.0),
        }
    )
    turned_off = Tuning(profiles={"default": TurnProfile(), "player": TurnProfile()})

    a = make_entity(faction="player", tuning=turned_on)
    b = make_entity(faction="player", tuning=turned_off)
    for entity in (a, b):
        entity.turn_profile = "player"
        entity.apply_turn_profile()

    assert a.turn_enabled is True
    assert a.turn_brake_control == 12.0
    assert b.turn_enabled is False


def test_two_worlds_do_not_share_tuning_state() -> None:
    from tests.unit.helpers import make_entity

    first = Tuning(profiles={"default": TurnProfile(), "player": TurnProfile(enabled=True)})
    second = Tuning(profiles={"default": TurnProfile(), "player": TurnProfile()})
    a = make_entity(faction="player", tuning=first)
    b = make_entity(faction="player", tuning=second)
    for entity in (a, b):
        entity.turn_profile = "player"
        entity.apply_turn_profile()
    assert a.turn_enabled is True
    assert b.turn_enabled is False
