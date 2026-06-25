"""
Centralized game configuration.

This module contains all tunable values used throughout the game.
Settings are grouped by domain to improve readability and maintenance.
"""


class Display:
    """Window and rendering settings."""

    WIDTH = 1280
    HEIGHT = 720
    SIZE = (WIDTH, HEIGHT)

    FPS = 180
    TITLE = "Knightrock"


class World:
    """World and level settings."""

    TILE_SIZE = 64


class Physics:
    """Movement and physics parameters."""

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


DEBUG = True