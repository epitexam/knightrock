"""P1 sweep CCD tests (hitbox_amelioration.md, reception P1).

Cas (b), (b') et (b'') : ordre de tick REEL verifie code — capture,
`start_attack` (seed pool+prev), `update`, mouvement (lunge), sync,
detection (`entity.py:831-842`, interrupt synchrone
`state_machine.py:127-158`, lunge `player_states.py:147`).

(b) reste `xfail(strict=True)` tant que le sweep n est pas branche dans
`CombatSystem` ; (b')/(b'') (geometrie deja recouvrante en discret)
sont verts des le seed/capture de P1.2.
"""

import pygame
import pytest

from src.core.level.systems.combat_system import CombatSystem
from tests.unit.helpers import entity_at
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase


def _lunge_definition() -> object:
    return attack(phase(startup=1, active=8, recovery=1, size=(20.0, 20.0), offset=(0.0, 0.0)))


@pytest.mark.xfail(reason="P1 : sweep CCD non implemente", strict=True)
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
