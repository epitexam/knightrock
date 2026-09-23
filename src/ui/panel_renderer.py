import warnings
from collections import OrderedDict

import pygame

from src.core.settings import Debug
from src.ui.styles import PANEL_BG, PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_TITLE

#: Close button geometry (px): box side, inset from the panel corner, and the
#: air kept left of the box so the ``×`` never sits on the title or first line.
PANEL_CLOSE_BOX = 14
PANEL_CLOSE_INSET = 4
PANEL_CLOSE_GAP = 6

#: Margin (px) kept between the panels and the display border: shared by the
#: column flow and by the clamping of a manually dropped panel.
PANEL_MARGIN = 10


def close_box_rect(right: int, top: int) -> pygame.Rect:
    """Hit box of a panel's ``×``, inset from that panel's top-right corner.

    Shared by the interaction (hit tests, ``×`` geometry) and the renderer
    (drawing) so the clickable area is pixel-identical to the glyph seen on
    screen.
    """
    return pygame.Rect(
        right - PANEL_CLOSE_BOX - PANEL_CLOSE_INSET,
        top + PANEL_CLOSE_INSET,
        PANEL_CLOSE_BOX,
        PANEL_CLOSE_BOX,
    )


class PanelInteraction:
    """Mouse interaction state for the debug panels (close + drag & drop).

    Panels register their screen rect each frame under a stable id (their
    semantic name: ``"combat"``, ``"stats"``...). Closing hides a panel
    until F5 resets the set; dragging stores an override position the
    layout applies next frame, and the flow packs the remaining panels
    around it — the layout stays responsive by construction.
    """

    def __init__(self) -> None:
        self.closed: set[str] = set()
        #: Manual (dropped) top-left positions, applied instead of the flow slot.
        self.positions: dict[str, tuple[int, int]] = {}
        #: Rects painted by the previous frame (what the player can see): the
        #: hit tests and the ``×`` hover all run against this set.
        self.panels: dict[str, pygame.Rect] = {}
        self.drag_id: str | None = None
        self._drag_offset: tuple[int, int] = (0, 0)
        self._drag_target: tuple[int, int] = (0, 0)
        self._pending: dict[str, pygame.Rect] = {}

    def begin_frame(self) -> None:
        """Promote the rects drawn last frame and start a fresh registry.

        A panel skipped by this frame's draw pass (closed with its ``×``, or
        the whole layer hidden with F5) then drops out of the interactive
        set: its ghost never keeps swallowing clicks where it *used* to be.
        """
        self.panels = self._pending
        self._pending = {}

    def register(self, panel_id: str, rect: pygame.Rect) -> None:
        """Remember ``panel_id``'s drawn rect for the next frame's hit tests."""
        self._pending[panel_id] = rect

    def position_for(self, panel_id: str) -> tuple[int, int] | None:
        """Override position to use this frame, if any (drag beats drop)."""
        if self.drag_id == panel_id:
            return self._drag_target
        return self.positions.get(panel_id)

    def start_drag(self, panel_id: str, mouse_pos: tuple[int, int]) -> None:
        """Begin dragging ``panel_id`` from wherever the cursor grabbed it."""
        rect = self.panels.get(panel_id)
        if rect is None:
            return
        self.cancel_drag()
        self.drag_id = panel_id
        self._drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
        self._drag_target = rect.topleft

    def move_drag(self, mouse_pos: tuple[int, int]) -> None:
        """Track the cursor while dragging (clamped later, by the layout)."""
        if self.drag_id is None:
            return
        self._drag_target = (
            mouse_pos[0] - self._drag_offset[0],
            mouse_pos[1] - self._drag_offset[1],
        )

    def end_drag(self) -> None:
        """Release the dragged panel: the cursor's last position is the drop.

        The target is persisted rather than the last painted rect, so a drag
        completed within a single frame — press, move and release all seen
        before the next draw — still lands where the cursor left it. Both
        draw paths clamp the position, so an off-screen drop folds back
        inside the display on the very next frame.
        """
        if self.drag_id is not None:
            self.positions[self.drag_id] = self._drag_target
        self._clear_drag()

    def cancel_drag(self) -> None:
        """Discard an in-flight drag without persisting its target."""
        self._clear_drag()

    def _clear_drag(self) -> None:
        self.drag_id = None
        self._drag_offset = (0, 0)
        self._drag_target = (0, 0)

    def set_position(self, panel_id: str, position: tuple[int, int]) -> None:
        self.positions[panel_id] = position
        if self.drag_id == panel_id:
            self._drag_target = position

    def set_closed(self, panel_id: str, closed: bool = True) -> None:
        """Hide (or restore) one panel until the next F5 reset.

        The panel is dropped from the hit registry immediately: no ghost
        frame where an invisible panel could still swallow a click.
        """
        if closed:
            self.closed.add(panel_id)
            self.positions.pop(panel_id, None)
            self.panels.pop(panel_id, None)
            self._pending.pop(panel_id, None)
            if self.drag_id == panel_id:
                self.cancel_drag()
        else:
            self.closed.discard(panel_id)

    def clamp_positions(self, size: tuple[int, int], *, margin: int = PANEL_MARGIN) -> None:
        width, height = size
        max_x = max(margin, width - margin)
        max_y = max(margin, height - margin)
        self.positions = {
            panel_id: (
                max(margin, min(position[0], max_x)),
                max(margin, min(position[1], max_y)),
            )
            for panel_id, position in self.positions.items()
        }
        self.cancel_drag()

    def reset(self) -> None:
        """F5: restore every closed panel and clear drops and drags."""
        self.closed.clear()
        self.positions.clear()
        self._clear_drag()

    def close_rect(self, panel_id: str) -> pygame.Rect | None:
        """Hit box of ``panel_id``'s ``×`` button, if the panel is drawn."""
        rect = self.panels.get(panel_id)
        if rect is None:
            return None
        return close_box_rect(rect.right, rect.top)

    def is_closed(self, panel_id: str) -> bool:
        """Whether ``panel_id`` was closed (until the next :meth:`reset`)."""
        return panel_id in self.closed

    def panel_at(self, mouse_pos: tuple[int, int]) -> str | None:
        """Id of the topmost panel under the cursor, if any.

        Panels register in draw order, so the last drawn one is the topmost:
        iterate backwards so a dragged panel wins over what it covers.
        """
        for panel_id, rect in reversed(list(self.panels.items())):
            if rect.collidepoint(mouse_pos):
                return panel_id
        return None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Route a mouse event; return ``True`` when it was consumed.

        Left click on a ``×`` closes that panel; left click anywhere else on
        a panel grabs it for a drag. Motion and release only matter while a
        drag is in flight, so the rest of the game keeps receiving its input.
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = tuple(event.pos)
            for panel_id in reversed(list(self.panels)):
                close = self.close_rect(panel_id)
                if close is not None and close.collidepoint(pos):
                    self.set_closed(panel_id)
                    return True
            hit = self.panel_at(pos)
            if hit is not None:
                self.start_drag(hit, pos)
                return True
        elif event.type == pygame.MOUSEMOTION and self.drag_id is not None:
            self.move_drag(tuple(event.pos))
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_id is not None:
            self.end_drag()
            return True
        elif event.type == pygame.WINDOWFOCUSLOST and self.drag_id is not None:
            self.cancel_drag()
            return True
        return False


class PanelLayoutError(RuntimeError):
    pass


class PanelLayout:
    """Column-flow placement for debug panels (responsive by construction).

    Pin fixed panels first with :meth:`place_top_right` (the performance
    gauge), then stack the flow downward from the top-left margin: a panel
    that would overflow the bottom edge wraps to a new column on the right,
    and a slot that would cover an already drawn panel slides below it
    instead of stacking on it. A dragged panel takes a manual slot via
    :meth:`place_at`: it keeps its dropped position (clamped inside the
    display) and the remaining panels keep packing around it, so the
    layout stays responsive.
    """

    def __init__(
        self, width: int, height: int, *, margin: int = PANEL_MARGIN, gutter: int = 8
    ) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.margin = margin
        self.gutter = gutter
        self._column_x = margin
        self._cursor_y = margin
        self._column_right = margin
        self._placed: list[pygame.Rect] = []
        self._pinned: list[pygame.Rect] = []

    def _bounds(self, w: int, h: int) -> tuple[int, int]:
        if w <= 0 or h <= 0:
            raise PanelLayoutError("panel dimensions must be positive")
        max_x = self.width - self.margin - w
        max_y = self.height - self.margin - h
        if max_x < self.margin or max_y < self.margin:
            raise PanelLayoutError(f"panel {w}x{h} cannot fit in {self.width}x{self.height}")
        return max_x, max_y

    def _clamp_x(self, x: int, max_x: int) -> int:
        return max(self.margin, min(x, max_x))

    def _clamp_y(self, y: int, max_y: int) -> int:
        return max(self.margin, min(y, max_y))

    def _hits_placed(self, x: int, y: int, w: int, h: int) -> bool:
        candidate = pygame.Rect(x, y, w, h)
        return any(candidate.colliderect(other) for other in self._placed)

    def _next_column_x(self, w: int) -> int:
        x = self._column_right + self.gutter
        for pin in self._pinned:
            if x + w > pin.left and x < pin.right:
                right_of = pin.right + self.gutter
                if right_of + w <= self.width - self.margin:
                    x = right_of
        return x

    def _find_slot(
        self,
        w: int,
        h: int,
        preferred: list[tuple[int, int]],
        *,
        flow: bool,
    ) -> tuple[int, int] | None:
        max_x, max_y = self._bounds(w, h)
        clamped = [(self._clamp_x(x, max_x), self._clamp_y(y, max_y)) for x, y in preferred]
        xs = {x for x, _ in clamped}
        ys = {y for _, y in clamped}
        xs.update((self.margin, max_x))
        ys.update((self.margin, max_y))
        for rect in self._placed:
            xs.update((rect.right + self.gutter, rect.left - w - self.gutter))
            ys.update((rect.bottom + self.gutter, rect.top - h - self.gutter))
        candidates = [
            (x, y) for x in xs if self.margin <= x <= max_x for y in ys if self.margin <= y <= max_y
        ]
        preferred_x, preferred_y = clamped[0]
        if flow:
            _, preferred_y = min(clamped, key=lambda pos: (pos[1], pos[0]))
            candidates.sort(key=lambda pos: (abs(pos[1] - preferred_y), pos[0], pos[1]))
        else:
            candidates.sort(
                key=lambda pos: (
                    abs(pos[0] - preferred_x) + abs(pos[1] - preferred_y),
                    pos[1],
                    pos[0],
                )
            )
        return next(
            (position for position in candidates if not self._hits_placed(*position, w, h)),
            None,
        )

    def place(self, w: int, h: int) -> tuple[int, int]:
        self._bounds(w, h)
        x, y = self._column_x, self._cursor_y
        preferred = [(x, y)]
        if y > self.margin and y + h > self.height - self.margin:
            preferred.append((self._next_column_x(w), self.margin))
        position = self._find_slot(w, h, preferred, flow=True)
        if position is None:
            raise PanelLayoutError(f"no free slot for panel {w}x{h}")
        x, y = position
        self._placed.append(pygame.Rect(x, y, w, h))
        self._column_x = x
        self._column_right = max(self._column_right, x + w)
        self._cursor_y = y + h + self.gutter
        return x, y

    def place_at(self, x: int, y: int, w: int, h: int) -> tuple[int, int]:
        position = self._find_slot(w, h, [(x, y)], flow=False)
        if position is None:
            raise PanelLayoutError(f"no free slot for panel {w}x{h} at {(x, y)}")
        x, y = position
        self._placed.append(pygame.Rect(x, y, w, h))
        self._column_right = max(self._column_right, x + w)
        return x, y

    def place_top_right(self, w: int, h: int) -> tuple[int, int]:
        max_x, _ = self._bounds(w, h)
        x = self._clamp_x(self.width - self.margin - w, max_x)
        if self._hits_placed(x, self.margin, w, h):
            raise PanelLayoutError(f"no free top-right slot for panel {w}x{h}")
        pinned = pygame.Rect(x, self.margin, w, h)
        self._pinned.append(pinned)
        self._placed.append(pinned)
        return x, self.margin


class PanelRenderer:
    """Render debug panels and cache fonts."""

    def __init__(self, display_surface: pygame.Surface, *, text_cache_capacity: int = 256) -> None:
        self.display_surface = display_surface
        if text_cache_capacity < 0:
            raise ValueError("text_cache_capacity must be non-negative")
        self.text_cache_capacity = text_cache_capacity

        self.debug_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE)
        self.title_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE, bold=True)
        self.label_font = pygame.font.SysFont("Consolas", Debug.LABEL_FONT_SIZE)
        # World-space entity cards: compact fonts so the floating labels
        # stay readable without covering the sprites they describe.
        self.world_title_font = pygame.font.SysFont(
            "Consolas", Debug.WORLD_TITLE_FONT_SIZE, bold=True
        )
        self.world_label_font = pygame.font.SysFont("Consolas", Debug.WORLD_LABEL_FONT_SIZE)

        self._text_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._text_cache_hits = 0
        self._text_cache_misses = 0
        self._background_cache: OrderedDict[
            tuple[int, int, tuple[int, int, int, int]], pygame.Surface
        ] = OrderedDict()
        #: Panel ids closed this frame set (draw_panel leaves them out).
        self.interaction = PanelInteraction()

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface
        self.clear_text_cache()
        self.interaction.clamp_positions(
            (display_surface.get_width(), display_surface.get_height())
        )

    @property
    def text_cache_stats(self) -> dict[str, int]:
        return {
            "hits": self._text_cache_hits,
            "misses": self._text_cache_misses,
            "entries": len(self._text_cache),
        }

    def clear_text_cache(self) -> None:
        self._text_cache.clear()
        self._text_cache_hits = 0
        self._text_cache_misses = 0

    def render_text(
        self, text: str, font: pygame.font.Font, color: tuple[int, int, int]
    ) -> pygame.Surface:
        key = (text, id(font), color)
        cached = self._text_cache.get(key)
        if cached is not None:
            self._text_cache.move_to_end(key)
            self._text_cache_hits += 1
            return cached
        self._text_cache_misses += 1
        rendered = font.render(text, True, color)
        if self.text_cache_capacity:
            self._text_cache[key] = rendered
            if len(self._text_cache) > self.text_cache_capacity:
                self._text_cache.popitem(last=False)
        return rendered

    def measure_panel(
        self,
        lines: list[str],
        title: str | None = None,
        title_font: pygame.font.Font | None = None,
        line_height: int | None = None,
        padding: int = 12,
        title_gap: int = 8,
        reserve_close: bool = False,
    ) -> tuple[int, int]:
        """Measure a panel without drawing it (layout pass before ``draw``).

        ``reserve_close`` widens the panel just enough for the ``×`` button
        plus the gap kept left of it, so the header text never runs under
        the glyph: every caller that places a *closable* panel (an
        interactive debug panel) measures with it, and :meth:`draw_panel`
        then draws exactly the size that was reserved.
        """
        title_font = title_font or self.title_font
        line_height = line_height if line_height is not None else self.debug_font.get_linesize()

        max_w = 0
        for line in lines:
            max_w = max(max_w, self.render_text(line, self.debug_font, TEXT_MUTED).get_width())
        title_w = 0
        title_block_h = 0
        if title:
            title_surf = self.render_text(title, title_font, TEXT_TITLE)
            title_w = title_surf.get_width()
            max_w = max(max_w, title_w)
            title_block_h = title_surf.get_height() + title_gap + 1 + title_gap

        panel_w = max_w + padding * 2
        if reserve_close:
            header_w = title_w or max_w  # untitled: also clear of the first line
            panel_w = max(
                panel_w, header_w + PANEL_CLOSE_GAP + PANEL_CLOSE_BOX + PANEL_CLOSE_INSET + padding
            )
        panel_h = title_block_h + len(lines) * line_height + padding * 2
        return panel_w, panel_h

    def _clamp_panel(self, x: int, y: int, w: int, h: int) -> tuple[int, int]:
        """Keep a manually placed panel fully inside the display (margin aside)."""
        screen = self.display_surface.get_rect()
        return (
            max(PANEL_MARGIN, min(x, max(PANEL_MARGIN, screen.width - PANEL_MARGIN - w))),
            max(PANEL_MARGIN, min(y, max(PANEL_MARGIN, screen.height - PANEL_MARGIN - h))),
        )

    def _place_panel(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        layout: PanelLayout | None,
        panel_id: str | None,
    ) -> tuple[int, int] | None:
        override = self.interaction.position_for(panel_id) if panel_id is not None else None
        try:
            if panel_id is not None and override is not None and layout is not None:
                x, y = layout.place_at(override[0], override[1], w, h)
                self.interaction.set_position(panel_id, (x, y))
            elif panel_id is not None and override is not None:
                x, y = self._clamp_panel(override[0], override[1], w, h)
                self.interaction.set_position(panel_id, (x, y))
            elif layout is not None:
                x, y = layout.place(w, h)
        except PanelLayoutError as error:
            if panel_id is not None:
                self.interaction.positions.pop(panel_id, None)
                if self.interaction.drag_id == panel_id:
                    self.interaction.cancel_drag()
            warnings.warn(str(error), RuntimeWarning, stacklevel=2)
            return None
        return x, y

    def _panel_surface(
        self, width: int, height: int, color: tuple[int, int, int, int]
    ) -> pygame.Surface:
        key = (width, height, color)
        cached = self._background_cache.get(key)
        if cached is not None:
            self._background_cache.move_to_end(key)
            return cached
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(surface, color, surface.get_rect())
        pygame.draw.rect(surface, PANEL_BORDER, surface.get_rect(), width=1)
        self._background_cache[key] = surface
        if len(self._background_cache) > 16:
            self._background_cache.popitem(last=False)
        return surface

    def draw_panel(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: tuple[int, int, int, int] = PANEL_BG,
        text_color: tuple[int, int, int] = TEXT_MUTED,
        title: str | None = None,
        line_colors: dict[int, tuple[int, int, int]] | None = None,
        title_font: pygame.font.Font | None = None,
        line_height: int | None = None,
        padding: int = 12,
        title_gap: int = 8,
        layout: PanelLayout | None = None,
        panel_id: str | None = None,
    ) -> int:
        """Draw a semi-transparent debug panel with optional title and colored lines.

        The ``title_font`` / ``line_height`` / ``padding`` / ``title_gap``
        parameters let menu scenes breathe: the debug overlays keep the
        compact defaults while full-screen menus use larger spacing and a
        dedicated title font. ``line_height`` defaults to the font's own
        line advance so rows never overlap. With ``layout``, the ``x``/``y``
        hint is ignored: the panel is measured, placed by the column flow,
        and drawn there.

        ``panel_id`` makes the panel interactive: it gains a ``×`` in its
        top-right corner, is skipped entirely while closed, follows the spot
        stored by a drag & drop, and registers its rect so the next frame can
        hit test it. A dragged panel is placed at its drop position — clamped
        inside the display — and the column flow packs the remaining panels
        around it, so responsiveness survives a drop.
        """
        if panel_id is not None and self.interaction.is_closed(panel_id):
            return 0

        line_colors = line_colors or {}
        title_font = title_font or self.title_font
        line_height = line_height if line_height is not None else self.debug_font.get_linesize()

        panel_w, panel_h = self.measure_panel(
            lines,
            title=title,
            title_font=title_font,
            line_height=line_height,
            padding=padding,
            title_gap=title_gap,
            reserve_close=panel_id is not None,
        )

        position = self._place_panel(x, y, panel_w, panel_h, layout, panel_id)
        if position is None:
            return 0
        x, y = position

        rendered_lines = [
            self.render_text(line, self.debug_font, line_colors.get(i, text_color))
            for i, line in enumerate(lines)
        ]
        title_surf = self.render_text(title, title_font, TEXT_TITLE) if title else None

        bg = self._panel_surface(panel_w, panel_h, color)
        self.display_surface.blit(bg, (x, y))

        content_y = y + padding
        if title_surf:
            self.display_surface.blit(title_surf, (x + padding, content_y))
            content_y += title_surf.get_height() + title_gap
            pygame.draw.line(
                self.display_surface,
                PANEL_BORDER,
                (x + padding, content_y),
                (x + panel_w - padding, content_y),
                1,
            )
            content_y += title_gap + 1

        for i, surf in enumerate(rendered_lines):
            self.display_surface.blit(surf, (x + padding, content_y + i * line_height))

        if panel_id is not None:
            self.draw_close_button(x, y, panel_w, panel_id)
            self.interaction.register(panel_id, pygame.Rect(x, y, panel_w, panel_h))

        return panel_h + padding

    def draw_close_button(
        self, x: int, y: int, panel_w: int, panel_id: str | None = None
    ) -> pygame.Rect:
        """Draw the ``×`` in a panel's top-right corner; returns its hit box.

        The glyph highlights while the cursor hovers the box registered on
        the previous frame — the one the player can actually see, and the
        very same rect a click is tested against.
        """
        rect = close_box_rect(x + panel_w, y)
        hover_rect = self.interaction.close_rect(panel_id) if panel_id is not None else None
        hovered = bool(hover_rect and hover_rect.collidepoint(pygame.mouse.get_pos()))

        if hovered:
            pygame.draw.rect(self.display_surface, PANEL_BORDER, rect)
        pygame.draw.rect(self.display_surface, PANEL_BORDER, rect, width=1)
        color = TEXT_CRIT if hovered else TEXT_MUTED
        pygame.draw.line(
            self.display_surface,
            color,
            (rect.left + 3, rect.top + 3),
            (rect.right - 4, rect.bottom - 4),
            2,
        )
        pygame.draw.line(
            self.display_surface,
            color,
            (rect.right - 4, rect.top + 3),
            (rect.left + 3, rect.bottom - 4),
            2,
        )
        return rect

    def get_panel_width(self, lines: list[str]) -> int:
        """Compute panel width for positioning (e.g., performance panel on the right)."""
        max_w = max(
            self.render_text(line, self.debug_font, TEXT_MUTED).get_width() for line in lines
        )
        return max_w + 24
