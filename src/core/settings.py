"""
Centralized game configuration.
"""
import os


class Display:
    """Represent a Display."""
    WIDTH = 1280
    HEIGHT = 720
    SIZE = (WIDTH, HEIGHT)
    FPS = 180
    TITLE = "Knightrock"


class World:
    """Represent a World."""
    TILE_SIZE = 64


class Physics:
    """Represent a Physics."""
    PLAYER_SPEED = 450
    GRAVITY = 3500
    JUMP_FORCE = 950
    DASH_SPEED = 2750
    DASH_DURATION = 0.12
    DASH_FRICTION = 15.0
    DASH_MAX_CHARGES = 2
    DASH_RECHARGE_TIME = 0.40
    DASH_PENALTY_TIME = 2.20
    DASH_GRAVITY_MULT = 0.0

    FLOOR_CONTROL = 25.0
    AIR_CONTROL = 12.0
    WALL_SLIDE_SPEED = 100.0
    COYOTE_DURATION = 0.12
    JUMP_BUFFER_DURATION = 0.10
    MAX_BLOCK_STAMINA = 0.75


class Combat:
    """Represent a Combat."""
    HURT_DURATION = 0.4
    PLAYER_HURT_DURATION = 0.12
    INVINCIBILITY_DURATION = 0.18
    BLOCK_STAMINA_COST_RATIO = 0.05
    BLOCK_KNOCKBACK_FACTOR = 0.3
    BLOCK_HEIGHT_REDUCTION = 16.0
    BLOCK_COOLDOWN_NORMAL = 0.5
    BLOCK_COOLDOWN_BROKEN = 2.0
    HITSTOP_BASE = 0.05
    HITSTOP_DAMAGE_FACTOR = 0.002
    HURT_DURATION_KNOCKBACK_SCALE = 0.0002
    STAGGER_DURATION = 0.25
    PLAYER_STAGGER_DURATION = 0.15
    SUPER_ARMOR_THRESHOLD = 3
    DAMAGE_TYPES = ["slash", "blunt", "pierce", "magic", "fire", "ice"]
    COMBO_WINDOW = 0.5


class Separation:
    """Represent a Separation."""
    SEARCH_INFLATE = 400
    SUB_STEP_SIZE = 16.0


class Debug:
    """Represent a Debug."""
    ENABLED = os.getenv("DEBUG", "0") == "1"
    FONT_SIZE = 24
    LABEL_FONT_SIZE = 16


class Simulation:
    """Settings for fixed timestep and network."""
    TICK_RATE = 60
    TICK_DURATION = 1.0 / TICK_RATE
    TIMESTEP = TICK_DURATION
    MAX_PREDICTION_FRAMES = 8
    ROLLBACK_FRAMES = 4
