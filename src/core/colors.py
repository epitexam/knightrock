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
    debug_hurtbox_zones: ClassVar[tuple[Color, ...]] = (
        (80, 210, 120),
        (90, 170, 235),
        (235, 200, 90),
    )
    debug_attack_box: ClassVar[Color] = (230, 120, 60)
    debug_shape_outline: ClassVar[Color] = (20, 22, 28)
    debug_broadphase: ClassVar[Color] = (80, 220, 230)
    debug_sweep: ClassVar[Color] = (170, 130, 245)
    debug_anchor: ClassVar[Color] = (255, 255, 255)
    debug_static: ClassVar[Color] = (140, 145, 155)
    debug_velocity: ClassVar[Color] = (245, 230, 90)
    debug_otg: ClassVar[Color] = (80, 220, 230)
    debug_juggle: ClassVar[Color] = (170, 85, 235)


class FXColors:
    """The FX plane's palette, kept apart from the gameplay colours.

    A particle is judged against the whole frame rather than against the
    sprite it sits next to, so its colours answer a different question than
    ``Colors`` does: a bright body, a dark ink rim so it separates from a
    bright sky, and a near-white core for anything that has to read as light
    rather than as matter.
    """

    ink: ClassVar[Color] = (26, 22, 32)
    ink_warm: ClassVar[Color] = (58, 24, 16)

    dust: ClassVar[Color] = (184, 179, 170)
    """The mass of a dust cloud.

    A shade under the near-white this used to be, and cooler. At 198 the puffs
    read as the brightest thing in the plane and pulled the eye off the
    fighter standing in them, which is the one thing a landing dust has no
    business doing. A puff is a register against the tiles, not a light source.
    """
    dust_lit: ClassVar[Color] = (238, 234, 226)
    """The lit edge of a dust cloud.

    This is an *edge* now, not a lobe. It used to be a disc of this colour set
    into the top-left of the cloud, and a round patch of light inside a round
    mass is the oldest convention in children's illustration -- it is how a
    bubble, a pearl and a cartoon cloud are all drawn, and it is the single
    thing that made the puffs read as drawn-for-children rather than as a
    material. The light is now one pixel of rim, laid along the top-left of
    the whole silhouette, which is how a volume is described without an
    ellipse of pure white sitting on it.
    """
    dust_deep: ClassVar[Color] = (74, 69, 63)
    """The dark side of a dust cloud: its ink rim and its underbelly.

    It used to sit 44 units under the body, which at a one-pixel outline is
    barely a shade -- against a bright background the cloud lost its edge and
    read as a smudge. It is now close to the ink the rest of the plane uses,
    which is both the fix for that smudge and the reason the puff stopped
    looking soft: a 110-unit step at one pixel is an edge, where a 44-unit one
    is a stain.

    It carries two jobs rather than one. A grown pass puts it a pixel outside
    the silhouette, where it separates the mark from the tiles behind it, and
    a second pass puts it a pixel *inside* and below, where it is the shadow
    the mass sits in. One tone doing both is what keeps the puff at three
    tones; four would be a stripe pattern at this scale.
    """
    dust_shade: ClassVar[Color] = (128, 122, 113)
    """The shadow the landing sheet sits in, a shade under its own body.

    Separate from ``dust_deep`` because the rim and the shadow are different
    jobs, and painting both in the dark tone made the sheet read as a
    hamburger. A one-pixel rim outside the silhouette is an edge, and an edge
    wants to be dark; the shadow *under* the mass wants to be a step below the
    body, because it is the body's own tone falling off rather than a line
    drawn round it. Sharing the tone filled the gaps between the lobes along
    the bottom into a solid three-pixel band, and a solid band across the base
    of a mark is a stripe.

    It is the one tone in the plane that is neither a line nor a light, and it
    is what makes the sheet sit on the floor instead of float over it.
    """
    dust_grain: ClassVar[Color] = (126, 120, 111)
    """A loose speck thrown out of a cloud.

    Between the body and the dark side, and never lighter than the body: grains
    are the shadowed debris a kick scatters, and a spec field of highlights
    reads as glitter. The landing puff and the dash trail used to carry
    nothing but themselves, which is why they read as one solid mass -- a
    silhouette of dust thrown at a floor has loose matter around it, and this
    is the tone that matter is drawn in.
    """

    speed_ghost: ClassVar[Color] = (228, 238, 250)
    """The hue the dash afterimages are knocked back to.

    Multiplied over the sprite's own greyscale, so this is close to white and
    barely darkens: the ghost keeps the character's shading, its outline and
    its silhouette, and loses only the hue. A near-black fill was the other
    reading of "noir et blanc" and it was wrong -- a flat fill throws away
    every one of those, and five of them in a row are five blobs rather than
    five copies of a fighter.
    """
    speed_tint: ClassVar[Color] = (100, 200, 255)
    """The dash's speed colour, shared by the sprite and the marks around it.

    This one member is additive: the renderer adds it to the dashing sprite to
    brighten it, and the ghosts photograph that result, so every ghost is
    already this colour. It was a literal in the renderer and nothing else in
    the repository agreed with it.

    Additive and opaque are not the same colour. Added to a sprite, this
    lightens it; filled in, the same triple is a saturated cyan that reads as
    a stain. So a mark drawn in this colour needs its own opaque member, and
    the dash has none: the only mark it has is the sprite itself.
    """

    guard_spark: ClassVar[Color] = (96, 226, 238)
    guard_core: ClassVar[Color] = (226, 250, 255)
    parry_spark: ClassVar[Color] = (255, 206, 64)
    parry_core: ClassVar[Color] = (255, 252, 236)
    break_spark: ClassVar[Color] = (244, 96, 72)
    break_core: ClassVar[Color] = (255, 210, 144)

    star: ClassVar[Color] = (255, 214, 84)
    star_core: ClassVar[Color] = (255, 250, 224)

    vortex: ClassVar[Color] = (186, 84, 226)
    vortex_ink: ClassVar[Color] = (54, 18, 72)

    sweat: ClassVar[Color] = (150, 240, 245)
    sweat_ink: ClassVar[Color] = (20, 60, 90)
    sweat_shine: ClassVar[Color] = (240, 255, 255)

    decal: ClassVar[Color] = (168, 160, 148)
    decal_ink: ClassVar[Color] = (92, 86, 78)
    shield_arc: ClassVar[Color] = (132, 232, 242)
    shield_ink: ClassVar[Color] = (18, 74, 96)


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
