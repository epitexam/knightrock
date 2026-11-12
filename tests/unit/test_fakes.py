"""The shared stand-ins keep the shape of what they stand in for.

The contact pipeline reads its targets' fields directly now; a stand-in that
lacks one fails loudly. This pins ``BodyStub`` to the ``Combatant`` protocol,
so a field added to one and forgotten in the other shows up here first.
"""

from __future__ import annotations

import typing

import pygame

from src.combat.combatant_protocol import Combatant
from tests.fakes import BodyStub

#: What the contact, hazard and pairing systems read from a body.
CONTACT_PIPELINE_READS = (
    "id",
    "faction",
    "is_dead",
    "is_invincible",
    "velocity",
    "hitbox",
    "hurtbox",
    "hurtbox_mult",
    "hurtbox_tags",
    "swept_hurtboxes",
    "swept_hurtbox",
    "swept_pushbox",
    "contact_shape",
    "swept_contact_shapes",
    "combat",
    "receive_damage",
)


def test_every_field_the_pipeline_reads_is_declared_by_combatant() -> None:
    declared = typing.get_protocol_members(Combatant)

    assert set(CONTACT_PIPELINE_READS) <= declared, set(CONTACT_PIPELINE_READS) - declared


def test_the_body_stand_in_has_every_field_the_pipeline_reads() -> None:
    body = BodyStub(pygame.FRect(0, 0, 40, 40))

    missing = [name for name in CONTACT_PIPELINE_READS if not hasattr(body, name)]

    assert not missing, missing
