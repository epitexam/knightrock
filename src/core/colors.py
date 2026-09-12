"""
Shared color constants and palettes.

``src/ui/styles.py`` remains the canonical theme for debug/HUD panels
(audit F6.2); ``Colors`` is the gameplay/rendering palette. To avoid
two diverging sources of truth, the theme aliases below re-export the
same values.
"""
from typing import ClassVar

Color = tuple[int, int, int]
ColorRGBA = tuple[int, int, int, int]


class Colors:
    """Define shared color constants used by the game rendering and UI."""

    black: ClassVar[Color] = (0, 0, 0)
    dark_grey: ClassVar[Color] = (24, 28, 36)
    grey: ClassVar[Color] = (80, 85, 95)
    light_grey: ClassVar[Color] = (160, 163, 170)
    white: ClassVar[Color] = (255, 255, 255)
    off_white: ClassVar[Color] = (245, 245, 245)

    dark_red: ClassVar[Color] = (140, 30, 30)
    red: ClassVar[Color] = (235, 70, 70)
    light_red: ClassVar[Color] = (255, 130, 130)

    dark_orange: ClassVar[Color] = (180, 90, 20)
    orange: ClassVar[Color] = (245, 140, 60)
    light_orange: ClassVar[Color] = (255, 190, 120)

    dark_yellow: ClassVar[Color] = (180, 160, 30)
    yellow: ClassVar[Color] = (245, 230, 90)
    gold: ClassVar[Color] = (255, 200, 50)

    dark_green: ClassVar[Color] = (30, 120, 50)
    green: ClassVar[Color] = (56, 220, 90)
    light_green: ClassVar[Color] = (140, 240, 160)

    dark_cyan: ClassVar[Color] = (30, 140, 150)
    cyan: ClassVar[Color] = (80, 220, 230)
    light_cyan: ClassVar[Color] = (160, 240, 245)

    dark_blue: ClassVar[Color] = (40, 45, 90)
    blue: ClassVar[Color] = (70, 110, 235)
    light_blue: ClassVar[Color] = (200, 220, 255)
    sky_blue: ClassVar[Color] = (135, 185, 255)

    dark_purple: ClassVar[Color] = (90, 40, 140)
    purple: ClassVar[Color] = (170, 85, 235)
    light_purple: ClassVar[Color] = (210, 160, 255)
    pink: ClassVar[Color] = (255, 120, 200)

    # --- Debug/HUD theme aliases (single source; see src/ui/styles.py) ---
    panel_bg: ClassVar[ColorRGBA] = (20, 22, 26, 220)
    panel_border: ClassVar[Color] = (90, 100, 110)
    text_muted: ClassVar[Color] = (185, 192, 198)
    text_title: ClassVar[Color] = (215, 220, 224)
    text_warn: ClassVar[Color] = (200, 150, 90)
    text_crit: ClassVar[Color] = (190, 100, 100)
    text_ok: ClassVar[Color] = (120, 170, 140)

    debug_hitbox: ClassVar[Color] = (80, 140, 210)
    debug_hurtbox: ClassVar[Color] = (80, 210, 120)
    debug_attack_box: ClassVar[Color] = (230, 120, 60)


#: Valid ``LevelConfig.bg`` names: avoids ``getattr(Colors, cfg.bg)``
#: typos by failing closed on unknown values (audit F5.1).
BG_COLORS: dict[str, Color] = {
    "black": Colors.black,
    "dark_grey": Colors.dark_grey,
    "grey": Colors.grey,
    "light_grey": Colors.light_grey,
    "white": Colors.white,
    "off_white": Colors.off_white,
    "dark_red": Colors.dark_red,
    "red": Colors.red,
    "light_red": Colors.light_red,
    "dark_orange": Colors.dark_orange,
    "orange": Colors.orange,
    "light_orange": Colors.light_orange,
    "dark_yellow": Colors.dark_yellow,
    "yellow": Colors.yellow,
    "gold": Colors.gold,
    "dark_green": Colors.dark_green,
    "green": Colors.green,
    "light_green": Colors.light_green,
    "dark_cyan": Colors.dark_cyan,
    "cyan": Colors.cyan,
    "light_cyan": Colors.light_cyan,
    "dark_blue": Colors.dark_blue,
    "blue": Colors.blue,
    "light_blue": Colors.light_blue,
    "sky_blue": Colors.sky_blue,
    "dark_purple": Colors.dark_purple,
    "purple": Colors.purple,
    "light_purple": Colors.light_purple,
    "pink": Colors.pink,
}