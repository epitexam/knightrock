"""A last-resort error screen that needs no assets at all.

When the game crashes before its display/UI exists -- a checkout without the
versioned font art, for instance -- the normal :class:`FatalErrorScene` cannot
be built. This screen opens its own medium-sized window, using pygame's
built-in font and the palette the menus use, so the player can read the whole
traceback, copy it, and choose what to do next.

It returns ``"quit"`` or ``"retry"``; the application owns the exit code and
the decision to rebuild the game.
"""

from __future__ import annotations

import contextlib
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pygame
import pygame.scrap

from src.core.colors import Colors
from src.core.display.detection import topology
from src.core.display.monitors import centre_on, fit_size, opening_size

# The menu palette (src/ui/styles.py mirrors Colors). No alarm-red dialog:
# this is the same dark panel, grey border and gold selection as the menus.
BACKGROUND = Colors.dark_grey
PANEL_BG = (20, 22, 26)
TEXT_BG = (16, 18, 22)
BORDER = Colors.panel_border
TEXT = Colors.text_muted
TITLE = Colors.text_title
ACCENT = Colors.gold
DARK_TEXT = Colors.black

GRACE_SECONDS = 0.35
ERROR_FILE = "knightrock-error.txt"
HINT = "Arrows / PageUp-Down / wheel: scroll · drag the bar · C: copy"

Choice = Literal["quit", "retry"]
Action = Choice | Literal["copy"]

_RESIZE_EVENTS = frozenset(
    event
    for name in ("VIDEORESIZE", "WINDOWRESIZED", "WINDOWSIZECHANGED")
    if (event := getattr(pygame, name, None)) is not None
)


@dataclass(frozen=True)
class Panel:
    """Rectangles and fonts, measured once for the current window."""

    box: pygame.Rect
    text_area: pygame.Rect
    rail: pygame.Rect
    copy: pygame.Rect
    quit: pygame.Rect
    menu: pygame.Rect
    font: pygame.font.Font
    small: pygame.font.Font
    title: pygame.Surface
    line: int


@dataclass
class State:
    """What changes while the screen is open."""

    scroll: int = 0
    dragging: bool = False
    drag_offset: int = 0
    notice: str = ""


def _window_geometry() -> tuple[tuple[int, int], tuple[int, int]]:
    """A medium window on the desktop holding the game window, centred there."""
    desk = topology()
    position: tuple[int, int] | None = None
    with contextlib.suppress(AttributeError, pygame.error):
        found = pygame.display.get_window_position()
        position = (found[0], found[1])
    monitor = desk.nearest(position) if position is not None else desk.primary
    base = opening_size(monitor)
    # Three fifths of the game's opening size: big enough to read, small
    # enough that the player still sees it is a separate, temporary window.
    size = fit_size(
        (min(960, max(640, base[0] * 3 // 5)), min(640, max(480, base[1] * 3 // 5))),
        monitor,
    )
    return size, centre_on(monitor, size)


def _place_window(position: tuple[int, int]) -> None:
    """Put the window where the game window would be. Best effort only."""
    with contextlib.suppress(AttributeError, pygame.error):
        pygame.Window.from_display_module().position = position
    with contextlib.suppress(AttributeError, pygame.error):
        pygame.display.set_window_position(position)


def _layout(surface: pygame.Surface) -> Panel:
    """Place the panel, the trace, the rail and the three buttons."""
    width, height = surface.get_size()
    margin = max(8, round(min(width, height) * 0.03))
    box = pygame.Rect(margin, margin, max(1, width - 2 * margin), max(1, height - 2 * margin))
    font = pygame.font.Font(None, max(14, height // 34))
    small = pygame.font.Font(None, max(12, height // 44))
    title_font = pygame.font.Font(None, max(16, height // 26))
    title = title_font.render("GAME ERROR", False, TITLE)

    copy = pygame.Rect(box.right - margin - 112, box.y + margin, 112, 26)
    button_w = max(120, min(200, box.width // 3 - 8))
    button_h = max(28, height // 16)
    buttons_y = box.bottom - margin - button_h - 20
    quit = pygame.Rect(box.centerx - button_w - 4, buttons_y, button_w, button_h)
    menu = pygame.Rect(box.centerx + 4, buttons_y, button_w, button_h)

    header_bottom = box.y + margin + title.get_height() + small.get_linesize() + 12
    line = font.get_linesize() + 2
    area = pygame.Rect(
        box.x + margin,
        header_bottom,
        max(1, box.width - 2 * margin - 18),
        max(line, quit.y - header_bottom - 10),
    )
    rail = pygame.Rect(area.right + 5, area.y, 8, area.height)
    return Panel(box, area, rail, copy, quit, menu, font, small, title, line)


def _summary(text: str) -> str:
    """The exception line, so the error is visible without scrolling."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "Unknown error"


def _fit(text: str, font: pygame.font.Font, width: int) -> str:
    """Ellipsize one line so it cannot run out of the panel."""
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text)[0] > width:
        text = text[:-1]
    return (text[:-1] + "…") if text else ""


def _render_trace(panel: Panel, text: str) -> pygame.Surface:
    """Wrap the whole traceback for the current width; scrolling clips it."""
    return panel.font.render(
        text.expandtabs(4), False, TEXT, wraplength=max(1, panel.text_area.width - 12)
    )


def _clamp(value: int, maximum: int) -> int:
    return max(0, min(value, maximum))


def _thumb(panel: Panel, scroll: int, maximum: int) -> pygame.Rect:
    """The scrollbar's thumb, proportional to how much is visible."""
    rail = panel.rail
    if maximum <= 0:
        return pygame.Rect(rail)
    height = max(
        18, round(rail.height * panel.text_area.height / (maximum + panel.text_area.height))
    )
    travel = rail.height - height
    return pygame.Rect(rail.x, rail.y + round(travel * scroll / maximum), rail.width, height)


def _scroll_at(y: int, panel: Panel, thumb_height: int, maximum: int) -> int:
    """Turn a pointer position on the rail into a scroll offset."""
    travel = max(1, panel.rail.height - thumb_height)
    fraction = (y - panel.rail.y - thumb_height / 2) / travel
    return round(fraction * maximum)


def _key_action(key: int, line: int, page: int, bottom: int) -> tuple[Action | None, int]:
    """A key either chooses an action or moves the text window."""
    if key in (pygame.K_ESCAPE, pygame.K_q):
        return "quit", 0
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_r):
        return "retry", 0
    if key == pygame.K_c:
        return "copy", 0
    steps = {
        pygame.K_DOWN: line,
        pygame.K_UP: -line,
        pygame.K_PAGEDOWN: page,
        pygame.K_PAGEUP: -page,
        pygame.K_END: bottom,
        pygame.K_HOME: -bottom,
    }
    return None, steps.get(key, 0)


def _pointer_action(
    event: pygame.event.Event, panel: Panel, state: State, maximum: int
) -> Action | None:
    """Click a button, or start a jump/drag on the rail."""
    actions: tuple[tuple[Action, pygame.Rect], ...] = (
        ("copy", panel.copy),
        ("quit", panel.quit),
        ("retry", panel.menu),
    )
    for action, rect in actions:
        if rect.collidepoint(event.pos):
            return action
    if not panel.rail.collidepoint(event.pos):
        return None
    thumb = _thumb(panel, state.scroll, maximum)
    if thumb.collidepoint(event.pos):
        state.drag_offset = event.pos[1] - thumb.y
    else:
        state.scroll = _clamp(_scroll_at(event.pos[1], panel, thumb.height, maximum), maximum)
    state.dragging = True
    return None


def _drag_to(event: pygame.event.Event, panel: Panel, state: State, maximum: int) -> None:
    if not state.dragging:
        return
    thumb_height = _thumb(panel, state.scroll, maximum).height
    y = event.pos[1] - state.drag_offset
    state.scroll = _clamp(_scroll_at(y, panel, thumb_height, maximum), maximum)


def _handle_event(
    event: pygame.event.Event,
    panel: Panel,
    state: State,
    maximum: int,
    *,
    grace: bool,
) -> Action | None:
    """One event, one action at most; scroll changes go into ``state``."""
    # A stale QUIT from the failed window setup must not close the screen the
    # player has not even seen yet.
    if grace:
        return None
    if event.type == pygame.QUIT:
        return "quit"
    if event.type == pygame.KEYDOWN:
        action, steps = _key_action(event.key, panel.line, panel.text_area.height, maximum)
        state.scroll = _clamp(state.scroll + steps, maximum)
        return action
    if event.type == pygame.MOUSEWHEEL:
        state.scroll = _clamp(state.scroll + event.y * panel.line, maximum)
        return None
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        state.dragging = False
    elif event.type == pygame.MOUSEMOTION:
        _drag_to(event, panel, state, maximum)
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        return _pointer_action(event, panel, state, maximum)
    return None


def _copy_error(text: str) -> str:
    """Put the whole traceback on the clipboard and save it as a file."""
    path = Path(tempfile.gettempdir()) / ERROR_FILE
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        return "Could not save the error to a file"
    try:
        put_text = getattr(pygame.scrap, "put_text", None)
        if put_text is not None:
            # pygame-ce 2.2+: one call, no explicit scrap init.
            put_text(text)
        else:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
    except AttributeError, pygame.error, TypeError:
        return f"Error saved to {path}"
    return f"Copied to clipboard · saved to {path}"


def _button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    font: pygame.font.Font,
    *,
    active: bool,
) -> None:
    """A menu-style row: gold bar behind the row a press would act on."""
    if active:
        surface.fill(ACCENT, rect)
        color = DARK_TEXT
    else:
        surface.fill(PANEL_BG, rect)
        color = TEXT
    pygame.draw.rect(surface, BORDER, rect, width=1, border_radius=3)
    glyph = font.render(label, False, color)
    surface.blit(
        glyph,
        (rect.centerx - glyph.get_width() // 2, rect.centery - glyph.get_height() // 2),
    )


def _draw(
    surface: pygame.Surface,
    panel: Panel,
    trace: pygame.Surface,
    state: State,
    summary: str,
    maximum: int,
) -> None:
    """Paint the panel, the clipped trace, the rail and the buttons."""
    surface.fill(BACKGROUND)
    pygame.draw.rect(surface, PANEL_BG, panel.box, border_radius=5)
    pygame.draw.rect(surface, BORDER, panel.box, width=1, border_radius=5)
    surface.blit(panel.title, (panel.box.x + 12, panel.box.y + 10))

    summary_y = panel.box.y + 10 + panel.title.get_height() + 6
    summary_width = panel.box.width - panel.copy.width - 24
    surface.blit(
        panel.small.render(_fit(summary, panel.small, summary_width), False, TEXT),
        (panel.box.x + 12, summary_y),
    )

    area = panel.text_area
    surface.fill(TEXT_BG, area)
    pygame.draw.rect(surface, BORDER, area, width=1)
    visible = min(area.height - 8, trace.get_height() - state.scroll)
    if visible > 0:
        source = pygame.Rect(0, state.scroll, area.width - 12, visible)
        surface.blit(trace, (area.x + 6, area.y + 5), source)

    pygame.draw.rect(surface, BORDER, panel.rail, border_radius=3)
    pygame.draw.rect(surface, TEXT, _thumb(panel, state.scroll, maximum), border_radius=3)

    pointer = pygame.mouse.get_pos()
    _button(surface, panel.copy, "Copy error", panel.small, active=panel.copy.collidepoint(pointer))
    _button(
        surface, panel.quit, "Quit the game", panel.font, active=panel.quit.collidepoint(pointer)
    )
    _button(
        surface,
        panel.menu,
        "Back to main menu",
        panel.font,
        active=panel.menu.collidepoint(pointer),
    )

    hint = state.notice or HINT
    surface.blit(
        panel.small.render(_fit(hint, panel.small, panel.box.width - 24), False, TEXT),
        (panel.box.x + 12, panel.menu.bottom + 6),
    )


def show_fatal_error(error: Exception) -> Choice:
    """Show the medium error window and wait for the player's choice."""
    if not pygame.font.get_init():
        pygame.font.init()
    text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    summary = _summary(text)
    size, position = _window_geometry()
    surface = pygame.display.set_mode(size, pygame.RESIZABLE)
    _place_window(position)
    panel = _layout(surface)
    trace = _render_trace(panel, text)
    maximum = max(0, trace.get_height() - panel.text_area.height)
    state = State()
    started = time.monotonic()
    clock = pygame.time.Clock()

    while True:
        grace = time.monotonic() - started < GRACE_SECONDS
        for event in pygame.event.get():
            if event.type in _RESIZE_EVENTS:
                surface = pygame.display.get_surface() or surface
                panel = _layout(surface)
                trace = _render_trace(panel, text)
                maximum = max(0, trace.get_height() - panel.text_area.height)
                state.scroll = _clamp(state.scroll, maximum)
                continue
            action = _handle_event(event, panel, state, maximum, grace=grace)
            if action == "copy":
                state.notice = _copy_error(text)
            elif action == "quit":
                return "quit"
            elif action == "retry":
                return "retry"

        _draw(surface, panel, trace, state, summary, maximum)
        pygame.display.flip()
        clock.tick(30)
