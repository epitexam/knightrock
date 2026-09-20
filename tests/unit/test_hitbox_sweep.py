"""P1 sweep CCD tests (hitbox_amelioration.md, reception P1).

Cas (b), (b') et (b'') : ordre de tick REEL verifie code — capture,
`start_attack` (seed pool+prev), `update`, mouvement (lunge), sync,
detection (`entity.py:831-842`, interrupt synchrone
`state_machine.py:127-158`, lunge `player_states.py:147`).

Les trois cas sont verts : (b) par le sweep union prev+cur branche
dans `CombatSystem` (P1.4), (b')/(b'') par le seed + la capture
frontiere (P1.2/P1.3, geometrie deja recouvrante en discret).
"""

import json
import math

import pygame
import pytest

from src.combat.sweep import swept_box
from src.core.level.systems.combat_system import CombatSystem
from src.core.settings import Combat as CombatSettings
from src.core.settings import Physics as PhysicsSettings
from src.core.settings import Simulation as SimulationSettings
from src.physics.entity_grid import EntityGrid
from tests.unit.helpers import entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _lunge_definition() -> object:
    return attack(phase(startup=1, active=8, recovery=1, size=(20.0, 20.0), offset=(0.0, 0.0)))


def test_lunge_frame1_sweeps_transition_tick() -> None:
    """(b) Lunge frame 1 : seed startup -> ACTIVE post-lunge, meme tick.

    Geometrie (verifiee sur le repro 2.1 : box.x = attacker.x + 10) :
    attaquant en x=10 -> seed (20..40) chevauche la hurtbox cible (20..60) ;
    lunge +40 -> cur (60..80) la rate ; l union (20..80) touche.
    Sans seed de `prev`, discret et aucun contact.
    """
    attacker = entity_at(10.0, faction="A", definition=_lunge_definition())
    target = entity_at(20.0, faction="B")
    attacker.combat.capture_attack_origin()  # P1 : frontiere, comme gameplay_loop
    assert attacker.combat.start_attack("test")  # P1 : seed pool+prev
    attacker.combat.update(1 / 60)  # STARTUP(1) -> ACTIVE
    attacker.hitbox.x += 40.0  # lunge : Entity.update applique move avant sync
    attacker.combat.sync_attack_box()

    system = CombatSystem()
    system.process_attacks([attacker, target])

    assert system.metrics.contacts == 1


def test_startup_ge2_seeds_naturally_via_capture() -> None:
    """(b') `startup >= 2` : `prev` du 1er ACTIVE = startup, via capture."""
    definition = attack(phase(startup=2, active=4, recovery=1, size=(20.0, 20.0), offset=(0.0, 0.0)))
    attacker = entity_at(10.0, faction="A", definition=definition)
    target = entity_at(20.0, faction="B")

    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)  # f0 -> f1, reste STARTUP
    assert not attacker.combat.state.is_active
    attacker.combat.sync_attack_box()
    startup_center = attacker.combat.attack_box.center

    attacker.combat.capture_attack_origin()  # tick N+1 : prev = startup
    attacker.combat.update(1 / 60)  # f1 -> f2, ACTIVE
    attacker.combat.sync_attack_box()

    assert attacker.combat.hitbox.prev_rects[0].center == pytest.approx(startup_center)
    system = CombatSystem()
    system.process_attacks([attacker, target])
    assert system.metrics.contacts == 1


def test_phase_transition_sweeps_from_own_startup() -> None:
    """(b'') Transition de phase : 1er ACTIVE de phase N depuis son startup.

    Les phases sont separees par recovery + startup (`attack_state.py`) :
    aucun `prev` de l ACTIVE precedente ne doit fuiter (et on n invalide
    rien — la capture assure la continuite, cf. D1).
    """
    definition = attack(
        phase(startup=1, active=1, recovery=1, size=(20.0, 20.0), offset=(0.0, 0.0)),
        phase(startup=1, active=1, recovery=1, size=(20.0, 20.0), offset=(30.0, 0.0)),
    )
    attacker = entity_at(0.0, faction="A", definition=definition)
    target = entity_at(30.0, faction="B")
    system = CombatSystem()

    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)  # phase 0 ACTIVE
    attacker.combat.sync_attack_box()
    system.process_attacks([attacker, target])

    attacker.combat.update(1 / 60)  # phase 0 RECOVERY
    attacker.combat.sync_attack_box()
    attacker.combat.capture_attack_origin()
    attacker.combat.update(1 / 60)  # phase 1 STARTUP
    attacker.combat.sync_attack_box()
    startup_p1 = attacker.combat.attack_box.center

    attacker.combat.capture_attack_origin()  # prev = startup phase 1
    attacker.combat.update(1 / 60)  # phase 1 ACTIVE
    attacker.combat.sync_attack_box()

    prev_center = attacker.combat.hitbox.prev_rects[0].center
    assert prev_center == pytest.approx(startup_p1)
    assert prev_center[0] == pytest.approx(startup_p1[0])
    system.process_attacks([attacker, target])
    assert system.metrics.contacts == 1


def test_pygame_frect_union_semantics_for_sweep() -> None:
    """Sanity non-xfail : l union prev+cur est l operateur du sweep P1."""
    prev = pygame.FRect(20.0, 10.0, 20.0, 20.0)
    cur = pygame.FRect(60.0, 10.0, 20.0, 20.0)
    target = pygame.FRect(20.0, 10.0, 40.0, 30.0)
    assert not cur.colliderect(target)
    assert cur.union(prev).colliderect(target)


# --- Reception P1 : cas (a), (c), (d), (f), (g), (h), (h'), (i) ------------


def _run_sweep_tick(attacker, target) -> CombatSystem:
    """One detection pass, exactly as the gameplay loop sees the tick."""
    system = CombatSystem()
    system.process_attacks([attacker, target])
    return system


def test_fine_target_miss_discrete_hit_via_sweep() -> None:
    """(a) Repro 2.1 : saut 40 px, ACTIVE, cible fine.

    Miss en discret (boxes finales), hit via sweep — le test rejoue la
    capture frontiere comme `gameplay_loop.update`.
    """
    attacker = entity_at(0.0, faction="A", definition=_lunge_definition())
    target = entity_at(70.0, faction="B")
    target.capture_sweep_origin()  # prev hurtbox (50..90)
    target.hitbox.x -= 45.0  # croisee pendant le tick
    target.sync_rects()  # cur hurtbox (25..65)
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")  # seed prev box (10..30)
    attacker.combat.update(1 / 60)  # STARTUP(1) -> ACTIVE
    attacker.hitbox.x += 60.0  # saut + lunge du porteur (60 px < borne MAX)
    attacker.combat.sync_attack_box()  # cur box (70..90) : discret, rate (25..65)

    # Discret : les boxes finales ne se recouvrent plus.
    assert attacker.combat.attack_box.colliderect(target.hurtbox) is False
    system = _run_sweep_tick(attacker, target)
    # Sweep : la box seed (10..30) recouvre la hurtbox cur (15..55).
    assert system.metrics.contacts == 1


def test_rollback_rederives_prev_without_snapshot_field() -> None:
    """(c) save/load puis capture puis contact au tick suivant.

    Non-regression 2.4 : prouve la re-derivation D3 — aucun champ
    snapshot ; `load_state` remet `prev` a vide, la capture frontiere
    suivante refait `prev` depuis `cur` re-synchronise.
    """
    attacker = entity_at(10.0, faction="A", definition=_lunge_definition())
    target = entity_at(60.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)  # ACTIVE f0
    attacker.combat.sync_attack_box()
    snapshot = attacker.combat.save_state()

    attacker.combat.reset()
    assert attacker.combat.hitbox.prev_rects == ()

    attacker.hitbox.x = 40.0  # respawn/rollback a une autre position
    attacker.combat.load_state(snapshot)  # re-sync cur, prev = ()
    assert attacker.combat.hitbox.prev_rects == ()
    attacker.combat.capture_attack_origin()  # frontiere : prev = cur
    assert attacker.combat.hitbox.prev_rects[0].center == (
        pytest.approx(attacker.combat.attack_box.centerx),
        pytest.approx(attacker.combat.attack_box.centery),
    )
    attacker.hitbox.x += 40.0
    attacker.combat.sync_attack_box()  # lunge post-rollback

    system = _run_sweep_tick(attacker, target)
    assert system.metrics.contacts == 1


class _CountingGrid(EntityGrid):
    """EntityGrid counting post-prune queries for the parity helper."""

    def __init__(self) -> None:
        super().__init__()
        self.queries = 0

    def near(self, box):  # noqa: ANN001, ANN202 (test double)
        self.queries += 1
        return super().near(box)


def test_grid_parity_candidates_and_contacts_with_and_without_grid() -> None:
    """(d) Parite grille : candidats + contacts avec/sans `EntityGrid`.

    Deux passes sur des doublons isomorphes (une par mode) : la premiere
    passe enregistre `targets_hit` et applique les degats, elle ne doit
    pas polluer la seconde (sinon la parite mesure un double-hit, pas
    l elagage).
    """
    results = []
    for use_grid in (False, True):
        definition = attack(phase(size=(20.0, 20.0), offset=(0.0, 0.0)))
        attacker = entity_at(10.0, faction="A", definition=definition)
        target = entity_at(20.0, faction="B")
        attacker.combat.capture_attack_origin()
        assert attacker.combat.start_attack("test")
        attacker.combat.update(1 / 60)  # ACTIVE f0 : prev seed (10..30)
        attacker.hitbox.x += 60.0  # lunge < borne MAX : cur (70..90)
        attacker.combat.sync_attack_box()
        target.capture_sweep_origin()

        system = CombatSystem()
        if use_grid:
            grid = _CountingGrid()
            grid.rebuild([attacker, target])
            system.process_attacks([attacker, target], grid)
            # Non bloquant (D2) : incremente apres elagage, borne seulement.
            assert grid.queries == len(attacker.combat.swept_attack_boxes)
        else:
            system.process_attacks([attacker, target])
        results.append(
            (system.metrics.pairs_tested, system.metrics.overlaps, system.metrics.contacts)
        )

    assert results[0] == results[1] == (1, 1, 1)


def test_dodge_within_one_tick_stays_hittable() -> None:
    """(f) Cible esquivant de > 4 px : touchable 1 tick (bilateral genereux)."""
    attacker = entity_at(0.0, faction="A", definition=attack(phase(size=(20.0, 20.0))))
    target = entity_at(90.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)  # ACTIVE (10..30) vs hurtbox (70..110)
    target.hitbox.x += 5.0  # esquive > SWEEP_MIN au-dela du bord
    target.sync_rects()  # cur hurtbox (75..115) : discret, rate

    # Cote cible seul : l union (70..115) ne rejoint toujours pas la box
    # d attaque (10..30) — la generosite ne fabrique pas de touche magique.
    assert attacker.combat.attack_box.colliderect(target.hurtbox) is False
    assert target.swept_hurtbox().colliderect(attacker.combat.attack_box) is False

    # Face a un lunge, la meme esquive laisse passer le coup 1 tick :
    # box cur (42..62) rate la hurtbox esquivée (65..105), mais les unions
    # se recouvrent (box swept 10..62 vs cible swept 60..105).
    attacker2 = entity_at(0.0, faction="A", definition=_lunge_definition())
    target2 = entity_at(60.0, faction="B")
    target2.capture_sweep_origin()  # prev (60..100)
    attacker2.combat.capture_attack_origin()
    assert attacker2.combat.start_attack("test")  # seed box (10..30)
    attacker2.combat.update(1 / 60)  # ACTIVE
    attacker2.hitbox.x += 32.0  # lunge : cur box (42..62)

    attacker2.combat.sync_attack_box()
    target2.hitbox.x += 5.0  # esquive : cur hurtbox (65..105)
    target2.sync_rects()

    assert attacker2.combat.attack_box.colliderect(target2.hurtbox) is False
    assert target2.swept_hurtbox().colliderect(attacker2.combat.attack_box)
    system = _run_sweep_tick(attacker2, target2)
    assert system.metrics.contacts == 1


def test_teleport_beyond_max_yields_no_phantom_contact() -> None:
    """(g) Deplacement > MAX (respawn, gros carry) -> swept = cur."""
    prev = pygame.FRect(0.0, 0.0, 40.0, 40.0)
    cur = pygame.FRect(2000.0, 0.0, 40.0, 40.0)
    swept = swept_box(prev, cur)
    assert swept.size == cur.size
    assert swept.topleft == cur.topleft

    # Bout en bout : le smear d une cible teleportee ne cree aucun contact.
    attacker = entity_at(0.0, faction="A", definition=attack(phase(size=(20.0, 20.0))))
    target = entity_at(2000.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)  # ACTIVE (10..30)
    attacker.combat.sync_attack_box()
    target.hitbox.x = 100.0  # teleport pendant le tick (respawn/carry)
    target.capture_sweep_origin()
    target.hitbox.x = 2000.0  # retour : prev (100..140) doit etre ignore

    assert target.swept_hurtbox().topleft == target.hurtbox.topleft
    system = _run_sweep_tick(attacker, target)
    assert system.metrics.contacts == 0


def test_owner_push_between_syncs_sweeps_full_width() -> None:
    """(h) Proprietaire decale entre les deux syncs (push separation simule)."""
    attacker = entity_at(0.0, faction="A", definition=attack(phase(size=(20.0, 20.0))))
    target = entity_at(45.0, faction="B")
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()  # 1er sync : cur (0..20), rate la cible
    attacker.hitbox.x += 30.0  # push/separation entre les deux syncs
    attacker.combat.sync_attack_box()  # 2e sync : cur (30..50)

    # prev (0..20) intact (aucune capture entre les deux syncs) : sweep
    # pleine largeur, alors que cur seul reste sous la cible.
    swept = attacker.combat.hitbox.swept_rects[0]
    assert swept.width == pytest.approx(50.0)
    system = _run_sweep_tick(attacker, target)
    assert system.metrics.contacts == 1


def test_stationary_attacker_swept_equals_cur_from_second_tick() -> None:
    """(h') Attaquant immobile 3 ticks : swept == cur des le 2e tick."""
    attacker = entity_at(0.0, faction="A", definition=attack(phase(size=(20.0, 20.0))))
    attacker.combat.capture_attack_origin()
    assert attacker.combat.start_attack("test")
    for _ in range(3):
        attacker.combat.update(1 / 60)
        attacker.combat.sync_attack_box()
        attacker.combat.capture_attack_origin()
        swept = attacker.combat.hitbox.swept_rects[0]
        assert swept.size == attacker.combat.attack_box.size
        assert swept.topleft == attacker.combat.attack_box.topleft


def test_sweep_max_displacement_invariant_holds() -> None:
    """(i) Invariant borne : SWEEP_MAX >= VMAX * TIMESTEP * 1.5.

    VMAX = max(MAX_FALL_SPEED, DASH_SPEED, JUMP_FORCE, KB_MAX * CHARGE_MAX)
    avec KB_MAX = magnitude max des `power` de `attacks.json`,
    CHARGE_MAX = 2.0 (charge_handler). Le knockback vitesse REMPLACE la
    velocite (`reaction.py`), donc pas d addition de termes ; dt sim fixe,
    pas de spike possible.
    """
    with open("data/gameplay/attacks.json") as file:
        data = json.load(file)
    kb_max = 0.0

    def walk(node) -> None:  # noqa: ANN001 (local helper)
        nonlocal kb_max
        if isinstance(node, dict):
            power = node.get("knockback", {}).get("power")
            if isinstance(power, list) and len(power) == 2:
                kb_max = max(kb_max, math.hypot(power[0], power[1]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    charge_max = 2.0  # `charge_handler.py` : multiplicateur lineaire 1.0 -> 2.0
    vmax = max(
        PhysicsSettings.MAX_FALL_SPEED,
        PhysicsSettings.DASH_SPEED,
        PhysicsSettings.JUMP_FORCE,
        kb_max * charge_max,
    )
    required = vmax * SimulationSettings.TIMESTEP * 1.5
    assert kb_max == pytest.approx(1081.67, abs=0.01)
    assert required == pytest.approx(54.08, abs=0.05)
    assert required <= CombatSettings.SWEEP_MAX_DISPLACEMENT_PX
