from typing import Any

from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.entities.player import Player
from src.ui.panel_renderer import PanelLayout, PanelRenderer
from src.ui.styles import TEXT_CRIT, TEXT_OK, TEXT_WARN


def _yes(flag: object) -> str:
    """A flag as a reader says it, padded so the column after it stays put."""
    return "yes" if flag else "no "


class PlayerUI:
    """Collect and display player data.

    STATE and STATS are split by what a line is *for*, which is the rule the two
    panels were already half following and never applying: a live value -- a
    timer running down, a request waiting -- belongs in STATE, a constant of the
    fighter belongs in STATS.

    The split is why the dash used to cost three lines across both panels, and
    why ``dur`` meant two things: STATE printed ``dash.duration_timer`` and STATS
    printed the ``dash_duration`` constant, both labelled ``dur``. Reading it
    twice gave no way to tell which was which. The live one is now ``rem``, the
    constant stays ``dur``, and each panel prints one.

    The attack in progress is deliberately *not* in STATE. It is what the world
    overlay's label card prints on the fighter themselves
    (``ATK <name> p<n> <substate>:<frame> hits:<n>``), so the side panel's copy
    meant reading the same fact in two places. The ``CDs`` line next to it was
    ``combat.cooldowns`` truncated to four -- with seventeen registered moves, the
    air and crouch ones were visible only when they happened to be the first four
    currently cooling.
    """

    def __init__(self, renderer: PanelRenderer):
        self.renderer = renderer

    @staticmethod
    def _state_lines(player: Player, state_machine: Any, compact: bool) -> list[str]:
        if compact:
            return [
                f"State  {state_machine.current_state_name or 'None'}",
                f"Vel    ({player.velocity.x:6.1f}, {player.velocity.y:6.1f})",
                f"Axis   {player.move_axis:+.2f}",
            ]
        current = state_machine.current_state_name or "None"
        previous = state_machine.previous_state_name or "-"
        history = list(state_machine.history)[-6:] if state_machine.history else []
        return [
            f"State  {current}   (prev {previous})",
            f"Hist   {' > '.join(history)}",
            f"Vel    ({player.velocity.x:6.1f}, {player.velocity.y:6.1f})",
            f"Floor  {_yes(player.on_surface['floor'])}  L {_yes(player.on_surface['left'])}"
            f"  R {_yes(player.on_surface['right'])}",
            f"Axis   {player.move_axis:+.2f}",
            # Timers and both jump budgets on one line: all four are live, all
            # four were about one ability, and two lines read as two subjects.
            f"Jump   buf {player.jump.jump_buffer_timer:.2f}s  coy {player.jump.coyote_timer:.2f}s"
            f"  mid {player.jump.midair_jumps_left}  wall {player.jump.wall_jumps_left}",
            # ``rem``, not ``dur``: the time left on the live dash, against the
            # ``dur`` constant STATS prints for the same ability.
            f"Dash   req {_yes(player.dash.requested)}  rem {player.dash.duration_timer:.2f}s",
        ]

    def draw_state_panel(
        self,
        x: int,
        y: int,
        player: Player | None,
        layout: PanelLayout | None = None,
        panel_id: str | None = None,
        compact: bool = False,
    ) -> int:
        if panel_id is not None and self.renderer.interaction.is_closed(panel_id):
            return 0
        if player is None:
            return 0

        sm = player.state_machine
        lines = self._state_lines(player, sm, compact)

        line_colors = {}
        combat = player.combat

        # Geometry only, and the reason no attack name appears here: see the
        # class docstring. The label card already prints it on the fighter.
        shapes = combat.attack_shapes
        anchors = combat.attack_anchors
        if shapes:
            anchor = anchors[0] if anchors else (0.0, 0.0)
            lines.append(
                f"Hitbox {shapes[0].kind.value} x{len(shapes)}"
                f"  anchor ({anchor[0]:.0f},{anchor[1]:.0f})"
            )

        hurt_idx = len(lines)
        hurt_timer = combat.hurt_timer
        is_hurt = combat.is_hurt
        lines.append(f"Hurt   {_yes(is_hurt)} {hurt_timer:.2f}s")
        if is_hurt:
            line_colors[hurt_idx] = TEXT_CRIT

        charging = combat.charging
        if charging.is_charging and charging.attack_name:
            idx = len(lines)
            lines.append(f"Charge {charging.attack_name} {charging.charge_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        stagger_timer = player.stagger_timer
        if stagger_timer > 0:
            idx = len(lines)
            lines.append(f"Stagger {stagger_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        inv_timer = player.invincibility_timer
        if inv_timer > 0:
            idx = len(lines)
            lines.append(f"Invincible {inv_timer:.2f}s")
            line_colors[idx] = TEXT_OK

        return self.renderer.draw_panel(
            x,
            y,
            lines,
            title="PLAYER STATE",
            line_colors=line_colors,
            layout=layout,
            panel_id=panel_id,
        )

    @staticmethod
    def _stats_lines(
        player: Player, combat: CombatComponent | NullCombatComponent, compact: bool
    ) -> list[str]:
        """The constants of a fighter, and nothing that runs down on its own.

        A mirror of :meth:`_state_lines`, for the same reason: the dash was
        spread over three lines in two panels, and the only way to assert
        anything about a panel's *text* is for that text to be buildable without
        a surface. Reading the format strings back out of the source does not
        work -- a line continued over three string literals is three matches, not
        one -- and a test that has to guess at quoting can pass without testing
        anything.
        """
        if compact:
            lines = [
                f"HP     {player.health:.0f}/{player.max_health:.0f}",
                f"Guard  {player.guard.posture:.0f}/{player.guard.max_posture:.0f}",
                f"Move   spd {player.speed:.0f}",
            ]
        else:
            lines = [
                f"HP     {player.health:.0f}/{player.max_health:.0f}",
                f"Guard  {player.guard.posture:.0f}/{player.guard.max_posture:.0f}"
                f"   lock {player.guard.lockout_timer:.2f}s",
                # One dash line, not two. Both were constants of the same ability
                # and STATE printed a third field of it, so the dash was the only
                # subject in the debug view spread over three lines in two panels.
                #
                # Kept to two rows deliberately. Merged into one it is 54
                # characters, which made STATS the widest panel in the stack, and
                # the column flow packs the whole set into 1440x900 -- widening
                # the widest one is what pushes the last panel out of the display
                # entirely. Charges and speed stay together; the two timers drop
                # to a second row that is only as wide as the first.
                f"Dash   {player.dash.charges}/{player.dash.max_charges}"
                f"  spd {player.dash.speed:.0f}  dur {player.dash.duration:.2f}s",
                f"      pen {player.dash.penalty_timer:.2f}s  regen {player.dash.recharge_timer:.2f}s",
                f"Move   spd {player.speed:.0f}  ctrl {player.floor_control:.1f}/{player.air_control:.1f}",
                f"Jump   h {player.jump.jump_height:.0f}  wall {player.jump.wall_jump_height:.0f}",
            ]
        lines.append(
            f"Combo  x{combat.combo_count} (air x{combat.air_combo_count})   {combat.combo_timer:.2f}s"
        )
        return lines

    def draw_stats_panel(
        self,
        x: int,
        y: int,
        player: Player | None,
        layout: PanelLayout | None = None,
        panel_id: str | None = None,
        compact: bool = False,
    ) -> int:
        if panel_id is not None and self.renderer.interaction.is_closed(panel_id):
            return 0
        if player is None:
            return 0

        hp_ratio = player.health / player.max_health if player.max_health else 0
        hp_color = TEXT_OK if hp_ratio > 0.5 else TEXT_WARN if hp_ratio > 0.25 else TEXT_CRIT

        lines = self._stats_lines(player, player.combat, compact)

        gravity_scale = player.gravity_scale
        line_colors: dict[int, tuple[int, int, int]] = {0: hp_color}
        posture_ratio = (
            player.guard.posture / player.guard.max_posture if player.guard.max_posture else 0
        )
        if player.guard.lockout_timer > 0:
            line_colors[1] = TEXT_CRIT
        elif posture_ratio <= 0.3:
            line_colors[1] = TEXT_WARN
        if player.guard.riposte_timer > 0:
            idx = len(lines)
            lines.append(f"RIPOSTE {player.guard.riposte_timer:.2f}s")
            line_colors[idx] = TEXT_OK
        if gravity_scale != 1.0:
            idx = len(lines)
            lines.append(f"Juggle grav x{gravity_scale:.2f} {player.juggle_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        otg_timer = player.otg_timer
        if otg_timer > 0:
            idx = len(lines)
            lines.append(f"OTG guard {otg_timer:.2f}s")
            line_colors[idx] = TEXT_OK

        return self.renderer.draw_panel(
            x, y, lines, title="STATS", line_colors=line_colors, layout=layout, panel_id=panel_id
        )
