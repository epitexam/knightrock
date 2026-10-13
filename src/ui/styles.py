# ui/styles.py
"""Debug/HUD theme. Values mirror src.core.colors.Colors (audit F6.2)."""

from src.core.colors import Colors

PANEL_BG = Colors.panel_bg
PANEL_BORDER = Colors.panel_border
#: The outline around the row the pointer is on, when that is not the row a key
#: press would act on. A different device's claim, so a different mark: the `>`
#: and the amber text both say "a key press acts here", and nothing used to say
#: "the cursor is here".
POINTER_OUTLINE = Colors.gold
TEXT_MUTED = Colors.text_muted
TEXT_TITLE = Colors.text_title
TEXT_WARN = Colors.text_warn
TEXT_CRIT = Colors.text_crit
TEXT_OK = Colors.text_ok
GOLD = Colors.gold
