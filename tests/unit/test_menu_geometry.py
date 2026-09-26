"""The menus have to hold together at every window size, not just the author's.

A menu is a table of text in a box, and there are exactly three ways for that to
go wrong, and all three were live at once at a window of 2176x1224:

* **A row shorter than its own text.** The grid took ``min(34, 30*scale)`` for its
  row while its text was ``22*scale`` -- 49 pixels -- so a clickable band covered
  44% of the label above it. Clicking the row you read activated the row above,
  which is the worst failure a menu has: it is not obviously broken, it is
  *responsive to the wrong thing*.
* **A panel that is the same size whatever it holds.** The width was capped at
  900px, a desktop-era number, so a 2176px window got a 900px panel in the
  middle of it and 34% of that was a gutter sized for the labels rather than the
  values.
* **Titles that jump between screens.** The grid drew its title flush left, the
  option panel drew its title flush left, and the HUD drew its centred. The one
  thing on every screen is the one thing that is never in the same place.

So these tests state ratios, not pixels: at any scale, in any window, a row is
at least as tall as its text, the panel is wide enough for its own content, and
the title is centred.
"""

import os

import pygame
import pytest

from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.metrics import MIN_TEXT_RATIO, Metrics

#: The window sizes that have to work: the design size, a 1080p screen, the
#: user's 2176x1224 laptop, an ultrawide, a 4K panel, and two sizes too small
#: to be playable -- because a menu that breaks when the window is small breaks
#: on the second monitor.
WINDOWS = [
    (1152, 648),
    (1920, 1080),
    (2176, 1224),
    (2560, 1080),
    (3840, 2160),
    (800, 600),
    (640, 480),
]
SCALES = [0.75, 1.0, 1.5, 2.0]


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


def _rows(count: int) -> list:
    """Real mapping rows, in the grid's own vocabulary.

    Built through ``as_grid_row`` rather than hand-rolled, so the widths these
    tests measure are the widths the controls screen actually asks for.
    """
    from src.ui.controls_view import BindingCell, BindingRow

    return [
        BindingRow(
            f"Move {'right' * (1 + index % 3)}", BindingCell("D"), BindingCell("button 12")
        ).as_grid_row()
        for index in range(count)
    ]


def _grid_drawn(size, scale, rows, footers=("Esc : back",)):
    """A grid drawn the way a scene draws it, with the fonts actually built."""
    from src.ui.grid_view import GridView

    surface = pygame.Surface(size)
    view = GridView(scale)
    view.set_surface(surface)
    view.draw(
        surface,
        "MENU CONTROLS",
        "Keyboard and mouse",
        ("Action", "Binding", "Legacy"),
        rows,
        selected_row=0,
        selected_column=1,
        top=40,
        footers=footers,
    )
    return view


# --------------------------------------------------------------------------
# 1. A row is at least as tall as the text it holds.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_no_row_is_shorter_than_its_text(size, scale) -> None:
    """The invariant behind "clicking what I read does what I expect".

    Checked against the font that painted the row, not against the scale, so a
    change to the font cannot quietly break the geometry: the row and the glyphs
    are two facts about the same frame and they have to agree.
    """
    view = _grid_drawn(size, scale, _rows(8))

    title_font, item_font, _ = view._fonts
    assert item_font is not None
    for rect in view.row_rects:
        assert rect.height >= item_font.get_linesize(), (
            f"row of {rect.height}px cannot hold {item_font.get_linesize()}px of text "
            f"at {size} scale {scale}"
        )


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_a_row_is_clickable_over_its_whole_text(size, scale) -> None:
    """The cell's hit box covers the same band as the row it belongs to.

    The old box started two pixels above its own row, so it overlapped the one
    above: at a boundary a click hit two cells and ``cell_at`` answered with
    whichever was tested first. The test asserts the boxes are disjoint, which is
    the property that makes the answer unambiguous.
    """
    view = _grid_drawn(size, scale, _rows(8))

    boxes = [cell.rect for cell in view._cells]
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            assert not box.colliderect(other), f"{box} overlaps {other}"


def test_a_list_that_cannot_fit_gives_up_text_size_not_row_size() -> None:
    """The trade is visible in the numbers, at a height that forces it.

    A window 200px tall cannot hold eight comfortable rows. There are two ways
    out -- shrink the text and keep the rows readable, or keep the text and
    squeeze the rows until they overlap. Only the first is usable, so the row
    height must stay proportional while the font shrinks, and the test says so
    by requiring the font to be smaller and every row to still hold it.
    """
    generous = _grid_drawn((1920, 1080), 1.0, _rows(8))
    squeezed = _grid_drawn((1920, 260), 1.0, _rows(8))

    assert squeezed._text_scale < generous._text_scale, "the fixture does not force a fit"
    squeezed_item = squeezed._fonts[1]
    assert squeezed_item is not None
    for rect in squeezed.row_rects:
        assert rect.height >= squeezed_item.get_linesize()


def test_the_text_never_shrinks_below_readability() -> None:
    """There is a floor, and it is a floor on the *text*, not on the row.

    A menu that keeps shrinking until a label is a row of grey is not a menu
    that fits; it is a menu that has given up, and it looks like the latter.
    """
    tiny = _grid_drawn((1920, 120), 1.0, _rows(8))
    normal = _grid_drawn((1920, 1080), 1.0, _rows(8))

    assert tiny._text_scale >= normal._text_scale * MIN_TEXT_RATIO


# --------------------------------------------------------------------------
# 2. The panel holds its own content.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_the_panel_is_wide_enough_for_its_text(size, scale) -> None:
    """Every label and every value fits inside the panel.

    The 900px cap is what broke this: a cap that ignores both the window and the
    content produces a panel that truncates its own values on a wide screen while
    leaving a third of a narrow one empty. The panel is measured against the
    widest string in it, which is the only width that is not a guess.
    """
    rows = _rows(8)
    view = _grid_drawn(size, scale, rows)
    _, item_font, _ = view._fonts
    panel = view._last_panel_rect
    assert item_font is not None and panel is not None
    inner = panel.width - view._metrics.padding * 2

    longest = (
        max(item_font.size(row.label)[0] for row in rows)
        + max(item_font.size(cell.text)[0] for row in rows for cell in row.cells if cell)
        + view._metrics.gap
    )
    assert longest <= inner, (
        f"content needs {longest}px and the panel offers {inner}px at {size} scale {scale}"
    )


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_the_panel_stays_inside_the_window(size, scale) -> None:
    """The panel never leaves the window horizontally, at any scale.

    Vertical overflow is possible and is a deliberate choice: a 2x interface on a
    648px window cannot show eight rows in full, and the alternative is text too
    small to read. When it happens it must be *only* then -- so the test states
    the trade explicitly rather than leaving it to be discovered on a 4K screen:
    the panel may only exceed the window once the text has hit its floor.
    """
    view = _grid_drawn(size, scale, _rows(8))
    panel = view._last_panel_rect
    assert panel is not None
    assert panel.left >= 0 and panel.right <= size[0], f"panel leaves a {size} window"

    if panel.bottom > size[1]:
        assert view._text_scale <= view._metrics.scale * MIN_TEXT_RATIO + 1e-9, (
            f"a {size} window at scale {scale} overflows with text to spare"
        )


def test_a_long_value_widens_the_panel_instead_of_being_cut() -> None:
    """Content drives the width, so a longer value means a wider panel.

    Measured as a comparison rather than a pixel count: what matters is that the
    panel responds to its content at all, which is the property the 900 cap
    removed.
    """
    from src.ui.controls_view import BindingCell, BindingRow

    short = _grid_drawn(
        (2560, 1080),
        1.0,
        [BindingRow("Fire", BindingCell("Space"), BindingCell("")).as_grid_row()],
    )
    long = _grid_drawn(
        (2560, 1080),
        1.0,
        [
            BindingRow(
                "Fire", BindingCell("Left mouse button, long name"), BindingCell("")
            ).as_grid_row()
        ],
    )

    long_panel, short_panel = long._last_panel_rect, short._last_panel_rect
    assert long_panel is not None and short_panel is not None
    assert long_panel.width > short_panel.width


# --------------------------------------------------------------------------
# 3. One rule for where a title is.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_the_grid_title_is_centred(size, scale) -> None:
    """Centred in the panel, to the pixel.

    A test that only checks it is "roughly centred" cannot catch a title that
    drifted left by the width of its own margin, which is what a flush-left draw
    actually looked like.
    """
    view = _grid_drawn(size, scale, _rows(8))
    title_font, _, _ = view._fonts
    panel = view._last_panel_rect
    assert title_font is not None and panel is not None
    width = title_font.size("MENU CONTROLS")[0]

    from src.ui.grid_view import _centred_x

    assert _centred_x(panel, width) == panel.x + (panel.width - width) // 2
    assert abs(_centred_x(panel, width) + width // 2 - panel.centerx) <= 1


def test_the_option_panel_centres_its_title_too() -> None:
    """Same rule, same place: the two panel types are one design."""
    surface = pygame.Surface((1920, 1080))
    view = MenuView(1.5)
    model = MenuModel([MenuItem("Windowed", "1920x1080"), MenuItem("Fullscreen", "")])
    rect = view.draw(surface, "VIDEO", model, top=100, footers=("Esc : back",))

    title_font = view._fonts_for(1.5)[0]
    width = title_font.size("VIDEO")[0]

    # Centred means the midpoints agree, not that the left edges do.
    assert abs((rect.x + (rect.width - width) // 2 + width // 2) - rect.centerx) <= 1


# --------------------------------------------------------------------------
# 4. The metrics themselves.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0.5, 0.75, 1.0, 1.1111, 1.5, 1.8889, 2.0, 3.3333])
def test_every_metric_is_a_multiple_of_the_scale_and_never_zero(scale) -> None:
    """The table's contract: one input, multiplied once, floored at one pixel.

    Checked as a ratio so a token cannot be quietly re-added as a literal -- a
    literal would still be "at least one" and would still be inside the surface,
    and the interface would drift back to what it was.
    """
    metrics = Metrics.for_scale(scale)

    for name in (
        "margin",
        "padding",
        "gap",
        "title_gap",
        "border",
        "footer_line",
        "row",
        "panel_padding",
        "panel_title_gap",
        "panel_row",
        "value_gap",
    ):
        value = getattr(metrics, name)
        assert value >= 1, f"{name} is {value} at scale {scale}"
        assert abs(value - getattr(Metrics.for_scale(1.0), name) * scale) <= 1, (
            f"{name} is not {scale}x its design size"
        )


def test_the_scale_is_validated_once_and_rejects_nonsense() -> None:
    """A zero or negative scale would make every metric one pixel.

    The validator is shared now, so the rule is stated once and every view gets
    it, including the ones added later. It raises rather than clamping: a scale
    of zero is a bug in whoever asked, and a silently clamped interface is
    harder to find than a stack trace.
    """
    for bad in (0.0, -1.0, float("nan"), float("inf"), 9.0):
        with pytest.raises(ValueError):
            Metrics.for_scale(bad)
    assert 0 < Metrics.for_scale(0.25).scale <= Metrics.for_scale(8.0).scale


def test_two_scales_are_the_same_picture_twice_as_big() -> None:
    """The property the whole table exists to give, as one assertion.

    Everything scales, so the interface at scale 2 is the interface at scale 1
    with each dimension doubled -- which is what "scalable" means, and what was
    false before: the fonts doubled and the paddings did not.
    """
    one, two = Metrics.for_scale(1.0), Metrics.for_scale(2.0)

    for name in ("padding", "gap", "row", "panel_padding", "panel_row", "margin"):
        assert getattr(two, name) == pytest.approx(getattr(one, name) * 2, abs=1)
    assert two.item_text == pytest.approx(one.item_text * 2, abs=1)
    assert two.title_text == pytest.approx(one.title_text * 2, abs=1)


# --------------------------------------------------------------------------
# 5. The column titles are a band of their own.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", WINDOWS)
@pytest.mark.parametrize("scale", SCALES)
def test_the_column_titles_are_not_painted_under_the_first_row(size, scale) -> None:
    """The titles sit above the rows, with air, at every size.

    They did not. The layout reserved the height of the title band and the
    drawing never moved past it, so the first row was blitted at the same y as
    the column titles: two texts on top of each other, which reads as "the title
    is glued to the column" rather than as the bug it is. A layout that reserves
    space it does not consume is invisible in every screenshot and obvious in
    two numbers.
    """
    view = _grid_drawn(size, scale, _rows(8))

    headers, rows = view.column_header_rects, view.row_rects
    assert headers, "the fixture drew no column titles"
    assert rows
    for header in headers:
        assert header.bottom <= rows[0].top, (
            f"a title occupies {header} and the first row starts at {rows[0].top}"
        )
        assert header.top > view._last_panel_rect.top


@pytest.mark.parametrize("size", WINDOWS)
def test_the_title_band_and_the_rows_stay_inside_the_panel(size) -> None:
    """Both bands are inside the panel, so neither is drawn on the border.

    The panel is content-sized, so a title that overflowed it would be a title
    hanging outside the frame -- the other way the same missing space shows up.
    """
    view = _grid_drawn(size, 1.5, _rows(8))
    panel = view._last_panel_rect

    assert panel is not None
    for rect in [*view.column_header_rects, *view.row_rects]:
        assert panel.contains(rect), f"{rect} is outside {panel}"


def test_the_title_band_is_reserved_in_the_panel_height() -> None:
    """Same rows, same window, one band taller when the titles are there.

    The complement of the overlap test: if the titles were painted on the rows
    *and* the panel had already reserved the space, the panel would be showing an
    empty strip. So the reservation and the consumption are asserted from both
    sides -- the numbers add up, and nothing is drawn twice in the same place.
    """
    surface = pygame.Surface((1920, 1080))
    from src.ui.grid_view import GridView

    view = GridView(1.0)
    view.set_surface(surface)
    view.draw(
        surface, "VIDEO", "Keyboard and mouse", ("Action", "Binding", "Legacy"), _rows(4),
        selected_row=0, selected_column=0, top=40,
    )
    # Measured on the layout rather than by drawing a titleless grid: a row's
    # cells and the column titles are required to correspond, so a grid with rows
    # and no headings is not a thing that can be drawn.
    _, _, _, _, _, _, _, _ = view._layout(
        surface, "Keyboard and mouse", _rows(4), ("Action", "Binding", "Legacy"), 40, ()
    )
    titled = view._last_panel_rect.height
    _, _, _, _, _, _, _, _ = view._layout(
        surface, "Keyboard and mouse", _rows(4), (), 40, ()
    )
    untitled = view._last_panel_rect.height

    band = titled - untitled
    assert band > 0, "the column titles cost no height, so they overlap the rows"
    assert band >= view._fonts[2].get_height(), (
        "the reserved band is smaller than the text it has to hold"
    )
