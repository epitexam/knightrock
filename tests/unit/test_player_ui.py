"""Tests for PlayerUI (ui/player_ui)."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.entities.player_config import PlayerConfig
from src.entities.player_controllers import DashController
from src.ui.panel_renderer import PanelRenderer
from src.ui.player_ui import PlayerUI


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def player_ui() -> PlayerUI:
    return PlayerUI(PanelRenderer(pygame.display.get_surface()))


def _mock_state():
    return SimpleNamespace(enter=lambda *a, **kw: None, tags=[])


def _make_player(**overrides) -> SimpleNamespace:
    """Build a SimpleNamespace with all attributes PlayerUI draws."""
    from src.states.state_machine import StateMachine

    sm = StateMachine(SimpleNamespace())
    sm.add_state("idle", _mock_state())
    sm.set_initial_state("idle")

    defaults = {
        "state_machine": sm,
        "velocity": pygame.Vector2(10.0, 0.0),
        "on_surface": {"floor": True, "left": False, "right": False},
        "move_axis": 0.0,
        "jump_buffer_timer": 0.0,
        "coyote_timer": 0.0,
        "midair_jumps_left": 1,
        "wall_jumps_left": 2,
        "dash": DashController(PlayerConfig()),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_full_player(**overrides) -> SimpleNamespace:
    """Player with all stats attributes for draw_stats_panel."""
    base = {
        "health": 100.0,
        "max_health": 100.0,
        "guard_posture": 50.0,
        "guard_posture_max": 100.0,
        "guard_lockout_timer": 0.0,
        "guard_riposte_timer": 0.0,
        "dash_charges": 2,
        "max_dash_charges": 2,
        "dash_penalty_timer": 0.0,
        "dash_recharge_timer": 0.0,
        "speed": 450,
        "floor_control": 25.0,
        "air_control": 12.0,
        "jump_height": 750.0,
        "wall_jump_height": 612.0,
        "dash_speed": 1500,
        "dash_duration": 0.12,
        "dash_friction": 15.0,
    }
    base.update(overrides)
    return _make_player(**base)


def test_draw_state_panel_none_player(player_ui: PlayerUI) -> None:
    assert player_ui.draw_state_panel(0, 0, None) == 0


def test_draw_state_panel_no_state_machine(player_ui: PlayerUI) -> None:
    player = _make_player(state_machine=None)
    assert player_ui.draw_state_panel(0, 0, player) == 0


def test_draw_state_panel_draws(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_state_panel_with_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        combat=SimpleNamespace(
            state=SimpleNamespace(
                attack_name="slash",
                phase_index=0,
                current_attack_def=SimpleNamespace(phases=[]),
            ),
            hurt_timer=0.0,
            is_hurt=False,
            charging=None,
            cooldowns={},
            combo_count=0,
            combo_timer=0.0,
        ),
    )
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_state_panel_is_hurt_shows_line(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        combat=SimpleNamespace(
            state=SimpleNamespace(attack_name="-", phase_index=0, current_attack_def=None),
            hurt_timer=0.2,
            is_hurt=True,
            charging=None,
            cooldowns={},
            combo_count=1,
            combo_timer=0.3,
        ),
    )
    height = player_ui.draw_state_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_none_player(player_ui: PlayerUI) -> None:
    assert player_ui.draw_stats_panel(0, 0, None) == 0


def test_draw_stats_panel_draws(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_low_health(player_ui: PlayerUI) -> None:
    player = _make_full_player(health=10.0, max_health=100.0, combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_with_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(
        health=80.0,
        combat=SimpleNamespace(combo_count=3, combo_timer=0.5),
    )
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_without_combat(player_ui: PlayerUI) -> None:
    player = _make_full_player(combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_shows_riposte_window(player_ui: PlayerUI) -> None:
    player = _make_full_player(guard_riposte_timer=0.4, combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


def test_draw_stats_panel_shows_lockout(player_ui: PlayerUI) -> None:
    player = _make_full_player(guard_lockout_timer=1.0, guard_posture=0.0, combat=None)
    height = player_ui.draw_stats_panel(0, 0, player)
    assert height > 0


# --- the two panels are split by what a line is for -------------------------


def _state_lines_of(player) -> list[str]:
    return PlayerUI._state_lines(player, player.state_machine, compact=False)


def test_the_dash_live_field_is_not_called_dur() -> None:
    """``dur`` meant two things across two panels, and reading it twice hid which.

    STATE printed ``dash.duration_timer`` -- the time left -- and STATS printed
    the ``dash_duration`` constant, both labelled ``dur``. So a developer reading
    both had no way to know that the two numbers were different quantities and not
    a disagreement about the same one. The live one is ``rem``.
    """
    lines = _state_lines_of(_make_player())
    dash = [line for line in lines if line.startswith("Dash")]

    assert len(dash) == 1
    assert "rem " in dash[0]
    assert "dur " not in dash[0]


def test_the_live_jump_fields_share_one_line() -> None:
    """Four live values about one ability, on one line.

    The buffer, the coyote window, the midair budget and the wall budget were
    two lines between them, which read as two subjects -- the split happening to
    be the only thing that gave it away.
    """
    jump = [line for line in _state_lines_of(_make_player()) if line.startswith("Jump")]

    assert len(jump) == 1
    for field in ("buf", "coy", "mid", "wall"):
        assert field in jump[0]


def test_state_prints_the_dash_constants_nowhere() -> None:
    """STATS owns the constants, and that is the half of the split that is easy
    to undo by accident: adding a field to the fighter feels like it belongs
    wherever the other fields for that field are."""
    text = "\n".join(_state_lines_of(_make_player()))

    for constant in ("dash_speed", "dash_charges", "dash_friction"):
        assert constant not in text, constant


def test_stats_prints_the_dash_constants_on_one_line() -> None:
    """One line, so the dash is a single row to scan rather than two.

    Asserted on ``_stats_lines`` rather than on the format strings in the source:
    that line is continued over four string literals, so reading it back out of
    the source yields four matches and not one, and a test that has to guess at
    quoting can pass without testing anything.
    """
    lines = PlayerUI._stats_lines(_make_full_player(), None, compact=False)
    dash = [line for line in lines if line.startswith("Dash") or line.startswith("      pen")]

    assert len(dash) == 2, dash
    for field in ("dur", "spd", "pen", "regen"):
        assert field in "\n".join(dash)

    # The widest line in the panel decides how wide the panel is, and the column
    # flow packs the whole debug set into 1440x900. A single 54-character dash
    # row made STATS the widest panel and pushed the last one off the display.
    assert max(len(line) for line in lines) <= 46, max(lines, key=len)


class _RecordingRenderer:
    """Captures the lines a panel hands to the renderer.

    ``draw_state_panel`` returns a consumed height and paints into the display,
    so the lines it builds are not readable afterwards -- which is why the first
    version of the test below asserted on ``_state_lines`` alone and passed with
    the ``CDs`` block put straight back. Reading what actually reached
    ``draw_panel`` covers the whole method, conditionals included, without
    needing the panel restructured for the sake of being testable.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.interaction = SimpleNamespace(is_closed=lambda _panel_id: False)

    def draw_panel(self, _x, _y, lines, **_kwargs) -> int:
        self.lines = list(lines)
        return 100


def _state_panel_lines(player) -> list[str]:
    renderer = _RecordingRenderer()
    PlayerUI(renderer).draw_state_panel(0, 0, player)
    return renderer.lines


def test_state_no_longer_prints_the_attack_name_or_the_cooldowns() -> None:
    """Both were second copies of something printed elsewhere.

    ``Combat <name> phase <n>/<m>`` is what the label card prints on the fighter
    themselves, and the ``CDs`` line was ``combat.cooldowns`` truncated to four
    -- so with seventeen registered moves the air and crouch ones were only
    visible when they happened to be the first four currently cooling.

    Dropping them is a de-duplication rather than a loss, which is the claim the
    next test pins.
    """
    player = _make_full_player()
    player.combat = SimpleNamespace(
        state=SimpleNamespace(attack_name="light_attack", phase_index=0, current_attack_def=None),
        attack_shapes=(),
        attack_anchors=(),
        hurt_timer=0.0,
        is_hurt=False,
        charging=None,
        cooldowns={"light_attack": 1.2, "air_rise": 0.5},
    )

    text = "\n".join(_state_panel_lines(player))

    assert "Combat" not in text
    assert "CDs" not in text
    # Two moves on cooldown and none of them shown, which is the point: the line
    # used to print at most four of seventeen, and only when they happened to be
    # the first four registered and cooling.
    assert "light_attack" not in text
    assert "air_rise" not in text


def test_state_still_prints_the_hitbox_geometry() -> None:
    """The half of the old combat block that stayed, so the removal is not a
    misunderstanding of what the line was for.

    Geometry belongs here: it is about where the fighter's box is, next to
    ``Vel`` and ``Floor``. The *name* of the move does not.
    """
    player = _make_full_player()
    player.combat = SimpleNamespace(
        state=SimpleNamespace(attack_name="light_attack", phase_index=0, current_attack_def=None),
        attack_shapes=(SimpleNamespace(kind=SimpleNamespace(value="AABB")),),
        attack_anchors=((26.0, -38.0),),
        hurt_timer=0.0,
        is_hurt=False,
        charging=None,
    )

    text = "\n".join(_state_panel_lines(player))

    assert "Hitbox" in text
    assert "AABB" in text
    assert "(26,-38)" in text


def test_the_attack_in_progress_is_still_printed_somewhere() -> None:
    """The justification for the removal above, so it cannot rot unnoticed.

    Dropping ``Combat`` from STATE is only free because the world overlay's label
    card prints the same thing on the sprite. If that ever stops, the debug view
    loses the running attack entirely -- and this is the test that would have
    said so, rather than the removal being quietly correct for a while.
    """
    from tests.unit.helpers import make_card_layer

    attacking = SimpleNamespace(
        combat=SimpleNamespace(
            state=SimpleNamespace(
                attack_name="air_rise",
                phase_index=0,
                frame_counter=3,
                sub_state=SimpleNamespace(value="active"),
            ),
            targets_hit=[],
        )
    )

    row = make_card_layer().attack_line(attacking)

    assert row is not None
    text = "".join(part for part, _ in row)
    assert "air_rise" in text
    assert "p0" in text
    assert "active" in text
