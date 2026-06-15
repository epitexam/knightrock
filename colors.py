from typing import ClassVar

Color = tuple[int, int, int]


class Colors:
    # Neutrals
    black: ClassVar[Color] = (0, 0, 0)
    dark_grey: ClassVar[Color] = (24, 28, 36)
    grey: ClassVar[Color] = (80, 85, 95)
    light_grey: ClassVar[Color] = (160, 163, 170)
    white: ClassVar[Color] = (255, 255, 255)
    off_white: ClassVar[Color] = (245, 245, 245)

    # Reds
    dark_red: ClassVar[Color] = (140, 30, 30)
    red: ClassVar[Color] = (235, 70, 70)
    light_red: ClassVar[Color] = (255, 130, 130)

    # Oranges
    dark_orange: ClassVar[Color] = (180, 90, 20)
    orange: ClassVar[Color] = (245, 140, 60)
    light_orange: ClassVar[Color] = (255, 190, 120)

    # Yellows
    dark_yellow: ClassVar[Color] = (180, 160, 30)
    yellow: ClassVar[Color] = (245, 230, 90)
    gold: ClassVar[Color] = (255, 200, 50)

    # Greens
    dark_green: ClassVar[Color] = (30, 120, 50)
    green: ClassVar[Color] = (56, 220, 90)
    light_green: ClassVar[Color] = (140, 240, 160)

    # Cyans
    dark_cyan: ClassVar[Color] = (30, 140, 150)
    cyan: ClassVar[Color] = (80, 220, 230)
    light_cyan: ClassVar[Color] = (160, 240, 245)

    # Blues
    dark_blue: ClassVar[Color] = (40, 45, 90)
    blue: ClassVar[Color] = (70, 110, 235)
    light_blue: ClassVar[Color] = (90, 130, 200)
    sky_blue: ClassVar[Color] = (135, 185, 255)

    # Purples
    dark_purple: ClassVar[Color] = (90, 40, 140)
    purple: ClassVar[Color] = (170, 85, 235)
    light_purple: ClassVar[Color] = (210, 160, 255)
    pink: ClassVar[Color] = (255, 120, 200)
