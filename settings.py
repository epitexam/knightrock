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

    FPS = 60
    TITLE = "Knightrock"


class World:
    """World and level settings."""

    TILE_SIZE = 64


class Animation:
    """Animation-related settings."""

    SPEED = 6


class Physics:
    """Movement and physics parameters."""

    PLAYER_SPEED = 450
    GRAVITY = 3500
    JUMP_FORCE = 950