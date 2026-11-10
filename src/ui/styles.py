# ui/styles.py
"""Debug/HUD theme. Values mirror src.core.colors.Colors (audit F6.2)."""

from src.core.colors import Colors

PANEL_BG = Colors.panel_bg
PANEL_BORDER = Colors.panel_border
#: The one selection mark: a bar behind the row a press acts on, whichever
#: device put it there, and the colour it flashes after a change.
SELECTION_BG = Colors.gold
SELECTION_FLASH = (255, 240, 170)
SELECTION_TEXT = (20, 22, 26)
TEXT_MUTED = Colors.text_muted
TEXT_TITLE = Colors.text_title
TEXT_WARN = Colors.text_warn
TEXT_CRIT = Colors.text_crit
TEXT_OK = Colors.text_ok
GOLD = Colors.gold
