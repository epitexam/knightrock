"""Every dimension of the interface, in one place, derived from one number.

There is exactly one input -- the scale, which is the player's preference times
the render target's pixel density -- and everything else is a multiple of it.
The alternative is what the interface used to be: a font size that scaled, next
to paddings and gaps and a capped row height that did not. On a window where the
density is 1.889 that produced a panel 900 pixels wide holding 49-pixel text in
34-pixel rows, which is not a cosmetic problem -- the clickable band of a row
recovered 44% of the text of the row above it, so clicking what you read
activated something else.

So: no literal layout number outside this file. A view asks for a token, the
token is multiplied once, and a test can state the whole interface as a ratio
between two scales rather than as a list of pixels.
"""

from dataclasses import dataclass

from src.ui.scale import checked_ui_scale, font_size

#: Design sizes, in the pixels of a 1152x648 picture. They are *not* pixels
#: until :class:`Metrics` multiplies them, and no view may use them directly.
DESIGN_MARGIN = 12
DESIGN_PADDING = 18
DESIGN_GAP = 18
#: The air that opens a new group inside a list -- above the block of options
#: at the bottom of a mapping screen. Bigger than a gap on purpose: a gap says
#: "these two are not nested", and this has to say "everything below this is
#: something else" from across a table.
DESIGN_SECTION_GAP = 30
DESIGN_TITLE_GAP = 12
DESIGN_BORDER = 2
DESIGN_FOOTER_LINE = 20
DESIGN_ROW = 30
DESIGN_HEAD = 102
DESIGN_SMALL_TEXT = 18
DESIGN_ITEM_TEXT = 22
DESIGN_TITLE_TEXT = 42

#: The option panel is a second family, larger than the grid: a menu is read one
#: row at a time from further away than a mapping table, and its rows are the
#: only things a player has to aim at. Same scale, different design sizes.
DESIGN_PANEL_PADDING = 28
DESIGN_PANEL_TITLE_GAP = 16
DESIGN_PANEL_ROW = 40
DESIGN_PANEL_TITLE_TEXT = 48
DESIGN_PANEL_ITEM_TEXT = 32
DESIGN_VALUE_GAP = 24
DESIGN_PANEL_MIN_WIDTH = 240

#: The smallest a row may be, as a multiple of the design row. A list that
#: cannot fit is allowed to get tighter -- but never tighter than the text it
#: has to hold, which is what the caller resolves before it ever gets here.
MIN_ROW_RATIO = 0.6

#: The smallest text this interface will draw, as a multiple of its design size.
#: Below this, a control label stops being readable, and a control you cannot
#: read is a control you cannot use.
MIN_TEXT_RATIO = 0.62


@dataclass(frozen=True)
class Metrics:
    """The interface's dimensions for one scale."""

    scale: float

    @classmethod
    def for_scale(cls, scale: float) -> Metrics:
        return cls(checked_ui_scale(scale))

    def px(self, design: float) -> int:
        """A design dimension in whole target pixels, never below one."""
        return max(1, round(design * self.scale))

    def font(self, design: int) -> int:
        """A design font size in whole target pixels."""
        return font_size(design, self.scale)

    # -- tokens -------------------------------------------------------------
    # Named, because ``metrics.gap`` says what it is and ``metrics.px(18)`` is a
    # puzzle the reader has to solve against the file that used 18.

    @property
    def margin(self) -> int:
        """Air between the panel and the screen edge."""
        return self.px(DESIGN_MARGIN)

    @property
    def padding(self) -> int:
        """Air inside the panel, around its content."""
        return self.px(DESIGN_PADDING)

    @property
    def gap(self) -> int:
        """Air between two things that are not nested: columns, panel and list."""
        return self.px(DESIGN_GAP)

    @property
    def section_gap(self) -> int:
        """Air that opens a new group inside a list, before its first row."""
        return self.px(DESIGN_SECTION_GAP)

    @property
    def title_gap(self) -> int:
        """Air under the title."""
        return self.px(DESIGN_TITLE_GAP)

    @property
    def border(self) -> int:
        """The panel outline."""
        return self.px(DESIGN_BORDER)

    @property
    def footer_line(self) -> int:
        """One line of hint text under the list."""
        return self.px(DESIGN_FOOTER_LINE)

    @property
    def row(self) -> int:
        """A comfortable row: one text line plus the padding around it."""
        return self.px(DESIGN_ROW)

    @property
    def head(self) -> int:
        """The fixed block above the list: title, subtitle and column headers."""
        return self.px(DESIGN_HEAD)

    # -- the option panel's family -------------------------------------------

    @property
    def panel_padding(self) -> int:
        return self.px(DESIGN_PANEL_PADDING)

    @property
    def panel_title_gap(self) -> int:
        return self.px(DESIGN_PANEL_TITLE_GAP)

    @property
    def panel_row(self) -> int:
        return self.px(DESIGN_PANEL_ROW)

    @property
    def panel_title_text(self) -> int:
        return self.font(DESIGN_PANEL_TITLE_TEXT)

    @property
    def panel_item_text(self) -> int:
        return self.font(DESIGN_PANEL_ITEM_TEXT)

    @property
    def value_gap(self) -> int:
        """The gutter between a menu row's label and its value."""
        return self.px(DESIGN_VALUE_GAP)

    @property
    def panel_min_width(self) -> int:
        """Below this a menu is a list of one-word rows, so it stops shrinking."""
        return self.px(DESIGN_PANEL_MIN_WIDTH)

    @property
    def title_text(self) -> int:
        return self.font(DESIGN_TITLE_TEXT)

    @property
    def item_text(self) -> int:
        return self.font(DESIGN_ITEM_TEXT)

    @property
    def small_text(self) -> int:
        return self.font(DESIGN_SMALL_TEXT)

    # -- the same sizes, at a scale a view had to give up -------------------
    # A list that does not fit asks for smaller text rather than taller rows, so
    # the three sizes are readable at any scale, not only at the setting's.

    def title_text_at(self, text_scale: float) -> int:
        return font_size(DESIGN_TITLE_TEXT, text_scale)

    def item_text_at(self, text_scale: float) -> int:
        return font_size(DESIGN_ITEM_TEXT, text_scale)

    def small_text_at(self, text_scale: float) -> int:
        return font_size(DESIGN_SMALL_TEXT, text_scale)
