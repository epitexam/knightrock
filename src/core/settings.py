"""
Centralized game configuration and constants.
"""
import os


class Display:
    """Display and rendering settings."""
    WIDTH = 1440
    HEIGHT = 900
    SIZE = (WIDTH, HEIGHT)
    FPS = 180
    TITLE = "Knightrock"


class World:
    """World and tilemap dimensions."""
    TILE_SIZE = 64


class Physics:
    """Physics and movement constants."""
    PLAYER_SPEED = 450
    GRAVITY = 2000.0
    FALL_GRAVITY = 2800.0
    JUMP_FORCE = 750.0
    MAX_FALL_SPEED = 1500.0
    DASH_SPEED = 1500
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
    
    # Drag coefficients
    DRAG_COEFFICIENT = 0.08
    FALL_DRAG_COEFFICIENT = 0.12
    MAX_SLIDE_SPEED = 80.0
    
    HURT_FRICTION = 5.0
    KNOCKBACK_FRICTION = 8.0
    STAGGER_FRICTION = 8.0
    DASH_AIR_CONTROL = 100.0


class Combat:
    """Combat, damage, and stagger mechanics."""
    HURT_DURATION = 0.4
    PLAYER_HURT_DURATION = 0.12
    INVINCIBILITY_DURATION = 0.18
    BLOCK_STAMINA_COST_RATIO = 0.05
    BLOCK_KNOCKBACK_FACTOR = 0.3
    BLOCK_HEIGHT_REDUCTION = 16.0
    BLOCK_COOLDOWN_NORMAL = 0.5
    BLOCK_COOLDOWN_BROKEN = 2.0
    BLOCK_AIR_DRAIN_MULT = 2.0
    HITSTOP_BASE = 0.05
    HITSTOP_DAMAGE_FACTOR = 0.002
    HURT_DURATION_KNOCKBACK_SCALE = 0.0002
    STAGGER_DURATION = 0.25
    PLAYER_STAGGER_DURATION = 0.15
    SUPER_ARMOR_THRESHOLD = 3
    DAMAGE_TYPES = ["slash", "blunt", "pierce", "magic", "fire", "ice"]
    COMBO_WINDOW = 0.5
    CONTACT_DAMAGE_THRESHOLD = 300.0


class Separation:
    """Collision separation and resolution constants."""
    SEARCH_INFLATE = 400
    SUB_STEP_SIZE = 16.0
    STRENGTH = 0.65
    VERTICAL_STACK_RATIO = 0.4


class Debug:
    """Debug overlay settings."""
    ENABLED = os.getenv("DEBUG", "0") == "1"
    FONT_SIZE = 24
    LABEL_FONT_SIZE = 16


class Simulation:
    """Fixed timestep and simulation loop settings."""
    TICK_RATE = 60
    TICK_DURATION = 1.0 / TICK_RATE
    TIMESTEP = TICK_DURATION
    MAX_PREDICTION_FRAMES = 8
    ROLLBACK_FRAMES = 4
