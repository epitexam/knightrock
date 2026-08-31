from typing import Any
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_TITLE, TEXT_CRIT, TEXT_WARN, TEXT_OK

class PlayerUI:
    """Collect and display player data."""
    
    def __init__(self, renderer: PanelRenderer):
        self.renderer = renderer

    def draw_state_panel(self, x: int, y: int, player: Any) -> int:
        if not player or not getattr(player, "state_machine", None):
            return 0

        sm = player.state_machine
        current = sm.current_state_name or "None"
        previous = sm.previous_state_name or "-"
        history = list(sm.history)[-6:] if sm.history else []

        lines = [
            f"State  {current}   (prev {previous})",
            f"Hist   {' > '.join(history)}",
            f"Vel    ({player.velocity.x:6.1f}, {player.velocity.y:6.1f})",
            f"Floor {player.on_surface['floor']!s:5}  L {player.on_surface['left']!s:5}  R {player.on_surface['right']!s:5}",
            f"Axis   {player.move_axis:+.2f}",
            f"Jump   buf {player.jump_buffer_timer:.2f}s  coy {player.coyote_timer:.2f}s",
            f"Jumps  mid {player.midair_jumps_left}  wall {player.wall_jumps_left}",
            f"Dash   req {player.dash.requested!s:5}  dur {player.dash.duration_timer:.2f}s",
        ]

        line_colors = {}
        combat = getattr(player, "combat", None)

        if combat:
            attack_name = combat.state.attack_name if hasattr(combat.state, "attack_name") else "-"
            phase_idx = getattr(combat.state, "phase_index", 0)
            total_phases = len(combat.state.current_attack_def.phases) if getattr(combat.state, "current_attack_def", None) else 0

            phase_text = f"{phase_idx}/{total_phases-1}" if total_phases > 0 else "idle"
            lines.append(f"Combat {attack_name}  phase {phase_text}")

            hurt_idx = len(lines)
            hurt_timer = getattr(combat, "hurt_timer", 0.0)
            is_hurt = getattr(combat, "is_hurt", False)
            lines.append(f"Hurt   {is_hurt!s:5} {hurt_timer:.2f}s")
            if is_hurt: line_colors[hurt_idx] = TEXT_CRIT

            charging = getattr(combat, "charging", None)
            if charging and getattr(charging, "is_charging", False) and charging.attack_name:
                idx = len(lines)
                lines.append(f"Charge {charging.attack_name} {charging.charge_timer:.2f}s")
                line_colors[idx] = TEXT_WARN

            cooldowns_dict = getattr(combat, "cooldowns", {})
            cooldowns = [f"{name}:{cd:.2f}s" for name, cd in cooldowns_dict.items() if cd > 0]
            if cooldowns: lines.append("CDs    " + ", ".join(cooldowns[:4]))

        stagger_timer = getattr(player, "stagger_timer", 0.0)
        if stagger_timer > 0:
            idx = len(lines)
            lines.append(f"Stagger {stagger_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        inv_timer = getattr(player, "invincibility_timer", 0.0)
        if inv_timer > 0:
            idx = len(lines)
            lines.append(f"Invincible {inv_timer:.2f}s")
            line_colors[idx] = TEXT_OK

        return self.renderer.draw_panel(x, y, lines, title="PLAYER STATE", line_colors=line_colors)

    def draw_stats_panel(self, x: int, y: int, player: Any) -> int:
        if not player: return 0

        hp_ratio = player.health / player.max_health if player.max_health else 0
        hp_color = TEXT_OK if hp_ratio > 0.5 else TEXT_WARN if hp_ratio > 0.25 else TEXT_CRIT

        lines = [
            f"HP     {player.health:.0f}/{player.max_health:.0f}",
            f"Block  {player.block_stamina:.2f}/{player.max_block_stamina:.2f}   cd {player.block_cooldown_timer:.2f}s",
            f"Dash   {player.dash_charges}/{player.max_dash_charges}   pen {player.dash_penalty_timer:.2f}s  regen {player.dash_recharge_timer:.2f}s",
            f"Move   spd {player.speed:.0f}  ctrl {player.floor_control:.1f}/{player.air_control:.1f}",
            f"Jump   h {player.jump_height:.0f}  wall {player.wall_jump_height:.0f}",
            f"Dash   spd {player.dash_speed:.0f}  dur {player.dash_duration:.2f}s  fric {player.dash_friction:.1f}",
        ]

        combat = getattr(player, "combat", None)
        if combat:
            lines.append(f"Combo  x{getattr(combat, 'combo_count', 0)}   {getattr(combat, 'combo_timer', 0.0):.2f}s")
        else:
            lines.append("Combo  x0   0.00s")

        return self.renderer.draw_panel(x, y, lines, title="STATS", line_colors={0: hp_color})