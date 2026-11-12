"""Every word the player-facing menus say, in one table.

English only for now. A translation is another table with the same keys and
one more line in :data:`LANGUAGES`; nothing else changes, because the screens
ask for a key and never hold a sentence of their own. ``{name}`` fields are
filled by :func:`t`.

The debug overlay is not in here: it is for whoever is developing the game,
and it is not translated.
"""

from __future__ import annotations

ENGLISH: dict[str, str] = {
    # -- titles
    "title.game": "KNIGHTROCK",
    "title.options": "OPTIONS",
    "title.video": "VIDEO",
    "title.controls": "CONTROLS",
    "title.pause": "PAUSE",
    "title.game_over": "GAME OVER",
    "title.victory": "VICTORY",
    "title.levels": "SELECT LEVEL",
    "title.quit": "QUIT?",
    "title.window_size": "WINDOW SIZE",
    "title.fit": "PICTURE FIT",
    "title.frame_limit": "FRAME LIMIT",
    "title.ui_scale": "UI SCALE",
    "title.panel_scale": "DEBUG PANEL SCALE",
    "title.menu_controls": "MENU CONTROLS",
    "title.gameplay_controls": "GAMEPLAY CONTROLS",
    # -- common rows
    "row.back": "Back",
    "row.options": "Options",
    "row.levels": "Level select",
    "row.quit": "Quit",
    "row.play": "Play",
    "row.continue": "Continue (level {level})",
    "row.new_game": "New game",
    "row.resume": "Resume",
    "row.retry": "Retry",
    "row.to_menu": "Back to menu",
    "row.main_menu": "Main menu",
    "row.level": "Level {level}",
    "row.video": "Video settings",
    "row.controls": "Controls",
    "row.menu_controls": "Menu controls",
    "row.gameplay_controls": "Gameplay controls",
    "row.quit_no": "No, go back",
    "row.quit_yes": "Yes, quit",
    # -- the Video screen
    "section.window": "WINDOW",
    "section.picture": "PICTURE",
    "section.performance": "PERFORMANCE",
    "section.interface": "INTERFACE",
    "video.size": "Window size",
    "video.fullscreen": "Fullscreen",
    "video.fit": "Picture fit",
    "video.vsync": "VSync",
    "video.frame_limit": "Frame limit",
    "video.ui_scale": "UI scale",
    "video.panel_scale": "Debug panel scale",
    "video.reset": "Reset video settings",
    "video.readout": "Picture",
    "value.on": "On",
    "value.off": "Off",
    "value.uncapped": "Uncapped",
    "value.size": "{width} x {height}",
    "note.size": "Drag the window to any size. This list offers sizes that fit this screen.",
    "note.fullscreen": "Covers the screen without changing its mode. Alt+Enter at any time.",
    "note.vsync.on": "Requested from the driver: frames follow the {rate} Hz screen.",
    "note.vsync.on.unknown": "Requested from the driver: frames follow the screen.",
    "note.vsync.off": "Frames are paced by the frame limit.",
    "note.frame_limit": "How many frames a second, at most.",
    "note.frame_limit.vsync": "Ignored while VSync is on: the screen sets the pace.",
    "note.ui_scale": "Text at {effective:.1f}x on this screen.",
    "note.reset": "Back to the defaults. The window size and your controls are kept.",
    "note.readout": "What the game draws: the target, its density, and any bars.",
    # -- the fit policies, as the player reads them
    "fit.auto": "Auto",
    "fit.bars": "Black bars",
    "fit.integer": "Sharp pixels",
    "fit.zoom": "Fill screen",
    "fit.note.auto": "Sharp pixels when the bars stay small, black bars otherwise.",
    "fit.note.bars": "Shows the whole picture, with black bars on the sides.",
    "fit.note.integer": "Every art pixel an exact square. Can leave wide bars.",
    "fit.note.zoom": "Fills the window and crops the edges of the picture.",
    "fit.note.integer.small": "Not on this window: too small to hold a whole block.",
    "fit.note.integer.same": "No change here: this window already is a whole multiple.",
    # -- the option lists
    "size.free": "free size",
    "size.free.note": "no stored size: the window keeps whatever size you drag it to",
    "size.largest": "as large as fits, title bar included",
    "size.whole": "whole multiple: sharpest with the integer fit",
    "size.current": "current",
    "size.current_after": "{note} · current",
    "size.too_large": "too large for this screen ({width}x{height})",
    "size.earlier": "the size you chose earlier",
    "limit.uncapped": "uncapped",
    "limit.note.uncapped": "as fast as the machine draws",
    "limit.note.30": "saves power, and a lot of it",
    "limit.note.60": "one frame per simulation tick",
    "limit.note.120": "smoother, if the machine can hold it",
    "limit.note.vsync": "ignored while VSync is on",
    "scale.note": "text at {effective:.2f}x on this screen",
    "panel.note.small": "small enough for the whole stack on a small window",
    # -- the Controls screens
    "controls.move_up": "Move up",
    "controls.move_down": "Move down",
    "controls.move_left": "Move left",
    "controls.move_right": "Move right",
    "controls.confirm": "Confirm",
    "controls.back": "Back",
    "controls.cancel": "Cancel",
    "controls.pause": "Pause",
    "controls.page_up": "Page up",
    "controls.page_down": "Page down",
    "controls.first_row": "First row",
    "controls.last_row": "Last row",
    "controls.new_game": "New game shortcut",
    "controls.crouch": "Crouch / fast fall",
    "controls.jump": "Jump",
    "controls.dash": "Dash",
    "controls.attack_1": "Attack 1",
    "controls.attack_2": "Attack 2",
    "controls.attack_3": "Attack 3",
    "controls.attack_4": "Attack 4",
    "controls.guard": "Guard",
    "controls.reset_position": "Reset (debug)",
    "controls.invert_y": "Invert stick Y",
    "controls.reset": "Reset to defaults",
    "controls.column.keyboard": "KEYBOARD / MOUSE",
    "controls.column.gamepad": "GAMEPAD",
    "controls.inverted": "Inverted",
    "controls.normal": "Normal",
    "controls.unbound": "Unbound",
    "controls.keyboard_only": "Keyboard only",
    "controls.press_key": "Press a key…",
    "controls.press_pad": "Press a button…",
    "controls.with_mouse": "{keys} / mouse {button}",
    "controls.mouse_button": "mouse button {button}",
    "pad.button": "Button {index}",
    "pad.axis": "Axis {index}",
    "pad.hat": "D-pad",
    "pad.hat.numbered": "D-pad {index}",
    "status.capture": "{back} cancels · Delete unbinds a key",
    "status.cancelled": "Capture cancelled",
    "status.inverted": "Stick Y inverted",
    "status.normal": "Stick Y normal",
    "status.keyboard_only": "This shortcut is keyboard-only",
    "status.defaults": "Defaults restored",
    "status.unbound": "{label}: keyboard unbound",
    "status.bound": "{label} → {binding}",
    "status.back_reserved": "That button is Back's; rebind Back first",
    # -- help lines; {move} {change} {select} {back} are the device's keys
    "footer.page": "{move} move · {select} select · {back} back",
    "footer.values": "{move} move · {change} change · {back} back",
    "footer.page_keys": "PgDn page",
    "footer.controls": "{move} row · {change} column · {select} assign · {back} back",
}

#: The tables, by language code. The first is the fallback for a missing key.
LANGUAGES: dict[str, dict[str, str]] = {"en": ENGLISH}

#: The language in force.
_language = "en"


def set_language(code: str) -> None:
    """Switch the table every later :func:`t` reads. Unknown codes are refused."""
    global _language
    if code not in LANGUAGES:
        raise ValueError(f"No text table for {code!r}")
    _language = code


def t(key: str, **values: object) -> str:
    """The text for ``key`` in the language in force, with its fields filled."""
    table = LANGUAGES[_language]
    template = table.get(key) or ENGLISH.get(key)
    if template is None:
        raise KeyError(f"No text for {key!r}")
    return template.format(**values) if values else template


#: The keys each device presses, for the help lines.
DEVICE_KEYS: dict[str, dict[str, str]] = {
    "keyboard": {"move": "↑↓", "change": "←→", "select": "Enter", "back": "Esc"},
    "gamepad": {"move": "D-pad", "change": "◀▶", "select": "A", "back": "B"},
}
