"""Behavioral tests for hitbox timing, geometry, lifecycle, and trades."""

import math

import pytest
from pygame.sprite import Group

from src.combat.attack_data import GOBLIN_ATTACKS, PLAYER_ATTACKS, SLIME_ATTACKS
from src.combat.attack_state import AttackStateMachine
from src.combat.frame_data import AttackDefinition, HitProperties, PhaseDefinition
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from tests.unit.helpers import activate, entity_at, make_entity
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def test_attack_state_never_skips_an_active_window_on_large_delta() -> None:
    machine = AttackStateMachine({"test": attack(phase(active=1))})
    assert machine.start("test")

    machine.update(0.2)

    assert machine.is_active
    assert machine.frame_counter == 0


def test_hitbox_tracks_facing_and_reuses_its_rectangle() -> None:
    owner = entity_at(
        100.0,
        definition=attack(
            phase(offset=(25.0, -5.0)),
            lock_direction=False,
        ),
    )
    activate(owner)
    first_rect = owner.combat.attack_box
    assert first_rect is not None
    assert first_rect.center == (
        owner.hitbox.centerx + 25.0,
        owner.hitbox.centery - 5.0,
    )

    owner.hitbox.x += 10.0
    owner.facing_right = False
    owner.combat.sync_attack_box()

    assert owner.combat.attack_box is first_rect
    assert first_rect.center == (
        owner.hitbox.centerx - 25.0,
        owner.hitbox.centery - 5.0,
    )


def test_entity_update_syncs_attack_box_after_movement() -> None:
    owner = entity_at(0.0, definition=attack(phase(offset=(20.0, 0.0))))
    owner.velocity.x = 600.0
    assert owner.combat.start_attack("test")

    owner.update(1 / 60)

    assert owner.combat.attack_box is not None
    assert owner.combat.attack_box.centerx == pytest.approx(owner.hitbox.centerx + 20.0)


def test_attack_box_is_resynchronized_after_entity_separation() -> None:
    definition = attack(phase(size=(20.0, 20.0), offset=(0.0, 0.0)))
    attacker = entity_at(0.0, faction="same", definition=definition)
    other = entity_at(10.0, faction="same")
    activate(attacker)
    initial_center = attacker.combat.attack_box.center
    loop = GameplayLoop.combat_only()

    loop.process_combat_and_separation(
        1 / 60,
        Group(attacker, other),
        Group(attacker, other),
    )

    assert attacker.hitbox.center != initial_center
    assert attacker.combat.attack_box.center == attacker.hitbox.center


def test_simultaneous_attacks_trade_independently_of_resolution_order() -> None:
    definition = attack(phase(size=(60.0, 40.0), offset=(0.0, 0.0)))
    left = entity_at(0.0, faction="left", definition=definition)
    right = entity_at(10.0, faction="right", definition=definition)
    activate(left)
    activate(right)

    CombatSystem().process_attacks([left, right])

    assert left.health == 90.0
    assert right.health == 90.0


def test_combat_system_materializes_generators_once() -> None:
    definition = attack(phase(size=(60.0, 40.0), offset=(0.0, 0.0)))
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    target = entity_at(10.0, faction="target")
    activate(attacker)
    system = CombatSystem()

    system.process_attacks(entity for entity in (attacker, target))

    assert target.health == 90.0
    assert system.metrics.pairs_tested == 1
    assert system.metrics.overlaps == 1
    assert system.metrics.contacts == 1


def test_rollback_restore_synchronizes_derived_attack_geometry() -> None:
    owner = entity_at(0.0, definition=attack(phase()))
    activate(owner)
    snapshot = owner.combat.save_state()
    owner.combat.reset()
    assert owner.combat.attack_box is None

    owner.hitbox.x = 50.0
    owner.combat.load_state(snapshot)

    assert owner.combat.attack_box is not None
    assert owner.combat.attack_box.centerx == pytest.approx(owner.hitbox.centerx + 20.0)

    # P1 (D3, re-derivation) : la boucle rejoue les captures frontiere
    # explicitement ; prev est re-derive depuis cur, jamais relu a travers
    # un load sans capture. Aucun champ snapshot n'existe pour prev.
    assert owner.combat.hitbox.prev_rects == ()
    owner.combat.capture_attack_origin()
    owner.capture_sweep_origin()
    assert owner.combat.hitbox.prev_rects[0].center == (
        pytest.approx(owner.combat.attack_box.centerx),
        pytest.approx(owner.combat.attack_box.centery),
    )


def test_death_clears_active_offensive_state() -> None:
    owner = entity_at(0.0, definition=attack(phase()))
    activate(owner)

    owner.die()

    assert owner.is_dead
    assert owner.combat.attack_box is None
    assert not owner.combat.is_attacking


def test_hurtbox_is_distinct_and_synchronized_with_collider() -> None:
    owner = entity_at(0.0, hurtbox_inflate=(-8.0, -4.0))
    assert owner.hurtbox is not owner.hitbox
    assert owner.hurtbox.size == (32.0, 36.0)

    owner.hitbox.center = (120.0, 80.0)
    owner.sync_rects()

    assert owner.hurtbox.center == owner.hitbox.center


@pytest.mark.parametrize(
    ("reset_targets", "expected_contact"),
    [(False, True), (True, False)],
)
def test_phase_policy_controls_repeat_contacts(reset_targets: bool, expected_contact: bool) -> None:
    machine = AttackStateMachine(
        {
            "test": attack(
                phase(active=1),
                phase(active=1, reset_targets=reset_targets),
            )
        }
    )
    assert machine.start("test")
    machine.update(1 / 60)
    machine.targets_hit.add("target")
    machine.update(1 / 60)
    machine.update(1 / 60)

    assert ("target" in machine.targets_hit) is expected_contact


def test_extra_box_hits_target_outside_primary_reach() -> None:
    definition = attack(
        phase(
            size=(20.0, 20.0),
            offset=(20.0, 0.0),
            extra=[((20.0, 20.0), (-30.0, 0.0))],
        )
    )
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    # Only the rear extra box overlaps this target: the primary box misses.
    target = entity_at(-30.0, faction="target")
    activate(attacker)

    assert len(attacker.combat.attack_boxes) == 2
    assert attacker.combat.attack_boxes[0] is attacker.combat.attack_box

    CombatSystem().process_attacks([attacker, target])

    assert target.health == 90.0
    assert target.id in attacker.combat.targets_hit


def test_single_box_attack_exposes_only_the_primary_box() -> None:
    owner = entity_at(0.0, definition=attack(phase()))
    activate(owner)

    assert owner.combat.attack_boxes == (owner.combat.attack_box,)


def test_animated_box_interpolates_along_startup_curve() -> None:
    owner = entity_at(
        0.0,
        definition=attack(
            phase(
                startup=4,
                active=4,
                offset=(10.0, 0.0),
                keyframes=(
                    (0, (20.0, 20.0), (10.0, 0.0)),
                    (4, (40.0, 20.0), (30.0, 0.0)),
                ),
            )
        ),
    )
    assert owner.combat.start_attack("test")
    # One attack frame per tick by design: a single update advances the
    # machine by one frame, landing mid-curve (frame 1 of 0->4).
    owner.combat.update(1 / 60)
    owner.combat.sync_attack_box()

    box = owner.combat.attack_box
    assert box is not None
    assert box.size == (25.0, 20.0)
    assert box.centerx == owner.hitbox.centerx + 15.0


def test_animated_box_holds_last_keyframe_through_active() -> None:
    owner = entity_at(
        0.0,
        definition=attack(
            phase(
                startup=2,
                active=4,
                offset=(10.0, 0.0),
                keyframes=((0, (20.0, 20.0), (10.0, 0.0)),),
            )
        ),
    )
    activate(owner)  # startup done, first active frame
    owner.combat.update(1 / 60)
    owner.combat.sync_attack_box()

    box = owner.combat.attack_box
    assert box is not None
    assert box.size == (20.0, 20.0)
    assert box.centerx == owner.hitbox.centerx + 10.0


def test_animated_hit_connects_only_when_curve_reaches_target() -> None:
    definition = attack(
        phase(
            startup=4,
            active=4,
            size=(10.0, 10.0),
            offset=(10.0, 0.0),
            keyframes=(
                (0, (10.0, 10.0), (10.0, 0.0)),
                (4, (10.0, 10.0), (60.0, 0.0)),
            ),
        )
    )
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    target = entity_at(60.0, faction="target")
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()

    early_box = attacker.combat.attack_box
    assert early_box is not None
    assert not early_box.colliderect(target.hurtbox)

    for _ in range(3):
        attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()

    late_box = attacker.combat.attack_box
    assert late_box is not None
    assert late_box.colliderect(target.hurtbox)

    CombatSystem().process_attacks([attacker, target])
    assert target.health == 90.0


def test_disjoint_boxes_share_one_contact_per_target() -> None:
    definition = attack(
        phase(
            size=(20.0, 20.0),
            offset=(0.0, 0.0),
            extra=[((20.0, 20.0), (0.0, 0.0))],
        )
    )
    attacker = entity_at(0.0, faction="attacker", definition=definition)
    target = entity_at(0.0, faction="target")
    activate(attacker)
    system = CombatSystem()

    system.process_attacks([attacker, target])

    # Both boxes overlap, but the per-phase `targets_hit` policy still
    # records exactly one contact: no double damage from twin boxes.
    assert target.health == 90.0
    assert system.metrics.contacts == 1


def test_invalid_frame_data_fails_fast() -> None:
    with pytest.raises(ValueError, match="active frame"):
        phase(active=0)
    with pytest.raises(ValueError, match="at least one phase"):
        AttackDefinition(phases=(), cooldown=0.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        HitProperties(damage=-1)

    invalid_cancel = PhaseDefinition(
        startup_frames=1,
        active_frames=1,
        recovery_frames=1,
        hitbox_size=(10.0, 10.0),
        hitbox_offset=(0.0, 0.0),
        hit=HitProperties(damage=1),
        cancel_into=("missing",),
    )
    with pytest.raises(ValueError, match="unknown cancels"):
        entity_at(0.0, definition=attack(invalid_cancel))


# ── P0.1 golden trajectoires + recensement (hitbox_amelioration.md) ─────────
#
# Les trajectoires ci-dessous figent la geometrie predetection, frame par
# frame d animation (`attack_state.animation_frame`), proprietaire immobile
# en x=0. Tout changement de ces valeurs en P1+ doit etre explique dans le
# recettage du rapport (regression vs changement voulu). Constate notable :
# `dash_attack` (startup=1) n expose JAMAIS de frame startup — le premier
# sync voit deja ACTIVE (trou du seed, cf. D1) ; la recovery expose encore
# de la geometrie (comportement legacy, detection verrouillee sur ACTIVE).


def _drive(name: str, attacks: dict) -> list[tuple[str, int, tuple | None]]:
    owner = make_entity(pos=(0.0, 0.0), faction="A", attacks=dict(attacks))
    assert owner.combat.start_attack(name), name
    frames: list[tuple[str, int, tuple | None]] = []
    while owner.combat.is_attacking:
        owner.combat.update(1 / 60)
        owner.combat.sync_attack_box()
        box = owner.combat.attack_box
        frames.append(
            (
                owner.combat.state.sub_state.value,
                owner.combat.state.phase_index,
                None
                if box is None
                else (
                    round(box.centerx, 3),
                    round(box.centery, 3),
                    round(box.width, 3),
                    round(box.height, 3),
                ),
            )
        )
    return frames


def test_golden_dash_attack_trajectory() -> None:
    frames = _drive("dash_attack", PLAYER_ATTACKS)

    assert len(frames) == 13
    # Pas de frame startup : startup=1 bascule en ACTIVE avant le 1er sync.
    assert frames[0][0] == "active"
    assert all(box == (62.0, 12.0, 70.0, 24.0) for _, _, box in frames if box is not None)
    assert frames[-1] == ("idle", 0, None)


def test_golden_sweeping_arc_trajectory() -> None:
    frames = _drive("sweeping_arc", PLAYER_ATTACKS)

    assert len(frames) == 17
    assert [sub for sub, _, _ in frames].count("startup") == 5
    assert [sub for sub, _, _ in frames].count("active") == 6
    assert frames[0] == ("startup", 0, (38.333, 17.333, 32.5, 16.333))
    assert frames[5] == ("active", 0, (50.0, 14.0, 55.0, 28.0))
    assert frames[10] == ("active", 0, (56.667, 12.333, 67.5, 33.0))
    assert frames[-1] == ("idle", 0, None)


def test_golden_sky_launcher_trajectory() -> None:
    frames = _drive("sky_launcher", PLAYER_ATTACKS)

    assert len(frames) == 22
    assert [sub for sub, _, _ in frames].count("startup") == 6
    assert [sub for sub, _, _ in frames].count("active") == 5
    assert all(box == (36.0, -8.0, 32.0, 48.0) for _, _, box in frames if box is not None)
    assert frames[-1] == ("idle", 0, None)


def test_golden_special_attack_phase_transitions() -> None:
    """Golden P0.1 : special_attack (5 phases), geometrie figee par phase.

    Chaque phase demarre sur son propre startup (pas de saut depuis l ACTIVE
    de la phase precedente) et change de taille (offset (0,-20) constant,
    pas de keyframes). Premier ACTIVE de phase N = boite du startup de N.
    """
    frames = _drive("special_attack", PLAYER_ATTACKS)

    assert len(frames) == 110  # 4 * 18 + 38
    # Frontieres internes entre phases (le tick final idle ramene phase 0).
    boundaries = [
        i
        for i in range(1, len(frames) - 1)
        if frames[i][1] != frames[i - 1][1]
    ]
    assert boundaries == [17, 35, 53, 71]
    assert [sub for sub, _, _ in frames].count("startup") == 26
    assert [sub for sub, _, _ in frames].count("active") == 42
    assert [sub for sub, _, _ in frames].count("recovery") == 41
    # Tailles figees par phase : 30 -> 40 -> 50 -> 70 -> 90, centre constant.
    phase_starts = [0, *boundaries]
    phase_ends = [*boundaries, len(frames) - 1]
    for phase, (start, end) in enumerate(zip(phase_starts, phase_ends)):
        size = (30.0, 40.0, 50.0, 70.0, 90.0)[phase]
        assert frames[start] == (
            "startup",
            phase,
            (20.0, 0.0, size, size),
        ), frames[start]
        # Toute la phase voit la meme geometrie (pas de keyframes).
        for _, ph, box in frames[start:end]:
            if ph == phase and box is not None:
                assert box == (20.0, 0.0, size, size)
    assert frames[0] == ("startup", 0, (20.0, 0.0, 30.0, 30.0))
    assert frames[-1] == ("idle", 0, None)


def test_golden_claw_swipe_phase_transitions() -> None:
    """Golden P0.1 : claw_swipe (2 phases), transition recovery -> startup.

    Phase 0 : 40x20 offset (20,-4) -> centre (40,16) ; phase 1 : 48x24
    offset (24,4) -> centre (44,24). Le premier tick de phase 1 expose la
    geometrie du startup de phase 1 (jamais l ACTIVE de phase 0).
    """
    frames = _drive("claw_swipe", GOBLIN_ATTACKS)

    assert len(frames) == 25  # 13 + 12
    boundaries = [
        i
        for i in range(1, len(frames) - 1)
        if frames[i][1] != frames[i - 1][1]
    ]
    assert boundaries == [12]
    assert [sub for sub, _, _ in frames].count("startup") == 5
    assert [sub for sub, _, _ in frames].count("active") == 10
    assert frames[0] == ("startup", 0, (40.0, 16.0, 40.0, 20.0))
    assert frames[12] == ("startup", 1, (44.0, 24.0, 48.0, 24.0))
    assert all(
        box == (40.0, 16.0, 40.0, 20.0)
        for _, ph, box in frames[:12]
        if box is not None and ph == 0
    )
    assert all(
        box == (44.0, 24.0, 48.0, 24.0)
        for _, ph, box in frames[12:-1]
        if box is not None and ph == 1
    )
    assert frames[-1] == ("idle", 0, None)


def _lethal_jumps(attacks: dict, name: str) -> list[float]:
    """Deplacements de centre vus par la detection (vers un tick ACTIVE).

    Ne retient que les arrives en ACTIVE : seul ce sous-etat est teste par
    `_attacker_ready`, donc seuls ces sauts peuvent changer un contact en P1.
    """
    owner = make_entity(pos=(0.0, 0.0), faction="A", attacks=dict(attacks))
    assert owner.combat.start_attack(name), name
    jumps: list[float] = []
    prev: tuple[float, float] | None = None
    while owner.combat.is_attacking:
        owner.combat.update(1 / 60)
        owner.combat.sync_attack_box()
        box = owner.combat.attack_box
        cur = None if box is None else (box.centerx, box.centery)
        if owner.combat.state.is_active and cur is not None and prev is not None:
            jumps.append(math.hypot(cur[0] - prev[0], cur[1] - prev[1]))
        prev = cur
    return jumps


def test_census_no_lethal_window_jump_needs_sweep_on_static_owner() -> None:
    """Recensement P0 : aucun saut >= 4 px en fenetre letale, data actuelle.

    Verifie le 2026-09-20 : `sweeping_arc` ~2.43 px/frame en startup->active,
    `claw_swipe` 8.94 px en recovery->startup de phase (non letal),
    `sweeping_arc` 21.4 px en active->recovery (non letal). Consequence : le
    sweep P1 ne change aucun contact a proprietaire immobile — il ne capture
    que le mouvement du porteur (lunge/dash/chute), i.e. les tunnelings.
    Toute edition des donnees qui fait echouer ce test reclame une
    revalidation du golden simulation (changement voulu, pas regression).
    """
    worst: dict[str, float] = {}
    for set_name, sets in (
        ("player", PLAYER_ATTACKS),
        ("goblin", GOBLIN_ATTACKS),
        ("slime", SLIME_ATTACKS),
    ):
        for name in sets:
            jumps = _lethal_jumps(sets, name)
            worst[f"{set_name}.{name}"] = max(jumps, default=0.0)

    assert worst["player.sweeping_arc"] == pytest.approx(2.427, abs=0.01)
    for key, value in worst.items():
        assert value < 4.0, f"{key}: saut letal {value:.2f} px >= seuil sweep"
