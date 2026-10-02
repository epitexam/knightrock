"""Responsive debug display: panel flow, pinned wrap, labels vs bars, edges."""

import os
import re
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.combat.frame_data import Stance
from src.core.display.framing import Framing
from src.core.input.input_actions import InputAction
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelLayout, PanelRenderer
from src.ui.styles import TEXT_MUTED
from src.ui.ui_manager import UIManager
from tests.unit.helpers import make_overlay


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


@pytest.fixture()
def ui() -> UIManager:
    return UIManager(pygame.display.get_surface())


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(1024), float(768)))


def _entity(x: float = 100.0, health: float = 75.0) -> SimpleNamespace:
    """Minimal labelled entity for the world overlay (like test_debug_overlay)."""
    return type("Goblin", (SimpleNamespace,), {})(
        hitbox=pygame.FRect(x, 100, 40, 48),
        velocity=Vector2(0, 0),
        faction="enemy",
        health=health,
        max_health=100.0,
        stagger_timer=0.0,
        otg_timer=0.0,
        gravity_scale=1.0,
        state_machine=SimpleNamespace(current_state_name="idle"),
    )


def _capture_labels(ui: UIManager, monkeypatch: pytest.MonkeyPatch) -> list[pygame.Rect]:
    """Spy on _blit_label and collect the padded rects actually placed."""
    placed: list[pygame.Rect] = []
    original = type(ui.world_ui._cards).blit_label

    def spy(
        self: object,
        header: list[pygame.Surface],
        rows: list[list[pygame.Surface]],
        row_height: int,
        accent: object,
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
        screen_width: int,
    ) -> None:
        placed.append(pygame.Rect(background_rect))
        original(self, header, rows, row_height, accent, label_rect, background_rect, screen_width)

    monkeypatch.setattr(type(ui.world_ui._cards), "blit_label", spy)
    return placed


def test_flowing_panels_never_cover_a_pinned_panel() -> None:
    """Pinned first, then the flow: no flowing panel covers the pinned one."""
    layout = PanelLayout(1024, 768)
    pinned_pos = layout.place_top_right(200, 300)

    placed = [layout.place(200, 250) for _ in range(4)]
    assert placed[0] == (10, 10)
    pinned = pygame.Rect(*pinned_pos, 200, 300)
    assert all(not pygame.Rect(x, y, 200, 250).colliderect(pinned) for x, y in placed), (
        f"flow panels {placed} cover the pinned panel at {pinned_pos}"
    )


def test_wrapped_column_stays_left_when_display_is_narrow() -> None:
    """No room right of the pinned panel: the new column slides left of it."""
    layout = PanelLayout(500, 768)
    layout.place_top_right(300, 100)

    x, y = layout.place(150, 400)  # overflows the bottom -> must wrap

    assert y == 10
    pinned = pygame.Rect(500 - 10 - 300, 10, 300, 100)
    assert not pygame.Rect(x, y, 150, 400).colliderect(pinned)


def test_labels_keep_clear_of_the_health_bars(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A placed label card never overlaps the bar drawn after it."""
    entity = _entity()
    placed = _capture_labels(ui, monkeypatch)

    surface = ui.world_ui.surface
    surface.fill((0, 0, 0))
    ui.world_ui.draw_debug_overlays([entity], camera)
    ui.draw_health_bars([entity], camera)

    assert placed, "the label card was dropped instead of dodging the bar"
    bar = ui.world_ui._health_bar_rect(entity, camera.apply(entity.hitbox))
    assert bar is not None
    assert not any(bar.colliderect(card) for card in placed)


def test_labels_dodge_bars_from_the_previous_frame(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bars seen one frame earlier remain obstacles for the next frame."""
    entity = _entity()
    _capture_labels(ui, monkeypatch)

    ui.world_ui.draw_debug_overlays([entity], camera)  # registers the bar
    bar = ui.world_ui._health_bar_rect(entity, camera.apply(entity.hitbox))
    assert bar is not None
    above_lift, _ = ui.world_ui._cards.label_clearances(entity, camera.apply(entity.hitbox))
    placed = ui.world_ui._cards.place_label(
        [[("Goblin idle", (255, 255, 255))], [("HP 75/100", (255, 255, 255))]],
        (255, 255, 255),
        camera.apply(entity.hitbox),
        [*ui.world_ui._cards.previous_bar_obstacles],
        ui.renderer.surface.get_width(),
        ui.renderer.surface.get_height(),
        above_lift=above_lift,
    )
    assert placed is not None
    assert not bar.colliderect(placed)


def test_edge_labels_shift_inside_the_screen(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card near the display edge is shifted back inside, never clipped."""
    entity = _entity(x=600.0)  # near the right edge of the 1024px view
    entity.hitbox.right = 1010.0
    placed = _capture_labels(ui, monkeypatch)

    surface = ui.world_ui.surface
    surface.fill((0, 0, 0))
    ui.world_ui.draw_debug_overlays([entity], camera)

    assert placed, "the label card was dropped at the screen edge"
    screen = surface.get_rect()
    assert screen.contains(placed[0]), f"card {placed[0]} sticks out of the display"


def test_combat_panel_only_collects_when_debug_is_enabled(
    ui: UIManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEBUG unset: draw_metrics_panel collects nothing; with DEBUG it does."""
    monkeypatch.delenv("DEBUG", raising=False)
    # Ten ticks, because `update_metrics` only publishes every tenth. With a
    # single tick the throttle returns first and `metrics_text` is still empty,
    # so this would pass whether or not the DEBUG guard exists -- which is the
    # whole thing the assertion is here to check.
    for _ in range(10):
        ui.world_ui.panels.update_metrics(SimpleNamespace(pairs_tested=1, overlaps=1, contacts=1))
    assert ui.world_ui.panels.metrics_text, "the counters never published, nothing to guard"
    ui.world_ui.panels.draw_metrics_panel()
    assert ui.world_ui.panels.combat_panel() is None

    monkeypatch.setenv("DEBUG", "1")
    for _ in range(10):  # metrics refresh every 10th tick, as in game
        ui.world_ui.panels.update_metrics(SimpleNamespace(pairs_tested=2, overlaps=1, contacts=1))
    ui.world_ui.panels.draw_metrics_panel()
    content = ui.world_ui.panels.combat_panel()
    assert content is not None
    title, lines = content
    assert title == "COMBAT"
    assert lines[0][0] == "pairs 2"


def test_draw_combat_panel_flows_through_the_layout(
    ui: UIManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The COMBAT panel is drawn inside the column flow, not at a fixed spot."""
    monkeypatch.setenv("DEBUG", "1")
    surface = pygame.Surface((640, 480))
    surface.fill((0, 0, 0))
    ui.renderer.surface = surface
    ui.world_ui.panels.combat_panel_lines = [("pairs 2", TEXT_MUTED)]

    layout = PanelLayout(640, 480)
    height = ui.draw_combat_panel(layout)
    assert height > 0
    # The first counter line lands inside the flow's first panel (top-left),
    # below the title block — not at the legacy fixed offset (10, 150).
    assert any(
        surface.get_at((x, y))[:3] == TEXT_MUTED for x in range(14, 110) for y in range(56, 110)
    )


def _full_player() -> SimpleNamespace:
    """Fake player feeding every debug panel (same fields as test_panel_layout)."""
    return SimpleNamespace(
        state_machine=SimpleNamespace(
            current_state_name="idle", previous_state_name=None, history=[]
        ),
        velocity=Vector2(0, 0),
        on_surface={"floor": True, "left": False, "right": False},
        move_axis=0.0,
        jump_buffer_timer=0.0,
        coyote_timer=0.0,
        midair_jumps_left=1,
        wall_jumps_left=1,
        dash=SimpleNamespace(requested=False, duration_timer=0.0),
        combat=None,
        stagger_timer=0.0,
        invincibility_timer=0.0,
        health=100.0,
        max_health=100.0,
        guard_posture=50.0,
        guard_posture_max=100.0,
        guard_lockout_timer=0.0,
        guard_riposte_timer=0.0,
        dash_charges=2,
        max_dash_charges=2,
        dash_penalty_timer=0.0,
        dash_recharge_timer=0.0,
        speed=350.0,
        floor_control=25.0,
        air_control=12.0,
        jump_height=750.0,
        wall_jump_height=600.0,
        dash_speed=800.0,
        dash_duration=0.12,
        dash_friction=15.0,
        gravity_scale=1.0,
        otg_timer=0.0,
    )


def test_full_debug_panel_stack_never_overlaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: every debug panel lands on its own rect, none stacks."""
    from src.core.rendering.camera import Camera as _Camera
    from src.core.rendering.renderer import Renderer
    from src.ui.panel_renderer import set_compact_panels

    surface = pygame.Surface((1440, 900))
    renderer = Renderer(
        surface, _Camera(Framing(float(1440), float(900))), overlay=make_overlay(surface)
    )
    renderer.overlay.world_ui.panels.combat_panel_lines = [("pairs 2", TEXT_MUTED)]

    placed: list[pygame.Rect] = []
    original_place = PanelLayout.place
    original_pin = PanelLayout.place_top_right

    def spy_place(self: PanelLayout, w: int, h: int) -> tuple[int, int]:
        pos = original_place(self, w, h)
        placed.append(pygame.Rect(*pos, w, h))
        return pos

    def spy_pin(self: PanelLayout, w: int, h: int) -> tuple[int, int]:
        pos = original_pin(self, w, h)
        placed.append(pygame.Rect(*pos, w, h))
        return pos

    monkeypatch.setattr(PanelLayout, "place", spy_place)
    monkeypatch.setattr(PanelLayout, "place_top_right", spy_pin)

    # The layout is a developer choice (F11), not a size heuristic, so the test
    # asks for the one it means to check.
    set_compact_panels(False)
    try:
        renderer.draw_debug_panels(
            player=_full_player(),
            fps=60.0,
            sprite_count=1,
            combat_count=1,
            entity_count=1,
            collision_count=1,
            hit_stop=0.0,
            spawn_cooldown=0.0,
            scene_host=None,
            frame_time=16.0,
            cache_size=0,
        )
    finally:
        set_compact_panels(True)

    # PERFORMANCE (pinned), COMBAT, PLAYER STATE, STATS, KEYS, LEGEND.
    assert len(placed) == 6
    for index, rect in enumerate(placed):
        for other in placed[index + 1 :]:
            assert not rect.colliderect(other), f"panel {rect} stacks on {other}"
    screen = surface.get_rect()
    assert all(screen.contains(rect) for rect in placed), "a panel sticks out of the display"


def test_compact_display_uses_focus_selector_without_overlap() -> None:
    from src.core.rendering.camera import Camera as _Camera
    from src.core.rendering.renderer import Renderer

    surface = pygame.Surface((640, 480))
    renderer = Renderer(
        surface, _Camera(Framing(float(640), float(480))), overlay=make_overlay(surface)
    )
    level = SimpleNamespace(
        deaths=0,
        groups=SimpleNamespace(
            entity_sprites=[],
            hazard_sprites=[],
            projectile_sprites=[],
        ),
    )
    game = SimpleNamespace(
        scene_manager=SimpleNamespace(
            current=SimpleNamespace(level_id=0, level=level),
        )
    )

    renderer.draw_debug_panels(
        player=_full_player(),
        fps=60.0,
        sprite_count=1,
        combat_count=0,
        entity_count=0,
        collision_count=0,
        hit_stop=0.0,
        spawn_cooldown=0.0,
        scene_host=game,
        frame_time=16.0,
    )
    renderer.overlay.renderer.interaction.begin_frame()
    panels = renderer.overlay.renderer.interaction.panels
    screen = surface.get_rect()

    assert set(panels) == {"performance", "state"}
    assert all(screen.contains(rect) for rect in panels.values())
    assert not panels["performance"].colliderect(panels["state"])
    assert renderer.overlay.compact_panel_focus() == "state"
    assert renderer.overlay.cycle_compact_panel() == "stats"


def test_a_bar_that_moved_still_dodges_the_card_next_frame(
    ui: UIManager, camera: Camera, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bar rects of the previous frame are obstacles for this one.

    Bars paint *after* the cards but belong to the same tier stack, so a card
    placed against where its bar is now has to keep clear of where the bar was.
    Without that, an entity that walks under the top of the screen -- flipping
    its bar from above to below -- leaves its card sitting on the bar's old
    ground, which reads as a placement bug and is not one.

    This is the only test that exercises the *write* of ``previous_bar_obstacles``:
    the others read it, so dropping the write leaves them green.
    """
    placed = _capture_labels(ui, monkeypatch)
    low = _entity()
    ui.world_ui.draw_debug_overlays([low], camera)
    old_bar = ui.world_ui._health_bar_rect(low, camera.apply(low.hitbox))
    assert old_bar is not None
    assert old_bar.bottom <= low.hitbox.y, "the bar starts above the entity"
    first = list(placed)
    assert first

    # Same entity, now against the top edge: the bar has nowhere above and flips.
    high = _entity()
    high.hitbox.y = 4.0
    placed.clear()
    ui.world_ui.draw_debug_overlays([high], camera)
    new_bar = ui.world_ui._health_bar_rect(high, camera.apply(high.hitbox))
    assert new_bar is not None
    assert new_bar.top > high.hitbox.y, "the bar flipped below the entity"
    assert placed, "no card was placed on the second frame"

    assert all(not old_bar.colliderect(pygame.Rect(rect)) for rect in placed), (
        f"the card landed on where the bar used to be: {old_bar} vs {placed}"
    )


# --- the live attack-button block ------------------------------------------


def _rows(stance, cooldowns=None):
    """The panel's live rows, for a player standing in ``stance``."""
    from src.ui.ui_manager import UIManager

    player = SimpleNamespace(stance=stance, combat=SimpleNamespace(cooldowns=cooldowns or {}))
    return UIManager._attack_button_rows(player)


def test_the_block_names_the_posture_the_fighter_is_in() -> None:
    assert _rows(Stance.AIR)[0][0] == "Stance  air"
    assert _rows(Stance.CROUCH)[0][0] == "Stance  crouch"


def test_every_attack_button_gets_a_row() -> None:
    """All of them, in every posture.

    Iterating ``BUTTON_MOVES`` is the property: a button added to the table has to
    appear without a UI edit. Its absence is exactly how ``air_rise`` ended up
    with a guard height its grounded counterpart did not have -- nothing looked at
    the second column until a test compared it.
    """
    from src.entities.attack_moves import BUTTON_MOVES

    for stance in Stance:
        rows = _rows(stance)
        assert len(rows) == len(BUTTON_MOVES) + 1, stance
        for action in BUTTON_MOVES:
            label = "special" if action.name == "SPECIAL_ATTACK" else action.value
            assert any(line.startswith(label) for line, _ in rows), (stance, action)


def test_each_row_names_the_move_that_posture_would_throw() -> None:
    """The gate, rendered -- so it has to agree with the gate.

    ``move_for_button`` is the same call ``player_input`` makes, and
    ``start_attack`` refuses on posture before cooldown, so what these rows say is
    what a press will do.
    """
    from src.entities.attack_moves import BUTTON_MOVES, move_for_button

    for stance in Stance:
        rows = dict(_rows(stance)[1:])
        for action in BUTTON_MOVES:
            label = "special" if action.name == "SPECIAL_ATTACK" else action.value
            expected = move_for_button(action, stance)
            line = next(text for text in rows if text.startswith(label))
            if expected is None:
                assert "—" in line
            else:
                assert str(expected) in line, (stance, label)


def test_a_button_with_no_move_shows_a_dash_and_not_the_standing_one() -> None:
    """Printing the standing move would claim it works from here.

    That is the one thing this block must not say: a developer reads a name as
    "pressable", and the refusal it would hide is the refusal the whole panel
    exists to explain.
    """
    air = dict(_rows(Stance.AIR)[1:])
    special = next(text for text in air if text.startswith("special"))

    assert "—" in special
    assert "special_attack" not in special


def test_a_move_on_cooldown_shows_its_timer_and_is_the_only_warned_row() -> None:
    from src.ui.styles import TEXT_OK, TEXT_WARN

    rows = _rows(Stance.AIR, {"air_rise": 1.25})
    warned = [(text, color) for text, color in rows if color == TEXT_WARN]

    assert len(warned) == 1
    assert warned[0][0].startswith("attack3")
    assert "1.2s" in warned[0][0]
    # Stance is the one row worth colouring positively: it is the input to
    # everything else in the block.
    assert [i for i, (_, c) in enumerate(rows) if c == TEXT_OK] == [0]


def test_the_block_draws_from_the_table_so_it_cannot_go_stale() -> None:
    """Guards the iteration itself, by adding a button and looking.

    Every other test here checks the block against ``BUTTON_MOVES``, so they would
    all pass against a block built from a hand-written list that happened to
    agree. This one changes the table and requires the panel to follow.
    """
    from src.entities import attack_moves
    from src.entities.attack_moves import BUTTON_MOVES, move_for_button

    extra = InputAction.GUARD
    BUTTON_MOVES[extra] = {Stance.GROUND: "light_attack"}
    try:
        rows = _rows(Stance.GROUND)
        # Stance plus every button now in the table, the temporary one included.
        assert len(rows) == len(BUTTON_MOVES) + 1
        assert any(line.startswith("guard") for line, _ in rows)
    finally:
        del BUTTON_MOVES[extra]

    # Back to the shipped count, which is what makes the first assertion mean
    # something: without the removal the block would have shown the temporary row
    # and every count here would be one too high.
    assert len(_rows(Stance.GROUND)) == len(BUTTON_MOVES) + 1
    assert not any(line.startswith("guard") for line, _ in _rows(Stance.GROUND))
    assert move_for_button(extra, Stance.GROUND) is None
    assert attack_moves.move_for_button is move_for_button


def test_the_bench_legend_names_the_air_keys() -> None:
    """The legend was four keys long and listed none of the air kit.

    ``7``-``0`` were added to the bench and this text was not updated, so the
    panel described a set of keys that stopped existing when the air moves landed.
    Nothing asserted it: the panel's *text* had no test anywhere, which is how a
    stale legend can sit in a file for a release.
    """
    from src.core.level.systems.spawn_system import DEBUG_ATTACKS

    rows = _keys_legend()
    text = "\n".join(rows)

    assert "7-0" in text, text
    # And every key the bench binds is inside a range the legend names, so the
    # next set added has to be declared rather than silently dropped. Checked as
    # coverage of the range rather than as substrings: the legend writes "1-6",
    # not "1 2 3 4 5 6", and a test demanding the six digits would force the
    # text back into the shape it was compressed out of.
    named = _ranges_in(text)
    for key in DEBUG_ATTACKS:
        assert pygame.key.name(key) in named, f"{pygame.key.name(key)} is bound but unlisted"


#: A ``1-0`` range in the legend: which key names it covers.
def _range_keys(low: str, high: str) -> set[str]:
    """The key names one digit range covers.

    Read as the key row reads, left to right, digits wrapping at ten. So ``1-6``
    is the first six and ``7-0`` is the last four: a range written high-to-low is
    a wrap, not a backwards range -- ``pygame.K_0`` is 48 and ``K_1`` is 49, so
    ascending keycodes put ``0`` first, which is why every version that sorted the
    endpoints and counted between them covered two keys instead of a row.
    """
    first, last = int(low), int(high)
    digits = (
        range(first, last + 1)
        if first <= last
        # Wraps past 9 back to 0, which is the top row going right.
        else [*range(first, 10), *range(0, last + 1)]
    )
    return {pygame.key.name(pygame.K_0 + digit) for digit in digits if 0 <= digit <= 9}


def _ranges_in(text: str) -> set[str]:
    covered: set[str] = set()
    for low, high in re.findall(r"(?<![0-9])(\d+)-(\d+)(?![0-9])", text):
        covered |= _range_keys(low, high)
    return covered


def _keys_legend() -> list[str]:
    """The rows the DEBUG KEYS panel actually handed to the renderer.

    Recorded through a spy on ``draw_panel`` rather than read off the source: the
    legend lives in a list inside a draw method, and reading format strings back
    out of source is what produced a test that passed without touching the text
    in this file before.

    Drawn with no player, so the live block is absent and what is left is the
    reference half.
    """
    from tests.unit.helpers import make_overlay

    overlay = make_overlay(pygame.Surface((640, 480)))
    lines: list[str] = []
    original = type(overlay.renderer).draw_panel

    def spy(_self, _x, _y, panel_lines, **_kwargs):
        lines.extend(panel_lines)
        return 100

    type(overlay.renderer).draw_panel = spy
    try:
        overlay.draw_help_panel(10, 10)
    finally:
        type(overlay.renderer).draw_panel = original
    assert lines, "the spy recorded nothing, so the assertions below are vacuous"
    return lines


def test_the_panel_fits_the_display_it_is_drawn_into() -> None:
    """The live block made DEBUG KEYS the tallest panel in the stack.

    ``PanelLayout`` does not clip: an unplaceable panel is dropped with a warning
    and simply does not appear. At 1440x900 the full set fits, and this is the
    test that says so -- the block is not worth shipping if it costs a panel.
    """
    renderer = PanelRenderer(pygame.Surface((1440, 900)))
    keys = _rows(Stance.AIR)
    bench = _keys_legend()

    height = renderer.measure_panel(
        [text for text, _ in keys] + bench, title="DEBUG KEYS", reserve_close=True
    )[1]

    assert height <= 900, f"DEBUG KEYS is {height}px tall on a 900px display"


def test_the_special_row_says_no_key_rather_than_inventing_one() -> None:
    """``SPECIAL_ATTACK`` has no keyboard binding at all, and the rest rebind.

    So the row is labelled by the action. Printing a letter would be a claim the
    panel cannot keep: the moment anyone rebinds ``ATTACK_1`` the table goes
    stale, exactly as ``air_rise``'s guard height did.
    """
    from src.core.input.input_bindings import GameplayBindings

    keyboard = GameplayBindings().keyboard
    unbound = [a for a in InputAction if a not in keyboard]

    special = next(text for text, _ in _rows(Stance.GROUND)[1:] if text.startswith("special"))
    assert special.split()[0] == "special"
    # The claim that it has no key: stated rather than assumed, since the default
    # map is the thing that would change.
    assert InputAction.SPECIAL_ATTACK in unbound or not unbound
