import pygame
import pytest

from src.core.input.input_manager import InputManager
from src.core.settings import Physics
from src.entities.player import Player
from src.states.player_states import _can_dash

#: Edge-triggered input flags the fake input manager exposes: a stale True
#: would re-fire on every frame, so the stepper clears them all up front.
_EDGE_FLAGS = (
    "dash_just_pressed",
    "attack1_just_pressed",
    "attack2_just_pressed",
    "attack2_just_released",
    "attack3_just_pressed",
    "attack4_just_pressed",
    "special_attack_just_pressed",
    "guard_just_pressed",
    "jump_just_pressed",
    "reset_just_pressed",
)


@pytest.fixture
def player_setup():
    pygame.init()
    pygame.display.set_mode((100, 100))
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    input_manager = InputManager()

    player = Player(
        pos=(0, 0),
        groups=groups,
        collision_sprites=collision_sprites,
        moving_platforms=[],
        input_manager=input_manager,
    )
    return player, input_manager


def _make_player(input_manager) -> Player:
    """Real player on an isolated patch of ground (no level, no assets)."""
    return Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=input_manager,
    )


def _step(
    player: Player, input_manager, frames: int, *, press: str | None = None, hold=None
) -> None:
    """Advance the player, optionally pressing one edge input on frame 0."""
    for index in range(frames):
        for name in _EDGE_FLAGS:
            setattr(input_manager, name, False)
        for name, value in (hold or {}).items():
            setattr(input_manager, name, value)
        if press is not None and index == 0:
            setattr(input_manager, press, True)
        player.on_surface["floor"] = True  # emulate standing on solid ground
        player.velocity.y = 0.0
        player.update(1 / 60)


def test_player_initialization(player_setup):
    player, _ = player_setup
    assert player.health == player.max_health
    assert player.state_machine.current_state_name == "idle"


def test_player_dash_charges(player_setup):
    player, _ = player_setup
    assert player.dash.charges == player.dash.max_charges

    # Dash request should be allowed in idle/fall state
    player.dash.requested = True
    assert _can_dash(player)


# --- Dash attack (F / attack4) ---


def test_attack4_starts_the_dash_attack(mock_input_manager):
    """The lunge move is bound to attack4 and applies its full-speed lunge."""
    player = _make_player(mock_input_manager)
    _step(player, mock_input_manager, 2)

    _step(player, mock_input_manager, 1, press="attack4_just_pressed")

    assert player.state_machine.current_state_name == "attack"
    assert player.combat.state.attack_name == "dash_attack"
    # dash_attack.lunge_speed_multiplier is 1.0: the whole run speed forward.
    assert player.velocity.x == pytest.approx(player.speed, rel=0.05)


def test_attack_is_refused_while_the_dash_is_committed(monkeypatch, mock_input_manager):
    """A positive cancel window keeps the dash: the press starts nothing.

    Regression guard for the swallowed input this fix repairs: before, the
    press was dropped even after the window, because ``can_attack()`` forbade
    the DASH state outright.
    """
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    player = _make_player(mock_input_manager)
    _step(player, mock_input_manager, 2)
    _step(player, mock_input_manager, 1, press="dash_just_pressed")
    assert player.state_machine.current_state_name == "dash"

    # One frame in: 0.016s elapsed, under the 0.03s window.
    _step(player, mock_input_manager, 1, press="attack4_just_pressed")

    assert player.state_machine.current_state_name == "dash"
    assert player.combat.is_attacking is False


def test_attack_cancels_the_dash_once_the_window_is_open(mock_input_manager):
    """Dash then F: the attack takes over and the dash perks drop with it."""
    player = _make_player(mock_input_manager)
    _step(player, mock_input_manager, 2)
    _step(player, mock_input_manager, 1, press="dash_just_pressed")
    assert player.state_machine.current_state_name == "dash"
    assert player.is_invincible is True
    squished_width = player.hitbox.width

    _step(player, mock_input_manager, 1, press="attack4_just_pressed")

    assert player.state_machine.current_state_name == "attack"
    assert player.combat.state.attack_name == "dash_attack"
    assert player.is_invincible is False  # i-frames belong to the dash state
    assert player.hitbox.width > squished_width  # dash squish restored on exit


def test_guard_still_cancels_the_dash(mock_input_manager):
    """The guard cancel predates the attack one: keep both working."""
    player = _make_player(mock_input_manager)
    _step(player, mock_input_manager, 2)
    _step(player, mock_input_manager, 1, press="dash_just_pressed")
    assert player.state_machine.current_state_name == "dash"

    _step(
        player,
        mock_input_manager,
        1,
        press="guard_just_pressed",
        hold={"guard_held": True},
    )

    assert player.state_machine.current_state_name == "guard"
